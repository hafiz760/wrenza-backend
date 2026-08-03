from fastapi import APIRouter

from app.core.deps import AdminUser, DbSession
from app.schemas.promotion import DiscountCreate, DiscountUpdate
from app.services import promotion_service

router = APIRouter(prefix="/discounts", tags=["Admin - Discounts"])


@router.get("")
async def list_discounts(db: DbSession, admin: AdminUser):
    return await promotion_service.list_discounts(db)


@router.post("")
async def create_discount(data: DiscountCreate, admin: AdminUser, db: DbSession):
    return await promotion_service.create_discount(db, data)


@router.put("/{discount_id}")
async def update_discount(discount_id: str, data: DiscountUpdate, admin: AdminUser, db: DbSession):
    return await promotion_service.update_discount(db, discount_id, data)


@router.delete("/{discount_id}")
async def delete_discount(discount_id: str, admin: AdminUser, db: DbSession):
    await promotion_service.delete_discount(db, discount_id)
    return {"message": "Discount deleted"}
