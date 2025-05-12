from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app import models
from app.api.deps import CurrentUser, SessionDep
from app.game.world import WorldManager
from app.schemas import PlayerOutPublic, VillageBasePublic

router = APIRouter(prefix="/world", tags=["world"])


@router.post("/join", response_model=PlayerOutPublic)
def join_world(*, session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Create a player record for the current user and spawn a village for them.
    Also spawns 3 barbarian villages in the world.
    Returns the created player with their village.
    """
    # Check if player already exists for this user
    existing_player = session.exec(
        select(models.Player).where(models.Player.id == current_user.id)
    ).first()

    if existing_player:
        raise HTTPException(
            status_code=400,
            detail="You have already joined the world",
        )

    # Create a new player record using the current user's ID and username
    player = models.Player(
        id=current_user.id,
        username=current_user.username,
    )
    session.add(player)
    session.commit()

    # Initialize world manager
    world_manager = WorldManager()

    # Spawn a village for the player
    village = world_manager.spawn_village(session=session, player_id=player.id)

    # Spawn 3 barbarian villages (player_id=None)
    for _ in range(3):
        world_manager.spawn_village(session=session, player_id=None)

    # Prepare the response with player and village data
    result = PlayerOutPublic(
        id=player.id,
        username=player.username,
        villages=[
            VillageBasePublic(
                id=village.id,
                name=village.name,
                x=village.x,
                y=village.y,
            )
        ],
        villages_count=1,
    )

    return result


@router.get("/players", response_model=list[PlayerOutPublic])
def get_all_players_with_villages(
    *,
    session: SessionDep,
    name: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    List all players and their villages public information.
    Supports pagination and filtering by player name.
    """
    # Build the query for filtering players
    query = select(models.Player)

    # Apply name filter if provided
    if name:
        query = query.where(models.Player.username.contains(name))

    # Apply pagination
    query = query.offset(skip).limit(limit)

    # Get filtered players
    players = session.exec(query).all()

    result = []
    for player in players:
        # Convert villages to public format
        villages_data = []
        for village in player.villages:
            villages_data.append(
                VillageBasePublic(
                    id=village.id,
                    name=village.name,
                    x=village.x,
                    y=village.y,
                )
            )

        # Add player with villages to result
        player_data = PlayerOutPublic(
            id=player.id,
            username=player.username,
            villages=villages_data,
            villages_count=len(villages_data),
        )
        result.append(player_data)

    return result
