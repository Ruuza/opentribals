from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy_utils import create_database, database_exists, drop_database
from sqlmodel import Session, SQLModel

from app import crud
from app.api.deps import get_db
from app.core.config import settings
from app.core.db import engine, init_db
from app.main import app
from app.schemas import UserCreate
from app.tests.utils.user import (
    EMAIL_TEST_USER,
    PASSWORD_TEST_USER,
    USERNAME_TEST_USER,
    get_superuser_auth_headers,
    get_user_auth_headers,
)

assert settings.ENVIRONMENT == "test"
assert settings.POSTGRES_DB == "OpenTribalsTest"
assert "OpenTribalsTest" in str(engine.url)
assert settings.FIRST_SUPERUSER_PASSWORD == "testpassword"


@pytest.fixture(scope="session")
def db() -> Generator[None, None, None]:
    if database_exists(engine.url):
        drop_database(engine.url)
    create_database(engine.url)
    yield
    drop_database(engine.url)


@pytest.fixture(autouse=True)
def session(db) -> Generator[Session, None, None]:
    with Session(engine) as session:
        SQLModel.metadata.drop_all(engine)
        SQLModel.metadata.create_all(engine)
        init_db(session)
        yield session
        session.commit()


@pytest.fixture()
def client(session: Session) -> Generator[TestClient, None, None]:
    def get_session_override():
        return session

    app.dependency_overrides[get_db] = get_session_override
    with TestClient(app) as c:
        yield c
    del app.dependency_overrides[get_db]


@pytest.fixture()
def test_user(session: Session) -> UserCreate:
    user_create = UserCreate(
        email=EMAIL_TEST_USER,
        password=PASSWORD_TEST_USER,
        username=USERNAME_TEST_USER,
        full_name="John Doe",
    )
    user = crud.User.create(session=session, user_create=user_create)
    return user


@pytest.fixture()
def superuser_token_headers(client: TestClient) -> dict[str, str]:
    return get_superuser_auth_headers(client)


@pytest.fixture()
def normal_user_token_headers(client: TestClient, test_user) -> dict[str, str]:
    return get_user_auth_headers(client=client)
