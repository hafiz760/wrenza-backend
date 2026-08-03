from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.schemas.order import OrderCreate
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("")
async def place_order(data: OrderCreate, user: CurrentUser, db: DbSession):
    return await order_service.create_order(db, user.id, data)


@router.get("")
async def list_my_orders(user: CurrentUser, db: DbSession):
    return await order_service.get_user_orders(db, user.id)


@router.get("/{order_id}")
async def get_order(order_id: str, user: CurrentUser, db: DbSession):
    return await order_service.get_order_detail(db, user.id, order_id)
