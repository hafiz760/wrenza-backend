from fastapi import APIRouter, Query
from sqlalchemy import select, desc

from app.core.deps import AdminUser, DbSession
from app.db.models.activity_log import ActivityLog
from app.utils.pagination import paginate
from app.utils.casing import camelize

router = APIRouter(prefix="/activity-log", tags=["Admin - Activity Log"])


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
    result["items"] = [
        {
            "id": str(log.id),
            "user_id": str(log.user_id) if log.user_id else None,
            "action": log.action,
            "entity": log.entity,
            "entity_id": log.entity_id,
            "details": log.details,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in result["items"]
    ]
    return camelize(result)
