import uuid
from datetime import UTC, datetime

from sqlmodel import Session, func, select

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
        return session.exec(statement).first()

    @staticmethod
    def get_by_username(*, session: Session, username: str) -> models.User | None:
        statement = select(models.User).where(models.User.username == username)
        return session.exec(statement).first()

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

    @staticmethod
    def get(
        *,
        session: Session,
        village_id: int,
    ) -> models.Village | None:
        """Get village without lock"""
        return session.exec(
            select(models.Village).where(models.Village.id == village_id)
        ).first()


class BuildingEvent:
    @staticmethod
    def get_following_events(
        *, session: Session, village_id: int
    ) -> list[models.BuildingEvent]:
        """Get uncompleted building events"""
        statement = (
            select(models.BuildingEvent)
            .where(models.BuildingEvent.village_id == village_id)
            .where(models.BuildingEvent.completed == False)  # noqa: E712
        )
        return session.exec(statement).all()


class UnitTrainingEvent:
    @staticmethod
    def get_following_events(
        *, session: Session, village_id: int
    ) -> list[models.UnitTrainingEvent]:
        """Get uncompleted unit training events"""
        statement = (
            select(models.UnitTrainingEvent)
            .where(models.UnitTrainingEvent.village_id == village_id)
            .where(models.UnitTrainingEvent.completed == False)  # noqa: E712
        )
        return session.exec(statement).all()

    @staticmethod
    def get_units_queued_count(*, session: Session, village_id: int) -> int:
        """Get total count of units queued for training"""
        statement = (
            select(func.sum(models.UnitTrainingEvent.count))
            .where(models.UnitTrainingEvent.village_id == village_id)
            .where(models.UnitTrainingEvent.completed == False)  # noqa: E712
        )
        result = session.exec(statement).first()
        return result if result is not None else 0


class UnitMovement:
    @staticmethod
    def get_ready_movements(
        *,
        session: Session,
        village_id: int,
        is_attack: bool | None = None,
        is_support: bool | None = None,
    ) -> list[models.UnitMovement]:
        """Get unit movements based on type and arrival time"""
        now = datetime.now(UTC)
        statement = (
            select(models.UnitMovement)
            .where(models.UnitMovement.target_village_id == village_id)
            .where(models.UnitMovement.completed == False)  # noqa: E712
            .where(models.UnitMovement.return_at == None)  # noqa: E711
            .where(models.UnitMovement.arrival_at <= now)
        )
        if is_attack is not None:
            statement = statement.where(models.UnitMovement.is_attack == is_attack)
        if is_support is not None:
            statement = statement.where(models.UnitMovement.is_support == is_support)
        return session.exec(statement).all()

    @staticmethod
    def get_all_ready_attack_target_villages(
        *,
        session: Session,
    ) -> list[int]:
        """Get all village IDs that have ready attacks waiting to be resolved"""
        now = datetime.now(UTC)
        statement = (
            select(models.UnitMovement.target_village_id)
            .where(models.UnitMovement.is_attack == True)  # noqa: E712
            .where(models.UnitMovement.completed == False)  # noqa: E712
            .where(models.UnitMovement.return_at == None)  # noqa: E711
            .where(models.UnitMovement.arrival_at <= now)
            .distinct()
        )
        return session.exec(statement).all()
