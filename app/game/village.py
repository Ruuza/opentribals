import logging
import math
from datetime import UTC, datetime, timedelta
from typing import TypeVar, cast

from sqlmodel import Session, select

from app import crud
from app.game.buildings import (
    BUILDING_CLASS_MAP,
    Barracks,
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
from app.game.units import UNIT_CLASS_MAP, UnitName
from app.models import BuildingEvent, UnitMovement, UnitTrainingEvent, Village
from app.schemas import Units

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


class BarracksRequiredError(Exception):
    """Exception raised when trying to train units without a barracks"""

    pass


class SelfTargetError(Exception):
    """Exception raised when trying to send units to own village"""

    pass


class InsufficientUnitsError(Exception):
    """Exception raised when there are not enough units available"""

    pass


class MovementNotFoundError(Exception):
    """Exception raised when a movement is not found"""

    pass


class VillageNotFoundError(Exception):
    """Exception raised when a village is not found"""

    pass

    # This class will be implemented later for simulating battles,
    # killing units, generating reports, and handling resources looting


class VillageManager:
    """Class for managing village operations and updates"""

    MAX_QUEUE_SIZE = 2

    def __init__(self, village: Village, session: Session):
        """Initialize and update the village"""
        self.village = village
        self.village_id = village.id
        self.session = session
        self.update()

    def update(self) -> None:
        """Update village resources, buildings and stats"""
        now = datetime.now(UTC)

        # Process unit events
        unit_events = crud.UnitTrainingEvent.get_following_events(
            session=self.session, village_id=self.village_id
        )
        self._train_units(unit_events, now)

        # Process building events
        building_events = crud.BuildingEvent.get_following_events(
            session=self.session, village_id=self.village_id
        )
        self._process_build_events(building_events, now)

        # Process returning movements
        self._process_returning_movements(now)

        self._update_until(now)
        self.session.flush()
        self.session.refresh(self.village)

    def _train_units(
        self,
        events: list[UnitTrainingEvent],
        until_time: datetime,
    ) -> None:
        """Finish unit training events and update the village's unit count."""
        while events:
            events_to_complete = [
                event for event in events if event.complete_at and not event.completed
            ]
            if not events_to_complete:
                self._set_complete_time_for_another_unit_event(events, until_time)
                break

            event = events_to_complete[0]
            tz_aware_complete_at = event.complete_at.replace(tzinfo=UTC)
            if tz_aware_complete_at <= until_time:
                self._complete_unit_training_event(event, events, until_time)
            else:
                break

    def _process_build_events(
        self,
        events: list[BuildingEvent],
        until_time: datetime,
    ) -> None:
        """
        Process build events and complete them if their completion time has passed.
        Update resources before the completion time, so it's not affected by the event.
        """
        while events:
            events_to_complete = [
                event for event in events if event.complete_at and not event.completed
            ]
            if not events_to_complete:
                self._set_complete_time_for_another_build_event(events, until_time)
                break

            event = events_to_complete[0]
            tz_aware_complete_at = event.complete_at.replace(tzinfo=UTC)
            if tz_aware_complete_at <= until_time:
                self._update_until(event.complete_at)
                self._complete_building_event(event, events)

                # Set complete time for next event if there are any left
                if events:
                    self._set_complete_time_for_another_build_event(
                        events, event.complete_at
                    )
            else:
                break

    def _process_returning_movements(self, now: datetime) -> None:
        """Process movements that have returned to the village"""
        stmt = (
            select(UnitMovement)
            .where(UnitMovement.village_id == self.village_id)
            .where(UnitMovement.completed == False)  # noqa: E712
            .where(UnitMovement.return_at <= now)
        )

        returning_movements = self.session.exec(stmt).all()

        for movement in returning_movements:
            # Add returned resources to village
            if movement.return_wood > 0:
                self._update_resource("wood", movement.return_wood)
            if movement.return_clay > 0:
                self._update_resource("clay", movement.return_clay)
            if movement.return_iron > 0:
                self._update_resource("iron", movement.return_iron)

            # Mark as completed
            movement.completed = True
            self.session.add(movement)

        if returning_movements:
            self.session.flush()

    def _get_building_with_lvl(self, building_class: type[T]) -> T:
        """Get building instance with current level"""
        level = getattr(self.village, building_class.level_db_name)
        return cast(T, building_class(level=level))

    def _set_complete_time_for_another_build_event(
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

    def _set_complete_time_for_another_unit_event(
        self, events: list[UnitTrainingEvent], start: datetime
    ) -> None:
        """Set complete time for another unit training event"""
        # Check that no other event has set complete_at
        for event in events:
            if event.complete_at:
                raise AnotherEventAlreadySetCompleteAt(
                    "Another event has already set complete_at"
                    f" for village {self.village_id}"
                )
        if not events:
            return

        # Set complete_at for the next event
        events_sorted_by_created_at = sorted(events, key=lambda event: event.created_at)
        next_event = events_sorted_by_created_at[0]
        unit = UNIT_CLASS_MAP[next_event.unit_type]()

        # Get barracks level and apply training speed factor
        barracks = self._get_building_with_lvl(Barracks)
        next_event.complete_at = start + timedelta(
            milliseconds=barracks.get_training_time(unit)
        )
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

    def _complete_building_event(
        self, event: BuildingEvent, events: list[BuildingEvent]
    ) -> None:
        """
        Complete a building event and update the building level.
        Remove the event from the `events` list.
        """
        db_building_name = f"{event.building_type.value}_lvl"
        current_level = getattr(self.village, db_building_name)
        new_level = current_level + 1
        setattr(self.village, db_building_name, new_level)
        event.completed = True
        events.remove(event)

    def _complete_unit_training_event(
        self,
        event: UnitTrainingEvent,
        events: list[UnitTrainingEvent],
        until_time: datetime,
    ) -> None:
        """
        Complete a unit training event and add a single unit to the village.
        Remove the event from the `events` list.

        TODO: This can be optimized by finishing all units at once
        """
        unit_type_field = event.unit_type.value
        original_count = getattr(self.village, unit_type_field)
        new_count = 0

        unit_training_duration = self._get_building_with_lvl(
            Barracks
        ).get_training_time(UNIT_CLASS_MAP[event.unit_type]())

        # Train units until the event is completed or the time limit is reached
        while event.complete_at.replace(tzinfo=UTC) <= until_time:
            new_count += 1
            event.count -= 1

            if event.count == 0:
                break

            # Calculate the time it takes to train the next unit
            event.complete_at = event.complete_at + timedelta(
                milliseconds=unit_training_duration
            )

        # If it was the last unit in the event, complete it and start the next one
        if event.count == 0:
            # Last unit completed, delete the event
            event.completed = True
            events.remove(event)
            self._set_complete_time_for_another_unit_event(events, event.complete_at)
            self.session.delete(event)
        setattr(self.village, unit_type_field, original_count + new_count)

    def get_current_population(self) -> int:
        """Calculate the current population of the village"""
        population = 0

        # Add up population from all building types
        for building_class in BUILDING_CLASS_MAP.values():
            building = self._get_building_with_lvl(building_class)
            population += building.population

        # Add up population from all unit types
        for unit, unit_class in UNIT_CLASS_MAP.items():
            unit_count = getattr(self.village, unit.value)
            population += unit_class.population * unit_count

        return population

    def get_max_population(self) -> int:
        """Calculate the maximum population capacity of the village"""
        farm = self._get_building_with_lvl(Farm)
        return farm.max_population

    def get_max_storage_capacity(self) -> int:
        """Calculate the maximum storage capacity of the village"""
        storage = self._get_building_with_lvl(Storage)
        return storage.max_capacity

    def check_enough_population_for_building(self, building_type: BuildingType) -> None:
        """
        Check if there's enough population capacity for a new building level

        Raises:
            InsufficientPopulationError: If not enough population capacity
        """
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

        # Check if there's enough capacity and raise error if not
        if (current_population + population_difference) > max_population:
            raise InsufficientPopulationError("Not enough population capacity")

    def check_enough_population_for_units(
        self, unit_name: UnitName, count: int
    ) -> None:
        """
        Check if there's enough population capacity for new units

        Raises:
            InsufficientPopulationError: If not enough population capacity
        """
        current_population = self.get_current_population()
        max_population = self.get_max_population()
        unit_class = UNIT_CLASS_MAP[unit_name]
        needed_population = unit_class.population * count
        population_queued = crud.UnitTrainingEvent.get_units_queued_count(
            session=self.session, village_id=self.village_id
        )

        if (
            current_population + needed_population + population_queued
        ) > max_population:
            raise InsufficientPopulationError("Not enough population capacity")

    def _consume_resources(self, wood: int, clay: int, iron: int) -> None:
        """Consume resources for building or training

        Args:
            wood: Wood cost
            clay: Clay cost
            iron: Iron cost

        Raises:
            InsufficientResourcesError: If not enough resources
        """
        # Check if resources are sufficient
        if (
            self.village.wood < wood
            or self.village.clay < clay
            or self.village.iron < iron
        ):
            raise InsufficientResourcesError("Not enough resources")

        # Spend resources
        self.village.wood -= wood
        self.village.clay -= clay
        self.village.iron -= iron
        self.session.add(self.village)

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

        # Check if queue is full
        building_events = crud.BuildingEvent.get_following_events(
            session=self.session, village_id=self.village_id
        )

        if len(building_events) >= self.MAX_QUEUE_SIZE:
            raise QueueFullError("Building queue is full")

        # Check if there's enough population capacity (except for Farm)
        if building_type != BuildingType.FARM:
            self.check_enough_population_for_building(building_type)

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

        # Check resources and consume them
        self._consume_resources(wood_cost, clay_cost, iron_cost)

        # Create building event
        event = BuildingEvent(
            village_id=self.village_id,
            building_type=building_type,
            created_at=datetime.now(UTC),
            complete_at=None,  # Will be set by update()
            completed=False,
        )

        self.session.add(event)
        self.session.flush()

        # Run update again to set complete_at for the event if needed
        self.update()

        return event

    def schedule_unit_training(
        self, unit_name: UnitName, count: int
    ) -> UnitTrainingEvent | None:
        """
        Schedule training of units

        Args:
            unit_name: Type of unit to train
            count: Number of units to train

        Returns:
            UnitTrainingEvent if successful, None otherwise

        Raises:
            BarracksRequiredError: If barracks is not built
            InsufficientResourcesError: If not enough resources
            QueueFullError: If training queue is full
            InsufficientPopulationError: If not enough population capacity
        """
        if count <= 0:
            raise ValueError("Count must be greater than 0")

        # Check barracks requirements
        barracks = self._get_building_with_lvl(Barracks)
        if barracks.level == 0:
            raise BarracksRequiredError("Barracks required to train units")

        # Check if queue is full
        unit_events = crud.UnitTrainingEvent.get_following_events(
            session=self.session, village_id=self.village_id
        )

        # Get current queue size and max allowed
        current_queue_count = sum(event.count for event in unit_events)
        max_queue_size = self._get_building_with_lvl(Barracks).max_queue_size

        if current_queue_count + count > max_queue_size:
            raise QueueFullError(f"Unit training queue limit is {max_queue_size}")

        # Check population capacity
        self.check_enough_population_for_units(unit_name, count)

        # Get unit costs
        unit_class = UNIT_CLASS_MAP[unit_name]
        wood_cost = unit_class.base_wood_cost * count
        clay_cost = unit_class.base_clay_cost * count
        iron_cost = unit_class.base_iron_cost * count

        # Check and consume resources
        self._consume_resources(wood_cost, clay_cost, iron_cost)

        # Create unit training event
        event = UnitTrainingEvent(
            village_id=self.village_id,
            unit_type=unit_name,
            count=count,
            created_at=datetime.now(UTC),
            complete_at=None,  # Will be set by update()
            completed=False,
        )

        self.session.add(event)
        self.session.flush()

        # Run update again to set complete_at for the event if needed
        self.update()

        return event

    def get_available_units(self) -> Units:
        """Get available units in village (accounting for units in movements)"""
        # Get all active movements from this village
        stmt = (
            select(UnitMovement)
            .where(UnitMovement.village_id == self.village_id)
            .where(UnitMovement.completed == False)  # noqa: E712
        )
        active_movements = self.session.exec(stmt).all()

        units_outside = Units()

        for movement in active_movements:
            units_outside.archer += movement.archer
            units_outside.swordsman += movement.swordsman
            units_outside.knight += movement.knight
            units_outside.skirmisher += movement.skirmisher
            units_outside.nobleman += movement.nobleman

        available_units = Units(
            archer=self.village.archer - units_outside.archer,
            swordsman=self.village.swordsman - units_outside.swordsman,
            knight=self.village.knight - units_outside.knight,
            skirmisher=self.village.skirmisher - units_outside.skirmisher,
            nobleman=self.village.nobleman - units_outside.nobleman,
        )

        # Check if any unit count is negative
        if (
            available_units.archer < 0
            or available_units.swordsman < 0
            or available_units.knight < 0
            or available_units.skirmisher < 0
            or available_units.nobleman < 0
        ):
            logger.error(
                f"Available units below 0 for village {self.village.id}: {available_units}"
            )

        return available_units

    def check_available_units(
        self,
        units: Units,
    ) -> None:
        """Check if there are enough units available for movement

        Raises:
            InsufficientUnitsError: If not enough units available
        """
        available = self.get_available_units()

        if (
            available.archer < units.archer
            or available.swordsman < units.swordsman
            or available.knight < units.knight
            or available.skirmisher < units.skirmisher
            or available.nobleman < units.nobleman
        ):
            raise InsufficientUnitsError("Not enough units available for movement")

    def calculate_arrival_time(
        self,
        target_village: Village,
        units: Units,
    ) -> datetime:
        """Calculate arrival time based on distance and slowest unit"""

        # Calculate distance between villages
        dx = self.village.x - target_village.x
        dy = self.village.y - target_village.y
        distance = math.sqrt(dx**2 + dy**2)

        slowest_speed = 0
        for unit_name, unit_class in UNIT_CLASS_MAP.items():
            unit_count = getattr(units, unit_name.value)
            if unit_count > 0:
                slowest_speed = max(slowest_speed, unit_class().speed)

        if slowest_speed == 0:
            raise ValueError("No units to calculate travel time")

        # Calculate travel time
        travel_time_ms = int(slowest_speed * distance)

        # Calculate arrival time
        now = datetime.now(UTC)
        arrival_time = now + timedelta(milliseconds=travel_time_ms)

        return arrival_time

    def _send_back(self, movement: UnitMovement) -> None:
        """Send units back to origin village"""

        if movement.completed:
            raise MovementNotFoundError(
                f"Movement with ID {movement.id} not found or already completed"
            )

        now = datetime.now(UTC)

        # If units haven't arrived yet, return them immediately
        if now < movement.arrival_at.replace(tzinfo=UTC):
            # Calculate time passed since departure
            time_passed = now - movement.created_at
            movement.return_at = now + time_passed
        else:
            units = Units(
                archer=movement.archer,
                swordsman=movement.swordsman,
                knight=movement.knight,
                skirmisher=movement.skirmisher,
            )
            movement.return_at = self.calculate_arrival_time(
                target_village=movement.target_village,
                units=units,
            )
        self.session.add(movement)
        self.session.flush()

    def cancel_support(self, movement: UnitMovement) -> None:
        """Cancel a support movement"""
        if movement.completed or not movement.is_support:
            raise MovementNotFoundError(
                f"Support Movement with ID {movement.id} not found or already completed"
            )

        self._send_back(movement)

    def _send_units(
        self,
        target_village: Village,
        units: Units,
        is_attack: bool = False,
        is_support: bool = False,
        is_spy: bool = False,
    ) -> UnitMovement:
        """
        Send units to another village (common function for attack, support, etc.)

        Args:
            target_village (Village): Target village object
            units: UnitsDataClass object representing the units to send
            is_attack (bool): Whether the movement is an attack (default: False)
            is_support: Whether the movement is support (default: False)
            is_spy: Whether the movement is a spy mission (default: False)

        Returns:
            unitMovement object representing the movement

        Raises:
            SelfTargetError: If target is the same as source village
            InsufficientUnitsError: If not enough units are available
        """
        # can only be attack or support or spy, not all three
        if sum([is_attack, is_support, is_spy]) != 1:
            raise ValueError("Movement must be either attack, support, or spy")

        # Check not sending to self
        if target_village.id == self.village_id:
            raise SelfTargetError("Cannot send units to own village")

        # Check if enough units
        self.check_available_units(units)

        # Calculate arrival time
        arrival_time = self.calculate_arrival_time(target_village, units)

        # Create unit movement
        movement = UnitMovement(
            village_id=self.village_id,
            target_village_id=target_village.id,
            created_at=datetime.now(UTC),
            arrival_at=arrival_time,
            return_at=None,
            completed=False,
            archer=units.archer,
            swordsman=units.swordsman,
            knight=units.knight,
            skirmisher=units.skirmisher,
            is_attack=is_attack,
            is_support=is_support,
            is_spy=is_spy,
        )

        self.session.add(movement)
        self.session.flush()

        return movement

    def send_support(
        self,
        target_village: Village,
        units: Units,
    ) -> UnitMovement:
        """
        Send units as support to another village

        Args:
            target_village: Target village object
            units: UnitsDataClass object representing the units to send

        Returns:
            unitMovement object representing the movement
        """

        return self._send_units(
            target_village=target_village,
            units=units,
            is_attack=False,
            is_support=True,
        )

    def send_attack(
        self,
        target_village: Village,
        units: Units,
    ) -> UnitMovement:
        """
        Send units to attack another village

        Args:
            target_village: Target village object
            units: UnitsDataClass object representing the units to send

        Returns:
            unitMovement object representing the movement
        """

        return self._send_units(
            target_village=target_village,
            units=units,
            is_attack=True,
            is_support=False,
        )
