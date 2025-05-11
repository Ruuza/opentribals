from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import or_, select

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.game.buildings import BUILDING_CLASS_MAP, Barracks, BuildingType
from app.game.units import UNIT_CLASS_MAP
from app.game.village import VillageManager
from app.models import UnitMovement, Village
from app.schemas import (
    AvailableBuildingsResponse,
    AvailableUnitsResponse,
    BuildingEventResponse,
    BuildingInformation,
    BuildingQueueResponse,
    UnitInformation,
    UnitMovementOut,
    Units,
    UnitTrainingEventResponse,
    UnitTrainingQueueResponse,
    UnitTrainingRequest,
    VillageOutPrivate,
    VillageOutPublic,
    VillageOutPublicList,
    VillageUpdate,
)

router = APIRouter(prefix="/villages", tags=["villages"])


def check_village_access(
    *,
    session: SessionDep,
    village_id: int,
    current_user: CurrentUser = None,
    for_update: bool = False,
) -> Village:
    """
    Common function to check village access and permissions.

    Args:
        session: Database session
        village_id: ID of the village to check
        current_user: Current user attempting to access the village (None if public access)
        for_update: Whether to get the village for update (using select for update)

    Returns:
        Village: The village object if access is granted

    Raises:
        HTTPException: 404 if village not found, 403 if permission denied
    """
    # Get village using the appropriate method
    if for_update:
        village = crud.Village.get_for_update(session=session, village_id=village_id)
    else:
        village = session.get(Village, village_id)

    if not village:
        raise HTTPException(status_code=404, detail="Village not found")

    # If current_user is provided, verify ownership
    if current_user and village.player_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You don't have permission to access this village"
        )

    return village


@router.get("", response_model=VillageOutPublicList)
def get_villages(
    *,
    session: SessionDep,
    x_min: int | None = None,
    y_min: int | None = None,
    x_max: int | None = None,
    y_max: int | None = None,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Get villages with optional coordinate filtering
    """
    query = select(Village)

    # Apply coordinate filters if provided
    if x_min is not None:
        query = query.where(Village.x >= x_min)
    if y_min is not None:
        query = query.where(Village.y >= y_min)
    if x_max is not None:
        query = query.where(Village.x <= x_max)
    if y_max is not None:
        query = query.where(Village.y <= y_max)

    # Apply pagination
    query = query.offset(skip).limit(limit)

    villages = session.exec(query).all()

    # Get total count for pagination
    count_query = select(Village)
    if x_min is not None:
        count_query = count_query.where(Village.x >= x_min)
    if y_min is not None:
        count_query = count_query.where(Village.y >= y_min)
    if x_max is not None:
        count_query = count_query.where(Village.x <= x_max)
    if y_max is not None:
        count_query = count_query.where(Village.y <= y_max)

    total_count = len(session.exec(count_query).all())

    return VillageOutPublicList(data=villages, count=total_count)


@router.get("/{village_id}", response_model=VillageOutPublic)
def get_village(*, session: SessionDep, village_id: int) -> Any:
    """
    Get public village information by ID
    """
    village = check_village_access(session=session, village_id=village_id)
    return village


@router.get("/{village_id}/private", response_model=VillageOutPrivate)
def get_village_private(
    *,
    session: SessionDep,
    village_id: int,
    current_user: CurrentUser,
) -> Any:
    """
    Get private village information (only available to the village owner).
    It also updates the village resources and stats.
    """
    village = check_village_access(
        session=session,
        village_id=village_id,
        current_user=current_user,
        for_update=True,
    )

    # Update village resources and stats
    village_manager = VillageManager(village=village, session=session)

    return village_manager.village


@router.patch("/{village_id}", response_model=VillageOutPrivate)
def update_village(
    *,
    session: SessionDep,
    village_id: int,
    village_update: VillageUpdate,
    current_user: CurrentUser,
) -> Any:
    """
    Update village information (name only for now)
    """
    village = check_village_access(
        session=session, village_id=village_id, current_user=current_user
    )

    # Update allowed fields
    update_data = village_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(village, key, value)
    session.add(village)
    session.commit()
    session.refresh(village)

    return village


@router.get("/{village_id}/buildings/queue", response_model=BuildingQueueResponse)
def get_building_queue(
    *,
    session: SessionDep,
    village_id: int,
    current_user: CurrentUser,
) -> Any:
    """
    Get the current building construction queue for a village
    """
    check_village_access(
        session=session, village_id=village_id, current_user=current_user
    )

    # Get building events
    building_events = crud.BuildingEvent.get_following_events(
        session=session, village_id=village_id
    )

    # Convert to response objects
    event_responses = []
    for event in building_events:
        event_responses.append(
            BuildingEventResponse(
                id=event.id,
                building_type=event.building_type,
                created_at=event.created_at,
                complete_at=event.complete_at,
            )
        )

    return BuildingQueueResponse(queue=event_responses)


@router.post(
    "/{village_id}/buildings/{building_type}", response_model=BuildingEventResponse
)
def schedule_building_construction(
    *,
    session: SessionDep,
    village_id: int,
    building_type: BuildingType,
    current_user: CurrentUser,
) -> Any:
    """
    Schedule a building upgrade construction
    """
    village = check_village_access(
        session=session,
        village_id=village_id,
        current_user=current_user,
        for_update=True,
    )

    # Create village manager and schedule the building construction
    village_manager = VillageManager(village=village, session=session)
    event = village_manager.schedule_building_upgrade(building_type)

    return BuildingEventResponse(
        id=event.id,
        building_type=event.building_type,
        created_at=event.created_at,
        complete_at=event.complete_at,
    )


@router.get(
    "/{village_id}/buildings/available", response_model=AvailableBuildingsResponse
)
def get_available_buildings(
    *,
    session: SessionDep,
    village_id: int,
    current_user: CurrentUser,
) -> Any:
    """
    Get information about all available buildings and their upgrade costs
    """
    village = check_village_access(
        session=session,
        village_id=village_id,
        current_user=current_user,
        for_update=True,
    )

    # Update village resources
    VillageManager(village=village, session=session)

    # Get information about all building types
    buildings_info = []
    for building_type, building_class in BUILDING_CLASS_MAP.items():
        current_level = getattr(village, building_class.level_db_name)
        next_level_building = building_class(level=current_level)

        # Check if max level reached
        max_level_reached = current_level >= next_level_building.max_level

        buildings_info.append(
            BuildingInformation(
                building_type=building_type,
                current_level=current_level,
                max_level=next_level_building.max_level,
                max_level_reached=max_level_reached,
                wood_cost=0 if max_level_reached else next_level_building.wood_cost,
                clay_cost=0 if max_level_reached else next_level_building.clay_cost,
                iron_cost=0 if max_level_reached else next_level_building.iron_cost,
                build_time_ms=0
                if max_level_reached
                else next_level_building.build_time,
                population=next_level_building.population,
            )
        )

    return AvailableBuildingsResponse(buildings=buildings_info)


# New endpoints for unit training
@router.get("/{village_id}/units/queue", response_model=UnitTrainingQueueResponse)
def get_unit_training_queue(
    *,
    session: SessionDep,
    village_id: int,
    current_user: CurrentUser,
) -> Any:
    """
    Get the current unit training queue for a village
    """
    village = check_village_access(
        session=session,
        village_id=village_id,
        current_user=current_user,
        for_update=True,
    )

    VillageManager(village=village, session=session)

    unit_events = crud.UnitTrainingEvent.get_following_events(
        session=session, village_id=village_id
    )

    # Convert to response objects
    event_responses = []
    for event in unit_events:
        event_responses.append(
            UnitTrainingEventResponse(
                id=event.id,
                unit_type=event.unit_type,
                count=event.count,
                created_at=event.created_at,
                complete_at=event.complete_at,
            )
        )

    return UnitTrainingQueueResponse(queue=event_responses)


@router.post("/{village_id}/units/train", response_model=UnitTrainingEventResponse)
def schedule_unit_training(
    *,
    session: SessionDep,
    village_id: int,
    training_request: UnitTrainingRequest,
    current_user: CurrentUser,
) -> Any:
    """
    Schedule training of units
    """
    village = check_village_access(
        session=session,
        village_id=village_id,
        current_user=current_user,
        for_update=True,
    )

    village_manager = VillageManager(village=village, session=session)
    event = village_manager.schedule_unit_training(
        unit_name=training_request.unit_type,
        count=training_request.count,
    )

    return UnitTrainingEventResponse(
        id=event.id,
        unit_type=event.unit_type,
        count=event.count,
        created_at=event.created_at,
        complete_at=event.complete_at,
    )


@router.get("/{village_id}/units/available", response_model=AvailableUnitsResponse)
def get_available_units(
    *,
    session: SessionDep,
    village_id: int,
    current_user: CurrentUser,
) -> Any:
    """
    Get information about all available units, their training costs and times
    """
    village = check_village_access(
        session=session,
        village_id=village_id,
        current_user=current_user,
        for_update=True,
    )

    # Update village resources
    VillageManager(village=village, session=session)

    units_info = []
    barracks_level = village.barracks_lvl
    can_train = barracks_level > 0

    for unit_name, unit_class in UNIT_CLASS_MAP.items():
        unit = unit_class()

        # Calculate training time based on barracks level
        training_time_ms = 0
        if can_train:
            barracks = Barracks(level=barracks_level)
            training_time_ms = barracks.get_training_time(unit)

        units_info.append(
            UnitInformation(
                unit_type=unit_name,
                wood_cost=unit.base_wood_cost,
                clay_cost=unit.base_clay_cost,
                iron_cost=unit.base_iron_cost,
                training_time_ms=training_time_ms,
                population=unit.population,
                attack=unit.attack,
                defense_melee=unit.defense_melee,
                defense_ranged=unit.defense_ranged,
                loot_capacity=unit.loot_capacity,
                speed_ms=unit.speed,
                can_train=True,
            )
        )

    return AvailableUnitsResponse(units=units_info)


@router.post("/{village_id}/attack/{target_village_id}", response_model=UnitMovement)
def send_attack(
    *,
    session: SessionDep,
    village_id: int,
    target_village_id: int,
    units: Units,
    current_user: CurrentUser,
) -> Any:
    """
    Send an attack from one village to another
    """
    # Check access to source village
    source_village = check_village_access(
        session=session,
        village_id=village_id,
        current_user=current_user,
        for_update=True,
    )

    # Check if target village exists
    target_village = session.get(Village, target_village_id)
    if not target_village:
        raise HTTPException(status_code=404, detail="Target village not found")

    village_manager = VillageManager(village=source_village, session=session)
    movement = village_manager.send_attack(
        target_village=target_village,
        units=units,
    )

    session.commit()
    session.refresh(movement)

    return movement


@router.post("/{village_id}/support/{target_village_id}", response_model=UnitMovement)
def send_support(
    *,
    session: SessionDep,
    village_id: int,
    target_village_id: int,
    units: Units,
    current_user: CurrentUser,
) -> Any:
    """
    Send support units from one village to another
    """
    # Check access to source village
    source_village = check_village_access(
        session=session,
        village_id=village_id,
        current_user=current_user,
        for_update=True,
    )

    # Check if target village exists
    target_village = session.get(Village, target_village_id)
    if not target_village:
        raise HTTPException(status_code=404, detail="Target village not found")

    village_manager = VillageManager(village=source_village, session=session)
    movement = village_manager.send_support(
        target_village=target_village,
        units=units,
    )

    session.commit()
    session.refresh(movement)

    return movement


@router.post("/{village_id}/cancel-support/{movement_id}", response_model=UnitMovement)
def cancel_support(
    *,
    session: SessionDep,
    village_id: int,
    movement_id: int,
    current_user: CurrentUser,
) -> Any:
    """
    Cancel a support movement and send units back to the origin village
    """
    # Check access to village
    village = check_village_access(
        session=session,
        village_id=village_id,
        current_user=current_user,
        for_update=True,
    )

    # Get the movement
    movement = session.get(UnitMovement, movement_id)
    if not movement:
        raise HTTPException(status_code=404, detail="Movement not found")

    # Check if movement is related to this village
    if movement.village_id != village_id:
        raise HTTPException(
            status_code=403, detail="You don't have permission to cancel this movement"
        )

    # Check if it's a support movement
    if not movement.is_support:
        raise HTTPException(
            status_code=400, detail="Only support movements can be cancelled"
        )

    # Check if movement is already completed
    if movement.completed:
        raise HTTPException(status_code=400, detail="Movement is already completed")

    # Check if support movement is already returning
    if movement.return_at is not None:
        raise HTTPException(status_code=400, detail="Movement is already returning")

    # Cancel the support movement
    village_manager = VillageManager(village=village, session=session)
    village_manager.cancel_support(movement)

    session.commit()
    session.refresh(movement)

    return movement


@router.get("/{village_id}/movements", response_model=list[UnitMovementOut])
def get_movements(
    *,
    session: SessionDep,
    village_id: int,
    current_user: CurrentUser,
) -> Any:
    """
    Get all active unit movements for a village (both incoming and outgoing)
    """
    # Check access to village
    check_village_access(
        session=session,
        village_id=village_id,
        current_user=current_user,
    )

    # Get all active movements for the village
    stmt = (
        select(UnitMovement)
        .where(
            or_(
                UnitMovement.target_village_id == village_id,
                UnitMovement.village_id == village_id,
            )
        )
        .where(UnitMovement.completed == False)  # noqa: E712
    )

    movements = session.exec(stmt).all()

    return movements
