import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import crud, models
from app.core.config import settings
from app.models import User
from app.schemas import UserCreate
from app.tests.utils.user import EMAIL_TEST_USER, PASSWORD_TEST_USER, USERNAME_TEST_USER
from app.tests.utils.utils import random_email, random_lower_string


def test_create_user_new_email(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    session: Session,
) -> None:
    with (
        patch("app.utils.send_email", return_value=None),
        patch("app.core.config.settings.SMTP_HOST", "smtp.example.com"),
        patch("app.core.config.settings.SMTP_USER", "admin@example.com"),
    ):
        email = random_email()
        password = random_lower_string()
        username = "john_doe"
        data = {"email": email, "username": username, "password": password}
        r = client.post(
            f"{settings.API_V1_STR}/users/",
            headers=superuser_token_headers,
            json=data,
        )
        assert 200 <= r.status_code < 300
        created_user = r.json()
        user = crud.User.get_by_email(session=session, email=email)
        assert user
        assert user.email == created_user["email"]


def test_create_user_existing_email(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    test_user: models.User,  # noqa: ARG001
) -> None:
    data = {
        "email": EMAIL_TEST_USER,
        "username": "new_username",
        "password": PASSWORD_TEST_USER,
    }
    r = client.post(
        f"{settings.API_V1_STR}/users/",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 400
    assert r.json() == {
        "detail": "The user with this email already exists in the system"
    }


def test_create_user_existing_username(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    test_user: models.User,  # noqa: ARG001
) -> None:
    email = random_email()

    data = {
        "email": email,
        "username": USERNAME_TEST_USER,
        "password": PASSWORD_TEST_USER,
    }
    r = client.post(
        f"{settings.API_V1_STR}/users/",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 400
    assert r.json() == {
        "detail": "The user with this username already exists in the system"
    }


def test_create_user_by_normal_user(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    username = random_email()
    password = random_lower_string()
    data = {"email": username, "password": password}
    r = client.post(
        f"{settings.API_V1_STR}/users/",
        headers=normal_user_token_headers,
        json=data,
    )
    assert r.status_code == 403


def test_retrieve_users(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    session: Session,
    test_user: models.User,  # noqa: ARG001
) -> None:
    email = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=email, username="user2", password=password)
    crud.User.create(session=session, user_create=user_in)

    r = client.get(f"{settings.API_V1_STR}/users/", headers=superuser_token_headers)
    all_users = r.json()

    assert len(all_users["data"]) > 1
    assert "count" in all_users
    for item in all_users["data"]:
        assert "email" in item


def test_update_user(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    session: Session,
    test_user: models.User,
) -> None:
    data = {"full_name": "Updated_full_name"}
    r = client.patch(
        f"{settings.API_V1_STR}/users/{test_user.id}",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 200
    updated_user = r.json()

    assert updated_user["full_name"] == "Updated_full_name"

    user_query = select(User).where(User.email == test_user.email)
    user_db = session.exec(user_query).first()
    assert user_db
    assert user_db.full_name == "Updated_full_name"


def test_update_user_not_exists(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    data = {"full_name": "Updated_full_name"}
    r = client.patch(
        f"{settings.API_V1_STR}/users/{uuid.uuid4()}",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "The user with this id does not exist in the system"


def test_update_user_email_exists(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    test_user: models.User,
) -> None:
    data = {"email": settings.FIRST_SUPERUSER}
    r = client.patch(
        f"{settings.API_V1_STR}/users/{test_user.id}",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "User with this email already exists"
