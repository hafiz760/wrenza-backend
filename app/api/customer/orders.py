from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession, RedisClient
from app.schemas.order import OrderCreate
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("")
async def place_order(
    data: OrderCreate, user: CurrentUser, db: DbSession, redis: RedisClient
):
    return await order_service.create_order(db, user.id, data, redis=redis)


@router.get("")
async def list_my_orders(user: CurrentUser, db: DbSession):
    return await order_service.get_user_orders(db, user.id)


@router.get("/{order_id}")
async def get_order(order_id: str, user: CurrentUser, db: DbSession):
    return await order_service.get_order_detail(db, user.id, order_id)


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: str, user: CurrentUser, db: DbSession, redis: RedisClient
):
    """Cancel your own order while it is still cancellable."""
    return await order_service.cancel_order(db, order_id, user_id=user.id, redis=redis)
