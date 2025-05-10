from fastapi import APIRouter

from app.api.routes import (
    combat,
    login,
    players,
    private,
    users,
    users_admin,
    utils,
    villages,
    world,
)
from app.core.config import settings

api_router = APIRouter()

# Account API
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(users_admin.router)

# Game API
api_router.include_router(players.router)
api_router.include_router(users_admin.router)
api_router.include_router(villages.router)
api_router.include_router(world.router)
api_router.include_router(combat.router)

if settings.ENVIRONMENT in ["test", "local"]:
    api_router.include_router(private.router)
