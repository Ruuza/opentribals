import logging
import random
from datetime import UTC, datetime
from math import sqrt

from pydantic import BaseModel

from app import crud, models
from app.game.units import UNIT_CLASS_MAP, UnitName, UnitType
from app.game.village import VillageManager
from app.schemas import BattleReport, BattleResultBase, BattleResultForMovement, Units

logger = logging.getLogger(__name__)


class Resources(BaseModel):
    wood: int = 0
    clay: int = 0
    iron: int = 0


class AttackResolver:
    """Class for resolving attacks between villages"""

    def __init__(
        self,
        village_manager: VillageManager,
    ):
        """
        Initialize attack resolver

        Args:
            session: The SQLAlchemy session for database operations
            village_manager: The village manager instance of the target village
        """
        self.village_manager = village_manager
        self.session = village_manager.session

    def resolve_attack(self):
        """
        Resolve the attack by simulating the battle and updating the database
        """
        attacking_movements = crud.UnitMovement.get_ready_movements(
            session=self.session,
            village_id=self.village_manager.village.id,
            is_attack=True,
        )

        if not attacking_movements:
            return  # No attacks to resolve

        # Get defending movements (supporting units from other villages)
        defending_movements = crud.UnitMovement.get_ready_movements(
            session=self.session,
            village_id=self.village_manager.village.id,
            is_support=True,
        )

        # Get available units in the target village
        available_units = self.village_manager.get_available_units()

        # Sum up all attacking units
        total_attacking_units = self._sum_units_from_movements(attacking_movements)

        # Sum up all supporting units
        total_supporting_units = self._sum_units_from_movements(defending_movements)

        # Sum up all defending units (village units + supporting units)
        total_defending_units = Units(
            archer=available_units.archer,
            swordsman=available_units.swordsman,
            knight=available_units.knight,
            skirmisher=available_units.skirmisher,
            nobleman=available_units.nobleman,
        )

        total_defending_units = self._add_units(
            total_defending_units, total_supporting_units
        )

        # Generate a random luck factor between -0.25 and 0.25

        luck_factor = random.uniform(-0.25, 0.25)

        # Calculate the battle result
        battle_result = self.calculate_battle_result(
            attacking_units=total_attacking_units,
            defending_units=total_defending_units,
            luck=luck_factor,
        )

        now = datetime.now(UTC)

        # Prepare resources for looting if attacker won
        resources = Resources(
            wood=self.village_manager.village.wood,
            clay=self.village_manager.village.clay,
            iron=self.village_manager.village.iron,
        )

        # Calculate looted resources if attacker won
        looted_resources = Resources()
        if battle_result.attacker_won:
            # Calculate total loot capacity of surviving attackers
            total_loot_capacity = self._calculate_loot_capacity(
                battle_result.attacking_units
            )

            # Calculate looted resources
            looted_resources = self._calculate_looted_resources(
                resources, total_loot_capacity
            )

            # Update village resources
            self.village_manager._update_resource("wood", -int(looted_resources.wood))
            self.village_manager._update_resource("clay", -int(looted_resources.clay))
            self.village_manager._update_resource("iron", -int(looted_resources.iron))

        # Process loyalty reduction if noblemen survived
        loyalty_damage = 0
        conquered_attack_movement = None

        if battle_result.attacker_won and battle_result.attacking_units.nobleman > 0:
            # Calculate loyalty damage (20-35 points per nobleman based on luck)
            base_loyalty_damage = 20
            luck_modifier = round((luck_factor + 0.25) * 2 * 15)
            loyalty_damage = base_loyalty_damage + luck_modifier

            # Apply loyalty damage
            current_loyalty = self.village_manager.village.loyalty
            new_loyalty = max(0, current_loyalty - loyalty_damage)
            self.village_manager.village.loyalty = new_loyalty

            # Check if village is conquered
            if new_loyalty <= 0:
                # Find the first attacking movement with nobleman surviving to be the new owner
                for movement in attacking_movements:
                    # Check how many noblemen survived in this attack
                    if movement.nobleman > 0:
                        movement_lost_units = self._calculate_lost_units(
                            movement,
                            self._calculate_unit_loss_ratios(
                                total_attacking_units,
                                battle_result.attacking_units_lost,
                            ),
                        )

                        nobleman_survived = (
                            movement.nobleman - movement_lost_units.nobleman
                        )

                        if nobleman_survived > 0:
                            conquered_attack_movement = movement
                            break

                # If we found a conquering attack, change village ownership
                if conquered_attack_movement:
                    # Change owner and reset loyalty
                    self.village_manager.village.player_id = (
                        conquered_attack_movement.origin_village.player_id
                    )
                    self.village_manager.village.loyalty = 100.0

        battle_result.loyalty_damage = loyalty_damage

        # Process attacking movements
        self._process_attacking_movements(
            attacking_movements=attacking_movements,
            battle_result=battle_result,
            total_attacking_units=total_attacking_units,
            looted_resources=looted_resources,
            now=now,
            conquered_attack_movement=conquered_attack_movement,
        )

        # Process defending village and units
        self._process_defending_village(
            battle_result,
            now,
            looted_resources,
            total_defending_units,
            conquered_attack_movement=conquered_attack_movement,
        )

        # Process supporting movements
        self._process_supporting_movements(
            supporting_movements=defending_movements,
            battle_result=battle_result,
            total_defending_units=total_defending_units,
            now=now,
        )
        self.session.flush()

    def _sum_units_from_movements(self, movements: list) -> Units:
        """Sum up all units from a list of movements"""
        total_units = Units()
        for movement in movements:
            total_units = self._add_units(
                total_units, self._movement_to_units(movement)
            )
        return total_units

    def _movement_to_units(self, movement) -> Units:
        """Convert a movement to Units object"""
        return Units(
            archer=movement.archer,
            swordsman=movement.swordsman,
            knight=movement.knight,
            skirmisher=movement.skirmisher,
            nobleman=movement.nobleman,
        )

    def _add_units(self, units1: Units, units2: Units) -> Units:
        """Add two Units objects together"""
        return Units(
            archer=units1.archer + units2.archer,
            swordsman=units1.swordsman + units2.swordsman,
            knight=units1.knight + units2.knight,
            skirmisher=units1.skirmisher + units2.skirmisher,
            nobleman=units1.nobleman + units2.nobleman,
        )

    def _calculate_loot_capacity(self, units: Units) -> int:
        """Calculate the total loot capacity of the units"""
        total = 0
        for unit_name in [
            UnitName.ARCHER,
            UnitName.SWORDSMAN,
            UnitName.KNIGHT,
            UnitName.SKIRMISHER,
            UnitName.NOBLEMAN,
        ]:
            unit_class = UNIT_CLASS_MAP[unit_name]
            unit_count = getattr(units, unit_name.value)
            total += unit_count * unit_class.loot_capacity
        return total

    def _calculate_looted_resources(
        self, resources: Resources, loot_capacity: int
    ) -> Resources:
        """Calculate the resources that can be looted based on capacity"""
        # Calculate looted resources (up to 80% of available resources)
        looted_wood = min(resources.wood * 0.8, int(loot_capacity / 3))
        looted_clay = min(resources.clay * 0.8, int(loot_capacity / 3))
        looted_iron = min(resources.iron * 0.8, int(loot_capacity / 3))

        return Resources(wood=looted_wood, clay=looted_clay, iron=looted_iron)

    def _calculate_unit_loss_ratios(
        self, total_units: Units, lost_units: Units
    ) -> dict[str, float]:
        """Calculate loss ratios for all unit types"""
        return {
            "archer": lost_units.archer / total_units.archer
            if total_units.archer > 0
            else 0,
            "swordsman": lost_units.swordsman / total_units.swordsman
            if total_units.swordsman > 0
            else 0,
            "knight": lost_units.knight / total_units.knight
            if total_units.knight > 0
            else 0,
            "skirmisher": lost_units.skirmisher / total_units.skirmisher
            if total_units.skirmisher > 0
            else 0,
            "nobleman": lost_units.nobleman / total_units.nobleman
            if total_units.nobleman > 0
            else 0,
        }

    def _calculate_lost_units(self, movement, loss_ratios: dict[str, float]) -> Units:
        """Calculate lost units based on loss ratios"""
        return Units(
            archer=round(movement.archer * loss_ratios["archer"]),
            swordsman=round(movement.swordsman * loss_ratios["swordsman"]),
            knight=round(movement.knight * loss_ratios["knight"]),
            skirmisher=round(movement.skirmisher * loss_ratios["skirmisher"]),
            nobleman=round(movement.nobleman * loss_ratios["nobleman"]),
        )

    def _calculate_surviving_units(
        self, movement, loss_ratios: dict[str, float]
    ) -> Units:
        """Calculate surviving units based on loss ratios"""
        return Units(
            archer=round(movement.archer * (1 - loss_ratios["archer"])),
            swordsman=round(movement.swordsman * (1 - loss_ratios["swordsman"])),
            knight=round(movement.knight * (1 - loss_ratios["knight"])),
            skirmisher=round(movement.skirmisher * (1 - loss_ratios["skirmisher"])),
            nobleman=round(movement.nobleman * (1 - loss_ratios["nobleman"])),
        )

    def _create_battle_report(
        self,
        battle_result,
        attacker_village_id,
        defender_village_id,
        own_units,
        own_units_lost,
        own_loot_capacity,
        looted_resources,
        now,
        conquered=False,
    ):
        """Create a battle report for a participant"""
        return BattleResultForMovement(
            attacker_won=battle_result.attacker_won,
            attacking_units=battle_result.attacking_units,
            attacking_units_lost=battle_result.attacking_units_lost,
            defending_units=battle_result.defending_units,
            defending_units_lost=battle_result.defending_units_lost,
            original_loyalty=battle_result.original_loyalty,
            loyalty_damage=battle_result.loyalty_damage,
            luck=battle_result.luck,
            datetime=now,
            loot_capacity=sum(
                [
                    battle_result.attacking_units.archer
                    * UNIT_CLASS_MAP[UnitName.ARCHER].loot_capacity,
                    battle_result.attacking_units.swordsman
                    * UNIT_CLASS_MAP[UnitName.SWORDSMAN].loot_capacity,
                    battle_result.attacking_units.knight
                    * UNIT_CLASS_MAP[UnitName.KNIGHT].loot_capacity,
                    battle_result.attacking_units.skirmisher
                    * UNIT_CLASS_MAP[UnitName.SKIRMISHER].loot_capacity,
                    battle_result.attacking_units.nobleman
                    * UNIT_CLASS_MAP[UnitName.NOBLEMAN].loot_capacity,
                ]
            )
            if battle_result.attacker_won
            else 0,
            looted_wood=looted_resources.wood,
            looted_clay=looted_resources.clay,
            looted_iron=looted_resources.iron,
            attacking_village_id=attacker_village_id,
            defending_village_id=defender_village_id,
            own_units=own_units,
            own_units_lost=own_units_lost,
            own_loot_capacity=own_loot_capacity,
            own_looted_wood=looted_resources.wood if own_loot_capacity > 0 else 0,
            own_looted_clay=looted_resources.clay if own_loot_capacity > 0 else 0,
            own_looted_iron=looted_resources.iron if own_loot_capacity > 0 else 0,
            conquered_village=self.village_manager.village if conquered else None,
        )

    def _send_battle_report(self, player_id, message_text, report_data, now):
        """Send a battle report to a player"""
        if player_id:
            battle_message = models.BattleMessage(
                from_player_id=None,
                to_player_id=player_id,
                message=message_text,
                battle_data=report_data.model_dump_json(),
                created_at=now,
            )
            self.session.add(battle_message)

    def _process_attacking_movements(
        self,
        attacking_movements,
        battle_result,
        total_attacking_units,
        looted_resources,
        now,
        conquered_attack_movement=None,
    ):
        """Process attacking movements after battle"""
        if battle_result.attacker_won:
            # Calculate loss ratios for attacking units
            loss_ratios = self._calculate_unit_loss_ratios(
                total_attacking_units, battle_result.attacking_units_lost
            )

            # Calculate total loot capacity of surviving attackers
            total_loot_capacity = self._calculate_loot_capacity(
                battle_result.attacking_units
            )

            # Process each attack
            for attack in attacking_movements:
                # Calculate lost units for this attack
                lost_units = self._calculate_lost_units(attack, loss_ratios)

                # Calculate surviving units for this attack
                surviving_units = self._calculate_surviving_units(attack, loss_ratios)

                # Update origin village
                origin_village = crud.Village.get(
                    session=self.session, village_id=attack.village_id
                )

                # Reduce original village units by the lost amount
                self._reduce_village_units(origin_village, lost_units)

                # Calculate loot capacity for this attack
                attack_loot_capacity = self._calculate_loot_capacity(surviving_units)

                # Calculate this attack's share of the loot
                attack_resources = Resources()
                if total_loot_capacity > 0:
                    loot_share = attack_loot_capacity / total_loot_capacity
                    attack_resources = Resources(
                        wood=round(looted_resources.wood * loot_share),
                        clay=round(looted_resources.clay * loot_share),
                        iron=round(looted_resources.iron * loot_share),
                    )

                # Update attack movement with surviving units and return resources
                attack.archer = surviving_units.archer
                attack.swordsman = surviving_units.swordsman
                attack.knight = surviving_units.knight
                attack.skirmisher = surviving_units.skirmisher
                attack.nobleman = surviving_units.nobleman
                attack.return_wood = attack_resources.wood
                attack.return_clay = attack_resources.clay
                attack.return_iron = attack_resources.iron

                # Mark as completed if no units survive
                if sum(vars(surviving_units).values()) == 0:
                    attack.completed = True
                else:
                    # Send surviving units back
                    self.village_manager._send_back(attack)

                # Check if this was the conquering movement
                conquered = (
                    conquered_attack_movement == attack
                    if conquered_attack_movement
                    else False
                )

                # Create and send battle report
                attack_report = self._create_battle_report(
                    battle_result=battle_result,
                    attacker_village_id=attack.village_id,
                    defender_village_id=self.village_manager.village.id,
                    own_units=surviving_units,
                    own_units_lost=lost_units,
                    own_loot_capacity=attack_loot_capacity,
                    looted_resources=attack_resources,
                    now=now,
                    conquered=conquered,
                )

                # Add conquest notification
                message_text = (
                    "Battle Report: Attack on " + f"{self.village_manager.village.name}"
                )
                if conquered:
                    message_text = f"CONQUEST: You have conquered {self.village_manager.village.name}!"

                self._send_battle_report(
                    player_id=origin_village.player_id,
                    message_text=message_text,
                    report_data=attack_report,
                    now=now,
                )

                self.session.add(origin_village)
                self.session.add(attack)
        else:
            # Defenders won - all attacking units are lost
            for attack in attacking_movements:
                # Get origin village
                origin_village = crud.Village.get(
                    session=self.session, village_id=attack.village_id
                )

                # All units are lost
                lost_units = self._movement_to_units(attack)
                self._reduce_village_units(origin_village, lost_units)

                # Mark attack as completed
                attack.completed = True

                # Create and send battle report
                attack_report = self._create_battle_report(
                    battle_result=battle_result,
                    attacker_village_id=attack.village_id,
                    defender_village_id=self.village_manager.village.id,
                    own_units=Units(
                        archer=0, swordsman=0, knight=0, skirmisher=0, nobleman=0
                    ),
                    own_units_lost=lost_units,
                    own_loot_capacity=0,
                    looted_resources=Resources(),
                    now=now,
                )

                self._send_battle_report(
                    player_id=origin_village.player_id,
                    message_text="Battle Report: Attack on "
                    f"{self.village_manager.village.name}",
                    report_data=attack_report,
                    now=now,
                )

                self.session.add(origin_village)
                self.session.add(attack)

    def _process_defending_village(
        self,
        battle_result,
        now,
        looted_resources,
        total_defending_units,
        conquered_attack_movement: models.UnitMovement | None = None,
    ):
        """Process the defending village after battle"""
        # Update the defending village's units
        target_village = self.village_manager.village

        # Check if there were any losses to defenders
        if sum(vars(battle_result.defending_units_lost).values()) > 0:
            # Get available units in the target village
            available_units = self.village_manager.get_available_units()

            # Calculate loss ratios
            loss_ratios = self._calculate_unit_loss_ratios(
                total_defending_units, battle_result.defending_units_lost
            )

            # Calculate lost units for village's own units
            lost_units = Units(
                archer=round(available_units.archer * loss_ratios["archer"]),
                swordsman=round(available_units.swordsman * loss_ratios["swordsman"]),
                knight=round(available_units.knight * loss_ratios["knight"]),
                skirmisher=round(
                    available_units.skirmisher * loss_ratios["skirmisher"]
                ),
                nobleman=round(available_units.nobleman * loss_ratios["nobleman"]),
            )

            # Apply losses
            self._reduce_village_units(target_village, lost_units)

        # Add conquest information to battle result
        battle_message = "Your village was successfully defended"
        conquered_by_player = None
        conquered_by_village = None
        if conquered_attack_movement:
            battle_message = f"Your village {target_village.name} was conquered!"
            conquered_by_player = conquered_attack_movement.origin_village.player
            conquered_by_village = conquered_attack_movement.origin_village

        # Send battle report to the defender
        if target_village.player_id:
            defender_report = BattleReport(
                attacker_won=battle_result.attacker_won,
                attacking_units=battle_result.attacking_units,
                attacking_units_lost=battle_result.attacking_units_lost,
                defending_units=battle_result.defending_units,
                defending_units_lost=battle_result.defending_units_lost,
                original_loyalty=battle_result.original_loyalty,
                loyalty_damage=battle_result.loyalty_damage,
                luck=battle_result.luck,
                datetime=now,
                loot_capacity=self._calculate_loot_capacity(
                    battle_result.attacking_units
                )
                if battle_result.attacker_won
                else 0,
                looted_wood=looted_resources.wood,
                looted_clay=looted_resources.clay,
                looted_iron=looted_resources.iron,
                conquered_by_player=conquered_by_player,
                conquered_village=conquered_by_village,
            )

            self._send_battle_report(
                player_id=target_village.player_id,
                message_text=battle_message,
                report_data=defender_report,
                now=now,
            )

        self.session.add(target_village)

    def _process_supporting_movements(
        self, supporting_movements, battle_result, total_defending_units, now
    ):
        """Process supporting movements after battle"""
        # Check if there were any losses to defenders
        if sum(vars(battle_result.defending_units_lost).values()) > 0:
            # Calculate loss ratios
            loss_ratios = self._calculate_unit_loss_ratios(
                total_defending_units, battle_result.defending_units_lost
            )

            # Process each support
            for support in supporting_movements:
                # Calculate lost units for this support
                lost_units = self._calculate_lost_units(support, loss_ratios)

                # Update support unit counts
                support.archer -= lost_units.archer
                support.swordsman -= lost_units.swordsman
                support.knight -= lost_units.knight
                support.skirmisher -= lost_units.skirmisher
                support.nobleman -= lost_units.nobleman

                # Mark as completed if all units are dead
                if (
                    sum(
                        [
                            support.archer,
                            support.swordsman,
                            support.knight,
                            support.skirmisher,
                            support.nobleman,
                        ]
                    )
                    == 0
                ):
                    support.completed = True

                # Update origin village
                origin_village = crud.Village.get(
                    session=self.session, village_id=support.village_id
                )

                self._reduce_village_units(origin_village, lost_units)

                # Create and send battle report to supporting player
                if origin_village.player_id:
                    surviving_units = Units(
                        archer=support.archer,
                        swordsman=support.swordsman,
                        knight=support.knight,
                        skirmisher=support.skirmisher,
                        nobleman=support.nobleman,
                    )

                    support_report = self._create_battle_report(
                        battle_result=battle_result,
                        attacker_village_id=0,  # Not applicable for support
                        defender_village_id=self.village_manager.village.id,
                        own_units=surviving_units,
                        own_units_lost=lost_units,
                        own_loot_capacity=0,
                        looted_resources=Resources(),
                        now=now,
                    )

                    self._send_battle_report(
                        player_id=origin_village.player_id,
                        message_text=f"Battle Report: Your supporting units in {self.village_manager.village.name}",
                        report_data=support_report,
                        now=now,
                    )

                self.session.add(origin_village)
                self.session.add(support)

    def _reduce_village_units(self, village, lost_units: Units) -> None:
        """Reduce village units by the lost amount"""
        village.archer = max(0, village.archer - lost_units.archer)
        village.swordsman = max(0, village.swordsman - lost_units.swordsman)
        village.knight = max(0, village.knight - lost_units.knight)
        village.skirmisher = max(0, village.skirmisher - lost_units.skirmisher)
        village.nobleman = max(0, village.nobleman - lost_units.nobleman)

    @staticmethod
    def _resolve_combat(attack: float, defense: float) -> tuple[float, float]:
        """
        Resolve a combat encounter between attacking and defending forces.

        Args:
            attack: The total attack power
            defense: The total defense power

        Returns:
            tuple: (attacker_loss_ratio, defender_loss_ratio)
        """
        attacker_losses = 0
        defender_losses = 0

        if attack > 0:
            if attack > defense:
                # Attacker wins combat
                # Calculate loss coefficient
                loss_coefficient = (defense / attack) * sqrt(defense / attack)

                # Attacker loses a percentage of units
                attacker_losses = loss_coefficient

                # Defender loses all units engaged in defense
                defender_losses = 1.0
            elif defense > attack:
                # Defender wins combat
                # Calculate loss coefficient
                loss_coefficient = (attack / defense) * sqrt(attack / defense)

                # Defender loses a percentage of units
                defender_losses = loss_coefficient

                # Attacker loses all units
                attacker_losses = 1.0
            else:
                # Equal strength, both sides lose all units
                attacker_losses = 1.0
                defender_losses = 1.0

        return attacker_losses, defender_losses

    @staticmethod
    def calculate_battle_result(
        attacking_units: Units,
        defending_units: Units,
        luck: float = 0.0,
    ) -> BattleResultBase:
        """
        Calculate battle result using the battle algorithm.

        Args:
            attacking_units: Units in the attacking army
            defending_units: Units in the defending army
            luck: Luck factor (-0.25 to 0.25) that affects attacker's power

        Returns:
            BattleResultBase object with battle outcome
        """

        # Make a copy of the units to track losses
        attacking_units_new = Units(
            archer=attacking_units.archer,
            swordsman=attacking_units.swordsman,
            knight=attacking_units.knight,
            skirmisher=attacking_units.skirmisher,
            nobleman=attacking_units.nobleman,
        )

        defending_units_new = Units(
            archer=defending_units.archer,
            swordsman=defending_units.swordsman,
            knight=defending_units.knight,
            skirmisher=defending_units.skirmisher,
            nobleman=defending_units.nobleman,
        )

        # Initialize the battle rounds
        attacker_has_units = True
        defender_has_units = True

        # Simulate battle until one side has no units left
        while attacker_has_units and defender_has_units:
            # Calculate total attack power and percentages by unit type (Melee/Ranged)
            melee_attack, ranged_attack = 0, 0

            # Calculate attack power by type
            for unit_name, unit_class in UNIT_CLASS_MAP.items():
                unit_count = getattr(attacking_units_new, unit_name.value)
                if unit_count > 0:
                    if unit_class.unit_type == UnitType.MELEE:
                        melee_attack += unit_count * unit_class.attack
                    elif unit_class.unit_type == UnitType.RANGED:
                        ranged_attack += unit_count * unit_class.attack

            # Apply luck factor to attacker's power
            melee_attack *= 1 + luck
            ranged_attack *= 1 + luck

            # Calculate attack percentages
            total_attack = melee_attack + ranged_attack
            if total_attack <= 0:
                # Attacker has no attacking power, defender wins
                attacker_has_units = False
                break

            melee_attack_percentage = (
                melee_attack / total_attack if total_attack > 0 else 0
            )
            ranged_attack_percentage = (
                ranged_attack / total_attack if total_attack > 0 else 0
            )

            # Split defense according to attack composition
            melee_defense, ranged_defense = 0, 0

            # Calculate defending units' defensive power
            split_defense_units = {}
            for unit_name, unit_class in UNIT_CLASS_MAP.items():
                unit_count = getattr(defending_units_new, unit_name.value)
                if unit_count > 0:
                    # Split units proportionally based on attack composition
                    melee_defense_units = unit_count * melee_attack_percentage
                    ranged_defense_units = unit_count * ranged_attack_percentage

                    # Calculate defense values
                    melee_defense += melee_defense_units * unit_class.defense_melee
                    ranged_defense += ranged_defense_units * unit_class.defense_ranged

                    # Store the split for loss calculation
                    split_defense_units[unit_name] = {
                        "melee": melee_defense_units,
                        "ranged": ranged_defense_units,
                    }

            # Use the common function to resolve combat
            melee_losses_attacker, melee_losses_defender = (
                AttackResolver._resolve_combat(melee_attack, melee_defense)
            )

            ranged_losses_attacker, ranged_losses_defender = (
                AttackResolver._resolve_combat(ranged_attack, ranged_defense)
            )

            # Apply losses to attacking units
            for unit_name, unit_class in UNIT_CLASS_MAP.items():
                unit_count = getattr(attacking_units_new, unit_name.value)
                if unit_count > 0:
                    if unit_class.unit_type == UnitType.MELEE:
                        losses = unit_count * melee_losses_attacker
                    elif unit_class.unit_type == UnitType.RANGED:
                        losses = unit_count * ranged_losses_attacker
                    else:
                        losses = 0
                    losses = round(losses)
                    setattr(
                        attacking_units_new,
                        unit_name.value,
                        max(0, unit_count - losses),
                    )

            # Apply losses to defending units
            for unit_name, split in split_defense_units.items():
                unit_count = getattr(defending_units_new, unit_name.value)
                if unit_count > 0:
                    melee_losses = split["melee"] * melee_losses_defender
                    ranged_losses = split["ranged"] * ranged_losses_defender
                    total_losses = round(min(unit_count, melee_losses + ranged_losses))

                    setattr(
                        defending_units_new,
                        unit_name.value,
                        max(0, unit_count - total_losses),
                    )

            # Check if either side has no units left
            attacker_has_units = sum(vars(attacking_units_new).values()) > 0
            defender_has_units = sum(vars(defending_units_new).values()) > 0

        # Calculate lost units
        attacking_units_lost = Units(
            archer=attacking_units.archer - attacking_units_new.archer,
            swordsman=attacking_units.swordsman - attacking_units_new.swordsman,
            knight=attacking_units.knight - attacking_units_new.knight,
            skirmisher=attacking_units.skirmisher - attacking_units_new.skirmisher,
            nobleman=attacking_units.nobleman - attacking_units_new.nobleman,
        )

        defending_units_lost = Units(
            archer=defending_units.archer - defending_units_new.archer,
            swordsman=defending_units.swordsman - defending_units_new.swordsman,
            knight=defending_units.knight - defending_units_new.knight,
            skirmisher=defending_units.skirmisher - defending_units_new.skirmisher,
            nobleman=defending_units.nobleman - defending_units_new.nobleman,
        )

        # Determine overall battle result
        attacker_won = attacker_has_units and not defender_has_units

        # Return the battle result
        return BattleResultBase(
            attacker_won=attacker_won,
            attacking_units=attacking_units_new,
            attacking_units_lost=attacking_units_lost,
            defending_units=defending_units_new,
            defending_units_lost=defending_units_lost,
            original_loyalty=100.0,  # Default value, will be updated by resolver
            luck=luck,
        )
