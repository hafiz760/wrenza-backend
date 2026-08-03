from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDMixin


class Attribute(Base, UUIDMixin):
    """A reusable product attribute, e.g. "Leather Color"."""

    __tablename__ = "attributes"

    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    # Whether this attribute is offered as a public catalog filter (phase 3)
    is_filterable: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    terms: Mapped[list["AttributeTerm"]] = relationship(
        back_populates="attribute",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="AttributeTerm.position, AttributeTerm.value",
    )


class AttributeTerm(Base, UUIDMixin):
    """One selectable value of an attribute, e.g. "Black"."""

    __tablename__ = "attribute_terms"
    __table_args__ = (
        UniqueConstraint("attribute_id", "slug", name="uq_attribute_term_slug"),
    )

    attribute_id: Mapped[str] = mapped_column(
        ForeignKey("attributes.id", ondelete="CASCADE")
    )
    value: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(120))
    # Presentation data such as a colour swatch: {"hex": "#000000"}
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    position: Mapped[int] = mapped_column(Integer, default=0)

    attribute: Mapped["Attribute"] = relationship(back_populates="terms")
