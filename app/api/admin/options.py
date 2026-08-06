"""Generic id/name lookups for admin dropdowns.

One endpoint serves every dropdown, but only for resources listed in
OPTION_SOURCES below. Nothing is reachable by default — adding a dropdown is a
deliberate one-line change, so a table holding customer data cannot be exposed
by accident.
"""

import uuid
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import InstrumentedAttribute

from app.core.deps import AdminUser, DbSession
from app.db.models.attribute import Attribute, AttributeTerm
from app.db.models.product import Category, Collection, Product

router = APIRouter(prefix="/options", tags=["Admin - Options"])

MAX_IDS = 100


@dataclass(frozen=True)
class OptionSource:
    """How one resource exposes itself as {id, name}."""

    model: type
    label: InstrumentedAttribute
    # Column marking a row as usable; omitted when the table has no such flag
    active: InstrumentedAttribute | None = None
    # Column the `parent` query param filters on, for resources that only make
    # sense scoped to an owner (terms belong to one attribute)
    parent: InstrumentedAttribute | None = None


OPTION_SOURCES: dict[str, OptionSource] = {
    "categories": OptionSource(Category, Category.name, Category.is_active),
    "collections": OptionSource(Collection, Collection.name, Collection.is_active),
    "products": OptionSource(Product, Product.name, Product.is_active),
    "attributes": OptionSource(Attribute, Attribute.name),
    "attribute-terms": OptionSource(
        AttributeTerm, AttributeTerm.value, parent=AttributeTerm.attribute_id
    ),
}


def _valid_uuids(raw: str | None) -> list[str]:
    """Parse a comma-separated id list, dropping anything malformed.

    Ids reach the database as UUIDs, so an unparseable value would raise from
    the type decorator and surface as a 500. Silently ignoring junk keeps a
    stale id in the query string from breaking the whole dropdown.
    """
    if not raw:
        return []

    parsed = []
    for part in raw.split(",")[:MAX_IDS]:
        part = part.strip()
        try:
            uuid.UUID(part)
        except (ValueError, AttributeError):
            continue
        parsed.append(part)
    return parsed


@router.get("/{resource}")
async def list_options(
    resource: str,
    db: DbSession,
    admin: AdminUser,
    search: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    ids: str | None = Query(
        None,
        description=(
            "Comma-separated ids to resolve by name. Use this to display an "
            "already-selected value that may fall outside the first page."
        ),
    ),
    exclude: str | None = Query(
        None, description="Id to omit — e.g. a category cannot be its own parent."
    ),
    parent: str | None = Query(
        None,
        description=(
            "Owner id for scoped resources. Required for attribute-terms, "
            "which are meaningless outside their attribute."
        ),
    ),
):
    """Return `[{id, name}]` for a dropdown.

    Never returns the whole table: results are capped by `limit` and narrowed by
    `search`, so a resource with 50,000 rows costs the same as one with 10.
    """
    source = OPTION_SOURCES.get(resource)
    if source is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown resource '{resource}'. "
                f"Available: {', '.join(sorted(OPTION_SOURCES))}"
            ),
        )

    model, label = source.model, source.label

    if source.parent is not None:
        scoped_to = _valid_uuids(parent)
        if not scoped_to:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"'{resource}' requires a valid `parent` id — listing every "
                    "row across all owners is never what a dropdown wants."
                ),
            )

    # Only two columns — selecting entities here would trigger the eager
    # relationship loads configured on Product and blow up the query count.
    query = select(model.id, label.label("name"))
    if source.parent is not None:
        query = query.where(source.parent.in_(scoped_to))

    requested_ids = _valid_uuids(ids)
    if requested_ids:
        # Resolve-by-id mode: return exactly these, skipping the active filter
        # so a deactivated row that is still selected renders with its name
        # instead of appearing blank.
        query = query.where(model.id.in_(requested_ids)).limit(len(requested_ids))
    else:
        if source.active is not None:
            query = query.where(source.active.is_(True))
        if search:
            query = query.where(label.ilike(f"%{search.strip()}%"))
        if excluded := _valid_uuids(exclude):
            query = query.where(model.id.notin_(excluded))
        query = query.order_by(label).limit(limit)

    result = await db.execute(query)
    return [{"id": str(row.id), "name": row.name} for row in result.all()]
