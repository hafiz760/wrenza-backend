from fastapi import APIRouter, Query

from app.core.deps import AdminUser, DbSession
from app.schemas.common import MessageResponse
from app.services import contact_service
from app.utils.casing import camelize

router = APIRouter(prefix="/contact-submissions", tags=["Admin - Contact"])


@router.get("")
async def list_contact_submissions(
    db: DbSession,
    admin: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
):
    return camelize(
        await contact_service.list_contact_submissions(db, page, page_size)
    )


@router.put("/{submission_id}/read")
async def set_contact_submission_read(
    submission_id: str,
    admin: AdminUser,
    db: DbSession,
    is_read: bool = Query(..., alias="isRead"),
):
    result = await contact_service.set_contact_submission_read(
        db, submission_id, is_read
    )
    result["message"] = "Contact message updated"
    return camelize(result)
