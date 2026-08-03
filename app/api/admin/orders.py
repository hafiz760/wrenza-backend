from fastapi import APIRouter, Query

from app.core.deps import AdminUser, DbSession
from app.schemas.order import OrderStatusUpdate
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["Admin - Orders"])


@router.get("")
async def list_orders(
    db: DbSession,
    admin: AdminUser,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100, alias="pageSize"),
    status: str | None = None,
):
    return await order_service.get_all_orders(db, page=page, page_size=pageSize, status_filter=status)


@router.put("/{order_id}/status")
async def update_order_status(
    order_id: str, data: OrderStatusUpdate, admin: AdminUser, db: DbSession
):
    return await order_service.update_order_status(db, order_id, data)
