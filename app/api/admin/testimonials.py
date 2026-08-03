from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.core.deps import AdminUser, DbSession
from app.db.models.review import Testimonial
from app.schemas.review import TestimonialCreate

router = APIRouter(prefix="/testimonials", tags=["Admin - Testimonials"])


@router.get("")
async def list_testimonials(db: DbSession, admin: AdminUser):
    result = await db.execute(select(Testimonial))
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "location": t.location,
            "avatar": t.avatar,
            "comment": t.comment,
            "rating": t.rating,
            "is_active": t.is_active,
        }
        for t in result.scalars().all()
    ]


@router.post("")
async def create_testimonial(data: TestimonialCreate, admin: AdminUser, db: DbSession):
    testimonial = Testimonial(
        name=data.name,
        location=data.location,
        avatar=data.avatar,
        comment=data.comment,
        rating=data.rating,
    )
    db.add(testimonial)
    await db.commit()
    await db.refresh(testimonial)
    return {
        "id": str(testimonial.id),
        "name": testimonial.name,
        "location": testimonial.location,
        "avatar": testimonial.avatar,
        "comment": testimonial.comment,
        "rating": testimonial.rating,
        "is_active": testimonial.is_active,
    }


@router.put("/{testimonial_id}")
async def update_testimonial(testimonial_id: str, data: TestimonialCreate, admin: AdminUser, db: DbSession):
    testimonial = await db.scalar(select(Testimonial).where(Testimonial.id == testimonial_id))
    if not testimonial:
        raise HTTPException(status_code=404, detail="Testimonial not found")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(testimonial, key, value)

    await db.commit()
    await db.refresh(testimonial)
    return {
        "id": str(testimonial.id),
        "name": testimonial.name,
        "location": testimonial.location,
        "avatar": testimonial.avatar,
        "comment": testimonial.comment,
        "rating": testimonial.rating,
        "is_active": testimonial.is_active,
    }


@router.delete("/{testimonial_id}")
async def delete_testimonial(testimonial_id: str, admin: AdminUser, db: DbSession):
    testimonial = await db.scalar(select(Testimonial).where(Testimonial.id == testimonial_id))
    if not testimonial:
        raise HTTPException(status_code=404, detail="Testimonial not found")
    await db.delete(testimonial)
    await db.commit()
    return {"message": "Testimonial deleted"}
