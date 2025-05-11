import math
import random
import uuid

from sqlmodel import Session, func, select

from app import crud, models


class WorldManager:
    """Class for managing the game world and spawning logic"""

    def __init__(self) -> None:
        """
        Initialize world manager with a positive coordinate system
        """
        self.world_size = 1000  # World size (0 to 999)
        self.world_center = self.world_size // 2  # Center point of the world
        self.initial_radius = 5  # Initial radius for first players
        self.radius_offset = 5  # Radius offset for each ring
        self.coverage_percent = (
            0.25  # When 25% of spots in a ring are filled, move to next ring
        )

    def _generate_random_position(
        self, min_radius: int, max_radius: int
    ) -> tuple[int, int]:
        """
        Generate a random position within the specified radius range.

        Args:
            min_radius (int): The minimum radius from the center.
            max_radius (int): The maximum radius from the center.

        Returns:
            Tuple[int, int]: A tuple containing the x and y coordinates of the random
                position.
        """
        angle = random.random() * 2 * math.pi
        radius = random.randint(min_radius, max_radius)
        x = int(self.world_center + radius * math.cos(angle))
        y = int(self.world_center + radius * math.sin(angle))
        return x, y

    def get_spawn_position(self, session: Session) -> tuple[int, int]:
        """
        Get a position for a new village based on current world state.
        Uses a simple ring-based approach with percent coverage.
        """
        current_radius = self._determine_current_radius(session)

        # Try to find an open spot in the current ring
        for extra_offset in range(0, 10):
            for _ in range(50):
                x, y = self._generate_random_position(
                    current_radius - self.radius_offset + extra_offset,
                    current_radius + self.radius_offset + extra_offset,
                )
                if self._is_position_valid(session, x, y):
                    return x, y

        raise ValueError("Could not find a valid spawn position!")

    def _determine_current_radius(self, session: Session) -> int:
        """
        Determine the radius to use for the next village based on the current
        world state.
        The goal is to have a 25% coverage rate for villages in the world.

        This means solving for r in: villages_count / (πr²) = 0.25
        Which gives us: r = 2 * √(villages_count / π)

        Returns:
            int: The radius to use for the next village
        """
        # Get the number of villages in the world
        villages_count = session.exec(select(func.count(models.Village.id))).one()

        if villages_count == 0:
            return self.initial_radius

        calculated_radius = 2 * math.sqrt(villages_count / math.pi)

        # Ensure minimum radius and round to integer
        current_radius = max(int(calculated_radius), self.initial_radius)

        return current_radius

    def _is_position_valid(self, session: Session, x: int, y: int) -> bool:
        """
        Check if a position is valid for a new village:
        - Must be within world bounds
        - No existing village at exact position
        """
        if x < 0 or x >= self.world_size or y < 0 or y >= self.world_size:
            return False
        does_village_exist = session.exec(
            select(models.Village)
            .where(models.Village.x == x)
            .where(models.Village.y == y)
        ).first()

        return does_village_exist is None

    def spawn_village(
        self, session: Session, player_id: uuid.UUID | None
    ) -> models.Village:
        """
        Spawn a new village in the world. If player_id is None, the village is
        considered as a barbarian village.
        """
        # Get spawn position
        x, y = self.get_spawn_position(session)

        # Create the village
        village = crud.Village.create(
            session=session,
            name="Village" if player_id else "Abandoned Village",
            x=x,
            y=y,
            player_id=player_id,
            # increase production rates for barbarian villages
            woodcutter_lvl=10 if player_id is None else 1,
            clay_pit_lvl=10 if player_id is None else 1,
            iron_mine_lvl=10 if player_id is None else 1,
        )
        return village
