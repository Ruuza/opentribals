import uuid
from datetime import UTC, datetime

from sqlmodel import Column, Enum, Field, Relationship, SQLModel

from app.game.buildings import BuildingType
from app.game.units import UnitName
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
    loyalty: float = Field(default=100.0)

    player: Player | None = Relationship(back_populates="villages")


class BuildingEvent(SQLModel, table=True):
    id: int = Field(primary_key=True)
    village_id: int = Field(foreign_key="village.id")
    building_type: BuildingType = Field(sa_column=Column(Enum(BuildingType)))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    complete_at: datetime | None
    completed: bool = False


class UnitTrainingEvent(SQLModel, table=True):
    id: int = Field(primary_key=True)
    village_id: int = Field(foreign_key="village.id")
    unit_type: UnitName = Field(sa_column=Column(Enum(UnitName)))
    count: int = Field(default=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    complete_at: datetime | None
    completed: bool = False


class UnitMovement(SQLModel, table=True):
    id: int = Field(primary_key=True)
    village_id: int = Field(foreign_key="village.id")
    target_village_id: int = Field(foreign_key="village.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    arrival_at: datetime | None
    return_at: datetime | None
    completed: bool = False
    archer: int = Field(default=0)
    swordsman: int = Field(default=0)
    knight: int = Field(default=0)
    skirmisher: int = Field(default=0)
    nobleman: int = Field(default=0)
    return_wood: int = Field(default=0)
    return_clay: int = Field(default=0)
    return_iron: int = Field(default=0)
    is_attack: bool = False
    is_support: bool = False
    is_spy: bool = False

    target_village: Village = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[UnitMovement.target_village_id]"}
    )
    origin_village: Village = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[UnitMovement.village_id]"}
    )


class BattleMessage(SQLModel, table=True):
    """Message model for battle reports and other player communications"""

    id: int = Field(primary_key=True)
    from_player_id: uuid.UUID | None = Field(default=None, foreign_key="player.id")
    to_player_id: uuid.UUID = Field(foreign_key="player.id")
    message: str
    battle_data: str | None = Field(default=None)  # JSON serialized battle report data
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    displayed: bool = Field(default=False)
