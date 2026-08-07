from fastapi import HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product import Collection
from app.schemas.collection import CollectionCreate, CollectionUpdate
from app.utils.slug import ensure_unique_slug, generate_slug
from app.utils.casing import camelize


def _collection_to_out(c: Collection, *, include_status: bool = False) -> dict:
    data = {
        "id": str(c.id),
        "slug": c.slug,
        "name": c.name,
        "tagline": c.tagline,
        "description": c.description,
        "image": c.image,
        "product_ids": [str(pid) for pid in (c.product_ids or [])],
        "season": c.season,
        "year": c.year,
        "is_featured": c.is_featured,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
    # The public listing only ever returns active collections, so the flag
    # would always be true there. The admin needs it to render the status and
    # to know what the toggle currently says.
    if include_status:
        data["is_active"] = c.is_active
    return camelize(data)


async def list_collections(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Collection)
        .where(Collection.is_active.is_(True))
        .order_by(desc(Collection.created_at))
    )
    return [_collection_to_out(c) for c in result.scalars().all()]


async def list_collections_admin(db: AsyncSession) -> list[dict]:
    """Every collection, active or not.

    The admin list must not reuse the public one. Deactivating a collection
    would drop it from the only screen that can reactivate it, leaving no way
    back through the dashboard.
    """
    result = await db.execute(
        select(Collection).order_by(desc(Collection.created_at))
    )
    return [
        _collection_to_out(c, include_status=True) for c in result.scalars().all()
    ]


async def get_by_slug(db: AsyncSession, slug: str) -> dict:
    result = await db.scalar(
        select(Collection).where(Collection.slug == slug, Collection.is_active.is_(True))
    )
    if not result:
        raise HTTPException(status_code=404, detail="Collection not found")
    return _collection_to_out(result)


async def create_collection(db: AsyncSession, data: CollectionCreate) -> dict:
    slug = data.slug or generate_slug(data.name)
    slug = await ensure_unique_slug(db, Collection, slug)

    collection = Collection(
        slug=slug,
        name=data.name,
        tagline=data.tagline,
        description=data.description,
        image=data.image,
        product_ids=data.product_ids,
        season=data.season,
        year=data.year,
        is_featured=data.is_featured,
    )
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    # Admin-only response — the dashboard renders status straight from this
    return _collection_to_out(collection, include_status=True)


async def update_collection(db: AsyncSession, collection_id: str, data: CollectionUpdate) -> dict:
    collection = await db.scalar(select(Collection).where(Collection.id == collection_id))
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    update_data = data.model_dump(exclude_unset=True)

    if "slug" in update_data and update_data["slug"]:
        update_data["slug"] = await ensure_unique_slug(
            db, Collection, update_data["slug"], exclude_id=collection.id
        )

    for key, value in update_data.items():
        if hasattr(collection, key):
            setattr(collection, key, value)

    await db.commit()
    await db.refresh(collection)
    return _collection_to_out(collection, include_status=True)


async def delete_collection(db: AsyncSession, collection_id: str) -> None:
    collection = await db.scalar(select(Collection).where(Collection.id == collection_id))
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    collection.is_active = False
    await db.commit()
