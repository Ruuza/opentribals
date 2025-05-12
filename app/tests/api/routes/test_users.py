import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import crud, models
from app.core.config import settings
from app.core.security import verify_password
from app.models import User
from app.schemas import UserCreate, UserPublic
from app.tests.utils.user import EMAIL_TEST_USER, PASSWORD_TEST_USER
from app.tests.utils.utils import random_email, random_lower_string


def test_get_users_superuser_me(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    r = client.get(f"{settings.API_V1_STR}/users/me", headers=superuser_token_headers)
    current_user = r.json()
    assert current_user
    assert current_user["is_active"] is True
    assert current_user["is_superuser"]
    assert current_user["email"] == settings.FIRST_SUPERUSER


def test_get_users_normal_user_me(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    r = client.get(f"{settings.API_V1_STR}/users/me", headers=normal_user_token_headers)
    current_user = r.json()
    assert current_user
    assert current_user["is_active"] is True
    assert current_user["is_superuser"] is False
    assert current_user["email"] == EMAIL_TEST_USER


def test_get_existing_user(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    test_user: models.User,
) -> None:
    user_id = test_user.id
    r = client.get(
        f"{settings.API_V1_STR}/users/{user_id}",
        headers=superuser_token_headers,
    )
    assert 200 <= r.status_code < 300
    api_user = r.json()
    expected_out = UserPublic.model_validate(test_user).model_dump()
    expected_out["id"] = str(expected_out["id"])
    assert api_user == expected_out


def test_get_existing_user_current_user(
    client: TestClient,
    session: Session,
    test_user: models.User,
) -> None:
    login_data = {
        "username": EMAIL_TEST_USER,
        "password": PASSWORD_TEST_USER,
    }
    r = client.post(f"{settings.API_V1_STR}/login/access-token", data=login_data)
    tokens = r.json()
    a_token = tokens["access_token"]
    headers = {"Authorization": f"Bearer {a_token}"}

    r = client.get(
        f"{settings.API_V1_STR}/users/{test_user.id}",
        headers=headers,
    )
    assert 200 <= r.status_code < 300
    api_user = r.json()
    existing_user = crud.User.get_by_email(session=session, email=test_user.email)
    assert existing_user
    assert existing_user.email == api_user["email"]


def test_get_existing_user_permissions_error(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    r = client.get(
        f"{settings.API_V1_STR}/users/{uuid.uuid4()}",
        headers=normal_user_token_headers,
    )
    assert r.status_code == 403
    assert r.json() == {"detail": "The user doesn't have enough privileges"}


def test_update_user_me(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    session: Session,
) -> None:
    full_name = "Updated Name"
    email = random_email()
    data = {"full_name": full_name, "email": email}
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=normal_user_token_headers,
        json=data,
    )
    assert r.status_code == 200
    updated_user = r.json()
    assert updated_user["email"] == email
    assert updated_user["full_name"] == full_name

    user_query = select(User).where(User.email == email)
    user_db = session.exec(user_query).first()
    assert user_db
    assert user_db.email == email
    assert user_db.full_name == full_name


def test_update_password_me(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    session: Session,
) -> None:
    new_password = random_lower_string()
    data = {
        "current_password": settings.FIRST_SUPERUSER_PASSWORD,
        "new_password": new_password,
    }
    r = client.patch(
        f"{settings.API_V1_STR}/users/me/password",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 200
    updated_user = r.json()
    assert updated_user["message"] == "Password updated successfully"

    user_query = select(User).where(User.email == settings.FIRST_SUPERUSER)
    user_db = session.exec(user_query).first()
    assert user_db
    assert user_db.email == settings.FIRST_SUPERUSER
    assert verify_password(new_password, user_db.hashed_password)

    # Revert to the old password to keep consistency in test
    old_data = {
        "current_password": new_password,
        "new_password": settings.FIRST_SUPERUSER_PASSWORD,
    }
    r = client.patch(
        f"{settings.API_V1_STR}/users/me/password",
        headers=superuser_token_headers,
        json=old_data,
    )

    assert r.status_code == 200
    assert verify_password(settings.FIRST_SUPERUSER_PASSWORD, user_db.hashed_password)


def test_update_password_me_incorrect_password(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    new_password = random_lower_string()
    data = {"current_password": new_password, "new_password": new_password}
    r = client.patch(
        f"{settings.API_V1_STR}/users/me/password",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 400
    updated_user = r.json()
    assert updated_user["detail"] == "Incorrect password"


def test_update_user_me_email_exists(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    session: Session,
) -> None:
    username = random_email()
    user_in = UserCreate(
        email=username, username=random_lower_string(), password=random_lower_string()
    )
    user = crud.User.create(session=session, user_create=user_in)

    data = {"email": user.email}
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=normal_user_token_headers,
        json=data,
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "User with this email already exists"


def test_update_password_me_same_password_error(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    data = {
        "current_password": settings.FIRST_SUPERUSER_PASSWORD,
        "new_password": settings.FIRST_SUPERUSER_PASSWORD,
    }
    r = client.patch(
        f"{settings.API_V1_STR}/users/me/password",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 400
    updated_user = r.json()
    assert (
        updated_user["detail"] == "New password cannot be the same as the current one"
    )


def test_register_user(client: TestClient, session: Session) -> None:
    email = random_email()
    password = random_lower_string()
    username = random_lower_string()
    full_name = random_lower_string()
    data = {
        "email": email,
        "password": password,
        "full_name": full_name,
        "username": username,
    }
    r = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json=data,
    )
    assert r.status_code == 200
    created_user = r.json()
    assert created_user["email"] == email
    assert created_user["full_name"] == full_name
    assert created_user["username"] == username

    user_query = select(User).where(User.email == email)
    user_db = session.exec(user_query).first()
    assert user_db
    assert user_db.email == email
    assert user_db.full_name == full_name
    assert user_db.username == username
    assert verify_password(password, user_db.hashed_password)


def test_register_user_already_exists_error(client: TestClient) -> None:
    data = {
        "email": settings.FIRST_SUPERUSER,
        "username": random_lower_string(),
        "password": random_lower_string(),
        "full_name": random_lower_string(),
    }
    r = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json=data,
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "The user with this email already exists in the system"


# TODO: Uncomment when added functionality to make barbarian from user's villages
# when inactive
#
# def test_delete_user_me(client: TestClient, db: Session) -> None:
#     email = random_email()
#     password = random_lower_string()
#     user_in = UserCreate(email=email, password=password)
#     user = crud.User.create_user(session=db, user_create=user_in)
#     user_id = user.id

#     login_data = {
#         "username": email,
#         "password": password,
#     }
#     r = client.post(f"{settings.API_V1_STR}/login/access-token", data=login_data)
#     tokens = r.json()
#     a_token = tokens["access_token"]
#     headers = {"Authorization": f"Bearer {a_token}"}

#     r = client.delete(
#         f"{settings.API_V1_STR}/users/me",
#         headers=headers,
#     )
#     assert r.status_code == 200
#     deleted_user = r.json()
#     assert deleted_user["message"] == "User deleted successfully"
#     result = db.exec(select(User).where(User.id == user_id)).first()
#     assert result is None

#     user_query = select(User).where(User.id == user_id)
#     user_db = db.execute(user_query).first()
#     assert user_db is None


# def test_delete_user_me_as_superuser(
#     client: TestClient, superuser_token_headers: dict[str, str]
# ) -> None:
#     r = client.delete(
#         f"{settings.API_V1_STR}/users/me",
#         headers=superuser_token_headers,
#     )
#     assert r.status_code == 403
#     response = r.json()
#     assert response["detail"] == "Super users are not allowed to delete themselves"


# def test_delete_user_super_user(
#     client: TestClient,
#     superuser_token_headers: dict[str, str],
#     session: Session,
# ) -> None:
#     email = random_email()
#     password = random_lower_string()
#     user_in = UserCreate(email=email, password=password)
#     user = crud.User.create(session=session, user_create=user_in)
#     user_id = user.id
#     r = client.delete(
#         f"{settings.API_V1_STR}/users/{user_id}",
#         headers=superuser_token_headers,
#     )
#     assert r.status_code == 200
#     deleted_user = r.json()
#     assert deleted_user["message"] == "User deleted successfully"
#     result = session.exec(select(User).where(User.id == user_id)).first()
#     assert result is None


# def test_delete_user_not_found(
#     client: TestClient, superuser_token_headers: dict[str, str]
# ) -> None:
#     r = client.delete(
#         f"{settings.API_V1_STR}/users/{uuid.uuid4()}",
#         headers=superuser_token_headers,
#     )
#     assert r.status_code == 404
#     assert r.json()["detail"] == "User not found"


# def test_delete_user_current_super_user_error(
#     client: TestClient,
#     superuser_token_headers: dict[str, str],
#     session: Session,
# ) -> None:
#     super_user = crud.User.get_by_email(session=session, email=settings.FIRST_SUPERUSER)
#     assert super_user
#     user_id = super_user.id

#     r = client.delete(
#         f"{settings.API_V1_STR}/users/{user_id}",
#         headers=superuser_token_headers,
#     )
#     assert r.status_code == 403
#     assert r.json()["detail"] == "Super users are not allowed to delete themselves"


# def test_delete_user_without_privileges(
#     client: TestClient,
#     normal_user_token_headers: dict[str, str],
#     session: Session,
# ) -> None:
#     email = random_email()
#     password = random_lower_string()
#     user_in = UserCreate(email=email, password=password)
#     user = crud.User.create(session=session, user_create=user_in)

#     r = client.delete(
#         f"{settings.API_V1_STR}/users/{user.id}",
#         headers=normal_user_token_headers,
#     )
#     assert r.status_code == 403
#     assert r.json()["detail"] == "The user doesn't have enough privileges"
