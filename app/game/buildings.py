import logging
from abc import ABC, abstractmethod
from enum import Enum

logger = logging.getLogger(__name__)


class BuildingType(str, Enum):
    HEADQUARTERS = "headquarters"
    WOODCUTTER = "woodcutter"
    CLAY_PIT = "clay_pit"
    IRON_MINE = "iron_mine"
    FARM = "farm"
    STORAGE = "storage"


class Building(ABC):
    """Base class for all buildings"""

    def __init__(self, level: int = 0):
        self.level = level
        self.buildtime_lvl_multiplier = 1.25
        self.max_level = 30
        self.population_cost_multiplier = 1.17

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
    def base_build_time(self) -> int:
        """Returns the base build time in milliseconds"""
        pass

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
        self.base_production = 30
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
    base_build_time = 1000 * 60 * 5  # 5 minutes
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
        if reduction > 1.0:
            reduction = 0.95  # Cap the reduction to 95%

        return 1.0 - reduction


class Woodcutter(ProductionBuilding):
    level_db_name = "woodcutter_lvl"
    base_build_time = 1000 * 60 * 4  # 4 minutes
    base_wood_cost = 65
    base_clay_cost = 55
    base_iron_cost = 45
    base_population = 3

    resource = "wood"
    last_update_db_name = "last_wood_update"

    def __init__(self, level: int = 1):
        super().__init__(level)


class ClayPit(ProductionBuilding):
    level_db_name = "clay_pit_lvl"
    base_build_time = 1000 * 60 * 4  # 4 minutes
    base_wood_cost = 70
    base_clay_cost = 55
    base_iron_cost = 45
    base_population = 3

    resource = "clay"
    last_update_db_name = "last_clay_update"

    def __init__(self, level: int = 1):
        super().__init__(level)


class IronMine(ProductionBuilding):
    level_db_name = "iron_mine_lvl"
    base_build_time = 1000 * 60 * 5  # 5 minutes
    base_wood_cost = 70
    base_clay_cost = 55
    base_iron_cost = 40
    base_population = 3

    resource = "iron"
    last_update_db_name = "last_iron_update"

    def __init__(self, level: int = 1):
        super().__init__(level)
        self.base_wood_cost = 70
        self.base_clay_cost = 55
        self.base_iron_cost = 40
        self.base_build_time = 1000 * 60 * 5  # 5 minutes
        self.base_population = 3


class Farm(Building):
    """Farm building for increasing population capacity"""

    level_db_name = "farm_lvl"
    base_build_time = 1000 * 60 * 5  # 5 minutes
    base_wood_cost = 55
    base_clay_cost = 45
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
    base_build_time = 1000 * 60 * 4  # 4 minutes
    base_wood_cost = 65
    base_clay_cost = 55
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


BUILDING_CLASS_MAP: dict[BuildingType, type[Building]] = {
    BuildingType.HEADQUARTERS: Headquarters,
    BuildingType.WOODCUTTER: Woodcutter,
    BuildingType.CLAY_PIT: ClayPit,
    BuildingType.IRON_MINE: IronMine,
    BuildingType.FARM: Farm,
    BuildingType.STORAGE: Storage,
}
