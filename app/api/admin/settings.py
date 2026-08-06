from typing import Annotated

from fastapi import APIRouter
from pydantic import EmailStr, Field
from sqlalchemy import select

from app.core.deps import AdminUser, DbSession
from app.db.models.settings import StoreSettings
from app.schemas.common import CamelModel

router = APIRouter(prefix="/settings", tags=["Admin - Settings"])


class StoreSettingsOut(CamelModel):
    store_name: str
    contact_email: str
    currency: str
    tax_rate: float
    auto_fulfill_orders: bool
    low_stock_threshold: int
    maintenance_mode: bool


class StoreSettingsUpdate(CamelModel):
    store_name: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    contact_email: EmailStr | None = None
    currency: Annotated[str, Field(min_length=1, max_length=10)] | None = None
    tax_rate: Annotated[float, Field(ge=0, le=100)] | None = None
    auto_fulfill_orders: bool | None = None
    low_stock_threshold: Annotated[int, Field(ge=0)] | None = None
    maintenance_mode: bool | None = None


async def _get_or_create(db) -> StoreSettings:
    """Settings are a single row, created lazily on first access."""
    settings = await db.scalar(select(StoreSettings).limit(1))
    if settings is None:
        settings = StoreSettings()
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


def _to_out(s: StoreSettings) -> StoreSettingsOut:
    return StoreSettingsOut(
        store_name=s.store_name,
        contact_email=s.contact_email,
        currency=s.currency,
        tax_rate=float(s.tax_rate),
        auto_fulfill_orders=s.auto_fulfill_orders,
        low_stock_threshold=s.low_stock_threshold,
        maintenance_mode=s.maintenance_mode,
    )


@router.get("", response_model=StoreSettingsOut)
async def get_settings(db: DbSession, admin: AdminUser):
    return _to_out(await _get_or_create(db))


@router.put("", response_model=StoreSettingsOut)
async def update_settings(
    data: StoreSettingsUpdate, admin: AdminUser, db: DbSession
):
    settings = await _get_or_create(db)

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(settings, key, value)

    await db.commit()
    await db.refresh(settings)
    return _to_out(settings)
