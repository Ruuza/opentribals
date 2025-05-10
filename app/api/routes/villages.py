from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.game.village import VillageManager
from app.models import Village
from app.schemas import (
    VillageOutPrivate,
    VillageOutPublic,
    VillageOutPublicList,
    VillageUpdate,
)

router = APIRouter(prefix="/villages", tags=["villages"])


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
    village = session.get(Village, village_id)
    if not village:
        raise HTTPException(status_code=404, detail="Village not found")

    return village


@router.get("/{village_id}/private", response_model=VillageOutPrivate)
def get_village_private(
    *,
    session: SessionDep,
    village_id: int,
    current_user: CurrentUser,
) -> Any:
    """
    Get private village information (only available to the village owner)
    """
    village = crud.Village.get_for_update(session=session, village_id=village_id)
    if not village:
        raise HTTPException(status_code=404, detail="Village not found")

    # Check if the current player owns this village
    if village.player_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to access this village's private data",
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
    village = session.get(Village, village_id)
    if not village:
        raise HTTPException(status_code=404, detail="Village not found")

    # Check if the current player owns this village
    if village.player_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You don't have permission to update this village"
        )

    # Update allowed fields
    update_data = village_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(village, key, value)
    session.add(village)
    session.commit()
    session.refresh(village)

    return village
