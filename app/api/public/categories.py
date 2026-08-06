from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import noload

from app.core.deps import DbSession, RedisClient
from app.db.models.product import Category
from app.utils.cache import cache_get, cache_key, cache_set

router = APIRouter(prefix="/categories", tags=["Categories"])


def _build_tree(categories: list[Category]) -> list[dict]:
    """Assemble the category tree in Python, to any depth, from one query.

    Walking `Category.children` instead would lazy-load a level at a time, and
    a self-referential eager load only covers a fixed depth — so any category
    nested deeper than that blows up with MissingGreenlet.
    """
    nodes = {
        str(c.id): {
            "id": str(c.id),
            "name": c.name,
            "slug": c.slug,
            "description": c.description,
            "imageUrl": c.image_url,
            "children": [],
        }
        for c in categories
    }

    roots: list[dict] = []
    for c in categories:
        node = nodes[str(c.id)]
        # A child whose parent is inactive is unreachable, so it is dropped
        # rather than promoted to the root.
        parent = nodes.get(str(c.parent_id)) if c.parent_id else None
        if parent is not None:
            parent["children"].append(node)
        elif c.parent_id is None:
            roots.append(node)

    return roots


@router.get("")
async def list_categories(db: DbSession, redis: RedisClient):
    ck = cache_key("categories", "tree")
    cached = await cache_get(redis, ck)
    if cached:
        return cached

    result = await db.execute(
        select(Category)
        .options(noload(Category.children))
        .where(Category.is_active.is_(True))
        .order_by(Category.name)
    )
    data = _build_tree(list(result.scalars().all()))

    await cache_set(redis, ck, data, ttl=600)
    return data
