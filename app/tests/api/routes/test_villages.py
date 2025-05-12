import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud, models
from app.core.config import settings


@pytest.fixture
def test_village(session: Session) -> models.Village:
    """Create a test village without an owner"""
    return crud.Village.create(
        session=session, name="Test Village", x=100, y=100, player_id=None
    )


@pytest.fixture
def owned_village(session: Session, test_player: models.User) -> models.Village:
    """Create a test village owned by the test player"""
    return crud.Village.create(
        session=session, name="Owned Village", x=200, y=200, player_id=test_player.id
    )


@pytest.fixture
def villages_grid(session: Session) -> list[models.Village]:
    """Create a grid of test villages for testing coordinate filters"""
    villages = []
    for x in range(50, 151, 50):
        for y in range(50, 151, 50):
            village = crud.Village.create(
                session=session, name=f"Village {x},{y}", x=x, y=y, player_id=None
            )
            villages.append(village)
    return villages


def test_get_villages(client: TestClient, villages_grid: list[models.Village]) -> None:
    """Test getting a list of villages"""
    response = client.get(f"{settings.API_V1_STR}/villages")
    assert response.status_code == 200

    data = response.json()
    assert "data" in data
    assert "count" in data
    assert data["count"] == len(villages_grid)

    # Verify all villages are returned
    villages = data["data"]
    assert len(villages) == len(villages_grid)


def test_get_villages_with_coord_filters(
    client: TestClient,
    villages_grid: list[models.Village],  # noqa: ARG001
) -> None:
    """Test getting villages with coordinate filters"""
    # Test with x_min and y_min filters
    response = client.get(f"{settings.API_V1_STR}/villages?x_min=100&y_min=100")
    assert response.status_code == 200

    data = response.json()
    assert (
        data["count"] == 4
    )  # Should return 4 villages (x,y): (100,100), (100,150), (150,100), (150,150)

    # Test with x_max and y_max filters
    response = client.get(f"{settings.API_V1_STR}/villages?x_max=100&y_max=100")
    assert response.status_code == 200

    data = response.json()
    assert (
        data["count"] == 4
    )  # Should return 4 villages (x,y): (50,50), (50,100), (100,50), (100,100)

    # Test with all filters combined to get a specific area
    response = client.get(
        f"{settings.API_V1_STR}/villages?x_min=50&y_min=50&x_max=100&y_max=100"
    )
    assert response.status_code == 200

    data = response.json()
    assert data["count"] == 4  # Should return 4 villages


def test_get_villages_pagination(
    client: TestClient, villages_grid: list[models.Village]
) -> None:
    """Test pagination of villages list"""
    # Test with skip and limit
    response = client.get(f"{settings.API_V1_STR}/villages?skip=2&limit=3")
    assert response.status_code == 200

    data = response.json()
    assert len(data["data"]) == 3  # Should return only 3 villages
    assert data["count"] == len(
        villages_grid
    )  # Total count should still be all villages


def test_get_village_by_id(client: TestClient, test_village: models.Village) -> None:
    """Test getting a specific village by ID"""
    response = client.get(f"{settings.API_V1_STR}/villages/{test_village.id}")
    assert response.status_code == 200

    village = response.json()
    assert village["id"] == test_village.id
    assert village["name"] == test_village.name
    assert village["x"] == test_village.x
    assert village["y"] == test_village.y


def test_get_nonexistent_village(client: TestClient) -> None:
    """Test getting a non-existent village returns 404"""
    response = client.get(f"{settings.API_V1_STR}/villages/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Village not found"


def test_get_village_private_as_owner(
    client: TestClient,
    owned_village: models.Village,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test getting private village data as the village owner"""
    response = client.get(
        f"{settings.API_V1_STR}/villages/{owned_village.id}/private",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200

    village = response.json()
    assert village["id"] == owned_village.id
    assert village["name"] == owned_village.name
    assert village["x"] == owned_village.x
    assert village["y"] == owned_village.y

    # Verify private fields are present
    assert "wood" in village
    assert "clay" in village
    assert "iron" in village
    assert "woodcutter_lvl" in village
    assert "clay_pit_lvl" in village
    assert "iron_mine_lvl" in village


def test_get_village_private_not_owner(
    client: TestClient,
    test_village: models.Village,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test attempting to get private village data of a village not owned by the user"""
    response = client.get(
        f"{settings.API_V1_STR}/villages/{test_village.id}/private",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 403
    assert (
        response.json()["detail"] == "You don't have permission to access this village"
    )


def test_get_village_private_not_authenticated(
    client: TestClient, test_village: models.Village
) -> None:
    """Test that unauthenticated requests to private village data are rejected"""
    response = client.get(f"{settings.API_V1_STR}/villages/{test_village.id}/private")
    assert response.status_code == 401


def test_update_village_as_owner(
    client: TestClient,
    owned_village: models.Village,
    normal_user_token_headers: dict[str, str],
    session: Session,
) -> None:
    """Test updating a village as the owner"""
    new_name = "Updated Village Name"
    update_data = {"name": new_name}

    response = client.patch(
        f"{settings.API_V1_STR}/villages/{owned_village.id}",
        headers=normal_user_token_headers,
        json=update_data,
    )
    assert response.status_code == 200

    # Verify the update in the response
    updated_village = response.json()
    assert updated_village["name"] == new_name

    # Verify the update in the database
    db_village = session.get(models.Village, owned_village.id)
    assert db_village is not None
    assert db_village.name == new_name


def test_update_village_not_owner(
    client: TestClient,
    test_village: models.Village,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test attempting to update a village not owned by the user"""
    update_data = {"name": "Attempted Update"}

    response = client.patch(
        f"{settings.API_V1_STR}/villages/{test_village.id}",
        headers=normal_user_token_headers,
        json=update_data,
    )
    assert response.status_code == 403
    assert (
        response.json()["detail"] == "You don't have permission to access this village"
    )


def test_update_village_not_authenticated(
    client: TestClient, test_village: models.Village
) -> None:
    """Test that unauthenticated update requests are rejected"""
    update_data = {"name": "Attempted Update"}

    response = client.patch(
        f"{settings.API_V1_STR}/villages/{test_village.id}", json=update_data
    )
    assert response.status_code == 401


def test_update_nonexistent_village(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Test updating a non-existent village returns 404"""
    update_data = {"name": "This Village Doesn't Exist"}

    response = client.patch(
        f"{settings.API_V1_STR}/villages/99999",
        headers=normal_user_token_headers,
        json=update_data,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Village not found"
