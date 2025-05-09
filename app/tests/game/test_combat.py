import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session, select

from app import crud, models
from app.game.combat import AttackResolver, Resources
from app.game.village import VillageManager
from app.schemas import Units


class TestAttackResolver:
    """Tests for the AttackResolver class"""

    @pytest.fixture
    def village_manager(self, session: Session) -> MagicMock:
        """Create a mock village manager"""
        # Create a real village for the test
        village = crud.Village.create(
            session=session, name="Defender Village", x=500, y=500, player_id=None
        )

        village_manager = VillageManager(village=village, session=session)

        # Add some resources and units to the village
        village.wood = 1000
        village.clay = 1000
        village.iron = 1000
        village.archer = 10
        village.swordsman = 10
        village.knight = 5
        village.skirmisher = 5
        session.add(village)
        session.commit()

        return village_manager

    def test_calculate_battle_result_attacker_wins(self):
        """Test battle calculation when attacker has stronger army"""
        # Many attackers vs few defenders
        attacking_units = Units(archer=50, swordsman=50, knight=25, skirmisher=25)

        defending_units = Units(archer=5, swordsman=5, knight=2, skirmisher=2)

        # Use static method to calculate battle result
        battle_result = AttackResolver.calculate_battle_result(
            attacking_units=attacking_units,
            defending_units=defending_units,
            luck=0.0,
        )

        # Verify attacker wins
        assert battle_result.attacker_won is True

        # Verify all defending units are lost
        assert battle_result.defending_units.archer == 0
        assert battle_result.defending_units.swordsman == 0
        assert battle_result.defending_units.knight == 0
        assert battle_result.defending_units.skirmisher == 0

        # Verify some attacking units survived
        assert battle_result.attacking_units.archer == 49
        assert battle_result.attacking_units.swordsman == 49
        assert battle_result.attacking_units.knight == 25
        assert battle_result.attacking_units.skirmisher == 25

        # Verify attacking units lost are calculated correctly
        assert battle_result.attacking_units_lost.archer == 1
        assert battle_result.attacking_units_lost.swordsman == 1
        assert battle_result.attacking_units_lost.knight == 0
        assert battle_result.attacking_units_lost.skirmisher == 0

    def test_calculate_battle_result_defender_wins(self):
        """Test battle calculation when defender has stronger army"""
        # Few attackers vs many defenders
        attacking_units = Units(archer=5, swordsman=5, knight=2, skirmisher=2)

        defending_units = Units(archer=50, swordsman=50, knight=25, skirmisher=25)

        # Use static method to calculate battle result
        battle_result = AttackResolver.calculate_battle_result(
            attacking_units=attacking_units,
            defending_units=defending_units,
            luck=0.0,
        )

        # Verify defender wins
        assert battle_result.attacker_won is False

        # Verify all attacking units are lost
        assert battle_result.attacking_units.archer == 0
        assert battle_result.attacking_units.swordsman == 0
        assert battle_result.attacking_units.knight == 0
        assert battle_result.attacking_units.skirmisher == 0

        # Verify some defending units survived
        assert battle_result.defending_units.archer == 47
        assert battle_result.defending_units.swordsman == 47
        assert battle_result.defending_units.knight == 24
        assert battle_result.defending_units.skirmisher == 24

        # Verify defending units lost are calculated correctly
        assert battle_result.defending_units_lost.archer == 3
        assert battle_result.defending_units_lost.swordsman == 3
        assert battle_result.defending_units_lost.knight == 1
        assert battle_result.defending_units_lost.skirmisher == 1

    @pytest.mark.parametrize(
        "luck_factor,expected_result",
        [
            (-0.25, False),  # Bad luck for attacker
            (0.25, True),  # Good luck for attacker
        ],
    )
    def test_luck_factor_impacts_battle(self, luck_factor, expected_result):
        """Test that luck factor impacts battle outcome in close battles"""
        # Create evenly matched armies where luck should be decisive
        attacking_units = Units(archer=20, swordsman=20, knight=10, skirmisher=10)

        defending_units = Units(archer=10, swordsman=10, knight=20, skirmisher=20)

        # Calculate battle with luck factor
        battle_result = AttackResolver.calculate_battle_result(
            attacking_units=attacking_units,
            defending_units=defending_units,
            luck=luck_factor,
        )

        # Verify luck influences outcome
        assert battle_result.attacker_won is expected_result

        if expected_result:
            assert battle_result.attacking_units.archer == 6
            assert battle_result.attacking_units.swordsman == 8
            assert battle_result.attacking_units.knight == 4
            assert battle_result.attacking_units.skirmisher == 4

            assert battle_result.defending_units.archer == 0
            assert battle_result.defending_units.swordsman == 0
            assert battle_result.defending_units.knight == 0
            assert battle_result.defending_units.skirmisher == 0
        else:
            assert battle_result.attacking_units.archer == 0
            assert battle_result.attacking_units.swordsman == 0
            assert battle_result.attacking_units.knight == 0
            assert battle_result.attacking_units.skirmisher == 0

            assert battle_result.defending_units.archer == 3
            assert battle_result.defending_units.swordsman == 3
            assert battle_result.defending_units.knight == 5
            assert battle_result.defending_units.skirmisher == 5

    def test_calculate_looted_resources(self, village_manager):
        """Test resource looting calculation"""
        resolver = AttackResolver(village_manager=village_manager)

        # Set up input values
        resources = Resources(wood=1000, clay=1000, iron=1000)
        loot_capacity = 800

        # Calculate looted resources
        looted = resolver._calculate_looted_resources(resources, loot_capacity)

        # Verify total looted doesn't exceed capacity
        total_looted = looted.wood + looted.clay + looted.iron
        assert total_looted <= loot_capacity

        # Verify each resource is at most 80% of available
        assert looted.wood <= 800  # 80% of 1000
        assert looted.clay <= 800
        assert looted.iron <= 800

    def test_resolve_combat_calculation(self):
        """Test the internal combat resolution calculation"""
        # Attacker stronger than defender
        attacker_losses, defender_losses = AttackResolver._resolve_combat(100.0, 50.0)
        assert attacker_losses < 1.0  # Attacker loses some units
        assert defender_losses == 1.0  # Defender loses all units

        # Defender stronger than attacker
        attacker_losses, defender_losses = AttackResolver._resolve_combat(50.0, 100.0)
        assert attacker_losses == 1.0  # Attacker loses all units
        assert defender_losses < 1.0  # Defender loses some units

        # Equal strength
        attacker_losses, defender_losses = AttackResolver._resolve_combat(100.0, 100.0)
        assert attacker_losses == 1.0  # Both lose all units
        assert defender_losses == 1.0

    def test_unit_survival_calculation(self):
        """Test the unit survival calculation logic"""
        resolver = AttackResolver(village_manager=MagicMock())

        original_units = Units(archer=100, swordsman=100, knight=50, skirmisher=50)
        remaining_units = Units(archer=50, swordsman=60, knight=20, skirmisher=30)

        survival_ratios = resolver._calculate_unit_loss_ratios(
            original_units, remaining_units
        )

        assert survival_ratios["archer"] == 0.5  # 50/100
        assert survival_ratios["swordsman"] == 0.6  # 60/100
        assert survival_ratios["knight"] == 0.4  # 20/50
        assert survival_ratios["skirmisher"] == 0.6  # 30/50

    def test_calculate_loot_capacity(self):
        """Test loot capacity calculation based on unit types"""
        resolver = AttackResolver(village_manager=MagicMock())

        # Units with different loot capacities
        units = Units(
            archer=10,  # Archer loot capacity is 15
            swordsman=10,  # Swordsman loot capacity is 20
            knight=5,  # Knight loot capacity is 25
            skirmisher=5,  # Skirmisher loot capacity is 25
        )

        expected_capacity = (
            10 * 15  # 10 archers * 15 capacity
            + 10 * 20  # 10 swordsmen * 20 capacity
            + 5 * 25  # 5 knights * 25 capacity
            + 5 * 25  # 5 skirmishers * 25 capacity
        )

        # Calculate and verify
        capacity = resolver._calculate_loot_capacity(units)
        assert capacity == expected_capacity


class TestIntegratedCombat:
    """Integration tests for the combat system"""

    @pytest.fixture
    def attacker_village(self, session: Session):
        """Create a test attacker village"""
        player = models.Player(username="Attacker", id=uuid.uuid4())
        session.add(player)
        session.commit()
        session.refresh(player)

        village = crud.Village.create(
            session=session, name="Attacker Village", x=500, y=500, player_id=player.id
        )
        village.archer = 40
        village.swordsman = 40
        village.knight = 20
        village.skirmisher = 20
        village.wood = 100
        village.clay = 100
        village.iron = 100
        session.add(village)
        session.commit()
        return village

    @pytest.fixture
    def defender_village(self, session: Session):
        """Create a test defender village"""
        player = models.Player(username="Deffender", id=uuid.uuid4())
        session.add(player)
        session.commit()
        session.refresh(player)

        village = crud.Village.create(
            session=session, name="Defender Village", x=510, y=510, player_id=player.id
        )
        village.archer = 5
        village.swordsman = 5
        village.knight = 2
        village.skirmisher = 2
        village.wood = 1000
        village.clay = 1000
        village.iron = 1000
        session.add(village)
        session.commit()
        return village

    @pytest.fixture
    def attack_movement(self, session: Session, attacker_village, defender_village):
        """Create an attack movement"""
        now = datetime.now(UTC)
        movement = models.UnitMovement(
            village_id=attacker_village.id,
            target_village_id=defender_village.id,
            arrival_at=now - timedelta(minutes=1),  # Already arrived
            created_at=now - timedelta(hours=1),
            archer=15,
            swordsman=15,
            knight=5,
            skirmisher=5,
            is_attack=True,
            completed=False,
        )
        session.add(movement)
        session.commit()
        return movement

    @pytest.fixture
    def support_movement(self, session: Session, attacker_village, defender_village):
        """Create a support movement"""
        now = datetime.now(UTC)
        movement = models.UnitMovement(
            village_id=attacker_village.id,
            target_village_id=defender_village.id,
            arrival_at=now - timedelta(minutes=1),  # Already arrived
            created_at=now - timedelta(hours=1),
            archer=10,
            swordsman=10,
            knight=10,
            skirmisher=10,
            is_support=True,
            completed=False,
        )
        session.add(movement)
        session.commit()
        return movement

    def add_inactive_movements(self, session, attacker_village, defender_village):
        """Add various inactive movements that should not affect the battle

        Creates movements that are:
        - Completed (have already been processed)
        - Future arrivals (not yet arrived)
        - With return_at set (units already returning)
        """
        now = datetime.now(UTC)

        # Already completed attack
        completed_attack = models.UnitMovement(
            village_id=attacker_village.id,
            target_village_id=defender_village.id,
            arrival_at=now - timedelta(hours=2),
            created_at=now - timedelta(hours=3),
            archer=20,
            swordsman=20,
            knight=10,
            skirmisher=10,
            is_attack=True,
            completed=True,  # Already completed
        )

        # Future attack (not arrived yet)
        future_attack = models.UnitMovement(
            village_id=attacker_village.id,
            target_village_id=defender_village.id,
            arrival_at=now + timedelta(hours=1),  # Future arrival
            created_at=now - timedelta(minutes=30),
            archer=25,
            swordsman=25,
            knight=15,
            skirmisher=15,
            is_attack=True,
            completed=False,
        )

        # Returning units after attack
        returning_units = models.UnitMovement(
            village_id=attacker_village.id,
            target_village_id=defender_village.id,
            arrival_at=now - timedelta(hours=3),
            return_at=now + timedelta(minutes=30),  # Will return in future
            created_at=now - timedelta(hours=4),
            archer=10,
            swordsman=10,
            knight=5,
            skirmisher=5,
            is_attack=True,
            completed=False,
        )

        # Already completed support
        completed_support = models.UnitMovement(
            village_id=attacker_village.id,
            target_village_id=defender_village.id,
            arrival_at=now - timedelta(hours=2),
            created_at=now - timedelta(hours=3),
            archer=15,
            swordsman=15,
            knight=5,
            skirmisher=5,
            is_support=True,
            completed=True,  # Already completed
        )

        # Future support (not arrived yet)
        future_support = models.UnitMovement(
            village_id=attacker_village.id,
            target_village_id=defender_village.id,
            arrival_at=now + timedelta(hours=1),  # Future arrival
            created_at=now - timedelta(minutes=30),
            archer=8,
            swordsman=8,
            knight=4,
            skirmisher=4,
            is_support=True,
            completed=False,
        )

        session.add_all(
            [
                completed_attack,
                future_attack,
                returning_units,
                completed_support,
                future_support,
            ]
        )
        session.commit()

    @pytest.mark.parametrize("with_inactive_movements", [False, True])
    def test_end_to_end_attack_win_no_support(
        self,
        session,
        attacker_village,
        defender_village,
        attack_movement,
        with_inactive_movements,
    ):
        """Test a complete attack flow from beginning to end"""
        # Add inactive movements if the parameter is True
        if with_inactive_movements:
            self.add_inactive_movements(session, attacker_village, defender_village)

        # Lock village
        defender_village = crud.Village.get_for_update(
            session=session, village_id=defender_village.id
        )
        defender_manager = VillageManager(village=defender_village, session=session)

        # Create resolver and resolve attack
        # patch combat.random.uniform to control luck
        with patch("app.game.combat.random.uniform", return_value=0.0):
            resolver = AttackResolver(village_manager=defender_manager)
            resolver.resolve_attack()

        # Refresh villages to get updated state
        session.refresh(attacker_village)
        session.refresh(defender_village)
        session.refresh(attack_movement)

        # Verify battle occurred
        # Check that units were lost on both sides
        assert defender_village.archer == 0
        assert defender_village.swordsman == 0
        assert defender_village.knight == 0
        assert defender_village.skirmisher == 0

        assert attacker_village.archer == 38
        assert attacker_village.swordsman == 38
        assert attacker_village.knight == 19
        assert attacker_village.skirmisher == 19

        RESOURCE_STOLEN = 218
        ORIGINAL_RESOURCES = 1000

        # Check that resources were looted
        assert defender_village.wood == ORIGINAL_RESOURCES - RESOURCE_STOLEN
        assert defender_village.clay == ORIGINAL_RESOURCES - RESOURCE_STOLEN
        assert defender_village.iron == ORIGINAL_RESOURCES - RESOURCE_STOLEN

        assert attack_movement.return_wood == RESOURCE_STOLEN
        assert attack_movement.return_clay == RESOURCE_STOLEN
        assert attack_movement.return_iron == RESOURCE_STOLEN

        assert attack_movement.completed is False
        assert attack_movement.return_at is not None

        # Check that battle reports were created
        battle_messages = session.exec(select(models.BattleMessage)).all()
        assert len(battle_messages) == 2

        attacker_message = [
            msg
            for msg in battle_messages
            if msg.to_player_id == attacker_village.player_id
        ]
        assert len(attacker_message) == 1
        attacker_message: models.BattleMessage = attacker_message[0]

        assert attacker_message.from_player_id is None
        assert attacker_message.created_at is not None
        assert attacker_message.message == "Battle Report: Attack on Defender Village"
        battle_data_json: dict = json.loads(attacker_message.battle_data)
        battle_data_json.pop("datetime")
        assert battle_data_json == {
            "attacker_won": True,
            "attacking_units": {
                "archer": 13,
                "swordsman": 13,
                "knight": 4,
                "skirmisher": 4,
                "nobleman": 0,
            },
            "attacking_units_lost": {
                "archer": 2,
                "swordsman": 2,
                "knight": 1,
                "skirmisher": 1,
                "nobleman": 0,
            },
            "defending_units": {
                "archer": 0,
                "swordsman": 0,
                "knight": 0,
                "skirmisher": 0,
                "nobleman": 0,
            },
            "defending_units_lost": {
                "archer": 5,
                "swordsman": 5,
                "knight": 2,
                "skirmisher": 2,
                "nobleman": 0,
            },
            "original_loyalty": 100.0,
            "loyalty_damage": 0.0,
            "luck": 0.0,
            "loot_capacity": 655,
            "looted_wood": 218,
            "looted_clay": 218,
            "looted_iron": 218,
            "conquered_by_player": None,
            "conquered_village": None,
            "attacking_village_id": 1,
            "defending_village_id": 2,
            "own_units": {
                "archer": 13,
                "swordsman": 13,
                "knight": 4,
                "skirmisher": 4,
                "nobleman": 0,
            },
            "own_units_lost": {
                "archer": 2,
                "swordsman": 2,
                "knight": 1,
                "skirmisher": 1,
                "nobleman": 0,
            },
            "own_loot_capacity": 655,
            "own_looted_wood": 218,
            "own_looted_clay": 218,
            "own_looted_iron": 218,
        }

        defender_message = [
            msg
            for msg in battle_messages
            if msg.to_player_id == defender_village.player_id
        ]
        assert len(defender_message) == 1
        defender_message: models.BattleMessage = defender_message[0]
        assert defender_message.from_player_id is None

    def test_end_to_end_attack_lose_with_support(
        self,
        session,
        attacker_village,
        defender_village,
        attack_movement,
        support_movement,
    ):
        """Test a complete attack flow with support units where attacker loses"""
        # Lock village
        defender_village = crud.Village.get_for_update(
            session=session, village_id=defender_village.id
        )
        defender_manager = VillageManager(village=defender_village, session=session)

        # Create resolver and resolve attack
        # patch combat.random.uniform to control luck - using negative luck against
        # attacker
        with patch("app.game.combat.random.uniform", return_value=-0.25):
            resolver = AttackResolver(village_manager=defender_manager)
            resolver.resolve_attack()

        # Refresh villages to get updated state
        session.refresh(attacker_village)
        session.refresh(defender_village)
        session.refresh(attack_movement)
        session.refresh(support_movement)

        # Attacker lost all their units
        assert attack_movement.completed is True

        # Defender should have lost some units but not all
        assert defender_village.archer == 2
        assert defender_village.swordsman == 2
        assert defender_village.knight == 1
        assert defender_village.skirmisher == 1

        # Support units should have lost some units but not all
        assert support_movement.archer == 3
        assert support_movement.swordsman == 3
        assert support_movement.knight == 3
        assert support_movement.skirmisher == 3

        # No resources should be looted since attacker lost
        assert attack_movement.return_wood == 0
        assert attack_movement.return_clay == 0
        assert attack_movement.return_iron == 0

        assert defender_village.wood == 1000
        assert defender_village.clay == 1000
        assert defender_village.iron == 1000

        # Check that battle reports were created
        battle_messages = session.exec(select(models.BattleMessage)).all()
        assert len(battle_messages) == 3  # Attacker, defender and support player

        # Check attacker message
        attacker_message = [
            msg
            for msg in battle_messages
            if msg.to_player_id == attacker_village.player_id
            and "Attack on" in msg.message
        ]
        assert len(attacker_message) == 1
        attacker_message: models.BattleMessage = attacker_message[0]
        assert attacker_message.from_player_id is None
        assert attacker_message.created_at is not None

        battle_data_json = json.loads(attacker_message.battle_data)
        assert battle_data_json["attacker_won"] is False

        # Check that all attacker units were lost
        assert battle_data_json["own_units"] == {
            "archer": 0,
            "swordsman": 0,
            "knight": 0,
            "skirmisher": 0,
            "nobleman": 0,
        }

        # Check defender message
        defender_message = [
            msg
            for msg in battle_messages
            if msg.to_player_id == defender_village.player_id
        ]
        assert len(defender_message) == 1

        # Check support message
        support_message = [
            msg for msg in battle_messages if "supporting units" in msg.message
        ]
        assert len(support_message) == 1

    @pytest.fixture
    def setup_nobleman_attack(
        self, session: Session, attacker_village, defender_village
    ):
        """Create a test attack with nobleman units"""
        now = datetime.now(UTC)

        # Add noblemen to attacker village
        attacker_village.nobleman = 2
        session.add(attacker_village)
        session.commit()

        # Create movement with noblemen
        movement = models.UnitMovement(
            village_id=attacker_village.id,
            target_village_id=defender_village.id,
            arrival_at=now - timedelta(minutes=1),  # Already arrived
            created_at=now - timedelta(hours=1),
            nobleman=1,
            archer=10,  # Add some regular units for support
            swordsman=10,
            is_attack=True,
            completed=False,
        )
        session.add(movement)
        session.commit()
        return movement

    def test_loyalty_reduction_on_successful_attack(
        self, session, attacker_village, defender_village, setup_nobleman_attack
    ):
        """Test that a successful attack with noblemen reduces loyalty"""
        original_loyalty = 100.0
        defender_village.loyalty = original_loyalty
        session.add(defender_village)
        session.commit()

        # Create resolver and resolve attack with controlled luck
        defender_manager = VillageManager(village=defender_village, session=session)

        with patch("app.game.combat.random.uniform", return_value=0.0):  # Neutral luck
            resolver = AttackResolver(village_manager=defender_manager)
            resolver.resolve_attack()

        # Refresh data
        session.refresh(defender_village)

        # Check that loyalty was reduced (20 per nobleman with neutral luck)
        assert defender_village.loyalty < original_loyalty
        assert defender_village.loyalty == 72

        # Check battle reports mention loyalty
        battle_messages = session.exec(select(models.BattleMessage)).all()
        attacker_message = [
            msg for msg in battle_messages if "Attack on" in msg.message
        ][0]
        battle_data = json.loads(attacker_message.battle_data)

        assert battle_data["loyalty_damage"] == 28.0
        assert battle_data["original_loyalty"] == 100.0

    def test_village_conquest_when_loyalty_reaches_zero(
        self, session, attacker_village, defender_village
    ):
        """Test village conquest when loyalty reaches zero"""
        # Set initial loyalty low enough that one attack will conquer it
        defender_village.loyalty = 15.0
        session.add(defender_village)
        session.commit()

        now = datetime.now(UTC)

        # Create movement with nobleman
        movement = models.UnitMovement(
            village_id=attacker_village.id,
            target_village_id=defender_village.id,
            arrival_at=now - timedelta(minutes=1),
            created_at=now - timedelta(hours=1),
            nobleman=1,
            archer=20,  # Strong attack to ensure victory
            swordsman=20,
            knight=10,
            skirmisher=10,
            is_attack=True,
            completed=False,
        )
        session.add(movement)
        session.commit()

        # Get original owner ID for verification
        original_owner_id = defender_village.player_id

        # Create resolver and resolve attack
        defender_manager = VillageManager(village=defender_village, session=session)

        with patch("app.game.combat.random.uniform", return_value=0.0):  # Neutral luck
            resolver = AttackResolver(village_manager=defender_manager)
            resolver.resolve_attack()

        # Refresh data
        session.refresh(defender_village)

        # Check that village ownership changed
        assert defender_village.player_id == attacker_village.player_id
        assert defender_village.player_id != original_owner_id

        # Check that loyalty is reset to 100
        assert defender_village.loyalty == 100.0

        # Check the battle report shows conquest
        battle_messages = session.exec(select(models.BattleMessage)).all()
        attacker_message = [
            msg for msg in battle_messages if "CONQUEST" in msg.message
        ][0]
        assert attacker_message is not None

    def test_loyalty_reduction_with_luck_factor(
        self, session, attacker_village, defender_village
    ):
        """Test that luck affects loyalty reduction"""
        original_loyalty = 100.0
        defender_village.loyalty = original_loyalty
        session.add(defender_village)
        session.commit()

        now = datetime.now(UTC)

        # Create movement with nobleman
        movement = models.UnitMovement(
            village_id=attacker_village.id,
            target_village_id=defender_village.id,
            arrival_at=now - timedelta(minutes=1),
            created_at=now - timedelta(hours=1),
            nobleman=1,
            archer=20,  # Strong attack to ensure victory
            swordsman=20,
            is_attack=True,
            completed=False,
        )
        session.add(movement)
        session.commit()

        # Create resolver and resolve attack with high luck (positive)
        defender_manager = VillageManager(village=defender_village, session=session)

        with patch(
            "app.game.combat.random.uniform", return_value=0.25
        ):  # Maximum good luck
            resolver = AttackResolver(village_manager=defender_manager)
            resolver.resolve_attack()

        # Refresh data
        session.refresh(defender_village)

        assert defender_village.loyalty == 65.0  # 100 - 35.0 = 65.0

        # Reset loyalty for second test
        defender_village.loyalty = original_loyalty
        session.add(defender_village)
        session.commit()

        # Create new movement with nobleman
        movement = models.UnitMovement(
            village_id=attacker_village.id,
            target_village_id=defender_village.id,
            arrival_at=now - timedelta(minutes=1),
            created_at=now - timedelta(hours=1),
            nobleman=1,
            archer=20,
            swordsman=20,
            is_attack=True,
            completed=False,
        )
        session.add(movement)
        session.commit()

        # Create resolver and resolve attack with poor luck (negative)
        with patch(
            "app.game.combat.random.uniform", return_value=-0.25
        ):  # Maximum bad luck
            resolver = AttackResolver(village_manager=defender_manager)
            resolver.resolve_attack()

        # Refresh data
        session.refresh(defender_village)

        assert defender_village.loyalty == 80
