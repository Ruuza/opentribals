from fastapi import APIRouter, Depends

from app import crud, models
from app.api.deps import SessionDep, get_current_active_superuser
from app.core.config import settings
from app.game.combat import AttackResolver
from app.game.village import VillageManager
from app.schemas import Message

router = APIRouter(prefix=f"{settings.API_V1_STR}/combat", tags=["combat"])


@router.post("/process", response_model=Message)
async def start_combat(
    *,
    session: SessionDep,
    _current_superuser: models.User = Depends(get_current_active_superuser),
) -> dict:
    """
    Process all ready attack movements in the game.
    Requires superuser privileges.
    """
    # Get unique target village IDs from ready attack movements
    target_village_ids = crud.UnitMovement.get_all_ready_attack_target_villages(
        session=session
    )

    processed_villages = 0

    # For each target village, resolve all attacks
    for village_id in target_village_ids:
        village = crud.Village.get_for_update(session=session, village_id=village_id)
        if not village:
            continue

        village_manager = VillageManager(session=session, village=village)
        attack_resolver = AttackResolver(village_manager=village_manager)

        # Resolve attacks for this village
        attack_resolver.resolve_attack()
        processed_villages += 1
        session.commit()  # Release the lock on the village

    return {"message": f"Combat processed for {processed_villages} villages"}
