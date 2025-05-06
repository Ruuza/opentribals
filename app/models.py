import uuid
from datetime import UTC, datetime

from sqlmodel import Column, Enum, Field, Relationship, SQLModel

from app.game.buildings import BuildingType
from app.schemas import PlayerBase, UserBase, VillageBasePrivate


class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str


# No relation between Player and User because they will be in different databases in the
# future
class Player(PlayerBase, table=True):
    id: uuid.UUID = Field(primary_key=True)

    villages: list["Village"] = Relationship(
        back_populates="player", cascade_delete=True
    )


class Village(VillageBasePrivate, table=True):
    player_id: uuid.UUID | None = Field(
        foreign_key="player.id", nullable=True, ondelete="SET NULL"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_wood_update: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_clay_update: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_iron_update: datetime = Field(default_factory=lambda: datetime.now(UTC))

    player: Player | None = Relationship(back_populates="villages")


class BuildingEvent(SQLModel, table=True):
    id: int = Field(primary_key=True)
    village_id: int
    building_type: BuildingType = Field(sa_column=Column(Enum(BuildingType)))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    complete_at: datetime | None
    completed: bool = False
