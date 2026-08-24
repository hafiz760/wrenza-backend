from itertools import product as cartesian

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.attribute import Attribute, AttributeTerm
from app.db.models.product import Product, ProductImage
from app.db.models.variation import (
    ProductAttribute,
    ProductAttributeTerm,
    ProductVariation,
    VariationAttributeValue,
)
from app.schemas.image import ProductImageOut
from app.utils.slug import generate_slug
from app.schemas.variation import (
    ProductAttributeOut,
    ProductAttributesUpdate,
    VariationBulkUpdate,
    VariationImageCreate,
    VariationOut,
    VariationValueOut,
)


async def _get_product_or_404(db: AsyncSession, product_id: str) -> Product:
    product = await db.scalar(select(Product).where(Product.id == product_id))
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


def _require_variable(product: Product) -> None:
    if product.kind != "variable":
        raise HTTPException(
            status_code=422,
            detail=(
                "This product is 'simple'. Set kind to 'variable' before "
                "managing attributes or variations."
            ),
        )


async def _term_lookup(db: AsyncSession, term_ids: list[str]) -> dict:
    """Resolve terms to (term, attribute) so responses carry names, not just ids."""
    if not term_ids:
        return {}
    result = await db.execute(
        select(AttributeTerm)
        .options(selectinload(AttributeTerm.attribute))
        .where(AttributeTerm.id.in_(term_ids))
    )
    return {str(t.id): t for t in result.scalars().all()}


def _value_out(term: AttributeTerm) -> VariationValueOut:
    return VariationValueOut(
        attribute_id=str(term.attribute_id),
        attribute_name=term.attribute.name,
        attribute_slug=term.attribute.slug,
        term_id=str(term.id),
        term_value=term.value,
        term_slug=term.slug,
        meta=term.meta or {},
    )


def _image_out(img: ProductImage) -> ProductImageOut:
    return ProductImageOut(
        id=str(img.id),
        url=img.url,
        alt=img.alt,
        width=img.width,
        height=img.height,
    )


def _variation_out(v: ProductVariation, terms: dict) -> VariationOut:
    featured = next((i for i in v.images if i.is_featured), None)
    gallery = [i for i in v.images if not i.is_featured]
    if featured is None and v.images:
        featured, gallery = v.images[0], list(v.images)

    return VariationOut(
        id=str(v.id),
        sku=v.sku,
        gtin=v.gtin,
        price=float(v.price),
        compare_at_price=float(v.compare_at_price) if v.compare_at_price else None,
        stock=v.stock,
        is_active=v.is_active,
        position=v.position,
        values=[
            _value_out(terms[str(val.term_id)])
            for val in v.values
            if str(val.term_id) in terms
        ],
        featured_image=_image_out(featured) if featured else None,
        images=[_image_out(i) for i in gallery],
    )


async def _load_variations(db: AsyncSession, product_id: str) -> list[VariationOut]:
    result = await db.execute(
        select(ProductVariation)
        .where(ProductVariation.product_id == product_id)
        .order_by(ProductVariation.position)
        # Rows written earlier in this session are already in the identity map
        # with stale collections; without this a just-added image is invisible.
        .execution_options(populate_existing=True)
    )
    variations = result.scalars().all()

    term_ids = [str(val.term_id) for v in variations for val in v.values]
    terms = await _term_lookup(db, term_ids)
    return [_variation_out(v, terms) for v in variations]


# ── Product attributes ──────────────────────────────────────────


async def _attribute_ids_in_use(db: AsyncSession, product_id: str) -> set[str]:
    """Attributes that this product's existing variations are keyed on."""
    result = await db.execute(
        select(VariationAttributeValue.attribute_id)
        .join(
            ProductVariation,
            ProductVariation.id == VariationAttributeValue.variation_id,
        )
        .where(ProductVariation.product_id == product_id)
        .distinct()
    )
    return {str(row) for row in result.scalars().all()}


async def set_product_attributes(
    db: AsyncSession, product_id: str, data: ProductAttributesUpdate
) -> list[ProductAttributeOut]:
    """Replace the product's attribute selection.

    Existing variations are left alone: removing an attribute here does not
    retroactively rewrite variations that were already generated and priced.
    """
    product = await _get_product_or_404(db, product_id)

    # Simple products may carry attributes too — they render as specifications.
    # Only variation *generation* requires a variable product.
    if product.kind != "variable" and any(
        assignment.used_for_variations for assignment in data.attributes
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "A simple product cannot use attributes as variation axes. "
                "Set usedForVariations to false, or change the product to variable."
            ),
        )

    # An attribute that existing variations are keyed on must stay a variation
    # axis. Demoting it leaves the variations buyable but with nothing to pick
    # them by, so the storefront would show a price range and no option picker.
    in_use = await _attribute_ids_in_use(db, product_id)
    demoted = {
        a.attribute_id
        for a in data.attributes
        if not a.used_for_variations and a.attribute_id in in_use
    }
    if demoted:
        raise HTTPException(
            status_code=422,
            detail=(
                "This attribute is used by existing variations, so it must stay "
                "a variation axis. Delete those variations first to demote it."
            ),
        )

    requested_attr_ids = [a.attribute_id for a in data.attributes]
    if len(set(requested_attr_ids)) != len(requested_attr_ids):
        raise HTTPException(
            status_code=422, detail="An attribute may only be listed once."
        )

    # Skipped entirely when nothing was sent. The previous `or [""]` guard fed
    # an empty string to the UUID column type, which raised — so clearing the
    # last attribute off a product, the normal way to detach one, was a 500.
    if requested_attr_ids:
        found = await db.execute(
            select(Attribute.id).where(Attribute.id.in_(requested_attr_ids))
        )
        known = {str(i) for i in found.scalars().all()}
        missing = [a for a in requested_attr_ids if a not in known]
        if missing:
            raise HTTPException(
                status_code=404, detail=f"Unknown attribute(s): {', '.join(missing)}"
            )

    for assignment in data.attributes:
        terms = await _term_lookup(db, assignment.term_ids)
        wrong = [
            t
            for t in assignment.term_ids
            if t not in terms
            or str(terms[t].attribute_id) != assignment.attribute_id
        ]
        if wrong:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Term(s) {', '.join(wrong)} do not belong to attribute "
                    f"{assignment.attribute_id}."
                ),
            )

    existing = await db.execute(
        select(ProductAttribute).where(ProductAttribute.product_id == product_id)
    )
    for row in existing.scalars().all():
        await db.delete(row)
    await db.flush()

    for assignment in data.attributes:
        pa = ProductAttribute(
            product_id=product_id,
            attribute_id=assignment.attribute_id,
            position=assignment.position,
            used_for_variations=assignment.used_for_variations,
        )
        db.add(pa)
        await db.flush()
        for term_id in assignment.term_ids:
            db.add(ProductAttributeTerm(product_attribute_id=pa.id, term_id=term_id))

    await db.commit()
    return await get_product_attributes(db, product_id)


async def get_product_attributes(
    db: AsyncSession, product_id: str
) -> list[ProductAttributeOut]:
    await _get_product_or_404(db, product_id)

    result = await db.execute(
        select(ProductAttribute)
        .where(ProductAttribute.product_id == product_id)
        .order_by(ProductAttribute.position)
    )
    rows = result.scalars().all()

    term_ids = [str(t.term_id) for pa in rows for t in pa.terms]
    terms = await _term_lookup(db, term_ids)

    out = []
    for pa in rows:
        pa_terms = [
            terms[str(t.term_id)] for t in pa.terms if str(t.term_id) in terms
        ]
        if not pa_terms:
            continue
        out.append(
            ProductAttributeOut(
                attribute_id=str(pa.attribute_id),
                attribute_name=pa_terms[0].attribute.name,
                attribute_slug=pa_terms[0].attribute.slug,
                used_for_variations=pa.used_for_variations,
                position=pa.position,
                terms=[_value_out(t) for t in pa_terms],
            )
        )
    return out


# ── Variations ──────────────────────────────────────────────────


def _sku_stem(product: Product) -> str:
    """Prefix every variation SKU shares.

    The product's own SKU when it has one, so a warehouse can read the family
    from the code; otherwise the slug, which is already URL-safe and unique.
    """
    base = product.sku or product.slug or "SKU"
    return generate_slug(base).upper()


def _variation_sku(stem: str, term_slugs: list[str], taken: set[str]) -> str:
    """`WEEKENDER-DUFFLE-GREEN` — readable in an invoice and safe in a URL.

    Term order follows the axis order, so the same combination always produces
    the same code. A numeric suffix resolves the rare collision, since the
    column is globally unique.
    """
    parts = [stem, *(generate_slug(slug).upper() for slug in term_slugs)]
    candidate = "-".join(part for part in parts if part)

    if candidate not in taken:
        taken.add(candidate)
        return candidate

    counter = 2
    while f"{candidate}-{counter}" in taken:
        counter += 1
    unique = f"{candidate}-{counter}"
    taken.add(unique)
    return unique


async def generate_variations(
    db: AsyncSession, product_id: str
) -> list[VariationOut]:
    """Create the cartesian product of the variation-axis terms.

    Non-destructive: combinations that already exist keep their price, stock,
    SKU and images, so adding a term and regenerating never wipes prior work.
    """
    product = await _get_product_or_404(db, product_id)
    _require_variable(product)

    result = await db.execute(
        select(ProductAttribute)
        .where(
            ProductAttribute.product_id == product_id,
            ProductAttribute.used_for_variations.is_(True),
        )
        # `id` breaks ties: positions default to 0, and without a second key
        # the axis order — and so the generated SKU — varies between runs
        .order_by(ProductAttribute.position, ProductAttribute.id)
    )
    axes = result.scalars().all()
    if not axes:
        raise HTTPException(
            status_code=422,
            detail=(
                "No attributes are marked used_for_variations. Assign at least "
                "one before generating."
            ),
        )

    # `pa.terms` is unordered — nothing sorts the join table itself, so its
    # row order is whatever SQLite happens to return, which is not guaranteed
    # and was observed to change under load. Queried explicitly here instead,
    # ordered the same way `load_swatches` orders terms elsewhere, so which
    # variation lands in position 0 is deterministic — the admin's product
    # listing and card fall back to exactly that variation when nothing is
    # photographed at the product level.
    term_rows = await db.execute(
        select(ProductAttributeTerm.product_attribute_id, ProductAttributeTerm.term_id)
        .join(AttributeTerm, AttributeTerm.id == ProductAttributeTerm.term_id)
        .where(
            ProductAttributeTerm.product_attribute_id.in_([pa.id for pa in axes])
        )
        .order_by(AttributeTerm.position, AttributeTerm.value)
    )
    terms_by_axis: dict[str, list[str]] = {}
    for attribute_id, term_id in term_rows.all():
        terms_by_axis.setdefault(str(attribute_id), []).append(str(term_id))

    axis_terms = [terms_by_axis.get(str(pa.id), []) for pa in axes]
    if any(not terms for terms in axis_terms):
        raise HTTPException(
            status_code=422, detail="Every variation attribute needs at least one term."
        )

    existing_result = await db.execute(
        select(ProductVariation).where(ProductVariation.product_id == product_id)
    )
    existing = existing_result.scalars().all()
    # A set-across-rows uniqueness rule is not expressible as a SQL index, so
    # duplicates are prevented here instead.
    seen = {frozenset(str(v.term_id) for v in var.values) for var in existing}

    # Every SKU already in use, so a generated one cannot collide with another
    # product's. Loaded once rather than queried per combination.
    taken_result = await db.execute(
        select(ProductVariation.sku).where(ProductVariation.sku.is_not(None))
    )
    taken = {sku for sku in taken_result.scalars().all() if sku}
    stem = _sku_stem(product)

    # Backfill anything already generated without one. Filling a blank is not
    # the same as resetting a value the admin set, so this stays within the
    # "never overwrites existing SKUs" promise.
    blanks = [v for v in existing if not v.sku]
    if blanks:
        blank_terms = await _term_lookup(
            db, [str(val.term_id) for v in blanks for val in v.values]
        )
        # Values come back in row order, which is not axis order — sorted so a
        # backfilled SKU reads the same as a freshly generated one
        axis_order = {str(pa.attribute_id): index for index, pa in enumerate(axes)}
        for variation in blanks:
            values = sorted(
                (v for v in variation.values if str(v.term_id) in blank_terms),
                key=lambda v: axis_order.get(str(v.attribute_id), len(axis_order)),
            )
            variation.sku = _variation_sku(
                stem, [blank_terms[str(v.term_id)].slug for v in values], taken
            )

    position = max((v.position for v in existing), default=-1) + 1
    for combo in cartesian(*axis_terms):
        key = frozenset(combo)
        if key in seen:
            continue
        seen.add(key)

        terms = await _term_lookup(db, list(combo))
        # `combo` is in axis order, so the code reads the way the picker does
        term_slugs = [terms[term_id].slug for term_id in combo if term_id in terms]

        variation = ProductVariation(
            product_id=product_id,
            sku=_variation_sku(stem, term_slugs, taken),
            price=product.price,  # seeded from the product; admin edits after
            stock=0,
            position=position,
        )
        position += 1
        db.add(variation)
        await db.flush()

        for term_id in combo:
            db.add(
                VariationAttributeValue(
                    variation_id=variation.id,
                    attribute_id=terms[term_id].attribute_id,
                    term_id=term_id,
                )
            )

    await db.commit()
    return await _load_variations(db, product_id)


async def load_active_variations(
    db: AsyncSession, product_id: str
) -> list[VariationOut]:
    """Public view of a product's variations — the buyable ones only."""
    return [v for v in await _load_variations(db, product_id) if v.is_active]


async def list_variations(db: AsyncSession, product_id: str) -> list[VariationOut]:
    await _get_product_or_404(db, product_id)
    return await _load_variations(db, product_id)


async def bulk_update_variations(
    db: AsyncSession, product_id: str, data: VariationBulkUpdate
) -> list[VariationOut]:
    await _get_product_or_404(db, product_id)

    ids = [v.id for v in data.variations]
    result = await db.execute(
        select(ProductVariation).where(
            ProductVariation.id.in_(ids),
            ProductVariation.product_id == product_id,
        )
    )
    by_id = {str(v.id): v for v in result.scalars().all()}

    missing = [i for i in ids if i not in by_id]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Variation(s) not found on this product: {', '.join(missing)}",
        )

    for row in data.variations:
        variation = by_id[row.id]
        for key, value in row.model_dump(exclude_unset=True).items():
            if key != "id":
                setattr(variation, key, value)

    await db.commit()
    return await _load_variations(db, product_id)


async def delete_variation(
    db: AsyncSession, product_id: str, variation_id: str
) -> None:
    variation = await db.scalar(
        select(ProductVariation).where(
            ProductVariation.id == variation_id,
            ProductVariation.product_id == product_id,
        )
    )
    if not variation:
        raise HTTPException(status_code=404, detail="Variation not found")

    await db.delete(variation)
    await db.commit()


async def add_variation_image(
    db: AsyncSession, product_id: str, variation_id: str, data: VariationImageCreate
) -> VariationOut:
    variation = await db.scalar(
        select(ProductVariation).where(
            ProductVariation.id == variation_id,
            ProductVariation.product_id == product_id,
        )
    )
    if not variation:
        raise HTTPException(status_code=404, detail="Variation not found")

    if data.is_featured:
        # One hero per variation gallery — demote the current one first
        for img in variation.images:
            if img.is_featured:
                img.is_featured = False
        await db.flush()

    db.add(
        ProductImage(
            product_id=product_id,
            variation_id=variation_id,
            url=data.url,
            alt=data.alt,
            width=data.width,
            height=data.height,
            position=data.position,
            is_featured=data.is_featured,
        )
    )
    await db.commit()

    variations = await _load_variations(db, product_id)
    return next(v for v in variations if v.id == str(variation_id))


async def delete_variation_image(
    db: AsyncSession, product_id: str, variation_id: str, image_id: str
) -> None:
    image = await db.scalar(
        select(ProductImage).where(
            ProductImage.id == image_id,
            ProductImage.variation_id == variation_id,
            ProductImage.product_id == product_id,
        )
    )
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    await db.delete(image)
    await db.commit()
