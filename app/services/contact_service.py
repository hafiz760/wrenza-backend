import uuid

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.contact import ContactSubmission
from app.utils.pagination import paginate


async def list_contact_submissions(
    db: AsyncSession, page: int, page_size: int
) -> dict:
    result = await paginate(
        select(ContactSubmission).order_by(desc(ContactSubmission.created_at)),
        page,
        page_size,
        db,
    )
    result["items"] = [
        {
            "id": str(item.id),
            "name": item.name,
            "email": item.email,
            "phone": item.phone,
            "subject": item.subject,
            "message": item.message,
            "is_read": item.is_read,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in result["items"]
    ]
    return result


async def set_contact_submission_read(
    db: AsyncSession, submission_id: str, is_read: bool
) -> dict:
    try:
        submission_id = str(uuid.UUID(submission_id))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Contact message not found")

    submission = await db.scalar(
        select(ContactSubmission).where(ContactSubmission.id == submission_id)
    )
    if not submission:
        raise HTTPException(status_code=404, detail="Contact message not found")

    submission.is_read = is_read
    await db.commit()
    return {"id": str(submission.id), "is_read": submission.is_read}
