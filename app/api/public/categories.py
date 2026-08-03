from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import DbSession, RedisClient
from app.db.models.product import Category
from app.utils.cache import cache_get, cache_key, cache_set

router = APIRouter(prefix="/categories", tags=["Categories"])


def _category_to_out(c: Category) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "slug": c.slug,
        "description": c.description,
        "image_url": c.image_url,
        "children": [_category_to_out(child) for child in c.children if child.is_active],
    }


@router.get("")
async def list_categories(db: DbSession, redis: RedisClient):
    ck = cache_key("categories", "tree")
    cached = await cache_get(redis, ck)
    if cached:
        return cached

    result = await db.execute(
        select(Category)
        .options(selectinload(Category.children))
        .where(Category.is_active.is_(True), Category.parent_id.is_(None))
        .order_by(Category.name)
    )
    categories = result.scalars().all()
    data = [_category_to_out(c) for c in categories]

    await cache_set(redis, ck, data, ttl=600)
    return data
