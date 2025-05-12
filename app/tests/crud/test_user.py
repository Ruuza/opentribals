from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlmodel import Session

from app import crud, models
from app.core.security import verify_password
from app.models import User
from app.schemas import UserCreate, UserUpdate

user_create = UserCreate(
    email="newuser@example.com",
    username="test_user",
    password="password",
    full_name="Test User",
)


def test_create_user(session: Session) -> None:
    user = crud.User.create(session=session, user_create=user_create)
    assert user.model_dump(exclude={"id", "hashed_password"}) == {
        "full_name": user_create.full_name,
        "is_active": True,
        "email": user_create.email,
        "username": user_create.username,
        "is_superuser": False,
    }

    assert isinstance(user.id, UUID)
    assert hasattr(user, "hashed_password")
    # Compare with the database
    db_user = session.get(User, user.id)
    assert jsonable_encoder(db_user) == jsonable_encoder(user)


def test_authenticate_user(session: Session) -> None:
    user = crud.User.create(session=session, user_create=user_create)
    authenticated_user = crud.User.authenticate(
        session=session, email=user_create.email, password=user_create.password
    )
    assert authenticated_user
    assert user.email == authenticated_user.email


def test_not_authenticate_user(session: Session) -> None:
    user = crud.User.authenticate(
        session=session, email=user_create.email, password=user_create.password
    )
    assert user is None


def test_check_if_user_is_active_inactive(session: Session) -> None:
    user_in = user_create.model_copy()
    user_in.is_active = False
    user = crud.User.create(session=session, user_create=user_in)
    assert not user.is_active


def test_check_if_user_is_superuser(session: Session) -> None:
    user_in = user_create.model_copy()
    user_in.is_superuser = True
    user = crud.User.create(session=session, user_create=user_in)
    assert user.is_superuser is True


def test_update_user(session: Session, test_user: models.User) -> None:
    new_password = "new_password"
    user_in_update = UserUpdate(password=new_password, is_superuser=True)
    user = crud.User.update(session=session, db_user=test_user, user_in=user_in_update)
    user_db = session.get(User, user.id)
    assert jsonable_encoder(user) == jsonable_encoder(user_db)
    assert user.email == user_db.email
    assert verify_password(new_password, user_db.hashed_password)
