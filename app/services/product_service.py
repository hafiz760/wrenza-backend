import hashlib
import json
from uuid import UUID

from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy import select, desc, asc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.attribute import Attribute, AttributeTerm
from app.db.models.product import Product, ProductImage, Category
from app.db.models.variation import ProductAttribute, ProductAttributeTerm
from app.schemas.product import (
    PriceRange,
    ProductSwatchOut,
    ProductCreate,
    ProductImageOut,
    ProductListOut,
    ProductOut,
    ProductUpdate,
)
from app.schemas.common import PaginatedResponse
from app.schemas.faq import FaqOut
from app.schemas.filters import (
    FilterAttributeOut,
    FilterTermOut,
    PriceBoundsOut,
    ProductFiltersOut,
)
from app.schemas.variation import ProductAttributeOut, VariationOut
from app.services import faq_service, variation_service
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


def _derived(p: Product) -> tuple[float, PriceRange | None, int]:
    """Price, price range and stock for a product.

    Simple products own their price and stock. For variable products both are
    derived from the active variations, so the two can never disagree.
    """
    if p.kind != "variable":
        return float(p.price), None, p.stock

    active = [v for v in p.variations if v.is_active]
    if not active:
        return float(p.price), None, 0

    prices = [float(v.price) for v in active]
    return (
        min(prices),
        PriceRange(min=min(prices), max=max(prices)),
        sum(v.stock for v in active),
    )


async def load_swatches(
    db: AsyncSession, products: list[Product]
) -> dict[str, list[ProductSwatchOut]]:
    """Colour options per product, for the swatch row on a card.

    One query for the whole page rather than one per product: a 12-card grid
    would otherwise cost 12 round-trips for decoration.
    """
    if not products:
        return {}

    rows = await db.execute(
        select(
            ProductAttribute.product_id,
            AttributeTerm.id,
            AttributeTerm.value,
            AttributeTerm.slug,
            AttributeTerm.meta,
        )
        .join(
            ProductAttributeTerm,
            ProductAttributeTerm.product_attribute_id == ProductAttribute.id,
        )
        .join(AttributeTerm, AttributeTerm.id == ProductAttributeTerm.term_id)
        .where(ProductAttribute.product_id.in_([str(p.id) for p in products]))
        .order_by(AttributeTerm.position, AttributeTerm.value)
    )

    swatches: dict[str, list[ProductSwatchOut]] = {}
    for product_id, term_id, value, slug, meta in rows.all():
        # A colour term is one the admin gave a swatch hex; everything else is
        # a size or a finish and has nothing to show as a dot
        hex_value = (meta or {}).get("hex")
        if not hex_value:
            continue
        swatches.setdefault(str(product_id), []).append(
            ProductSwatchOut(
                term_id=str(term_id), value=value, slug=slug, hex=hex_value
            )
        )

    return swatches


def _product_to_list_out(
    p: Product, swatches: list[ProductSwatchOut] | None = None
) -> ProductListOut:
    featured, gallery = _split_images(p)
    price, price_range, stock = _derived(p)
    return ProductListOut(
        kind=p.kind,
        swatches=swatches or [],
        id=str(p.id),
        slug=p.slug,
        name=p.name,
        price=price,
        price_range=price_range,
        compare_at_price=float(p.compare_at_price) if p.compare_at_price else None,
        currency=p.currency,
        featured_image=featured,
        images=gallery,
        category=p.category.slug if p.category else None,
        rating=float(p.rating),
        review_count=p.review_count,
        stock=stock,
        is_featured=p.is_featured,
        is_new_arrival=p.is_new_arrival,
        is_indexable=p.is_indexable,
        updated_at=p.updated_at,
    )


def _product_to_full_out(
    p: Product,
    attributes: list[ProductAttributeOut] | None = None,
    variations: list[VariationOut] | None = None,
    faqs: list[FaqOut] | None = None,
) -> ProductOut:
    featured, gallery = _split_images(p)
    price, price_range, stock = _derived(p)
    return ProductOut(
        attributes=attributes or [],
        variations=variations or [],
        faqs=faqs or [],
        id=str(p.id),
        slug=p.slug,
        name=p.name,
        sku=p.sku,
        canonical_url=p.canonical_url,
        og_image=p.og_image,
        short_description=p.short_description,
        description=p.description,
        kind=p.kind,
        price=price,
        price_range=price_range,
        compare_at_price=float(p.compare_at_price) if p.compare_at_price else None,
        currency=p.currency,
        featured_image=featured,
        images=gallery,
        category=p.category.slug if p.category else None,
        product_type=p.product_type,
        dimensions=p.dimensions or {},
        care_instructions=p.care_instructions or [],
        tags=p.tags or [],
        rating=float(p.rating),
        review_count=p.review_count,
        stock=stock,
        is_featured=p.is_featured,
        is_new_arrival=p.is_new_arrival,
        is_indexable=p.is_indexable,
        meta_title=p.meta_title,
        meta_description=p.meta_description,
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
    attribute_terms: list[str] | None = None,
    ids: list[str] | None = None,
    sort_by: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 12,
) -> PaginatedResponse[ProductListOut]:
    # Every argument goes into the key — a listing filtered by colour must not
    # be served to someone filtering by price. Hashed rather than concatenated
    # because a search term or an id list would otherwise produce unbounded key
    # lengths, and `ids` can hold a whole wishlist.
    fingerprint = json.dumps(
        {
            "category": category,
            "min_price": min_price,
            "max_price": max_price,
            "product_type": product_type,
            "attribute_terms": sorted(attribute_terms) if attribute_terms else None,
            "ids": ids,
            "sort_by": sort_by,
            "search": search,
            "page": page,
            "page_size": page_size,
        },
        sort_keys=True,
        default=str,
    )
    ck = cache_key(
        "products", "list", hashlib.sha1(fingerprint.encode()).hexdigest()[:16]
    )
    if redis:
        cached = await cache_get(redis, ck)
        if cached is not None:
            return PaginatedResponse[ProductListOut].model_validate(cached)

    query = (
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(Product.is_active.is_(True))
    )

    if ids is not None:
        # Explicit id list — used by collections and the wishlist to resolve
        # stored references in one request instead of one call per product.
        # An empty list means "nothing selected", not "no filter".
        if not ids:
            return PaginatedResponse(
                items=[], total=0, page=page, page_size=page_size, total_pages=0
            )
        query = query.where(Product.id.in_(ids))
    if category:
        query = query.join(Category).where(Category.slug == category)
    if min_price is not None:
        query = query.where(Product.price >= min_price)
    if max_price is not None:
        query = query.where(Product.price <= max_price)
    if product_type:
        query = query.where(Product.product_type == product_type)
    if attribute_terms:
        # AND across terms: ?leather-color=black&hardware=silver must match a
        # product offering both, not either.
        for term_slug in attribute_terms:
            query = query.where(
                Product.id.in_(
                    select(ProductAttribute.product_id)
                    .join(
                        ProductAttributeTerm,
                        ProductAttributeTerm.product_attribute_id
                        == ProductAttribute.id,
                    )
                    .join(
                        AttributeTerm,
                        AttributeTerm.id == ProductAttributeTerm.term_id,
                    )
                    .where(AttributeTerm.slug == term_slug)
                )
            )
    if search:
        query = query.where(
            or_(
                Product.name.ilike(f"%{search}%"),
                Product.description.ilike(f"%{search}%"),
                Product.tags.cast(str).ilike(f"%{search}%"),
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

    swatches = await load_swatches(db, result["items"])
    items = [
        _product_to_list_out(p, swatches.get(str(p.id))) for p in result["items"]
    ]

    payload = PaginatedResponse(
        items=items,
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        total_pages=result["total_pages"],
    )

    if redis:
        await cache_set(redis, ck, payload.model_dump(mode="json"), ttl=TTL_SHORT)

    return payload


async def list_products_admin(
    db: AsyncSession,
    status: str = "active",
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedResponse[ProductListOut]:
    """Product list for the admin panel.

    Separate from the public list because the rules are opposite: the storefront
    must never show an inactive product, while the admin must be able to see one
    — otherwise "deleting" a product, which only clears `is_active`, hides it
    from the person who needs to restore it.

    `status` is "active", "trashed", or "all".
    """
    query = (
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .order_by(desc(Product.created_at))
    )

    if status == "active":
        query = query.where(Product.is_active.is_(True))
    elif status == "trashed":
        query = query.where(Product.is_active.is_(False))

    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                Product.name.ilike(term),
                Product.slug.ilike(term),
                Product.sku.ilike(term),
            )
        )

    result = await paginate(query, page, page_size, db)
    swatches = await load_swatches(db, result["items"])

    return PaginatedResponse(
        items=[
            _product_to_list_out(p, swatches.get(str(p.id))) for p in result["items"]
        ],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        total_pages=result["total_pages"],
    )


async def count_by_status(db: AsyncSession) -> dict[str, int]:
    """Active and trashed counts, for the admin's tab badges."""
    rows = await db.execute(
        select(Product.is_active, func.count(Product.id)).group_by(Product.is_active)
    )
    counts = {"active": 0, "trashed": 0}
    for is_active, total in rows.all():
        counts["active" if is_active else "trashed"] = total
    counts["all"] = counts["active"] + counts["trashed"]
    return counts


async def restore_product(
    db: AsyncSession, redis: Redis | None, product_id: str
) -> ProductOut:
    """Bring a trashed product back. The inverse of `delete_product`."""
    product = await db.scalar(
        select(Product)
        .options(
            selectinload(Product.images),
            selectinload(Product.category),
            selectinload(Product.variations),
        )
        .where(Product.id == product_id)
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.is_active = True
    await db.commit()
    await db.refresh(product)

    if redis:
        await cache_delete_pattern(redis, "products:*")

    attributes, variations = await _load_options(db, product)
    faqs = await faq_service.list_for_product(db, str(product.id))
    return _product_to_full_out(product, attributes, variations, faqs)


async def purge_product(db: AsyncSession, redis: Redis | None, product_id: str) -> None:
    """Delete a product for good.

    Only permitted on an already-trashed product, so a live product can never
    be destroyed by a single misdirected call.

    Order history survives: `order_items.product_id` is ON DELETE SET NULL and
    each line carries its own product snapshot, so past orders stay readable.
    Images, variations, attributes, FAQs and reviews cascade away with it.
    """
    product = await db.scalar(select(Product).where(Product.id == product_id))
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.is_active:
        raise HTTPException(
            status_code=409,
            detail="Move the product to trash before deleting it permanently.",
        )

    await db.delete(product)
    await db.commit()

    if redis:
        await cache_delete_pattern(redis, "products:*")


async def get_filters(db: AsyncSession) -> ProductFiltersOut:
    """Facets for the catalog filter sidebar.

    Only filterable attributes, and only terms at least one active product
    actually offers — showing an option that yields an empty result set is
    worse than not showing it.
    """
    counts = await db.execute(
        select(
            AttributeTerm.attribute_id,
            AttributeTerm.id,
            AttributeTerm.value,
            AttributeTerm.slug,
            AttributeTerm.meta,
            func.count(func.distinct(Product.id)).label("product_count"),
        )
        .join(ProductAttributeTerm, ProductAttributeTerm.term_id == AttributeTerm.id)
        .join(
            ProductAttribute,
            ProductAttribute.id == ProductAttributeTerm.product_attribute_id,
        )
        .join(Product, Product.id == ProductAttribute.product_id)
        .join(Attribute, Attribute.id == AttributeTerm.attribute_id)
        .where(Product.is_active.is_(True), Attribute.is_filterable.is_(True))
        # Grouped by primary key alone: `meta` is json, which Postgres has no
        # equality operator for and so cannot group by. The remaining columns
        # are functionally dependent on the key, which Postgres accepts.
        .group_by(AttributeTerm.id)
        .order_by(AttributeTerm.value)
    )

    grouped: dict[str, list[FilterTermOut]] = {}
    for attribute_id, term_id, value, slug, meta, count in counts.all():
        grouped.setdefault(str(attribute_id), []).append(
            FilterTermOut(
                id=str(term_id),
                value=value,
                slug=slug,
                meta=meta or {},
                product_count=count,
            )
        )

    attributes: list[FilterAttributeOut] = []
    if grouped:
        rows = await db.execute(
            select(Attribute)
            .where(Attribute.id.in_(list(grouped)))
            .order_by(Attribute.position, Attribute.name)
        )
        attributes = [
            FilterAttributeOut(
                id=str(attr.id),
                name=attr.name,
                slug=attr.slug,
                terms=grouped[str(attr.id)],
            )
            for attr in rows.scalars().all()
        ]

    bounds = await db.execute(
        select(func.min(Product.price), func.max(Product.price)).where(
            Product.is_active.is_(True)
        )
    )
    low, high = bounds.one()

    return ProductFiltersOut(
        attributes=attributes,
        price=PriceBoundsOut(min=float(low or 0), max=float(high or 0)),
    )


async def get_by_slug(db: AsyncSession, redis: Redis | None, slug: str) -> ProductOut:
    # The most expensive read in the catalogue — images, category, variations,
    # attributes and FAQs, each its own round trip. Every write path already
    # calls cache_delete_pattern("products:detail:*"), so a stale entry cannot
    # outlive an edit.
    ck = cache_key("products", "detail", slug)
    if redis:
        cached = await cache_get(redis, ck)
        if cached is not None:
            return ProductOut.model_validate(cached)

    result = await db.execute(
        select(Product)
        .options(
            selectinload(Product.images),
            selectinload(Product.category),
            selectinload(Product.variations),
        )
        .where(Product.slug == slug, Product.is_active.is_(True))
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    attributes, variations = await _load_options(db, product)
    faqs = await faq_service.list_for_product(db, str(product.id))
    out = _product_to_full_out(product, attributes, variations, faqs)

    if redis:
        # `mode="json"` for the same reason order snapshots need it: the
        # payload carries datetimes and Decimals, and json.dumps cannot
        # serialise either.
        await cache_set(redis, ck, out.model_dump(mode="json"), ttl=TTL_LONG)

    return out


async def _load_options(
    db: AsyncSession, p: Product
) -> tuple[list[ProductAttributeOut], list[VariationOut]]:
    """Attributes and buyable variations for the public product detail.

    Attributes load for every product: a simple product can carry them with
    `used_for_variations=False`, where they act as displayed specifications.
    Variations only exist for variable products, and only active ones are
    public — an inactive variation is not purchasable, so offering it as an
    option would dead-end at checkout.
    """
    attributes = await variation_service.get_product_attributes(db, str(p.id))

    if p.kind != "variable":
        return attributes, []

    variations = await variation_service.load_active_variations(db, str(p.id))
    return attributes, variations


async def get_featured(
    db: AsyncSession, redis: Redis | None, limit: int = 8
) -> list[ProductListOut]:
    # Keyed by limit as well as name: the homepage asks for 8 and a section
    # elsewhere could ask for 4, and one must not serve the other's answer.
    ck = cache_key("products", "featured", str(limit))
    if redis:
        cached = await cache_get(redis, ck)
        if cached is not None:
            return [ProductListOut.model_validate(item) for item in cached]

    result = await db.execute(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(Product.is_active.is_(True), Product.is_featured.is_(True))
        .order_by(desc(Product.created_at))
        .limit(limit)
    )
    products = list(result.scalars().all())
    swatches = await load_swatches(db, products)
    items = [_product_to_list_out(p, swatches.get(str(p.id))) for p in products]

    if redis:
        await cache_set(
            redis, ck, [i.model_dump(mode="json") for i in items], ttl=TTL_MEDIUM
        )

    return items


async def get_new_arrivals(
    db: AsyncSession, redis: Redis | None, limit: int = 8
) -> list[ProductListOut]:
    # Keyed by limit as well as name: the homepage asks for 8 and a section
    # elsewhere could ask for 4, and one must not serve the other's answer.
    ck = cache_key("products", "new-arrivals", str(limit))
    if redis:
        cached = await cache_get(redis, ck)
        if cached is not None:
            return [ProductListOut.model_validate(item) for item in cached]

    result = await db.execute(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(Product.is_active.is_(True), Product.is_new_arrival.is_(True))
        .order_by(desc(Product.created_at))
        .limit(limit)
    )
    products = list(result.scalars().all())
    swatches = await load_swatches(db, products)
    items = [_product_to_list_out(p, swatches.get(str(p.id))) for p in products]

    if redis:
        await cache_set(
            redis, ck, [i.model_dump(mode="json") for i in items], ttl=TTL_MEDIUM
        )

    return items


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
    products = list(result.scalars().all())
    swatches = await load_swatches(db, products)
    return [_product_to_list_out(p, swatches.get(str(p.id))) for p in products]


async def create_product(
    db: AsyncSession, redis: Redis | None, data: ProductCreate
) -> ProductOut:
    slug = data.slug or generate_slug(data.name)
    slug = await ensure_unique_slug(db, Product, slug)

    product = Product(
        slug=slug,
        name=data.name,
        sku=data.sku,
        canonical_url=data.canonical_url,
        og_image=data.og_image,
        short_description=data.short_description,
        description=data.description,
        kind=data.kind,
        price=data.price,
        compare_at_price=data.compare_at_price,
        category_id=data.category_id,
        product_type=data.product_type,
        dimensions=data.dimensions.model_dump(),
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
        # `exclude_unset` drops nested defaults too, so a client sending only
        # {url, alt} — which is all ImageKit gives us — arrives without
        # dimensions. They are optional metadata, not a reason to fail.
        db.add(
            ProductImage(
                product_id=product.id,
                url=featured_data["url"],
                alt=featured_data.get("alt", ""),
                width=featured_data.get("width", 0),
                height=featured_data.get("height", 0),
                position=-1,
                is_featured=True,
            )
        )

    # Gallery sent as a whole, in display order. Reconciled rather than wiped
    # and rebuilt so unchanged images keep their ids — a variation or an order
    # snapshot may already point at one.
    gallery_data = update_data.pop("images", None)
    if gallery_data is not None:
        wanted = {image["url"]: index for index, image in enumerate(gallery_data)}

        for img in product.images:
            if img.is_featured:
                continue
            if img.url in wanted:
                img.position = wanted[img.url]
            else:
                await db.delete(img)

        existing_urls = {img.url for img in product.images if not img.is_featured}
        for image in gallery_data:
            if image["url"] in existing_urls:
                continue
            db.add(
                ProductImage(
                    product_id=product.id,
                    url=image["url"],
                    alt=image.get("alt", ""),
                    width=image.get("width", 0),
                    height=image.get("height", 0),
                    position=wanted[image["url"]],
                    is_featured=False,
                )
            )

    for key, value in update_data.items():
        if hasattr(product, key):
            setattr(product, key, value)

    await db.commit()

    # Re-fetch with relationships for full output. `populate_existing` is
    # required: the row is already in the identity map with the image
    # collection loaded before the edit, so without it the response echoes the
    # gallery as it was and the change looks like it did not save.
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(Product.id == product.id)
        .execution_options(populate_existing=True)
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


async def add_product_image(
    db: AsyncSession, redis: Redis | None, product_id: str, data
) -> ProductOut:
    """Add an image to the product-level gallery.

    Mirrors the variation image endpoints. Without this the gallery could only
    be set at creation time, since ProductUpdate carries no image list.
    """
    product = await db.scalar(select(Product).where(Product.id == product_id))
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if data.is_featured:
        # One hero per product gallery — demote the current one first
        for img in product.images:
            if img.is_featured:
                img.is_featured = False
        await db.flush()

    db.add(
        ProductImage(
            product_id=product_id,
            variation_id=None,
            url=data.url,
            alt=data.alt,
            width=data.width,
            height=data.height,
            position=-1 if data.is_featured else data.position,
            is_featured=data.is_featured,
        )
    )
    await db.commit()

    if redis:
        await cache_delete_pattern(redis, "products:*")

    result = await db.execute(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(Product.id == product_id)
        .execution_options(populate_existing=True)
    )
    return _product_to_full_out(result.scalar_one())


async def delete_product_image(
    db: AsyncSession, redis: Redis | None, product_id: str, image_id: str
) -> None:
    image = await db.scalar(
        select(ProductImage).where(
            ProductImage.id == image_id,
            ProductImage.product_id == product_id,
            ProductImage.variation_id.is_(None),
        )
    )
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    await db.delete(image)
    await db.commit()

    if redis:
        await cache_delete_pattern(redis, "products:*")
