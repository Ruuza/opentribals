import matplotlib.pyplot as plt

from app.game.world import WorldManager


def test_generate_and_plot_villages(session):
    """
    Generate 1000 villages and visualize their distribution.
    This test is used to validate the spatial distribution algorithm.
    """
    world = WorldManager()

    village_count = 1000
    x_coords = []
    y_coords = []

    # Track coordinates to avoid duplicates
    coordinates = {}

    # Track progress
    print(f"Generating {village_count} villages...")

    # Generate villages
    for _ in range(village_count):
        # Create village
        village = world.spawn_village(session, player_id=None)

        # Store coordinates
        x_coords.append(village.x)
        y_coords.append(village.y)

        # Check for duplicates
        coord_key = (village.x, village.y)
        if coord_key in coordinates:
            raise AssertionError(f"Duplicate village at coordinates {coord_key}")
        coordinates[coord_key] = True

    # Create a scatter plot
    plt.figure(figsize=(10, 10))

    # Plot villages
    plt.scatter(x_coords, y_coords, alpha=0.6, s=10)

    # Add grid and center marker
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.axhline(y=world.world_center, color="r", linestyle="-", alpha=0.3)
    plt.axvline(x=world.world_center, color="r", linestyle="-", alpha=0.3)

    plt.scatter(
        [world.world_center],
        [world.world_center],
        color="red",
        s=100,
        marker="*",
        label="World Center",
    )

    plt.xlim(450, 550)
    plt.ylim(450, 550)

    plt.title(f"Distribution of {village_count} Villages in the Game World")
    plt.xlabel("X Coordinate")
    plt.ylabel("Y Coordinate")
    plt.legend()

    # Save the plot
    output_path = "village_distribution.png"
    plt.savefig(output_path)
    print(f"Plot saved to {output_path}")

    plt.close()

    assert len(x_coords) == village_count
    assert all(0 <= x < world.world_size for x in x_coords)
    assert all(0 <= y < world.world_size for y in y_coords)
