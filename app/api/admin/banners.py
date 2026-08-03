from fastapi import APIRouter

from app.core.deps import AdminUser, DbSession
from app.schemas.promotion import BannerCreate, BannerUpdate
from app.services import promotion_service

router = APIRouter(prefix="/banners", tags=["Admin - Banners"])


@router.get("")
async def list_banners(db: DbSession, admin: AdminUser):
    return await promotion_service.list_all_banners(db)


@router.post("")
async def create_banner(data: BannerCreate, admin: AdminUser, db: DbSession):
    return await promotion_service.create_banner(db, data)


@router.put("/{banner_id}")
async def update_banner(banner_id: str, data: BannerUpdate, admin: AdminUser, db: DbSession):
    return await promotion_service.update_banner(db, banner_id, data)


@router.delete("/{banner_id}")
async def delete_banner(banner_id: str, admin: AdminUser, db: DbSession):
    await promotion_service.delete_banner(db, banner_id)
    return {"message": "Banner deleted"}
