import logging
from abc import ABC, abstractmethod
from enum import Enum

from app.core.config import settings
from app.game.units import Unit

logger = logging.getLogger(__name__)


class BuildingType(str, Enum):
    HEADQUARTERS = "headquarters"
    WOODCUTTER = "woodcutter"
    CLAY_PIT = "clay_pit"
    IRON_MINE = "iron_mine"
    FARM = "farm"
    STORAGE = "storage"
    BARRACKS = "barracks"


class Building(ABC):
    """Base class for all buildings"""

    max_level: int = 30  # Default max level for all buildings
    buildtime_lvl_multiplier = 1.25
    population_cost_multiplier = 1.17

    def __init__(self, level: int = 0):
        self.level = level

    @property
    def wood_cost(self) -> int:
        """Returns wood cost for the current level"""
        return int(self.base_wood_cost * (self.buildtime_lvl_multiplier**self.level))

    @property
    def clay_cost(self) -> int:
        """Returns clay cost for the current level"""
        return int(self.base_clay_cost * (self.buildtime_lvl_multiplier**self.level))

    @property
    def iron_cost(self) -> int:
        """Returns iron cost for the current level"""
        return int(self.base_iron_cost * (self.buildtime_lvl_multiplier**self.level))

    @property
    def build_time(self) -> int:
        """Returns build time in milliseconds"""
        return int(self.base_build_time * (self.buildtime_lvl_multiplier**self.level))

    @property
    def population(self) -> int:
        """Returns population usage"""
        if self.level == 0:
            return 0
        return int(
            self.base_population * (self.population_cost_multiplier ** (self.level - 1))
        )

    @property
    @abstractmethod
    def level_db_name(self) -> str:
        """Returns the database field name for the building level"""
        pass

    @property
    @abstractmethod
    def _base_build_time(self) -> int:
        """Returns the base build time in milliseconds (unaffected by game speed)"""
        pass

    @property
    def base_build_time(self) -> int:
        """Returns the base build time in milliseconds adjusted by game speed"""
        return int(self._base_build_time / settings.GAME_SPEED)

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
    def base_population(self) -> int:
        """Returns the base population cost"""
        pass


class ProductionBuilding(Building):
    """Base class for resource production buildings"""

    def __init__(self, level: int = 1):
        if level < 1:
            logger.error("Production building level got below 1")
            level = 1
        self.production_multiplier = 1.17  # Production multiplier per level
        self._base_production = 30
        super().__init__(level)

    @property
    @abstractmethod
    def resource(self) -> str | None:
        """Returns the resource type this building produces"""
        pass

    @property
    @abstractmethod
    def last_update_db_name(self) -> str | None:
        """Returns the database field name for the last update timestamp"""
        pass

    @property
    def base_production(self) -> float:
        """Returns the base production adjusted by game speed"""
        return self._base_production * settings.GAME_SPEED

    @property
    def production_rate(self) -> float:
        """Returns production rate per hour"""
        return self.base_production * (self.production_multiplier ** (self.level - 1))

    @property
    def production_rate_ms(self) -> int:
        """Returns milliseconds needed for 1 resource"""
        if self.level == 0:
            return 0
        resources_per_ms = self.production_rate / 3600000  # Convert to resources per ms
        if resources_per_ms <= 0:
            return 0
        return int(1 / resources_per_ms)  # ms needed for 1 resource


class Headquarters(Building):
    level_db_name = "headquarters_lvl"
    _base_build_time = 1000 * 60 * 5  # 5 minutes
    base_wood_cost = 95
    base_clay_cost = 85
    base_iron_cost = 75
    base_population = 5

    def __init__(self, level: int = 1):
        super().__init__(level)

    @property
    def build_time_reduction_factor(self) -> float:
        """
        Returns a factor by which building times are reduced.

        Provides a 2.5% reduction per level starting from level 2.
        Level 1: 1.0 (0% reduction)
        Level 2: 0.975 (2.5% reduction)
        Level 3: 0.95 (5% reduction)
        And so on...
        """
        if self.level <= 1:
            return 1.0

        # 2.5% reduction per level starting from level 2
        reduction = (self.level - 1) * 0.025
        if reduction > 0.95:
            reduction = 0.95  # Cap the reduction to 95%

        return 1.0 - reduction


class Woodcutter(ProductionBuilding):
    level_db_name = "woodcutter_lvl"
    _base_build_time = 1000 * 60 * 4  # 4 minutes
    base_wood_cost = 60
    base_clay_cost = 60
    base_iron_cost = 45
    base_population = 3

    resource = "wood"
    last_update_db_name = "last_wood_update"

    def __init__(self, level: int = 1):
        super().__init__(level)


class ClayPit(ProductionBuilding):
    level_db_name = "clay_pit_lvl"
    _base_build_time = 1000 * 60 * 4  # 4 minutes
    base_wood_cost = 70
    base_clay_cost = 50
    base_iron_cost = 45
    base_population = 3

    resource = "clay"
    last_update_db_name = "last_clay_update"

    def __init__(self, level: int = 1):
        super().__init__(level)


class IronMine(ProductionBuilding):
    level_db_name = "iron_mine_lvl"
    _base_build_time = 1000 * 60 * 5  # 5 minutes
    base_wood_cost = 65
    base_clay_cost = 60
    base_iron_cost = 40
    base_population = 3

    resource = "iron"
    last_update_db_name = "last_iron_update"

    def __init__(self, level: int = 1):
        super().__init__(level)


class Farm(Building):
    """Farm building for increasing population capacity"""

    level_db_name = "farm_lvl"
    _base_build_time = 1000 * 60 * 5  # 5 minutes
    base_wood_cost = 45
    base_clay_cost = 55
    base_iron_cost = 35
    base_population = 0  # Farm doesn't consume population

    base_max_population = 260
    population_multiplier = 1.17

    def __init__(self, level: int = 1):
        super().__init__(level)

    @property
    def max_population(self) -> int:
        """Returns the maximum population this farm can support"""
        return int(
            self.base_max_population * (self.population_multiplier ** (self.level - 1))
        )


class Storage(Building):
    """Storage building for increasing resource capacity"""

    level_db_name = "storage_lvl"
    _base_build_time = 1000 * 60 * 4  # 4 minutes
    base_wood_cost = 55
    base_clay_cost = 65
    base_iron_cost = 45
    base_population = 2

    base_capacity = 1200
    capacity_multiplier = 1.24

    def __init__(self, level: int = 1):
        super().__init__(level)

    @property
    def max_capacity(self) -> int:
        """Returns the maximum resource capacity this storage can hold"""
        return int(self.base_capacity * (self.capacity_multiplier ** (self.level - 1)))


class Barracks(Building):
    """Barracks building for training military units"""

    level_db_name = "barracks_lvl"
    _base_build_time = 1000 * 60 * 6
    base_wood_cost = 55
    base_clay_cost = 65
    base_iron_cost = 50
    base_population = 4

    training_reduction_per_level = 0.025  # 2.5% reduction per level
    queue_size_base = 10
    queue_per_level = 1

    def __init__(self, level: int = 0):
        super().__init__(level)

    @property
    def training_speed_factor(self) -> float:
        """
        Returns a factor by which unit training times are reduced.
        Provides a 2.5% reduction per level starting from level 1.
        Level 1: 1.0 (0% reduction)
        Level 2: 0.975 (2.5% reduction)
        Level 3: 0.95 (5% reduction)
        And so on...
        """
        if self.level <= 0:
            return 1.0

        reduction = (self.level - 1) * self.training_reduction_per_level
        if reduction > 0.95:
            reduction = 0.95  # Cap the reduction to 95%

        return 1.0 - reduction

    @property
    def max_queue_size(self) -> int:
        """
        Returns the maximum number of units that can be queued for training.
        This prevents the players to use the barracks as a hideout of resources.
        """
        return self.queue_size_base + (self.queue_per_level * (self.level - 1))

    def get_training_time(self, unit: Unit) -> int:
        """
        Returns the training time for a specific unit type in milliseconds.
        """
        return int(unit.base_training_time * self.training_speed_factor)


BUILDING_CLASS_MAP: dict[BuildingType, type[Building]] = {
    BuildingType.HEADQUARTERS: Headquarters,
    BuildingType.WOODCUTTER: Woodcutter,
    BuildingType.CLAY_PIT: ClayPit,
    BuildingType.IRON_MINE: IronMine,
    BuildingType.FARM: Farm,
    BuildingType.STORAGE: Storage,
    BuildingType.BARRACKS: Barracks,
}
