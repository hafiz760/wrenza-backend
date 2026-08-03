from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import DbSession
from app.db.models.review import Testimonial

router = APIRouter(prefix="/testimonials", tags=["Testimonials"])


@router.get("")
async def list_testimonials(db: DbSession):
    result = await db.execute(
        select(Testimonial).where(Testimonial.is_active.is_(True))
    )
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "location": t.location,
            "avatar": t.avatar,
            "comment": t.comment,
            "rating": t.rating,
        }
        for t in result.scalars().all()
    ]
