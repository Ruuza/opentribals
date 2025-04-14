import logging
from datetime import UTC, datetime, timedelta
from typing import TypeVar, cast

from sqlmodel import Session

from app import crud, models
from app.game.buildings import (
    BUILDING_CLASS_MAP,
    Building,
    BuildingType,
    ClayPit,
    Farm,
    Headquarters,
    IronMine,
    ProductionBuilding,
    Storage,
    Woodcutter,
)
from app.models import BuildingEvent

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Building)


class MaxLevelReachedError(Exception):
    """
    Exception raised when trying to upgrade a building that is already at max level
    """

    pass


class AnotherEventAlreadySetCompleteAt(Exception):
    """Exception raised when another event has already set complete_at"""

    pass


class InsufficientResourcesError(Exception):
    """Exception raised when there are not enough resources for upgrade"""

    pass


class QueueFullError(Exception):
    """Exception raised when building queue is full"""

    pass


class InsufficientPopulationError(Exception):
    """Exception raised when there is not enough population capacity"""

    pass


class VillageManager:
    """Class for managing village operations and updates"""

    MAX_QUEUE_SIZE = 2

    def __init__(self, village_id: int, session: Session):
        """Initialize with village_id and session"""
        self.village_id = village_id
        self.session = session
        self.village: models.Village | None = None

    def update(self) -> None:
        """Update village resources, buildings and stats"""
        now = datetime.now(UTC)

        self.village = crud.Village.get_for_update(
            session=self.session, village_id=self.village_id
        )

        building_events = crud.BuildingEvent.get_following_events_for_update(
            session=self.session, village_id=self.village_id
        )

        # Check if there are any building events to complete
        while building_events:
            events_to_complete = [
                (i, event)
                for i, event in enumerate(building_events)
                if event.complete_at and not event.completed
            ]
            if not events_to_complete:
                self._set_complete_time_for_another_event(building_events, now)
                break

            index, event = events_to_complete[0]
            tz_aware_complete_at = event.complete_at.replace(tzinfo=UTC)
            if tz_aware_complete_at <= now:
                self._update_until(event.complete_at)
                self._complete_building_event(event)
                building_events.pop(index)
                self._set_complete_time_for_another_event(
                    building_events, event.complete_at
                )
            else:
                break

        self._update_until(now)
        self.session.commit()

    def _get_building_with_lvl(self, building_class: type[T]) -> T:
        """Get building instance with current level"""
        level = getattr(self.village, building_class.level_db_name)
        return cast(T, building_class(level=level))

    def _set_complete_time_for_another_event(
        self, events: list[BuildingEvent], start: datetime
    ) -> None:
        """Set complete time for another event"""
        # Check that no other event has set complete_at
        for event in events:
            if event.complete_at:
                raise AnotherEventAlreadySetCompleteAt(
                    "Another event has already set complete_at"
                    f" for village {self.village_id}",
                )
        if not events:
            return
        # Set complete_at for the next event
        events_sorted_by_created_at = sorted(events, key=lambda event: event.created_at)
        next_event = events_sorted_by_created_at[0]
        building_class = BUILDING_CLASS_MAP[next_event.building_type]
        building = self._get_building_with_lvl(building_class)

        # Get headquarters level and apply build time reduction
        headquarters = self._get_building_with_lvl(Headquarters)
        time_factor = headquarters.build_time_reduction_factor
        adjusted_build_time = int(building.build_time * time_factor)

        next_event.complete_at = start + timedelta(milliseconds=adjusted_build_time)
        self.session.add(next_event)

    def _update_until(self, until: datetime) -> None:
        """Update resources until a specific time"""
        self._update_resource_until(Woodcutter, until)
        self._update_resource_until(ClayPit, until)
        self._update_resource_until(IronMine, until)
        # self._update_population()

    def _update_resource_until(
        self,
        production_building: type[ProductionBuilding],
        now: datetime,
    ) -> None:
        """Calculate and update a specific resource based on elapsed time"""
        building = self._get_building_with_lvl(production_building)

        production_rate_ms = building.production_rate_ms
        last_update: datetime = getattr(self.village, building.last_update_db_name)

        # Unify timezones
        last_update = last_update.replace(tzinfo=UTC)
        now = now.replace(tzinfo=UTC)

        elapsed_ms = int((now - last_update).total_seconds() * 1000)

        assert production_rate_ms > 0
        new_resources = elapsed_ms // production_rate_ms

        if new_resources > 0:
            # Update the timestamp by the exact time for the resources we added
            ms_used = new_resources * production_rate_ms
            new_timestamp = datetime.fromtimestamp(
                last_update.timestamp() + (ms_used / 1000), UTC
            )
            setattr(self.village, building.last_update_db_name, new_timestamp)

            self._update_resource(building.resource, new_resources)

    def _update_resource(self, resource_name: str, amount: int) -> None:
        """Update a specific resource, considering limitations like storage capacity"""
        current_amount = getattr(self.village, resource_name)
        new_amount = current_amount + amount

        if new_amount < 0:
            logger.error(
                f"Resource {resource_name} below 0 for village {self.village.id}"
            )

        # Check storage capacity limit
        max_capacity = self.get_max_storage_capacity()
        if new_amount > max_capacity:
            new_amount = max_capacity

        setattr(self.village, resource_name, new_amount)

    def _complete_building_event(self, event: BuildingEvent) -> None:
        """Complete a building event and update the building level"""
        db_building_name = f"{event.building_type.value}_lvl"
        current_level = getattr(self.village, db_building_name)
        new_level = current_level + 1
        setattr(self.village, db_building_name, new_level)
        self.session.add(self.village)
        event.completed = True
        self.session.add(event)

    def get_current_population(self) -> int:
        """Calculate the current population of the village"""
        population = 0

        # Add up population from all building types
        for building_class in BUILDING_CLASS_MAP.values():
            building = self._get_building_with_lvl(building_class)
            population += building.population

        return population

    def get_max_population(self) -> int:
        """Calculate the maximum population capacity of the village"""
        farm = self._get_building_with_lvl(Farm)
        return farm.max_population

    def get_max_storage_capacity(self) -> int:
        """Calculate the maximum storage capacity of the village"""
        storage = self._get_building_with_lvl(Storage)
        return storage.max_capacity

    def has_enough_population(self, building_type: BuildingType) -> bool:
        """Check if there's enough population capacity for a new building level"""
        current_population = self.get_current_population()
        max_population = self.get_max_population()

        # Get additional population needed for the upgrade
        building_class = BUILDING_CLASS_MAP[building_type]
        current_building = self._get_building_with_lvl(building_class)
        current_population_used = current_building.population

        # Calculate population after upgrade
        next_level_building = building_class(level=current_building.level + 1)
        next_level_population = next_level_building.population

        # Calculate the difference in population
        population_difference = next_level_population - current_population_used

        # Check if there's enough capacity
        return (current_population + population_difference) <= max_population

    def schedule_building_upgrade(
        self, building_type: BuildingType
    ) -> BuildingEvent | None:
        """
        Schedule a building upgrade

        Args:
            building_type: Type of building to upgrade

        Returns:
            BuildingEvent if successful, None otherwise

        Raises:
            InsufficientResourcesError: If not enough resources
            QueueFullError: If building queue is full
            InsufficientPopulationError: If not enough population capacity
        """
        # Ensure village data is up to date
        self.update()

        village = crud.Village.get_for_update(
            session=self.session, village_id=self.village_id
        )
        self.village = village

        # Check if queue is full
        building_events = crud.BuildingEvent.get_following_events_for_update(
            session=self.session, village_id=self.village_id
        )

        if len(building_events) >= self.MAX_QUEUE_SIZE:
            raise QueueFullError("Building queue is full")

        # Check if there's enough population capacity (except for Farm)
        if building_type != BuildingType.FARM and not self.has_enough_population(
            building_type
        ):
            raise InsufficientPopulationError("Not enough population capacity")

        # Get building and cost information
        building_class = BUILDING_CLASS_MAP[building_type]
        building = self._get_building_with_lvl(building_class)

        if building.level >= building.max_level:
            raise MaxLevelReachedError(
                f"Building {building_type.value} is already at max level"
            )

        wood_cost = building.wood_cost
        clay_cost = building.clay_cost
        iron_cost = building.iron_cost

        # Check if resources are sufficient
        if (
            self.village.wood < wood_cost
            or self.village.clay < clay_cost
            or self.village.iron < iron_cost
        ):
            raise InsufficientResourcesError("Not enough resources for upgrade")

        # Spend resources
        self.village.wood -= wood_cost
        self.village.clay -= clay_cost
        self.village.iron -= iron_cost
        self.session.add(self.village)

        # Create building event
        event = BuildingEvent(
            village_id=self.village_id,
            building_type=building_type,
            created_at=datetime.now(UTC),
            complete_at=None,  # Will be set by update()
            completed=False,
        )

        self.session.add(event)
        self.session.commit()

        # Run update again to set complete_at for the event if needed
        self.update()

        return event
