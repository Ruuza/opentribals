import uuid

from sqlmodel import Session, select

from app import models
from app.core.security import get_password_hash, verify_password
from app.schemas import UserCreate, UserUpdate


class User:
    @staticmethod
    def create(*, session: Session, user_create: UserCreate) -> models.User:
        db_obj = models.User.model_validate(
            user_create,
            update={"hashed_password": get_password_hash(user_create.password)},
        )
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj

    @staticmethod
    def update(
        *, session: Session, db_user: models.User, user_in: UserUpdate
    ) -> models.User:
        user_data = user_in.model_dump(exclude_unset=True)
        extra_data = {}
        if "password" in user_data:
            password = user_data["password"]
            hashed_password = get_password_hash(password)
            extra_data["hashed_password"] = hashed_password
        db_user.sqlmodel_update(user_data, update=extra_data)
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
        return db_user

    @staticmethod
    def get_by_email(*, session: Session, email: str) -> models.User | None:
        statement = select(models.User).where(models.User.email == email)
        session_user = session.exec(statement).first()
        return session_user

    @staticmethod
    def get_by_username(*, session: Session, username: str) -> models.User | None:
        statement = select(models.User).where(models.User.username == username)
        session_user = session.exec(statement).first()
        return session_user

    @staticmethod
    def authenticate(
        *, session: Session, email: str, password: str
    ) -> models.User | None:
        db_user = User.get_by_email(session=session, email=email)
        if not db_user:
            return None
        if not verify_password(password, db_user.hashed_password):
            return None
        return db_user


class Village:
    @staticmethod
    def create(
        *, session: Session, name: str, x: int, y: int, player_id: uuid.UUID | None
    ) -> models.Village:
        db_obj = models.Village(
            name=name,
            x=x,
            y=y,
            player_id=player_id,
        )
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj

    @staticmethod
    def get_for_update(*, session: Session, village_id: int) -> models.Village | None:
        """Get village with FOR UPDATE lock"""
        statement = (
            select(models.Village)
            .where(models.Village.id == village_id)
            .with_for_update()
        )
        village = session.exec(statement).first()
        return village


class BuildingEvent:
    @staticmethod
    def get_following_events_for_update(
        *, session: Session, village_id: int
    ) -> list[models.BuildingEvent]:
        """Get uncompleted building events with FOR UPDATE lock"""
        statement = (
            select(models.BuildingEvent)
            .where(models.BuildingEvent.village_id == village_id)
            .where(models.BuildingEvent.completed == False)  # noqa: E712
            .with_for_update()
        )
        building_events = session.exec(statement).all()

        return building_events
