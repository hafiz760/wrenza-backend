from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.attribute import Attribute, AttributeTerm
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
    await db.delete(term)
    await db.commit()
