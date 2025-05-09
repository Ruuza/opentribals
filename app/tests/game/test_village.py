from datetime import UTC, datetime, timedelta

import pytest
from freezegun import freeze_time
from sqlmodel import Session, select

from app import crud, models
from app.game.buildings import BuildingType, Storage, Woodcutter
from app.game.units import Archer, Swordsman, UnitName
from app.game.village import (
    BarracksRequiredError,
    InsufficientPopulationError,
    InsufficientResourcesError,
    MaxLevelReachedError,
    QueueFullError,
    VillageManager,
)


def time_close_enough(time1, time2, tolerance_ms=20):
    """Check if two timestamps are within a specified tolerance."""
    diff = abs((time1 - time2).total_seconds() * 1000)
    return diff <= tolerance_ms


INITIAL_RESOURCES = 500


class TestUpdateVillage:
    """Tests for the VillageManager class update method"""

    @pytest.fixture
    def village(self, session: Session) -> models.Village:
        """Create a test village"""
        village = crud.Village.create(
            session=session, name="Test Village", x=500, y=500, player_id=None
        )
        return village

    def test_update_without_building_events(
        self, session: Session, village: models.Village
    ):
        """Test updating a village with no building events"""

        # Fast forward 1 hour
        one_hour_later = village.last_wood_update + timedelta(hours=1, milliseconds=1)

        with freeze_time(one_hour_later):
            # Call update method
            manager = VillageManager(village=village, session=session)

            # Refresh the village to get updated values
            session.refresh(village)

            # Calculate expected resources based on production rates
            # Woodcutter at level 1 produces 30 resources per hour
            # ClayPit at level 1 produces 30 resources per hour
            # IronMine at level 1 produces 25 resources per hour
            expected_resource_count = INITIAL_RESOURCES + 30

            # Check that resources have increased correctly
            assert village.wood == expected_resource_count
            assert village.clay == expected_resource_count
            assert village.iron == expected_resource_count

            # Check that timestamps were updated ()
            for last_resource_update in [
                village.last_wood_update,
                village.last_clay_update,
                village.last_iron_update,
            ]:
                assert time_close_enough(last_resource_update, one_hour_later)

        another_minute_later = one_hour_later + timedelta(minutes=1)
        with freeze_time(another_minute_later):
            # Call update method again
            manager.update()

        # Refresh the village to get updated values
        session.refresh(village)

        # Check that resources have not changed
        assert village.wood == expected_resource_count
        assert village.clay == expected_resource_count
        assert village.iron == expected_resource_count

        # Check that timestamps were not updated
        for last_resource_update in [
            village.last_wood_update,
            village.last_clay_update,
            village.last_iron_update,
        ]:
            assert time_close_enough(last_resource_update, one_hour_later)

        another_2_minutes_later = one_hour_later + timedelta(minutes=2)
        with freeze_time(another_2_minutes_later):
            # Call update method again
            manager.update()

        # Refresh the village to get updated values
        session.refresh(village)

        assert village.wood == expected_resource_count + 1
        assert village.clay == expected_resource_count + 1
        assert village.iron == expected_resource_count + 1

        # Check that timestamps were updated (except iron, it should be the same)
        assert time_close_enough(village.last_wood_update, another_2_minutes_later)
        assert time_close_enough(village.last_clay_update, another_2_minutes_later)
        assert time_close_enough(village.last_iron_update, another_2_minutes_later)

    def test_complete_woodcutter_in_middle_update(
        self,
        session: Session,
        village: models.Village,
    ):
        """
        Test updating a village where woodcutter was completed in the middle of update
        """

        # Set the completion time for the woodcutter event to half hour later
        half_hour_later = village.last_wood_update + timedelta(
            minutes=30, milliseconds=1
        )
        woodcutter_event = models.BuildingEvent(
            village_id=village.id,
            building_type=BuildingType.WOODCUTTER,
            created_at=datetime.now(UTC),
            complete_at=half_hour_later,
            completed=False,
        )
        session.add(woodcutter_event)
        session.commit()

        one_hour_later = village.last_wood_update + timedelta(hours=1, milliseconds=1)

        with freeze_time(one_hour_later):
            VillageManager(village=village, session=session)

        # Refresh the village to get updated values
        session.refresh(village)

        # Check that the building event was completed
        assert woodcutter_event.completed

        # Check that the woodcutter level has increased
        assert village.woodcutter_lvl == 2

        # Calculate expected resources
        expected_wood = (
            INITIAL_RESOURCES + 15 + 17
        )  # 30 * 0.5 (half_hour) + 30 * 0.5 * (half_hour) * 1.17 (woodcutter lvl 2)
        expected_clay = INITIAL_RESOURCES + 30
        expected_iron = INITIAL_RESOURCES + 30

        # Check resources
        assert village.wood == expected_wood
        assert village.clay == expected_clay
        assert village.iron == expected_iron

        # Check that timestamps were updated correctly
        # 17.55 per 30 minutes ~= 102564.102564 ms per resource.
        # 30*60*1000 modulo 102564.102564 ~= 56410 ms
        # This means that the last update time should be 56410 ms before the now
        assert time_close_enough(
            village.last_wood_update,
            one_hour_later - timedelta(milliseconds=56410),
        )

        # Check that the building event was completed
        assert village.woodcutter_lvl == 2

    def test_complete_multiple_building_events(
        self,
        session: Session,
        village: models.Village,
    ):
        """
        Test completing multiple building events
        """
        fifteen_minutes_later = village.last_wood_update + timedelta(
            minutes=15, milliseconds=1
        )
        first_event = models.BuildingEvent(
            village_id=village.id,
            building_type=BuildingType.CLAY_PIT,
            created_at=datetime.now(UTC),
            complete_at=fifteen_minutes_later,
            completed=False,
        )
        session.add(first_event)

        # Add multiple iron mine events
        for i in range(6):
            iron_mine_event = models.BuildingEvent(
                village_id=village.id,
                building_type=BuildingType.IRON_MINE,
                created_at=datetime.now(UTC) + timedelta(seconds=i + 1),
                complete_at=None,  # Queued
                completed=False,
            )
            session.add(iron_mine_event)

        # Add a completed woodcutter event, should not affect the test
        woodcutter_event = models.BuildingEvent(
            village_id=village.id,
            building_type=BuildingType.WOODCUTTER,
            created_at=datetime.now(UTC),
            complete_at=datetime.now(UTC) - timedelta(minutes=1),
            completed=True,
        )
        session.add(woodcutter_event)

        session.commit()

        one_hour_later = village.last_wood_update + timedelta(hours=1, milliseconds=1)

        with freeze_time(one_hour_later):
            VillageManager(village=village, session=session)

        # Refresh the village to get updated values
        session.refresh(village)

        expected_iron = INITIAL_RESOURCES + 40
        assert village.iron == expected_iron

        # Check levels of buildings
        assert village.woodcutter_lvl == 1  # Should not change, event was completed
        assert village.clay_pit_lvl == 2
        assert village.iron_mine_lvl == 5  # Only 4 events completed in time, 2 waiting

        building_events = session.exec(
            select(models.BuildingEvent)
            .where(models.BuildingEvent.building_type == BuildingType.IRON_MINE)
            .order_by(models.BuildingEvent.complete_at)
        ).all()
        assert len(building_events) == 6

        non_completed_events = [
            event for event in building_events if not event.completed
        ]
        assert len(non_completed_events) == 2

        # Check that the first event got completion time (queued)
        event_to_complete = non_completed_events[0]
        assert time_close_enough(
            event_to_complete.complete_at,
            one_hour_later + timedelta(minutes=6, seconds=18),
            tolerance_ms=1000,
        )

        # Only one event can be queued. Second event not queued
        other_event = non_completed_events[1]
        assert other_event.complete_at is None

    @pytest.mark.parametrize(
        "headquarters_lvl, expected_time_ms",
        [
            (1, 1000 * 60 * 4 * 1.25),  # 4 minutes
            (2, 1000 * 60 * 4 * 1.25 * 0.975),  # 2.5% reduction
            (30, 1000 * 60 * 4 * 1.25 * 0.275),  # 72.5% reduction
        ],
    )
    def test_headquarters_lvl_increase_building_speed(
        self,
        session: Session,
        village: models.Village,
        headquarters_lvl: int,
        expected_time_ms: int,
    ):
        """
        Test that increasing the headquarters level increases building speed
        """

        # Given
        village.headquarters_lvl = headquarters_lvl
        village.farm_lvl = 20  # Set high farm level for enough population
        session.commit()

        # When
        manager = VillageManager(village=village, session=session)
        event = manager.schedule_building_upgrade(BuildingType.STORAGE)

        # Then
        assert event is not None
        assert event.complete_at is not None

        # Calculate the actual build time in milliseconds
        build_time_ms = (event.complete_at - event.created_at).total_seconds() * 1000

        # Check with tolerance
        assert (
            abs(build_time_ms - expected_time_ms) < 100
        )  # Small tolerance for rounding errors


class TestScheduleBuildingUpgrade:
    """Tests for the VillageManager schedule_building_upgrade method"""

    @pytest.fixture
    def village(self, session: Session) -> models.Village:
        """Create a test village with resources"""
        village = crud.Village.create(
            session=session, name="Test Village", x=500, y=500, player_id=None
        )
        # Set high resource values for testing
        village.wood = 2000
        village.clay = 2000
        village.iron = 2000
        # Set high farm level for enough population
        village.farm_lvl = 5
        session.commit()
        return village

    def test_building_upgrade_queued(self, session: Session, village: models.Village):
        """Test that building upgrade is correctly queued"""
        manager = VillageManager(village=village, session=session)

        # Schedule first building upgrade
        event1 = manager.schedule_building_upgrade(BuildingType.WOODCUTTER)

        # Verify event1 was created and has complete_at time set
        assert event1 is not None
        assert event1.complete_at is not None
        assert not event1.completed

        # Schedule second building upgrade (should be queued)
        event2 = manager.schedule_building_upgrade(BuildingType.CLAY_PIT)

        # Verify event2 was created but has no complete_at time yet
        assert event2 is not None
        assert event2.complete_at is None
        assert not event2.completed

        # Get all events from database to verify
        events = session.exec(
            select(models.BuildingEvent)
            .where(models.BuildingEvent.village_id == village.id)
            .order_by(models.BuildingEvent.created_at)
        ).all()

        assert len(events) == 2
        assert events[0].building_type == BuildingType.WOODCUTTER
        assert events[0].complete_at is not None
        assert events[1].building_type == BuildingType.CLAY_PIT
        assert events[1].complete_at is None

    def test_queue_full(self, session: Session, village: models.Village):
        """Test that exception is raised when queue is full"""
        manager = VillageManager(village=village, session=session)

        # Fill the queue
        manager.schedule_building_upgrade(BuildingType.WOODCUTTER)
        manager.schedule_building_upgrade(BuildingType.CLAY_PIT)

        # Try to add a third building - should raise QueueFullError
        with pytest.raises(QueueFullError):
            manager.schedule_building_upgrade(BuildingType.IRON_MINE)

    @pytest.mark.parametrize(
        "wood, clay, iron",
        [
            (10, 2000, 2000),  # Not enough wood
            (2000, 10, 2000),  # Not enough clay
            (2000, 2000, 10),  # Not enough iron
        ],
    )
    def test_not_enough_resources(
        self, session: Session, village: models.Village, wood, clay, iron
    ):
        """Test that exception is raised when there are not enough resources"""
        # Set resource values
        village.wood = wood
        village.clay = clay
        village.iron = iron
        session.commit()

        manager = VillageManager(village=village, session=session)

        # Try to upgrade - should raise the expected exception
        with pytest.raises(InsufficientResourcesError):
            manager.schedule_building_upgrade(BuildingType.WOODCUTTER)

    def test_not_enough_population(self, session: Session, village: models.Village):
        """Test that exception is raised when there is not enough population"""
        # Set low farm level and high building levels to exceed population
        village.farm_lvl = 1  # Low max population
        village.woodcutter_lvl = 20
        village.clay_pit_lvl = 20
        village.iron_mine_lvl = 20
        village.headquarters_lvl = 20
        session.commit()

        manager = VillageManager(village=village, session=session)

        # Try to upgrade a building that will exceed population - should raise InsufficientPopulationError
        with pytest.raises(InsufficientPopulationError):
            manager.schedule_building_upgrade(BuildingType.WOODCUTTER)

    def test_farm_upgrade_ignores_population_check(
        self, session: Session, village: models.Village
    ):
        """Test that farm upgrades ignore population check"""
        # Set low farm level and high building levels to exceed population
        village.farm_lvl = 1
        village.woodcutter_lvl = 20
        village.clay_pit_lvl = 20
        village.iron_mine_lvl = 20
        village.headquarters_lvl = 20
        session.commit()

        manager = VillageManager(village=village, session=session)

        # Farm upgrade should work despite population being maxed out
        event = manager.schedule_building_upgrade(BuildingType.FARM)

        assert event is not None
        assert event.building_type == BuildingType.FARM

    def test_resources_deducted(self, session: Session, village: models.Village):
        """Test that resources are correctly deducted when scheduling an upgrade"""
        manager = VillageManager(village=village, session=session)

        # Get initial resources
        initial_wood = village.wood
        initial_clay = village.clay
        initial_iron = village.iron

        # Get building costs
        woodcutter = Woodcutter(level=1)

        # Schedule upgrade
        manager.schedule_building_upgrade(BuildingType.WOODCUTTER)

        # Refresh village data
        session.refresh(village)

        # Verify resources were deducted correctly
        assert village.wood == initial_wood - woodcutter.wood_cost
        assert village.clay == initial_clay - woodcutter.clay_cost
        assert village.iron == initial_iron - woodcutter.iron_cost

    def test_max_level_reached(self, session: Session, village: models.Village):
        """Test that exception is raised when building is at max level"""
        # Set woodcutter to max level
        woodcutter = Woodcutter()
        village.woodcutter_lvl = woodcutter.max_level
        session.commit()

        manager = VillageManager(village=village, session=session)

        # Try to upgrade beyond max level - should raise MaxLevelReachedError
        with pytest.raises(MaxLevelReachedError):
            manager.schedule_building_upgrade(BuildingType.WOODCUTTER)


class TestStorageBuilding:
    """Tests for the Storage building functionality"""

    @pytest.fixture
    def village(self, session: Session) -> models.Village:
        """Create a test village with some resources"""
        village = crud.Village.create(
            session=session, name="Test Village", x=500, y=500, player_id=None
        )
        # Set specific storage level
        village.storage_lvl = 1
        # Set resource values for testing
        village.wood = 500
        village.clay = 500
        village.iron = 500
        session.commit()
        return village

    def test_storage_capacity_limit(self, session: Session, village: models.Village):
        """Test that resources cannot exceed storage capacity"""
        # Set up a village manager and get initial storage capacity
        manager = VillageManager(village=village, session=session)
        storage = Storage(level=1)
        initial_capacity = storage.max_capacity

        # Verify initial capacity is as expected
        assert initial_capacity == 1200

        # Manually set resources above capacity
        village.wood = initial_capacity + 500
        session.commit()

        # Update the village - this should cap resources at capacity
        with freeze_time(datetime.now(UTC) + timedelta(hours=1)):
            manager.update()

        # Refresh the village to get updated values
        session.refresh(village)

        # Check that wood has been capped at max capacity
        assert village.wood == initial_capacity

    def test_storage_upgrade_increases_capacity(
        self, session: Session, village: models.Village
    ):
        """Test that upgrading storage increases capacity"""
        # Set up a village manager
        manager = VillageManager(village=village, session=session)

        # Get initial capacity
        initial_capacity = manager.get_max_storage_capacity()

        # Upgrade storage
        manager.schedule_building_upgrade(BuildingType.STORAGE)

        # Update to complete the building
        with freeze_time(datetime.now(UTC) + timedelta(hours=1)):
            manager.update()

        # Refresh the village to get updated values
        session.refresh(village)

        # Verify storage level increased
        assert village.storage_lvl == 2

        # Calculate expected new capacity
        storage_lvl2 = Storage(level=2)
        expected_capacity = storage_lvl2.max_capacity

        # Get actual new capacity
        new_capacity = manager.get_max_storage_capacity()

        # Verify capacity increased
        assert new_capacity > initial_capacity
        assert new_capacity == expected_capacity


class TestScheduleUnitTraining:
    """Tests for the VillageManager schedule_unit_training method"""

    DEFAULT_RESOURCES = 2000

    @pytest.fixture
    def village(self, session: Session) -> models.Village:
        """Create a test village with resources and barracks"""
        village = crud.Village.create(
            session=session, name="Test Village", x=500, y=500, player_id=None
        )
        # Set high resource values for testing
        village.wood = self.DEFAULT_RESOURCES
        village.clay = self.DEFAULT_RESOURCES
        village.iron = self.DEFAULT_RESOURCES
        # Set barracks level
        village.barracks_lvl = 1
        # Set high farm level for enough population
        village.farm_lvl = 5
        session.commit()
        return village

    def test_unit_training_single_queued(
        self, session: Session, village: models.Village
    ):
        """Test that a single unit can be queued for training"""
        manager = VillageManager(village=village, session=session)

        # Schedule training of a single archer
        event = manager.schedule_unit_training(UnitName.ARCHER, 1)

        # Verify event was created and has complete_at time set
        assert event is not None
        assert event.complete_at is not None
        assert not event.completed
        assert event.count == 1
        assert event.unit_type == UnitName.ARCHER

        # Check that resources were deducted
        assert village.wood == self.DEFAULT_RESOURCES - Archer.base_wood_cost
        assert village.clay == self.DEFAULT_RESOURCES - Archer.base_clay_cost
        assert village.iron == self.DEFAULT_RESOURCES - Archer.base_iron_cost

        # Initial check - no units should be trained yet
        assert village.archer == 0

    def test_unit_training_multiple_queued(
        self, session: Session, village: models.Village
    ):
        """Test that multiple units can be queued for training"""
        manager = VillageManager(village=village, session=session)

        # Schedule training of multiple swordsmen
        event = manager.schedule_unit_training(UnitName.SWORDSMAN, 5)

        # Check resources taken
        assert village.wood == self.DEFAULT_RESOURCES - 5 * Swordsman.base_wood_cost
        assert village.clay == self.DEFAULT_RESOURCES - 5 * Swordsman.base_clay_cost
        assert village.iron == self.DEFAULT_RESOURCES - 5 * Swordsman.base_iron_cost

        # Verify event was created correctly
        assert event is not None
        assert event.complete_at is not None
        assert not event.completed
        assert event.count == 5
        assert event.unit_type == UnitName.SWORDSMAN

        # Check the database to verify
        unit_events = session.exec(
            select(models.UnitTrainingEvent).where(
                models.UnitTrainingEvent.village_id == village.id
            )
        ).all()

        assert len(unit_events) == 1
        assert unit_events[0].count == 5
        assert unit_events[0].unit_type == UnitName.SWORDSMAN

    def test_unit_training_completion_single(
        self, session: Session, village: models.Village
    ):
        """Test that a queued unit is added to the village when completed"""
        manager = VillageManager(village=village, session=session)

        # Set the time for test consistency
        start_time = datetime.now(UTC)

        with freeze_time(start_time):
            # Schedule training of one archer
            event = manager.schedule_unit_training(UnitName.ARCHER, 1)
            complete_time = event.complete_at

        # Move to just after completion time
        with freeze_time(complete_time + timedelta(seconds=1)):
            # Update should process the completed event
            manager.update()

        # Check that the unit is now in the village
        session.refresh(village)
        assert village.archer == 1

        # Check that the event was removed
        remaining_events = session.exec(
            select(models.UnitTrainingEvent).where(
                models.UnitTrainingEvent.village_id == village.id
            )
        ).all()
        assert len(remaining_events) == 0

    def test_unit_training_completion_multiple(
        self, session: Session, village: models.Village
    ):
        """Test that multiple queued units are added one by one when completed"""
        manager = VillageManager(village=village, session=session)

        # Set the time for test consistency
        start_time = datetime.now(UTC)

        with freeze_time(start_time):
            # Schedule training of 3 knights
            event = manager.schedule_unit_training(UnitName.KNIGHT, 3)
            first_complete_time = event.complete_at

        # Move to just after the first unit should complete
        with freeze_time(first_complete_time + timedelta(seconds=1)):
            # Update should process the first unit
            manager.update()

            # Check that one unit is now in the village
            session.refresh(village)
            assert village.knight == 1

            # Check that the event has reduced count but still exists
            updated_events = session.exec(
                select(models.UnitTrainingEvent).where(
                    models.UnitTrainingEvent.village_id == village.id
                )
            ).all()
            assert len(updated_events) == 1
            assert updated_events[0].count == 2

            # Get the next completion time
            second_complete_time = updated_events[0].complete_at

        # Move to after all units should be completed
        with freeze_time(second_complete_time + timedelta(minutes=15)):
            # Update should process all remaining units
            manager.update()

            # Check that all units are now in the village
            session.refresh(village)
            assert village.knight == 3

            # Check that the event was removed
            final_events = session.exec(
                select(models.UnitTrainingEvent).where(
                    models.UnitTrainingEvent.village_id == village.id
                )
            ).all()
            assert len(final_events) == 0

    def test_barracks_required(self, session: Session, village: models.Village):
        """Test that barracks is required to train units"""
        # Set barracks level to 0
        village.barracks_lvl = 0
        session.commit()

        manager = VillageManager(village=village, session=session)

        # Try to train units without barracks
        with pytest.raises(BarracksRequiredError):
            manager.schedule_unit_training(UnitName.ARCHER, 1)

    def test_not_enough_resources(self, session: Session, village: models.Village):
        """Test that exception is raised when there are not enough resources"""
        # Set low resource values
        village.wood = 10
        village.clay = 10
        village.iron = 10
        session.commit()

        manager = VillageManager(village=village, session=session)

        # Try to train units with insufficient resources
        with pytest.raises(InsufficientResourcesError):
            manager.schedule_unit_training(UnitName.SWORDSMAN, 1)

    def test_queue_limit(self, session: Session, village: models.Village):
        """Test that exception is raised when the training queue is full"""
        manager = VillageManager(village=village, session=session)

        # The max_queue_size for barracks level 1 is 10
        # Try to queue more units than allowed
        with pytest.raises(QueueFullError):
            manager.schedule_unit_training(UnitName.SKIRMISHER, 11)

    @pytest.mark.parametrize(
        "barracks_lvl, expected_time_ms",
        [
            (1, 1000 * 60 * 6.5),  # Base time for archer
            (2, 1000 * 60 * 6.5 * 0.975),  # 2.5% reduction
            (30, 1000 * 60 * 6.5 * 0.275),  # 72.5% reduction (capped at 95%)
        ],
    )
    def test_barracks_level_affects_training_speed(
        self,
        session: Session,
        village: models.Village,
        barracks_lvl: int,
        expected_time_ms: int,
    ):
        """Test that barracks level affects training speed"""
        # Set barracks level for the test
        village.barracks_lvl = barracks_lvl
        session.commit()

        manager = VillageManager(village=village, session=session)

        # Schedule archer training
        event = manager.schedule_unit_training(UnitName.ARCHER, 1)

        # Get actual training time
        training_time_ms = (event.complete_at - event.created_at).total_seconds() * 1000

        # Check with tolerance
        assert (
            abs(training_time_ms - expected_time_ms) < 100
        )  # Small tolerance for rounding

    @pytest.mark.parametrize("should_add_completed_events", [False, True])
    def test_population_limit(
        self,
        session: Session,
        village: models.Village,
        should_add_completed_events: bool,
    ):
        """Test that exception is raised when there's not enough population capacity"""
        # Set low farm level for limited population
        manager = VillageManager(village=village, session=session)
        village.farm_lvl = 1
        # Add population consumers to get close to the limit
        village.archer = (
            manager.get_max_population() - manager.get_current_population() - 5
        )

        # Add completed training events - these should be ignored in the calculations
        if should_add_completed_events:
            self._add_completed_training_events(session, village)

        session.commit()

        # The first batch of knights should be allowed
        manager.schedule_unit_training(UnitName.KNIGHT, 5)

        # The second batch should exceed the population limit
        with pytest.raises(InsufficientPopulationError):
            manager.schedule_unit_training(UnitName.KNIGHT, 5)

    def _add_completed_training_events(self, session: Session, village: models.Village):
        completed_events = [
            models.UnitTrainingEvent(
                village_id=village.id,
                unit_type=UnitName.KNIGHT,
                count=10,  # Large count that would exceed population if counted
                created_at=datetime.now(UTC) - timedelta(hours=1),
                complete_at=datetime.now(UTC) - timedelta(minutes=30),
                completed=True,
            ),
            models.UnitTrainingEvent(
                village_id=village.id,
                unit_type=UnitName.ARCHER,
                count=15,  # Another large count
                created_at=datetime.now(UTC) - timedelta(hours=2),
                complete_at=datetime.now(UTC) - timedelta(hours=1),
                completed=True,
            ),
        ]
        session.add_all(completed_events)
        session.commit()
