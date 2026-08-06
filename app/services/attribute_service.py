from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.attribute import Attribute, AttributeTerm
from app.db.models.variation import ProductAttribute, VariationAttributeValue
from app.schemas.attribute import (
    AttributeCreate,
    AttributeOut,
    AttributeTermCreate,
    AttributeTermOut,
    AttributeTermUpdate,
    AttributeUpdate,
)
from app.utils.slug import ensure_unique_slug, ensure_unique_slug_scoped, generate_slug


def _to_out(attr: Attribute) -> AttributeOut:
    return AttributeOut(
        id=str(attr.id),
        name=attr.name,
        slug=attr.slug,
        position=attr.position,
        is_filterable=attr.is_filterable,
        terms=[_term_to_out(t) for t in attr.terms],
    )


async def _get_or_404(db: AsyncSession, attribute_id: str) -> Attribute:
    attr = await db.scalar(select(Attribute).where(Attribute.id == attribute_id))
    if not attr:
        raise HTTPException(status_code=404, detail="Attribute not found")
    return attr


async def list_attributes(db: AsyncSession) -> list[AttributeOut]:
    result = await db.execute(
        select(Attribute).order_by(Attribute.position, Attribute.name)
    )
    return [_to_out(a) for a in result.scalars().all()]


async def create_attribute(db: AsyncSession, data: AttributeCreate) -> AttributeOut:
    slug = data.slug or generate_slug(data.name)
    slug = await ensure_unique_slug(db, Attribute, slug)

    attr = Attribute(
        name=data.name,
        slug=slug,
        position=data.position,
        is_filterable=data.is_filterable,
    )
    db.add(attr)
    await db.commit()
    await db.refresh(attr)
    return _to_out(attr)


async def update_attribute(
    db: AsyncSession, attribute_id: str, data: AttributeUpdate
) -> AttributeOut:
    attr = await _get_or_404(db, attribute_id)

    update_data = data.model_dump(exclude_unset=True)
    if update_data.get("slug"):
        update_data["slug"] = await ensure_unique_slug(
            db, Attribute, update_data["slug"], exclude_id=attr.id
        )

    for key, value in update_data.items():
        setattr(attr, key, value)

    await db.commit()
    await db.refresh(attr)
    return _to_out(attr)


async def delete_attribute(db: AsyncSession, attribute_id: str) -> None:
    attr = await _get_or_404(db, attribute_id)

    # Both FKs cascade, so deleting an in-use attribute would silently strip
    # terms off live variations. Refuse instead.
    in_use = await db.scalar(
        select(func.count(ProductAttribute.id)).where(
            ProductAttribute.attribute_id == attribute_id
        )
    )
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Attribute is used by {in_use} product(s). Remove it from them "
                "before deleting."
            ),
        )

    await db.delete(attr)
    await db.commit()


def _term_to_out(t: AttributeTerm) -> AttributeTermOut:
    return AttributeTermOut(
        id=str(t.id),
        value=t.value,
        slug=t.slug,
        meta=t.meta or {},
        position=t.position,
    )


async def _get_term_or_404(
    db: AsyncSession, attribute_id: str, term_id: str
) -> AttributeTerm:
    term = await db.scalar(
        select(AttributeTerm).where(
            AttributeTerm.id == term_id,
            AttributeTerm.attribute_id == attribute_id,
        )
    )
    if not term:
        raise HTTPException(status_code=404, detail="Attribute term not found")
    return term


async def create_term(
    db: AsyncSession, attribute_id: str, data: AttributeTermCreate
) -> AttributeTermOut:
    await _get_or_404(db, attribute_id)

    slug = data.slug or generate_slug(data.value)
    slug = await ensure_unique_slug_scoped(
        db, AttributeTerm, slug, "attribute_id", attribute_id
    )

    term = AttributeTerm(
        attribute_id=attribute_id,
        value=data.value,
        slug=slug,
        meta=data.meta,
        position=data.position,
    )
    db.add(term)
    await db.commit()
    await db.refresh(term)
    return _term_to_out(term)


async def reorder_attributes(db: AsyncSession, ids: list[str]) -> list[AttributeOut]:
    """Set attribute order from the given sequence.

    Positions come from the list index, so the result is always 0..n-1 with no
    gaps — the ordering cannot drift out of shape however often it is changed.
    """
    result = await db.execute(select(Attribute).where(Attribute.id.in_(ids)))
    found = {str(a.id): a for a in result.scalars().all()}

    missing = [i for i in ids if i not in found]
    if missing:
        raise HTTPException(
            status_code=404, detail=f"Unknown attribute(s): {', '.join(missing)}"
        )

    for position, attribute_id in enumerate(ids):
        found[attribute_id].position = position

    await db.commit()
    return await list_attributes(db)


async def reorder_terms(
    db: AsyncSession, attribute_id: str, ids: list[str]
) -> list[AttributeTermOut]:
    """Set term order within one attribute.

    Ids belonging to another attribute are rejected rather than silently
    ignored — a mismatch means the client is working from stale data.
    """
    await _get_or_404(db, attribute_id)

    result = await db.execute(
        select(AttributeTerm).where(
            AttributeTerm.id.in_(ids),
            AttributeTerm.attribute_id == attribute_id,
        )
    )
    found = {str(t.id): t for t in result.scalars().all()}

    missing = [i for i in ids if i not in found]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown term(s) for this attribute: {', '.join(missing)}",
        )

    for position, term_id in enumerate(ids):
        found[term_id].position = position

    await db.commit()

    ordered = await db.execute(
        select(AttributeTerm)
        .where(AttributeTerm.attribute_id == attribute_id)
        .order_by(AttributeTerm.position, AttributeTerm.value)
    )
    return [_term_to_out(t) for t in ordered.scalars().all()]


async def update_term(
    db: AsyncSession, attribute_id: str, term_id: str, data: AttributeTermUpdate
) -> AttributeTermOut:
    term = await _get_term_or_404(db, attribute_id, term_id)

    update_data = data.model_dump(exclude_unset=True)
    if update_data.get("slug"):
        update_data["slug"] = await ensure_unique_slug_scoped(
            db,
            AttributeTerm,
            update_data["slug"],
            "attribute_id",
            attribute_id,
            exclude_id=term.id,
        )

    for key, value in update_data.items():
        setattr(term, key, value)

    await db.commit()
    await db.refresh(term)
    return _term_to_out(term)


async def delete_term(db: AsyncSession, attribute_id: str, term_id: str) -> None:
    term = await _get_term_or_404(db, attribute_id, term_id)

    in_use = await db.scalar(
        select(func.count(VariationAttributeValue.id)).where(
            VariationAttributeValue.term_id == term_id
        )
    )
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Term is used by {in_use} variation(s). Delete those variations "
                "before deleting the term."
            ),
        )

    await db.delete(term)
    await db.commit()
