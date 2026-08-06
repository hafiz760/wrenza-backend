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
    auto_fulfill_orders: Mapped[bool] = mapped_column(Boolean, default=False)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=10)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
