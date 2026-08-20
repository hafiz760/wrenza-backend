from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import selectinload

from app.core.deps import AdminUser, DbSession, RedisClient
from app.utils.cache import cache_delete_pattern
from app.db.models.product import Product
from app.db.models.review import Review
from app.schemas.common import CamelModel, MessageResponse
from app.utils.casing import camelize
from app.utils.pagination import paginate

router = APIRouter(prefix="/reviews", tags=["Admin - Reviews"])


class ReviewModerationOut(CamelModel):
    id: str
    product_id: str
    product_name: str
    customer_name: str
    rating: int
    comment: str | None
    is_approved: bool
    created_at: str | None


async def _recalculate_product_rating(db, product_id: str) -> None:
    """Recompute a product's rating from its approved reviews only.

    `Product.rating` and `review_count` feed the storefront's aggregateRating
    structured data, so a rejected review must stop counting immediately —
    otherwise the rich result shows a score no visible review supports.
    """
    stats = await db.execute(
        select(func.avg(Review.rating), func.count(Review.id)).where(
            Review.product_id == product_id, Review.is_approved.is_(True)
        )
    )
    average, count = stats.one()

    product = await db.scalar(select(Product).where(Product.id == product_id))
    if product:
        product.rating = round(float(average), 1) if average else 0.0
        product.review_count = count or 0


@router.get("")
async def list_reviews(
    db: DbSession,
    admin: AdminUser,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100, alias="pageSize"),
    status: str | None = Query(
        None, description="'pending' or 'approved'; omit for all."
    ),
    productId: str | None = Query(None, alias="productId"),
):
    query = (
        select(Review)
        .options(selectinload(Review.product), selectinload(Review.user))
        .order_by(desc(Review.created_at))
    )

    if status == "pending":
        query = query.where(Review.is_approved.is_(False))
    elif status == "approved":
        query = query.where(Review.is_approved.is_(True))
    if productId:
        query = query.where(Review.product_id == productId)

    result = await paginate(query, page, pageSize, db)
    result["items"] = [
        {
            "id": str(review.id),
            "product_id": str(review.product_id),
            "product_name": review.product.name if review.product else "—",
            # A guest review has no user row; fall back to what they typed.
            "customer_name": (
                f"{review.user.first_name} {review.user.last_name}".strip()
                if review.user
                else (review.guest_name or "—")
            ),
            # Admin-only. Never present in the public review payload.
            "customer_email": (
                review.user.email if review.user else review.guest_email
            ),
            "is_guest": review.user_id is None,
            "rating": review.rating,
            "comment": review.comment,
            "is_approved": review.is_approved,
            "created_at": (
                review.created_at.isoformat() if review.created_at else None
            ),
        }
        for review in result["items"]
    ]
    return camelize(result)


@router.put("/{review_id}/approve")
async def set_review_approval(
    review_id: str,
    admin: AdminUser,
    db: DbSession,
    redis: RedisClient,
    approved: bool = True,
):
    review = await db.scalar(select(Review).where(Review.id == review_id))
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    review.is_approved = approved
    await _recalculate_product_rating(db, review.product_id)
    await db.commit()

    # Approving or hiding changes the product's rating and review count, both
    # of which sit inside the cached product payloads.
    await cache_delete_pattern(redis, "products:*")

    return camelize(
        {
            "id": str(review.id),
            "is_approved": review.is_approved,
            "message": "Review approved" if approved else "Review hidden",
        }
    )


@router.delete("/{review_id}", response_model=MessageResponse)
async def delete_review(
    review_id: str, admin: AdminUser, db: DbSession, redis: RedisClient
):
    review = await db.scalar(select(Review).where(Review.id == review_id))
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    product_id = review.product_id
    await db.delete(review)
    await db.flush()
    await _recalculate_product_rating(db, product_id)
    await db.commit()
    await cache_delete_pattern(redis, "products:*")

    return MessageResponse(message="Review deleted")
