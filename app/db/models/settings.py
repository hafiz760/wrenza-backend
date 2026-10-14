from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin


class StoreSettings(Base, UUIDMixin):
    """Store-wide configuration.

    Exactly one row exists; it is created on first read rather than seeded by a
    migration, so a fresh database needs no extra setup step.
    """

    __tablename__ = "store_settings"

    store_name: Mapped[str] = mapped_column(String(255), default="Wrenza")
    contact_email: Mapped[str] = mapped_column(String(255), default="")
    currency: Mapped[str] = mapped_column(String(10), default="PKR")
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    # Flat delivery charge, waived once the cart reaches the threshold below.
    shipping_cost: Mapped[float] = mapped_column(Numeric(10, 2), default=250)
    free_shipping_threshold: Mapped[float] = mapped_column(
        Numeric(10, 2), default=5000
    )
    auto_fulfill_orders: Mapped[bool] = mapped_column(Boolean, default=False)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=10)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    # Admin-facing kill switch, independent of whether SAFEPAY_* credentials
    # are configured on the server — lets the store take online payments
    # down (e.g. a Safepay outage) without touching env vars or redeploying.
    # The storefront only offers "pay online" at checkout when this is on.
    safepay_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Managed in dashboard settings so credentials can change without redeploys.
    instagram_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    instagram_business_id: Mapped[str | None] = mapped_column(String(255))
    # Write-only in the admin API; refreshed weekly by instagram_service.
    # Kept in the database so token refreshes persist across container restarts.
    instagram_access_token: Mapped[str | None] = mapped_column(String(500))
    instagram_token_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
