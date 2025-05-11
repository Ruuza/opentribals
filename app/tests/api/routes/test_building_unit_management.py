import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud, models
from app.core.config import settings
from app.game.buildings import BuildingType
from app.game.units import UnitName


@pytest.fixture
def player_village(session: Session, test_player: models.Player) -> models.Village:
    """Create a test village owned by the test player with some resources"""
    return crud.Village.create(
        session=session,
        name="Test Player Village",
        x=300,
        y=300,
        player_id=test_player.id,
        woodcutter_lvl=3,
        clay_pit_lvl=3,
        iron_mine_lvl=3,
    )


@pytest.fixture
def rich_player_village(session: Session, test_player: models.Player) -> models.Village:
    """
    Create a test village owned by the test player with lots of resources and buildings
    """
    village = crud.Village.create(
        session=session,
        name="Rich Player Village",
        x=400,
        y=400,
        player_id=test_player.id,
    )

    village.barracks_lvl = 5
    # Add resources
    village.wood = 10000
    village.clay = 10000
    village.iron = 10000
    session.add(village)
    session.commit()
    session.refresh(village)

    return village


# --- Building Tests ---


def test_get_building_queue_empty(
    client: TestClient,
    player_village: models.Village,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test getting an empty building queue"""
    response = client.get(
        f"{settings.API_V1_STR}/villages/{player_village.id}/buildings/queue",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "queue" in data
    assert len(data["queue"]) == 0


def test_schedule_building_construction(
    client: TestClient,
    rich_player_village: models.Village,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test scheduling a building construction"""
    # Schedule headquarters upgrade
    response = client.post(
        f"{settings.API_V1_STR}/villages/{rich_player_village.id}/"
        f"buildings/{BuildingType.HEADQUARTERS.value}",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    event = response.json()

    # Check response fields
    assert event["building_type"] == BuildingType.HEADQUARTERS.value
    assert event["complete_at"] is not None

    # Check that the event is in the queue
    response = client.get(
        f"{settings.API_V1_STR}/villages/{rich_player_village.id}/buildings/queue",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["queue"]) == 1
    assert data["queue"][0]["id"] == event["id"]


def test_schedule_building_construction_insufficient_resources(
    client: TestClient,
    player_village: models.Village,
    normal_user_token_headers: dict[str, str],
    session: Session,
) -> None:
    """Test scheduling a building construction with insufficient resources"""
    # Set resources to zero
    player_village.wood = 0
    player_village.clay = 0
    player_village.iron = 0
    session.add(player_village)
    session.commit()

    # Try to schedule headquarters upgrade
    response = client.post(
        f"{settings.API_V1_STR}/villages/{player_village.id}/"
        f"buildings/{BuildingType.HEADQUARTERS.value}",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 400
    assert "Not enough resources" in response.json()["detail"]


def test_get_available_buildings(
    client: TestClient,
    player_village: models.Village,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test getting information about available buildings"""
    response = client.get(
        f"{settings.API_V1_STR}/villages/{player_village.id}/buildings/available",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    data = response.json()

    # Check response structure and content
    assert "buildings" in data
    assert len(data["buildings"]) == len(BuildingType)

    # Check specific building information
    woodcutter_info = next(
        (b for b in data["buildings"] if b["building_type"] == BuildingType.WOODCUTTER),
        None,
    )
    assert woodcutter_info is not None
    assert woodcutter_info["current_level"] == 3
    assert woodcutter_info["wood_cost"] > 0
    assert woodcutter_info["clay_cost"] > 0
    assert woodcutter_info["iron_cost"] > 0
    assert woodcutter_info["build_time_ms"] > 0


# --- Unit Tests ---


def test_get_unit_training_queue_empty(
    client: TestClient,
    player_village: models.Village,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test getting an empty unit training queue"""
    response = client.get(
        f"{settings.API_V1_STR}/villages/{player_village.id}/units/queue",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "queue" in data
    assert len(data["queue"]) == 0


def test_schedule_unit_training(
    client: TestClient,
    rich_player_village: models.Village,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test scheduling unit training"""
    # Schedule archer training
    training_request = {"unit_type": UnitName.ARCHER, "count": 5}
    response = client.post(
        f"{settings.API_V1_STR}/villages/{rich_player_village.id}/units/train",
        headers=normal_user_token_headers,
        json=training_request,
    )
    assert response.status_code == 200
    event = response.json()

    # Check response fields
    assert event["unit_type"] == UnitName.ARCHER
    assert event["count"] == 5
    assert event["complete_at"] is not None

    # Check that the event is in the queue
    response = client.get(
        f"{settings.API_V1_STR}/villages/{rich_player_village.id}/units/queue",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["queue"]) == 1
    assert data["queue"][0]["id"] == event["id"]


def test_schedule_unit_training_barracks_required(
    client: TestClient,
    player_village: models.Village,
    normal_user_token_headers: dict[str, str],
    session: Session,
) -> None:
    """Test scheduling unit training without barracks"""
    # Set barracks level to 0
    player_village.barracks_lvl = 0
    session.add(player_village)
    session.commit()

    # Try to train units
    training_request = {"unit_type": UnitName.SWORDSMAN, "count": 1}
    response = client.post(
        f"{settings.API_V1_STR}/villages/{player_village.id}/units/train",
        headers=normal_user_token_headers,
        json=training_request,
    )
    assert response.status_code == 400
    assert "Barracks required" in response.json()["detail"]


def test_get_available_units(
    client: TestClient,
    rich_player_village: models.Village,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test getting information about available units"""
    response = client.get(
        f"{settings.API_V1_STR}/villages/{rich_player_village.id}/units/available",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    data = response.json()

    # Check response structure and content
    assert "units" in data
    assert len(data["units"]) == len(UnitName)

    # Check specific unit information
    archer_info = next(
        (u for u in data["units"] if u["unit_type"] == UnitName.ARCHER), None
    )
    assert archer_info is not None
    assert archer_info["wood_cost"] > 0
    assert archer_info["clay_cost"] > 0
    assert archer_info["iron_cost"] > 0
    assert archer_info["training_time_ms"] > 0
    assert archer_info["can_train"] is True  # Barracks level is 5

    # Check one more unit
    swordsman_info = next(
        (u for u in data["units"] if u["unit_type"] == UnitName.SWORDSMAN), None
    )
    assert swordsman_info is not None
    assert swordsman_info["wood_cost"] > 0
    assert swordsman_info["attack"] > 0
    assert swordsman_info["can_train"] is True


# --- Authorization Tests ---


def test_building_queue_unauthorized(
    client: TestClient,
    player_village: models.Village,
) -> None:
    """Test that unauthorized requests to building queue are rejected"""
    response = client.get(
        f"{settings.API_V1_STR}/villages/{player_village.id}/buildings/queue",
    )
    assert response.status_code == 401


def test_building_queue_not_owner(
    client: TestClient,
    session: Session,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test that non-owner cannot access building queue"""
    # Create a village without an owner
    village = crud.Village.create(
        session=session, name="Not Owned Village", x=500, y=500, player_id=None
    )

    response = client.get(
        f"{settings.API_V1_STR}/villages/{village.id}/buildings/queue",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 403
    assert "permission" in response.json()["detail"]


def test_unit_training_unauthorized(
    client: TestClient,
    rich_player_village: models.Village,
) -> None:
    """Test that unauthorized requests to train units are rejected"""
    training_request = {"unit_type": UnitName.ARCHER, "count": 5}
    response = client.post(
        f"{settings.API_V1_STR}/villages/{rich_player_village.id}/units/train",
        json=training_request,
    )
    assert response.status_code == 401


def test_invalid_village_id(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test that invalid village ID returns 404"""
    # Use a non-existent village ID
    invalid_id = 999999

    # Try to access building queue
    response = client.get(
        f"{settings.API_V1_STR}/villages/{invalid_id}/buildings/queue",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Village not found"
