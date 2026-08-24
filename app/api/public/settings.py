from fastapi import APIRouter

from app.core.deps import DbSession
from app.services import settings_service
from app.schemas.common import CamelModel

router = APIRouter(prefix="/settings", tags=["Settings"])


class PublicSettingsOut(CamelModel):
    """Only what pricing and shipping displays need.

    Deliberately narrow — the admin schema also carries store name, contact
    email, maintenance mode and the low-stock threshold, none of which are
    the storefront's business.
    """

    currency: str
    tax_rate: float
    shipping_cost: float
    free_shipping_threshold: float


@router.get("", response_model=PublicSettingsOut)
async def get_public_settings(db: DbSession):
    s = await settings_service.get_or_create(db)
    return PublicSettingsOut(
        currency=s.currency,
        tax_rate=float(s.tax_rate),
        shipping_cost=float(s.shipping_cost),
        free_shipping_threshold=float(s.free_shipping_threshold),
    )
