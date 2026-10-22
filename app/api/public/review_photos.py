from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core.deps import DbSession
from app.db.models.product import Product
from app.db.models.review import Review
from app.db.models.user import User
from app.schemas.common import CamelModel

router = APIRouter(prefix="/review-photos", tags=["Review Photos"])


class ReviewGalleryOut(CamelModel):
    id: str
    review_id: str
    images: list[str]
    product_name: str
    product_slug: str
    reviewer_name: str
    rating: int
    comment: str | None = None


@router.get("", response_model=list[ReviewGalleryOut])
async def list_review_photos(
    db: DbSession,
    limit: int = Query(24, ge=1, le=60),
):
    """Recent approved customer reviews with photos for the storefront gallery."""
    result = await db.execute(
        select(Review, Product, User)
        .join(Product, Review.product_id == Product.id)
        .outerjoin(User, Review.user_id == User.id)
        .where(
            Review.is_approved.is_(True),
            Product.is_active.is_(True),
            func.json_array_length(Review.images) > 0,
        )
        .order_by(Review.created_at.desc())
        .limit(limit)
    )

    galleries: list[ReviewGalleryOut] = []
    for review, product, user in result.all():
        reviewer_name = (
            f"{user.first_name} {user.last_name}".strip()
            if user
            else (review.guest_name or "Wrenza customer").strip()
        )
        galleries.append(
            ReviewGalleryOut(
                id=str(review.id),
                review_id=str(review.id),
                images=review.images or [],
                product_name=product.name,
                product_slug=product.slug,
                reviewer_name=reviewer_name,
                rating=review.rating,
                comment=review.comment,
            )
        )
    return galleries
