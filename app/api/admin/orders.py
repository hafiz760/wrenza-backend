from datetime import datetime

from fastapi import APIRouter, Query

from app.core.deps import AdminUser, DbSession, RedisClient
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
    search: str | None = Query(
        None, description="Matches order number, email, phone, or customer name."
    ),
    dateFrom: datetime | None = Query(None, alias="dateFrom"),
    dateTo: datetime | None = Query(None, alias="dateTo"),
):
    return await order_service.get_all_orders(
        db,
        page=page,
        page_size=pageSize,
        status_filter=status,
        search=search,
        date_from=dateFrom,
        date_to=dateTo,
    )


@router.get("/{order_id}")
async def get_order(order_id: str, db: DbSession, admin: AdminUser):
    """Full order detail. Unlike the customer route, not scoped to one user."""
    return await order_service.get_order_admin(db, order_id)


@router.put("/{order_id}/status")
async def update_order_status(
    order_id: str, data: OrderStatusUpdate, admin: AdminUser, db: DbSession
):
    """Move the order through its lifecycle. Cancelling restores stock."""
    return await order_service.update_order_status(db, order_id, data, admin_id=admin.id)


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: str, admin: AdminUser, db: DbSession, redis: RedisClient
):
    """Cancel any order and return its units to stock."""
    return await order_service.cancel_order(db, order_id, admin_id=admin.id, redis=redis)
