from uuid import UUID

from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product import Product
from app.db.models.review import Review
from app.db.models.user import User
from app.schemas.review import ReviewCreate
from app.utils.cache import cache_delete_pattern


def _review_to_out(r: Review, user: User | None = None) -> dict:
    user_name = ""
    if user:
        user_name = f"{user.first_name} {user.last_name}"
    return {
        "id": str(r.id),
        "user_id": str(r.user_id),
        "user_name": user_name,
        "rating": r.rating,
        "comment": r.comment,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


async def create_review(db: AsyncSession, user_id: UUID, data: ReviewCreate, redis: Redis | None = None) -> dict:
    # Validate rating
    if data.rating < 1 or data.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    # Check product exists
    product = await db.scalar(
        select(Product).where(Product.id == data.product_id, Product.is_active.is_(True))
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Check for existing review
    existing = await db.scalar(
        select(Review).where(
            Review.product_id == data.product_id, Review.user_id == user_id
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="You already reviewed this product")

    review = Review(
        product_id=data.product_id,
        user_id=user_id,
        rating=data.rating,
        comment=data.comment,
    )
    db.add(review)
    await db.flush()

    # Update product rating and review count
    avg_result = await db.execute(
        select(func.avg(Review.rating), func.count(Review.id)).where(
            Review.product_id == data.product_id, Review.is_approved.is_(True)
        )
    )
    avg_rating, count = avg_result.one()
    product.rating = round(float(avg_rating or 0), 1)
    product.review_count = count or 0

    await db.commit()

    # Invalidate product caches since rating/review_count changed
    if redis:
        await cache_delete_pattern(redis, "products:detail:*")
        await cache_delete_pattern(redis, "products:featured")
        await cache_delete_pattern(redis, "products:new-arrivals")

    user = await db.scalar(select(User).where(User.id == user_id))
    return _review_to_out(review, user)


async def list_reviews_for_product(
    db: AsyncSession, product_id: str
) -> list[dict]:
    result = await db.execute(
        select(Review, User)
        .join(User, Review.user_id == User.id)
        .where(Review.product_id == product_id, Review.is_approved.is_(True))
        .order_by(desc(Review.created_at))
    )
    return [_review_to_out(r, u) for r, u in result.all()]
