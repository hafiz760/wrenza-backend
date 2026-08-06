from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class ProductKind(str):
    SIMPLE = "simple"
    VARIABLE = "variable"


class ProductAttribute(Base, UUIDMixin):
    """Links a product to a global attribute it offers."""

    __tablename__ = "product_attributes"
    __table_args__ = (
        UniqueConstraint("product_id", "attribute_id", name="uq_product_attribute"),
    )

    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE")
    )
    attribute_id: Mapped[str] = mapped_column(
        ForeignKey("attributes.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    # False = shown on the product page but not a variation axis
    used_for_variations: Mapped[bool] = mapped_column(Boolean, default=True)

    terms: Mapped[list["ProductAttributeTerm"]] = relationship(
        back_populates="product_attribute",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ProductAttributeTerm(Base, UUIDMixin):
    """Which terms of that attribute this product actually offers."""

    __tablename__ = "product_attribute_terms"
    __table_args__ = (
        UniqueConstraint(
            "product_attribute_id", "term_id", name="uq_product_attribute_term"
        ),
    )

    product_attribute_id: Mapped[str] = mapped_column(
        ForeignKey("product_attributes.id", ondelete="CASCADE")
    )
    term_id: Mapped[str] = mapped_column(
        ForeignKey("attribute_terms.id", ondelete="CASCADE")
    )

    product_attribute: Mapped["ProductAttribute"] = relationship(
        back_populates="terms"
    )


class ProductVariation(Base, UUIDMixin, TimestampMixin):
    """One buyable combination — e.g. Black / Silver hardware."""

    __tablename__ = "product_variations"

    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE")
    )
    sku: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    compare_at_price: Mapped[float | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    stock: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)

    values: Mapped[list["VariationAttributeValue"]] = relationship(
        back_populates="variation",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="variation",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProductImage.position",
    )


class VariationAttributeValue(Base, UUIDMixin):
    """One (attribute, term) pair of a variation. Three attributes cost no
    more schema than two — this is what makes variations dynamic."""

    __tablename__ = "variation_attribute_values"
    __table_args__ = (
        UniqueConstraint(
            "variation_id", "attribute_id", name="uq_variation_attribute"
        ),
    )

    variation_id: Mapped[str] = mapped_column(
        ForeignKey("product_variations.id", ondelete="CASCADE")
    )
    attribute_id: Mapped[str] = mapped_column(
        ForeignKey("attributes.id", ondelete="CASCADE")
    )
    term_id: Mapped[str] = mapped_column(
        ForeignKey("attribute_terms.id", ondelete="CASCADE")
    )

    variation: Mapped["ProductVariation"] = relationship(back_populates="values")
