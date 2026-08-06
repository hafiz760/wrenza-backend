import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.core.deps import AdminUser, DbSession, RedisClient
from app.db.models.product import Category, Product
from app.schemas.product import CategoryCreate, CategoryUpdate
from app.utils.cache import cache_delete_pattern
from app.utils.slug import ensure_unique_slug, generate_slug
from app.utils.casing import camelize

router = APIRouter(prefix="/categories", tags=["Admin - Categories"])


def _category_out(c: Category) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "slug": c.slug,
        "description": c.description,
        "image_url": c.image_url,
        "parent_id": str(c.parent_id) if c.parent_id else None,
        "is_active": c.is_active,
    }


async def _get_or_404(db, category_id: str) -> Category:
    """Fetch by id, treating an unparseable id as not-found.

    Ids reach the database as UUIDs, so without this guard a malformed path
    segment raises from the type decorator and surfaces as a 500.
    """
    try:
        uuid.UUID(str(category_id))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Category not found")

    category = await db.scalar(select(Category).where(Category.id == category_id))
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.get("")
async def list_categories(db: DbSession, admin: AdminUser):
    result = await db.execute(select(Category).order_by(Category.name))
    return camelize([_category_out(c) for c in result.scalars().all()])


@router.get("/{category_id}")
async def get_category(category_id: str, db: DbSession, admin: AdminUser):
    return camelize(_category_out(await _get_or_404(db, category_id)))


@router.post("")
async def create_category(data: CategoryCreate, admin: AdminUser, db: DbSession, redis: RedisClient):
    slug = data.slug or generate_slug(data.name)
    slug = await ensure_unique_slug(db, Category, slug)

    category = Category(
        name=data.name,
        slug=slug,
        description=data.description,
        image_url=data.image_url,
        parent_id=data.parent_id,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)

    await cache_delete_pattern(redis, "categories:*")

    return camelize(_category_out(category))


@router.put("/{category_id}")
async def update_category(
    category_id: str, data: CategoryUpdate, admin: AdminUser, db: DbSession, redis: RedisClient
):
    category = await _get_or_404(db, category_id)

    update_data = data.model_dump(exclude_unset=True)

    if "slug" in update_data and update_data["slug"]:
        update_data["slug"] = await ensure_unique_slug(
            db, Category, update_data["slug"], exclude_id=category.id
        )

    for key, value in update_data.items():
        setattr(category, key, value)

    await db.commit()
    await db.refresh(category)

    await cache_delete_pattern(redis, "categories:*")

    return camelize(_category_out(category))


@router.delete("/{category_id}")
async def delete_category(
    category_id: str,
    admin: AdminUser,
    db: DbSession,
    redis: RedisClient,
    force: bool = False,
):
    """Remove the category row from the database.

    To hide a category without deleting it, use
    `PUT /admin/categories/{id}` with `{"isActive": false}`.

    Both foreign keys pointing at categories are ON DELETE SET NULL, so deleting
    a category in use silently uncategorizes its products and promotes its
    children to top level. That is refused by default; `force=true` accepts it.
    """
    category = await _get_or_404(db, category_id)

    product_count = await db.scalar(
        select(func.count(Product.id)).where(Product.category_id == category_id)
    )
    child_count = await db.scalar(
        select(func.count(Category.id)).where(Category.parent_id == category_id)
    )

    if (product_count or child_count) and not force:
        blockers = []
        if product_count:
            blockers.append(f"{product_count} product(s)")
        if child_count:
            blockers.append(f"{child_count} subcategory(ies)")
        raise HTTPException(
            status_code=409,
            detail=(
                f"Category is in use by {' and '.join(blockers)}. "
                "Pass force=true to delete anyway — products will become "
                "uncategorized and subcategories will move to top level."
            ),
        )

    await db.delete(category)
    await db.commit()

    await cache_delete_pattern(redis, "categories:*")
    return camelize({
        "message": "Category permanently deleted",
        "products_uncategorized": product_count or 0,
        "subcategories_promoted": child_count or 0,
    })
