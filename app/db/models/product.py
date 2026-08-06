import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class Category(Base, UUIDMixin):
    __tablename__ = "categories"


    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    parent: Mapped["Category | None"] = relationship(
        remote_side="Category.id", back_populates="children"
    )
    children: Mapped[list["Category"]] = relationship(
        back_populates="parent", lazy="selectin"
    )
    products: Mapped[list["Product"]] = relationship(
        back_populates="category", lazy="noload"
    )


class Product(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_active_created", "is_active", "created_at"),
        Index("ix_products_active_price", "is_active", "price"),
        Index("ix_products_active_featured", "is_active", "is_featured"),
        Index("ix_products_active_new_arrival", "is_active", "is_new_arrival"),
        Index("ix_products_active_rating", "is_active", "rating"),
        Index("ix_products_category", "category_id"),
    )

    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    # Both authored in TipTap and stored as sanitised HTML
    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text)
    # "simple" | "variable". Distinct from product_type (wallet/bag/belt).
    # For variable products price and stock below are derived, not authoritative.
    kind: Mapped[str] = mapped_column(String(20), default="simple", index=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    compare_at_price: Mapped[float | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(10), default="PKR")
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_type: Mapped[str | None] = mapped_column(
        String(30), nullable=True, index=True
    )
    dimensions: Mapped[dict] = mapped_column(JSON, default=dict)
    care_instructions: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[float] = mapped_column(Numeric(2, 1), default=0.0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    is_new_arrival: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Stock-keeping unit. Variations carry their own; this covers simple
    # products and is what Product schema's `sku` reports.
    sku: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )
    meta_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Points duplicates at the original; empty means the product's own URL
    canonical_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Social share card; falls back to the feature image when unset
    og_image: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships (string refs to avoid circular imports)
    category: Mapped["Category | None"] = relationship(
        back_populates="products", lazy="selectin"
    )
    # Product-level gallery only — variation images are reached via
    # ProductVariation.images, not here.
    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProductImage.position",
        primaryjoin=(
            "and_(Product.id == ProductImage.product_id, "
            "ProductImage.variation_id.is_(None))"
        ),
    )
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="product", lazy="noload"
    )
    variations: Mapped[list["ProductVariation"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProductVariation.position",
    )
    attributes: Mapped[list["ProductAttribute"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProductAttribute.position",
    )
    faqs: Mapped[list["ProductFaq"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProductFaq.position",
    )


class ProductImage(Base, UUIDMixin):
    __tablename__ = "product_images"
    __table_args__ = (
        # Two indexes, not one: Postgres treats NULLs as distinct, so a single
        # index over (product_id, variation_id) would allow many featured
        # product-level images.
        Index(
            "uq_product_images_featured",
            "product_id",
            unique=True,
            postgresql_where=text("is_featured AND variation_id IS NULL"),
            sqlite_where=text("is_featured AND variation_id IS NULL"),
        ),
        Index(
            "uq_variation_images_featured",
            "variation_id",
            unique=True,
            postgresql_where=text("is_featured AND variation_id IS NOT NULL"),
            sqlite_where=text("is_featured AND variation_id IS NOT NULL"),
        ),
    )

    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE")
    )
    # NULL = product-level gallery; set = belongs to that variation
    variation_id: Mapped[str | None] = mapped_column(
        ForeignKey("product_variations.id", ondelete="CASCADE"), nullable=True
    )
    url: Mapped[str] = mapped_column(String(500))
    alt: Mapped[str] = mapped_column(String(255), default="")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)
    # Hero image within its own scope (product gallery, or variation gallery)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="images")
    variation: Mapped["ProductVariation | None"] = relationship(
        back_populates="images"
    )


class Collection(Base, UUIDMixin):
    __tablename__ = "collections"

    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    tagline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    product_ids: Mapped[list] = mapped_column(JSON, default=list)
    season: Mapped[str | None] = mapped_column(String(50), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
