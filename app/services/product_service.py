from uuid import UUID

from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy import select, desc, asc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.product import Product, ProductImage, Category
from app.schemas.product import (
    ProductCreate,
    ProductImageOut,
    ProductListOut,
    ProductOut,
    ProductUpdate,
)
from app.schemas.common import PaginatedResponse
from app.utils.cache import (
    TTL_LONG,
    TTL_MEDIUM,
    TTL_SHORT,
    cache_delete_pattern,
    cache_get,
    cache_key,
    cache_set,
)
from app.utils.pagination import paginate
from app.utils.slug import ensure_unique_slug, generate_slug


def _image_to_out(img: ProductImage) -> ProductImageOut:
    return ProductImageOut(
        id=str(img.id),
        url=img.url,
        alt=img.alt,
        width=img.width,
        height=img.height,
    )


def _split_images(p: Product) -> tuple[ProductImageOut | None, list[ProductImageOut]]:
    """Separate the feature image from the gallery.

    Products created before feature images existed have nothing flagged, so the
    first gallery image stands in and the gallery is left whole.
    """
    featured = next((img for img in p.images if img.is_featured), None)
    if featured is not None:
        gallery = [img for img in p.images if not img.is_featured]
        return _image_to_out(featured), [_image_to_out(img) for img in gallery]

    gallery_out = [_image_to_out(img) for img in p.images]
    return (gallery_out[0] if gallery_out else None), gallery_out


def _product_to_list_out(p: Product) -> ProductListOut:
    featured, gallery = _split_images(p)
    return ProductListOut(
        id=str(p.id),
        slug=p.slug,
        name=p.name,
        price=float(p.price),
        compare_at_price=float(p.compare_at_price) if p.compare_at_price else None,
        currency=p.currency,
        featured_image=featured,
        images=gallery,
        category=p.category.slug if p.category else None,
        rating=float(p.rating),
        review_count=p.review_count,
        stock=p.stock,
        is_featured=p.is_featured,
        is_new_arrival=p.is_new_arrival,
    )


def _product_to_full_out(p: Product) -> ProductOut:
    featured, gallery = _split_images(p)
    return ProductOut(
        id=str(p.id),
        slug=p.slug,
        name=p.name,
        description=p.description,
        price=float(p.price),
        compare_at_price=float(p.compare_at_price) if p.compare_at_price else None,
        currency=p.currency,
        featured_image=featured,
        images=gallery,
        category=p.category.slug if p.category else None,
        product_type=p.product_type,
        material=p.material,
        leather_type=p.leather_type,
        dimensions=p.dimensions or {},
        hardware_finish=p.hardware_finish,
        closure_type=p.closure_type,
        sizes=p.sizes or [],
        colors=p.colors or [],
        fabric=p.fabric,
        care_instructions=p.care_instructions or [],
        tags=p.tags or [],
        rating=float(p.rating),
        review_count=p.review_count,
        stock=p.stock,
        is_featured=p.is_featured,
        is_new_arrival=p.is_new_arrival,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


async def list_products(
    db: AsyncSession,
    redis: Redis | None,
    category: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    product_type: str | None = None,
    material: str | None = None,
    leather_type: str | None = None,
    sizes: str | None = None,
    colors: str | None = None,
    fabric: str | None = None,
    sort_by: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 12,
) -> PaginatedResponse[ProductListOut]:
    query = (
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(Product.is_active.is_(True))
    )

    if category:
        query = query.join(Category).where(Category.slug == category)
    if min_price is not None:
        query = query.where(Product.price >= min_price)
    if max_price is not None:
        query = query.where(Product.price <= max_price)
    if product_type:
        query = query.where(Product.product_type == product_type)
    if material:
        query = query.where(Product.material.ilike(f"%{material}%"))
    if leather_type:
        query = query.where(Product.leather_type.ilike(f"%{leather_type}%"))
    if fabric:
        query = query.where(Product.fabric.ilike(f"%{fabric}%"))
    if search:
        query = query.where(
            or_(
                Product.name.ilike(f"%{search}%"),
                Product.description.ilike(f"%{search}%"),
                Product.tags.cast(str).ilike(f"%{search}%"),
                Product.material.ilike(f"%{search}%"),
                Product.leather_type.ilike(f"%{search}%"),
            )
        )

    if sort_by == "price_asc":
        query = query.order_by(asc(Product.price))
    elif sort_by == "price_desc":
        query = query.order_by(desc(Product.price))
    elif sort_by == "popular":
        query = query.order_by(desc(Product.review_count))
    elif sort_by == "rating":
        query = query.order_by(desc(Product.rating))
    else:
        query = query.order_by(desc(Product.created_at))

    result = await paginate(query, page, page_size, db)

    items = [_product_to_list_out(p) for p in result["items"]]

    return PaginatedResponse(
        items=items,
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        total_pages=result["total_pages"],
    )


async def get_by_slug(db: AsyncSession, redis: Redis | None, slug: str) -> ProductOut:
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(Product.slug == slug, Product.is_active.is_(True))
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return _product_to_full_out(product)


async def get_featured(
    db: AsyncSession, redis: Redis | None, limit: int = 8
) -> list[ProductListOut]:
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(Product.is_active.is_(True), Product.is_featured.is_(True))
        .order_by(desc(Product.created_at))
        .limit(limit)
    )
    products = result.scalars().all()
    return [_product_to_list_out(p) for p in products]


async def get_new_arrivals(
    db: AsyncSession, redis: Redis | None, limit: int = 8
) -> list[ProductListOut]:
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(Product.is_active.is_(True), Product.is_new_arrival.is_(True))
        .order_by(desc(Product.created_at))
        .limit(limit)
    )
    products = result.scalars().all()
    return [_product_to_list_out(p) for p in products]


async def get_related(
    db: AsyncSession, product_id: str, limit: int = 4
) -> list[ProductListOut]:
    product = await db.scalar(select(Product).where(Product.id == product_id))
    if not product:
        return []

    result = await db.execute(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(
            Product.is_active.is_(True),
            Product.category_id == product.category_id,
            Product.id != product.id,
        )
        .order_by(desc(Product.rating))
        .limit(limit)
    )
    products = result.scalars().all()
    return [_product_to_list_out(p) for p in products]


async def create_product(
    db: AsyncSession, redis: Redis | None, data: ProductCreate
) -> ProductOut:
    slug = data.slug or generate_slug(data.name)
    slug = await ensure_unique_slug(db, Product, slug)

    product = Product(
        slug=slug,
        name=data.name,
        description=data.description,
        price=data.price,
        compare_at_price=data.compare_at_price,
        category_id=data.category_id,
        product_type=data.product_type,
        material=data.material,
        leather_type=data.leather_type,
        dimensions=data.dimensions.model_dump(),
        hardware_finish=data.hardware_finish,
        closure_type=data.closure_type,
        fabric=data.fabric,
        gender=data.gender,
        sizes=[s.model_dump() for s in data.sizes],
        colors=[c.model_dump() for c in data.colors],
        care_instructions=data.care_instructions,
        tags=data.tags,
        stock=data.stock,
        is_featured=data.is_featured,
        is_new_arrival=data.is_new_arrival,
        meta_title=data.meta_title,
        meta_description=data.meta_description,
    )
    db.add(product)
    await db.flush()

    if data.featured_image:
        fi = data.featured_image
        db.add(
            ProductImage(
                product_id=product.id,
                url=fi.url,
                alt=fi.alt,
                width=fi.width,
                height=fi.height,
                position=-1,
                is_featured=True,
            )
        )

    for i, img in enumerate(data.images):
        db.add(
            ProductImage(
                product_id=product.id,
                url=img.url,
                alt=img.alt,
                width=img.width,
                height=img.height,
                position=img.position or i,
            )
        )

    await db.commit()

    result = await db.execute(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(Product.id == product.id)
    )
    product = result.scalar_one()

    if redis:
        await cache_delete_pattern(redis, "products:*")

    return _product_to_full_out(product)


async def update_product(
    db: AsyncSession, redis: Redis | None, product_id: str, data: ProductUpdate
) -> ProductOut:
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = data.model_dump(exclude_unset=True)

    # Handle slug update
    if "slug" in update_data and update_data["slug"]:
        update_data["slug"] = await ensure_unique_slug(
            db, Product, update_data["slug"], exclude_id=product.id
        )

    # Convert nested Pydantic models to dicts for JSONB
    if "sizes" in update_data and update_data["sizes"] is not None:
        update_data["sizes"] = [
            s.model_dump() if hasattr(s, "model_dump") else s
            for s in update_data["sizes"]
        ]
    if "colors" in update_data and update_data["colors"] is not None:
        update_data["colors"] = [
            c.model_dump() if hasattr(c, "model_dump") else c
            for c in update_data["colors"]
        ]
    if "dimensions" in update_data and update_data["dimensions"] is not None:
        update_data["dimensions"] = (
            update_data["dimensions"].model_dump()
            if hasattr(update_data["dimensions"], "model_dump")
            else update_data["dimensions"]
        )

    # Not a Product column — replace the flagged ProductImage row instead
    featured_data = update_data.pop("featured_image", None)
    if featured_data is not None:
        for img in product.images:
            if img.is_featured:
                await db.delete(img)
        await db.flush()
        db.add(
            ProductImage(
                product_id=product.id,
                url=featured_data["url"],
                alt=featured_data["alt"],
                width=featured_data["width"],
                height=featured_data["height"],
                position=-1,
                is_featured=True,
            )
        )

    for key, value in update_data.items():
        if hasattr(product, key):
            setattr(product, key, value)

    await db.commit()

    # Re-fetch with relationships for full output
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(Product.id == product.id)
    )
    product = result.scalar_one()

    if redis:
        await cache_delete_pattern(redis, "products:*")

    return _product_to_full_out(product)


async def delete_product(
    db: AsyncSession, redis: Redis | None, product_id: str
) -> None:
    product = await db.scalar(select(Product).where(Product.id == product_id))
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.is_active = False
    await db.commit()

    if redis:
        await cache_delete_pattern(redis, "products:*")
