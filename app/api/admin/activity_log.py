from fastapi import APIRouter, Query
from sqlalchemy import select, desc

from app.core.deps import AdminUser, DbSession
from app.db.models.activity_log import ActivityLog
from app.db.models.order import Order
from app.db.models.user import User
from app.utils.pagination import paginate
from app.utils.casing import camelize

router = APIRouter(prefix="/activity-log", tags=["Admin - Activity Log"])

# One phrase per action the app actually logs, so the table reads as a
# sentence rather than a snake_case identifier. Anything not in here falls
# back to the raw value rather than raising — new action types are cheap
# to add on the write side and should not need a router change to be safe
# to display.
ACTION_LABELS = {
    "order_status_changed": "Order status changed",
    "order_deleted": "Order deleted",
}


def _describe(details: dict | None) -> str | None:
    """A plain-English line from the `details` JSON, when the shape is known.

    `details` is opaque by design — different actions store different keys —
    so this only handles the one shape that exists today and leaves anything
    else to render as raw JSON rather than guessing at a summary.
    """
    if not details:
        return None
    if "from" in details and "to" in details:
        return f"{details['from']} → {details['to']}"
    if "orderNumber" in details:
        # Written for a delete, where the join to Order below finds nothing
        # — the row is gone — so this is the only trace of which order it was.
        return details["orderNumber"]
    return None


@router.get("")
async def list_activity_logs(
    db: DbSession,
    admin: AdminUser,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100, alias="pageSize"),
    entity: str | None = None,
):
    query = select(ActivityLog).order_by(desc(ActivityLog.created_at))

    if entity:
        query = query.where(ActivityLog.entity == entity)

    result = await paginate(query, page, pageSize, db)
    logs = result["items"]

    # Resolved in two batches rather than a query per row — a page of 20
    # logs would otherwise cost up to 40 extra round trips.
    user_ids = {str(log.user_id) for log in logs if log.user_id}
    users = {}
    if user_ids:
        rows = await db.execute(select(User).where(User.id.in_(user_ids)))
        users = {
            str(u.id): f"{u.first_name} {u.last_name}".strip()
            for u in rows.scalars().all()
        }

    order_ids = {
        log.entity_id for log in logs if log.entity == "order" and log.entity_id
    }
    order_numbers = {}
    if order_ids:
        rows = await db.execute(
            select(Order.id, Order.order_number).where(Order.id.in_(order_ids))
        )
        order_numbers = {str(oid): number for oid, number in rows.all()}

    result["items"] = [
        {
            "id": str(log.id),
            "user_id": str(log.user_id) if log.user_id else None,
            "user_name": users.get(str(log.user_id)) if log.user_id else None,
            "action": log.action,
            "action_label": ACTION_LABELS.get(log.action, log.action),
            "entity": log.entity,
            "entity_id": log.entity_id,
            # An order's own number where one exists; the raw id is still
            # sent underneath so the dashboard can still link to it even for
            # an entity type this endpoint has no label for yet.
            "entity_label": order_numbers.get(log.entity_id)
            if log.entity_id
            else None,
            "details": log.details,
            "detail_summary": _describe(log.details),
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]
    return camelize(result)
