from fastapi import APIRouter

from app.core.deps import DbSession
from app.services import promotion_service

router = APIRouter(prefix="/banners", tags=["Banners"])


@router.get("")
async def list_banners(db: DbSession):
    return await promotion_service.list_active_banners(db)
