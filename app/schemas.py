import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr
from sqlmodel import Field, SQLModel

# --- User schemas ---#


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    username: str = Field(unique=True, min_length=4, max_length=20)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=40)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    username: str = Field(min_length=4, max_length=20)
    password: str = Field(min_length=8, max_length=40)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore
    username: str | None = Field(default=None, min_length=4, max_length=20)
    password: str | None = Field(default=None, min_length=8, max_length=40)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=40)
    new_password: str = Field(min_length=8, max_length=40)


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# --- Other schemas ---#


# Generic message
class Message(SQLModel):
    message: str


# --- Token schemas ---#


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=40)


# --- Player schemas --- #


class PlayerBase(SQLModel):
    id: uuid.UUID
    username: str = Field(min_length=4, max_length=20)


# --- Village schemas --- #


class VillageBasePublic(SQLModel):
    id: int = Field(primary_key=True)
    name: str = Field(min_length=2, max_length=24)
    x: int
    y: int


class VillageBasePrivate(VillageBasePublic):
    headquarters_lvl: int = Field(default=1)
    woodcutter_lvl: int = Field(default=1)
    clay_pit_lvl: int = Field(default=1)
    iron_mine_lvl: int = Field(default=1)
    farm_lvl: int = Field(default=1)
    storage_lvl: int = Field(default=1)
    barracks_lvl: int = Field(default=1)

    swordsman: int = Field(default=0)
    archer: int = Field(default=0)

    knight: int = Field(default=0)
    skirmisher: int = Field(default=0)
    nobleman: int = Field(default=0)

    horse_units: int = Field(default=0)

    wood: int = Field(default=500)
    clay: int = Field(default=500)
    iron: int = Field(default=500)

    population: int = Field(default=0)
    population_limit: int = Field(default=100)
    loyalty: float = Field(default=100.0)


class VillageOutPublic(VillageBasePublic):
    player: PlayerBase | None


class VillageOutPrivate(VillageBasePrivate):
    player: PlayerBase | None


class VillageUpdate(SQLModel):
    name: str | None = Field(max_length=255)


class VillageOutPublicList(SQLModel):
    data: list[VillageOutPublic]
    count: int


# Battle result


class Units(BaseModel):
    """Class to represent available units in a village"""

    archer: int = 0
    swordsman: int = 0
    knight: int = 0
    skirmisher: int = 0
    nobleman: int = 0


class BattleResultBase(BaseModel):
    attacker_won: bool

    attacking_units: Units
    attacking_units_lost: Units
    defending_units: Units
    defending_units_lost: Units

    original_loyalty: float
    loyalty_damage: float | None = None

    luck: float


class BattleReport(BattleResultBase):
    datetime: datetime

    loot_capacity: int
    looted_wood: int
    looted_clay: int
    looted_iron: int

    conquered_by_player: PlayerBase | None = None
    conquered_village: VillageBasePublic | None = None


class BattleResultForMovement(BattleReport):
    attacking_village_id: int
    defending_village_id: int

    own_units: Units
    own_units_lost: Units

    own_loot_capacity: int
    own_looted_wood: int
    own_looted_clay: int
    own_looted_iron: int
