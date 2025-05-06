from datetime import UTC, datetime, timedelta

import pytest
from freezegun import freeze_time
from sqlmodel import Session, select

from app import crud, models
from app.game.buildings import BuildingType, Storage, Woodcutter
from app.game.village import (
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
            manager = VillageManager(village_id=village.id, session=session)
            manager.update()

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
            manager = VillageManager(village_id=village.id, session=session)
            manager.update()

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
            manager = VillageManager(village_id=village.id, session=session)
            manager.update()

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
        manager = VillageManager(village_id=village.id, session=session)
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
        manager = VillageManager(village_id=village.id, session=session)

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
        manager = VillageManager(village_id=village.id, session=session)

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

        manager = VillageManager(village_id=village.id, session=session)

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

        manager = VillageManager(village_id=village.id, session=session)

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

        manager = VillageManager(village_id=village.id, session=session)

        # Farm upgrade should work despite population being maxed out
        event = manager.schedule_building_upgrade(BuildingType.FARM)

        assert event is not None
        assert event.building_type == BuildingType.FARM

    def test_resources_deducted(self, session: Session, village: models.Village):
        """Test that resources are correctly deducted when scheduling an upgrade"""
        manager = VillageManager(village_id=village.id, session=session)

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

        manager = VillageManager(village_id=village.id, session=session)

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
        manager = VillageManager(village_id=village.id, session=session)
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
        manager = VillageManager(village_id=village.id, session=session)

        # Get initial capacity
        manager.update()
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
