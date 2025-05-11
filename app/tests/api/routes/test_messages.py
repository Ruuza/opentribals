import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import models
from app.core.config import settings


@pytest.fixture
def test_message(session: Session, test_player: models.Player) -> models.BattleMessage:
    """Create a test message sent from system to the test player"""
    message = models.BattleMessage(
        from_player_id=None,  # System message
        to_player_id=test_player.id,
        message="Test system message",
        displayed=False,
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


@pytest.fixture
def second_player(session: Session) -> models.Player:
    """Create a second player for testing message sending"""
    player = models.Player(
        id="00000000-0000-0000-0000-000000000002",
        username="second_player",
    )
    session.add(player)
    session.commit()
    session.refresh(player)
    return player


@pytest.fixture
def personal_message(
    session: Session, test_player: models.Player, second_player: models.Player
) -> models.BattleMessage:
    """Create a test message sent from second player to test player"""
    message = models.BattleMessage(
        from_player_id=second_player.id,
        to_player_id=test_player.id,
        message="Test personal message",
        displayed=False,
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


@pytest.fixture
def sent_message(
    session: Session, test_player: models.Player, second_player: models.Player
) -> models.BattleMessage:
    """Create a test message sent from test player to second player"""
    message = models.BattleMessage(
        from_player_id=test_player.id,
        to_player_id=second_player.id,
        message="Message from test user",
        displayed=False,
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def test_list_received_messages(
    client: TestClient,
    test_message: models.BattleMessage,
    personal_message: models.BattleMessage,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test getting a list of messages received by the user"""
    response = client.get(
        f"{settings.API_V1_STR}/messages/received",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200

    data = response.json()
    assert "data" in data
    assert "count" in data
    assert data["count"] == 2  # Two messages for the test user

    # Verify all messages are returned with correct fields
    messages = data["data"]
    assert len(messages) == 2
    message_ids = {msg["id"] for msg in messages}
    assert test_message.id in message_ids
    assert personal_message.id in message_ids

    for msg in messages:
        assert "from_player_id" in msg
        assert "to_player_id" in msg
        assert "message" in msg
        assert "displayed" in msg
        assert "created_at" in msg


def test_list_received_messages_filter_by_unread(
    client: TestClient,
    session: Session,
    test_message: models.BattleMessage,
    personal_message: models.BattleMessage,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test filtering received messages by unread status"""
    response = client.get(
        f"{settings.API_V1_STR}/messages/received?displayed=false",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200

    data = response.json()
    assert data["count"] == 2  # Both messages are unread

    # Mark test_message as read
    test_message.displayed = True
    session.add(test_message)
    session.commit()

    # Test again with filter
    response = client.get(
        f"{settings.API_V1_STR}/messages/received?displayed=false",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200

    data = response.json()
    assert data["count"] == 1  # Only one unread message now
    assert data["data"][0]["id"] == personal_message.id


def test_list_sent_messages(
    client: TestClient,
    sent_message: models.BattleMessage,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test getting a list of messages sent by the user"""
    response = client.get(
        f"{settings.API_V1_STR}/messages/sent",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200

    data = response.json()
    assert "data" in data
    assert "count" in data
    assert data["count"] == 1  # One message sent by the test user

    # Verify the message is returned with correct fields
    messages = data["data"]
    assert len(messages) == 1
    assert messages[0]["id"] == sent_message.id
    assert messages[0]["from_player_id"] == str(sent_message.from_player_id)
    assert messages[0]["to_player_id"] == str(sent_message.to_player_id)
    assert messages[0]["message"] == sent_message.message
    assert "displayed" in messages[0]
    assert "created_at" in messages[0]


def test_get_message_as_receiver(
    client: TestClient,
    session: Session,
    personal_message: models.BattleMessage,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test getting a specific message as the receiver"""
    assert personal_message.displayed is False  # Ensuring it starts as unread

    response = client.get(
        f"{settings.API_V1_STR}/messages/{personal_message.id}",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200

    # Verify the message is returned with correct fields
    message = response.json()
    assert message["id"] == personal_message.id
    assert message["message"] == personal_message.message
    assert message["displayed"] is True  # Should be marked as read now
    assert "battle_data" in message  # Detailed view includes battle_data

    # Verify the message is marked as read in the database
    updated_message = session.get(models.BattleMessage, personal_message.id)
    assert updated_message.displayed is True


def test_get_message_as_sender(
    client: TestClient,
    session: Session,
    sent_message: models.BattleMessage,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test getting a specific message as the sender"""
    initial_displayed = sent_message.displayed

    response = client.get(
        f"{settings.API_V1_STR}/messages/{sent_message.id}",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200

    # Verify the message is returned with correct fields
    message = response.json()
    assert message["id"] == sent_message.id
    assert message["message"] == sent_message.message
    assert message["displayed"] == initial_displayed  # Should not change for sender

    # Verify the message read status did not change in the database
    updated_message = session.get(models.BattleMessage, sent_message.id)
    assert updated_message.displayed == initial_displayed


def test_get_message_not_found(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test getting a non-existent message returns 404"""
    response = client.get(
        f"{settings.API_V1_STR}/messages/99999",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Message not found"


def test_get_message_forbidden(
    client: TestClient,
    test_message: models.BattleMessage,
) -> None:
    """Test that unauthenticated requests to get message are rejected"""
    response = client.get(
        f"{settings.API_V1_STR}/messages/{test_message.id}",
    )
    assert response.status_code == 401


def test_send_message(
    client: TestClient,
    session: Session,
    test_player: models.Player,  # noqa: ARG001
    second_player: models.Player,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Test sending a new message"""
    message_data = {
        "to_player_id": str(second_player.id),
        "message": "This is a test message",
    }

    response = client.post(
        f"{settings.API_V1_STR}/messages",
        headers=normal_user_token_headers,
        json=message_data,
    )
    assert response.status_code == 200

    # Verify the message is created with correct fields
    message = response.json()
    assert message["to_player_id"] == str(second_player.id)
    assert message["message"] == "This is a test message"
    assert message["displayed"] is False  # New messages start as unread

    # Verify the message is in the database
    created_message = session.get(models.BattleMessage, message["id"])
    assert created_message is not None
    assert str(created_message.to_player_id) == str(second_player.id)
    assert created_message.message == "This is a test message"


def test_send_message_unauthenticated(
    client: TestClient,
    second_player: models.Player,
) -> None:
    """Test that unauthenticated requests to send message are rejected"""
    message_data = {
        "to_player_id": str(second_player.id),
        "message": "This is a test message",
    }

    response = client.post(
        f"{settings.API_V1_STR}/messages",
        json=message_data,
    )
    assert response.status_code == 401
