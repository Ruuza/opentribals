import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud, models
from app.core.config import settings


@pytest.fixture
def world_player(session: Session, test_player: models.User) -> models.Player:
    """A player that has already joined the world with a village"""
    # Create a test village for the player
    crud.Village.create(
        session=session, name="Player Village", x=300, y=300, player_id=test_player.id
    )
    return test_player


@pytest.fixture
def extra_players(session: Session) -> list[models.Player]:
    """Create multiple players for testing pagination and filtering"""
    players = []
    for i in range(3):
        player_id = uuid.uuid4()
        player = models.Player(id=player_id, username=f"test_player_{i}")
        session.add(player)
        session.commit()

        # Create 2 villages for each player
        for j in range(2):
            crud.Village.create(
                session=session,
                name=f"Village {i}-{j}",
                x=400 + i * 10,
                y=400 + j * 10,
                player_id=player_id,
            )
        players.append(player)
    return players


def test_join_world(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Test joining the world as a new player"""
    response = client.post(
        f"{settings.API_V1_STR}/world/join", headers=normal_user_token_headers
    )
    assert response.status_code == 200

    # Check response structure
    data = response.json()
    assert "id" in data
    assert "username" in data
    assert "villages" in data
    assert "villages_count" in data
    assert len(data["villages"]) == 1
    assert data["villages_count"] == 1

    # Check village data
    village = data["villages"][0]
    assert "id" in village
    assert "name" in village
    assert "x" in village
    assert "y" in village


def test_join_world_already_joined(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    world_player: models.Player,  # noqa: ARG001
) -> None:
    """Test that a user cannot join the world twice"""
    response = client.post(
        f"{settings.API_V1_STR}/world/join", headers=normal_user_token_headers
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "You have already joined the world"


def test_join_world_not_authenticated(client: TestClient) -> None:
    """Test that an unauthenticated user cannot join the world"""
    response = client.post(f"{settings.API_V1_STR}/world/join")
    assert response.status_code == 401


def test_get_all_players(
    client: TestClient,
    world_player: models.Player,  # noqa: ARG001
    extra_players: list[models.Player],  # noqa: ARG001
) -> None:
    """Test getting all players with their villages"""
    # Using the fixtures to ensure test data is created
    response = client.get(f"{settings.API_V1_STR}/world/players")
    assert response.status_code == 200

    # Check response structure
    data = response.json()
    # Should contain our world_player and the 3 extra players
    assert len(data) == 4

    # Check that each player has the expected structure
    for player in data:
        assert "id" in player
        assert "username" in player
        assert "villages" in player
        assert "villages_count" in player

        # All extra players have 2 villages, the world_player has 1
        if player["username"].startswith("test_player_"):
            assert player["villages_count"] == 2
            assert len(player["villages"]) == 2
        else:
            assert player["villages_count"] == 1
            assert len(player["villages"]) == 1

        # Check village data
        for village in player["villages"]:
            assert "id" in village
            assert "name" in village
            assert "x" in village
            assert "y" in village


def test_get_players_with_pagination(
    client: TestClient,
    world_player: models.Player,  # Need the fixture for test data   # noqa: ARG001
    extra_players: list[  # noqa: ARG001
        models.Player
    ],  # Need the fixture for test data
) -> None:
    """Test pagination of players list"""
    # Test with skip and limit
    response = client.get(f"{settings.API_V1_STR}/world/players?skip=1&limit=2")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2  # Should return only 2 players


def test_get_players_with_name_filter(
    client: TestClient,
    world_player: models.Player,  # Need the fixture for test data  # noqa: ARG001
    extra_players: list[  # noqa: ARG001
        models.Player
    ],  # Need the fixture for test data
) -> None:
    """Test filtering players by name"""
    # Filter by a name that should match the extra players
    response = client.get(f"{settings.API_V1_STR}/world/players?name=test_player_")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 3  # Should match all 3 extra players

    # Filter by a specific player name
    response = client.get(f"{settings.API_V1_STR}/world/players?name=test_player_1")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1  # Should match only 1 player
    assert data[0]["username"] == "test_player_1"
