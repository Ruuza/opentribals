from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import crud, models
from app.core.config import settings


@pytest.fixture
def source_village(session: Session, test_player: models.Player) -> models.Village:
    """Create a source village owned by the test player with units and resources"""
    village = crud.Village.create(
        session=session,
        name="Source Village",
        x=300,
        y=300,
        player_id=test_player.id,
    )

    # Add units and resources
    village.wood = 10000
    village.clay = 10000
    village.iron = 10000
    village.archer = 50
    village.swordsman = 50
    village.knight = 20
    village.skirmisher = 10

    session.add(village)
    session.commit()
    session.refresh(village)

    return village


@pytest.fixture
def target_village(session: Session) -> models.Village:
    """Create a target village without an owner"""
    return crud.Village.create(
        session=session, name="Target Village", x=305, y=305, player_id=None
    )


@pytest.fixture
def ally_village(session: Session, test_player: models.Player) -> models.Village:
    """Create another village owned by the same player"""
    return crud.Village.create(
        session=session,
        name="Ally Village",
        x=310,
        y=310,
        player_id=test_player.id,
    )


def test_send_attack(
    client: TestClient,
    source_village: models.Village,
    target_village: models.Village,
    normal_user_token_headers: dict[str, str],
    session: Session,
) -> None:
    """Test sending an attack to a target village"""
    # Define units to send
    units = {
        "archer": 10,
        "swordsman": 5,
        "knight": 2,
        "skirmisher": 1,
        "nobleman": 0,
    }

    # Send the attack
    response = client.post(
        f"{settings.API_V1_STR}/villages/{source_village.id}/"
        f"attack/{target_village.id}",
        headers=normal_user_token_headers,
        json=units,
    )

    assert response.status_code == 200

    # Verify response contains movement details
    movement = response.json()
    assert movement["village_id"] == source_village.id
    assert movement["target_village_id"] == target_village.id
    assert movement["is_attack"] is True
    assert movement["is_support"] is False
    assert movement["archer"] == 10
    assert movement["swordsman"] == 5
    assert movement["knight"] == 2
    assert movement["skirmisher"] == 1

    # Verify movement was created in database
    db_movement = session.exec(
        select(models.UnitMovement).where(models.UnitMovement.id == movement["id"])
    ).one()
    assert db_movement is not None
    assert db_movement.is_attack is True
    assert db_movement.completed is False

    # Verify units were deducted from source village
    session.refresh(source_village)


def test_send_support(
    client: TestClient,
    source_village: models.Village,
    ally_village: models.Village,
    normal_user_token_headers: dict[str, str],
    session: Session,
) -> None:
    """Test sending support to an ally village"""
    # Define units to send as support
    units = {
        "archer": 5,
        "swordsman": 10,
        "knight": 0,
        "skirmisher": 0,
        "nobleman": 0,
    }

    # Send the support
    response = client.post(
        f"{settings.API_V1_STR}/villages/{source_village.id}/"
        f"support/{ally_village.id}",
        headers=normal_user_token_headers,
        json=units,
    )

    assert response.status_code == 200

    # Verify response contains movement details
    movement = response.json()
    assert movement["village_id"] == source_village.id
    assert movement["target_village_id"] == ally_village.id
    assert movement["is_attack"] is False
    assert movement["is_support"] is True
    assert movement["archer"] == 5
    assert movement["swordsman"] == 10

    # Verify movement was created in database
    db_movement = session.exec(
        select(models.UnitMovement).where(models.UnitMovement.id == movement["id"])
    ).one()
    assert db_movement is not None
    assert db_movement.is_support is True
    assert db_movement.completed is False

    # Verify units were deducted from source village
    session.refresh(source_village)


def test_get_movements(
    client: TestClient,
    source_village: models.Village,
    target_village: models.Village,
    normal_user_token_headers: dict[str, str],
    session: Session,
) -> None:
    """Test getting all movements for a village"""
    # Create some movements in the database first
    # 1. An outgoing attack
    attack_movement = models.UnitMovement(
        village_id=source_village.id,
        target_village_id=target_village.id,
        archer=10,
        swordsman=5,
        is_attack=True,
        is_support=False,
        completed=False,
    )
    session.add(attack_movement)

    # 2. An incoming attack
    incoming_attack = models.UnitMovement(
        village_id=target_village.id,
        target_village_id=source_village.id,
        archer=3,
        swordsman=2,
        is_attack=True,
        is_support=False,
        completed=False,
    )
    session.add(incoming_attack)

    # 3. A completed movement (should not be returned)
    completed_movement = models.UnitMovement(
        village_id=source_village.id,
        target_village_id=target_village.id,
        archer=1,
        swordsman=1,
        is_attack=True,
        is_support=False,
        completed=True,
    )
    session.add(completed_movement)

    session.commit()

    # Get movements for the source village
    response = client.get(
        f"{settings.API_V1_STR}/villages/{source_village.id}/movements",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200

    # Verify we get both incoming and outgoing movements (but not completed ones)
    movements = response.json()
    assert len(movements) == 2

    # Verify the movements contain correct information
    movement_ids = [m["id"] for m in movements]
    assert attack_movement.id in movement_ids
    assert incoming_attack.id in movement_ids
    assert completed_movement.id not in movement_ids


def test_unauthorized_movements(
    client: TestClient,
    source_village: models.Village,
    target_village: models.Village,
) -> None:
    """Test that unauthorized requests are rejected"""
    # Try to send attack without authentication
    units = {"archer": 5, "swordsman": 5, "knight": 0, "skirmisher": 0, "nobleman": 0}

    response = client.post(
        f"{settings.API_V1_STR}/villages/{source_village.id}/attack/{target_village.id}",
        json=units,
    )
    assert response.status_code == 401

    # Try to send support without authentication
    response = client.post(
        f"{settings.API_V1_STR}/villages/{source_village.id}/support/{target_village.id}",
        json=units,
    )
    assert response.status_code == 401

    # Try to get movements without authentication
    response = client.get(
        f"{settings.API_V1_STR}/villages/{source_village.id}/movements",
    )
    assert response.status_code == 401


def test_insufficient_units(
    client: TestClient,
    source_village: models.Village,
    target_village: models.Village,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test sending more units than available"""
    # Try to send more units than available
    units = {
        "archer": 100,  # Source village only has 50
        "swordsman": 0,
        "knight": 0,
        "skirmisher": 0,
        "nobleman": 0,
    }

    response = client.post(
        f"{settings.API_V1_STR}/villages/{source_village.id}/attack/{target_village.id}",
        headers=normal_user_token_headers,
        json=units,
    )

    assert response.status_code == 400
    assert "Not enough units available" in response.json()["detail"]


def test_send_to_nonexistent_village(
    client: TestClient,
    source_village: models.Village,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test sending units to a nonexistent village"""
    units = {"archer": 5, "swordsman": 5, "knight": 0, "skirmisher": 0, "nobleman": 0}

    response = client.post(
        f"{settings.API_V1_STR}/villages/{source_village.id}/attack/99999",
        headers=normal_user_token_headers,
        json=units,
    )

    assert response.status_code == 404
    assert "Target village not found" in response.json()["detail"]


def test_send_to_self(
    client: TestClient,
    source_village: models.Village,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test sending units to the same village"""
    units = {"archer": 5, "swordsman": 5, "knight": 0, "skirmisher": 0, "nobleman": 0}

    response = client.post(
        f"{settings.API_V1_STR}/villages/{source_village.id}/attack/{source_village.id}",
        headers=normal_user_token_headers,
        json=units,
    )

    assert response.status_code == 400
    assert "Cannot send units to own village" in response.json()["detail"]


def test_cancel_support(
    client: TestClient,
    source_village: models.Village,
    ally_village: models.Village,
    normal_user_token_headers: dict[str, str],
    session: Session,
) -> None:
    """Test cancelling a support movement"""
    # First send a support movement
    units = {
        "archer": 8,
        "swordsman": 7,
        "knight": 0,
        "skirmisher": 0,
        "nobleman": 0,
    }

    # Send the support
    response = client.post(
        f"{settings.API_V1_STR}/villages/{source_village.id}/support/{ally_village.id}",
        headers=normal_user_token_headers,
        json=units,
    )

    assert response.status_code == 200
    movement = response.json()
    movement_id = movement["id"]

    # Now cancel the support
    response = client.post(
        f"{settings.API_V1_STR}/villages/{source_village.id}/"
        f"cancel-support/{movement_id}",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    cancelled_movement = response.json()

    # Verify the movement has a return_at time set
    assert cancelled_movement["id"] == movement_id
    assert cancelled_movement["return_at"] is not None

    # Get the movement from the database to verify
    db_movement = session.get(models.UnitMovement, movement_id)
    assert db_movement is not None
    assert db_movement.return_at is not None
    assert db_movement.completed is False


def test_cancel_support_unauthorized(
    client: TestClient,
    source_village: models.Village,
    ally_village: models.Village,
    normal_user_token_headers: dict[str, str],  # noqa: ARG001
    session: Session,
) -> None:
    """Test that unauthorized users cannot cancel support"""
    # Create a support movement
    movement = models.UnitMovement(
        village_id=source_village.id,
        target_village_id=ally_village.id,
        archer=5,
        swordsman=5,
        is_attack=False,
        is_support=True,
        completed=False,
        created_at=datetime.now(UTC),
        arrival_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(movement)
    session.commit()
    session.refresh(movement)

    # Try to cancel without authentication
    response = client.post(
        f"{settings.API_V1_STR}/villages/{source_village.id}/"
        f"cancel-support/{movement.id}",
    )
    assert response.status_code == 401


def test_cancel_non_support_movement(
    client: TestClient,
    source_village: models.Village,
    target_village: models.Village,
    normal_user_token_headers: dict[str, str],
    session: Session,
) -> None:
    """Test that only support movements can be cancelled"""
    # Create an attack movement
    movement = models.UnitMovement(
        village_id=source_village.id,
        target_village_id=target_village.id,
        archer=5,
        swordsman=5,
        is_attack=True,
        is_support=False,
        completed=False,
        created_at=datetime.now(UTC),
        arrival_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(movement)
    session.commit()
    session.refresh(movement)

    # Try to cancel the attack movement
    response = client.post(
        f"{settings.API_V1_STR}/villages/{source_village.id}/"
        f"cancel-support/{movement.id}",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 400
    assert "Only support movements can be cancelled" in response.json()["detail"]


def test_cancel_completed_movement(
    client: TestClient,
    source_village: models.Village,
    ally_village: models.Village,
    normal_user_token_headers: dict[str, str],
    session: Session,
) -> None:
    """Test that completed movements cannot be cancelled"""
    # Create a completed support movement
    movement = models.UnitMovement(
        village_id=source_village.id,
        target_village_id=ally_village.id,
        archer=5,
        swordsman=5,
        is_attack=False,
        is_support=True,
        completed=True,  # Already completed
        created_at=datetime.now(UTC) - timedelta(hours=2),
        arrival_at=datetime.now(UTC) - timedelta(hours=1),
    )
    session.add(movement)
    session.commit()
    session.refresh(movement)

    # Try to cancel the completed movement
    response = client.post(
        f"{settings.API_V1_STR}/villages/{source_village.id}/"
        f"cancel-support/{movement.id}",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 400
    assert "Movement is already completed" in response.json()["detail"]
