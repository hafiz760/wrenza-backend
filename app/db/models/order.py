import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class PaymentStatus(str, enum.Enum):
    """Independent of OrderStatus on purpose — fulfillment and money are
    separate concerns. A Safepay order can be `paid` while its fulfillment
    `status` is still `pending`; admin still reviews and confirms it like any
    other order, they just know it's already been paid for."""

    UNPAID = "unpaid"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class Order(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "orders"

    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    order_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default=OrderStatus.PENDING.value)
    subtotal: Mapped[float] = mapped_column(Numeric(10, 2))
    shipping: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    # On (subtotal + shipping), at the store's tax_rate when the order was
    # placed. Stored rather than recomputed so a later rate change does not
    # rewrite the tax on an order already placed — same reasoning as why line
    # items snapshot the product.
    tax: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    discount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(10, 2))
    shipping_address: Mapped[dict] = mapped_column(JSON)
    payment_method: Mapped[str] = mapped_column(String(50), default="Cash on Delivery")
    payment_status: Mapped[str] = mapped_column(
        String(20), default=PaymentStatus.UNPAID.value
    )
    # Safepay's tracker token (e.g. "track_..."). How the webhook finds its
    # way back to this order — set when a Safepay checkout session is
    # created, null for Cash on Delivery orders.
    payment_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    discount_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    guest_first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    guest_last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships (string refs)
    user: Mapped["User | None"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )


class OrderItem(Base, UUIDMixin):
    __tablename__ = "order_items"

    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    product_id: Mapped[str | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )
    variation_id: Mapped[str | None] = mapped_column(
        ForeignKey("product_variations.id", ondelete="SET NULL"), nullable=True
    )
    # Carries the chosen attributes, so a deleted variation does not make the
    # order unreadable
    product_snapshot: Mapped[dict] = mapped_column(JSON)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2))

    # Relationships
    order: Mapped["Order"] = relationship(back_populates="items")
