from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin


class Discount(Base, UUIDMixin):
    __tablename__ = "discounts"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    percentage: Mapped[int] = mapped_column(Integer)
    min_order_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    max_uses: Mapped[int] = mapped_column(Integer, default=0)
    current_uses: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Banner(Base, UUIDMixin):
    __tablename__ = "banners"

    title: Mapped[str] = mapped_column(String(255))
    image_url: Mapped[str] = mapped_column(String(500))
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    active_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    active_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
