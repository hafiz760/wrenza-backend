from fastapi import APIRouter

from app.core.deps import DbSession
from app.services import settings_service
from app.schemas.common import CamelModel

router = APIRouter(prefix="/settings", tags=["Settings"])


class PublicSettingsOut(CamelModel):
    """What pricing displays and the site gate need.

    Deliberately narrow — the admin schema also carries store name, contact
    email and the low-stock threshold, none of which are the storefront's
    business. `maintenance_mode` earns its place here: the storefront's own
    root layout reads it on every request to decide whether to show the
    coming-soon page, replacing what used to be a build-time env var that
    needed a rebuild to flip.
    """

    currency: str
    tax_rate: float
    shipping_cost: float
    free_shipping_threshold: float
    maintenance_mode: bool


@router.get("", response_model=PublicSettingsOut)
async def get_public_settings(db: DbSession):
    s = await settings_service.get_or_create(db)
    return PublicSettingsOut(
        currency=s.currency,
        tax_rate=float(s.tax_rate),
        shipping_cost=float(s.shipping_cost),
        free_shipping_threshold=float(s.free_shipping_threshold),
        maintenance_mode=s.maintenance_mode,
    )
