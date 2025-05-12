import logging
from abc import ABC, abstractmethod
from enum import Enum

from app.core.config import settings

logger = logging.getLogger(__name__)


class UnitType(str, Enum):
    RANGED = "ranged"
    MELEE = "melee"
    SPY = "spy"


class UnitName(str, Enum):
    ARCHER = "archer"
    SWORDSMAN = "swordsman"
    KNIGHT = "knight"
    SKIRMISHER = "skirmisher"
    NOBLEMAN = "nobleman"


class Unit(ABC):
    """Base class for all units"""

    population: int = 1  # Default population cost for all units

    @property
    @abstractmethod
    def unit_type(self) -> UnitType:
        """Returns the type of unit (ranged or melee)"""
        pass

    @property
    @abstractmethod
    def name(self) -> UnitName:
        """Returns the name of the unit"""
        pass

    @property
    @abstractmethod
    def _base_training_time(self) -> int:
        """Returns the base training time in milliseconds (unaffected by game speed)"""
        pass

    @property
    def base_training_time(self) -> int:
        """Returns the base training time in milliseconds adjusted by game speed"""
        return int(self._base_training_time / settings.GAME_SPEED)

    @property
    @abstractmethod
    def base_wood_cost(self) -> int:
        """Returns the base wood cost"""
        pass

    @property
    @abstractmethod
    def base_clay_cost(self) -> int:
        """Returns the base clay cost"""
        pass

    @property
    @abstractmethod
    def base_iron_cost(self) -> int:
        """Returns the base iron cost"""
        pass

    @property
    @abstractmethod
    def attack(self) -> int:
        """Returns the attack power of the unit"""
        pass

    @property
    @abstractmethod
    def _speed(self) -> int:
        """Returns the speed of the unit in milliseconds per tile (unaffected by game speed)"""
        pass

    @property
    def speed(self) -> int:
        """Returns the speed of the unit in milliseconds per tile adjusted by game speed"""
        return int(self._speed / settings.GAME_SPEED)

    @property
    @abstractmethod
    def loot_capacity(self) -> int:
        """Returns the amount of resources the unit can carry"""
        pass

    @property
    @abstractmethod
    def defense_ranged(self) -> int:
        """Returns the defense against ranged attacks"""
        pass

    @property
    @abstractmethod
    def defense_melee(self) -> int:
        """Returns the defense against melee attacks"""
        pass


class Swordsman(Unit):
    """Swordsman unit - standard melee unit"""

    unit_type = UnitType.MELEE
    name = UnitName.SWORDSMAN
    _base_training_time = 1000 * 60 * 6  # 6 minutes
    base_wood_cost = 45
    base_clay_cost = 35
    base_iron_cost = 65
    attack = 20
    _speed = 1000 * 60 * 20  # 20 minutes per tile
    loot_capacity = 20
    defense_ranged = 8
    defense_melee = 9


class Archer(Unit):
    """Archer unit - standard ranged unit"""

    unit_type = UnitType.RANGED
    name = UnitName.ARCHER
    _base_training_time = int(1000 * 60 * 6.5)  # 6.5 minutes
    base_wood_cost = 75
    base_clay_cost = 30
    base_iron_cost = 45
    attack = 23
    _speed = 1000 * 60 * 18  # 18 minutes per tile
    loot_capacity = 15
    defense_ranged = 7
    defense_melee = 8


class Knight(Unit):
    """Knight unit - anti-melee specialist"""

    unit_type = UnitType.MELEE
    name = UnitName.KNIGHT
    _base_training_time = int(1000 * 60 * 6.8)  # 6.8 minutes
    base_wood_cost = 35
    base_clay_cost = 35
    base_iron_cost = 75
    attack = 10
    _speed = 1000 * 60 * 20  # 20 minutes per tile
    loot_capacity = 25
    defense_ranged = 13
    defense_melee = 28  # Strong against melee


class Skirmisher(Unit):
    """Skirmisher unit - anti-ranged specialist"""

    unit_type = UnitType.MELEE
    name = UnitName.SKIRMISHER
    _base_training_time = int(1000 * 60 * 6.2)  # 6.2 minutes
    base_wood_cost = 75
    base_clay_cost = 30
    base_iron_cost = 40
    attack = 8
    _speed = 1000 * 60 * 18  # 18 minutes per tile
    loot_capacity = 25
    defense_ranged = 30  # Strong against ranged
    defense_melee = 10


class Nobleman(Unit):
    """Nobleman unit - used to conquer villages"""

    unit_type = UnitType.MELEE
    name = UnitName.NOBLEMAN
    _base_training_time = 1000 * 60 * 60  # 1 hour
    base_wood_cost = 50000
    base_clay_cost = 50000
    base_iron_cost = 50000
    attack = 50
    _speed = 1000 * 60 * 30
    loot_capacity = 0
    defense_ranged = 50
    defense_melee = 50
    population = 100


# Map of unit names to their classes
UNIT_CLASS_MAP: dict[UnitName, type[Unit]] = {
    UnitName.ARCHER: Archer,
    UnitName.SWORDSMAN: Swordsman,
    UnitName.KNIGHT: Knight,
    UnitName.SKIRMISHER: Skirmisher,
    UnitName.NOBLEMAN: Nobleman,
}
