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


class GenderType(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    UNISEX = "unisex"


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
    description: Mapped[str] = mapped_column(Text)
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
    material: Mapped[str | None] = mapped_column(String(100), nullable=True)
    leather_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dimensions: Mapped[dict] = mapped_column(JSON, default=dict)
    hardware_finish: Mapped[str | None] = mapped_column(String(50), nullable=True)
    closure_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fabric: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Stored as JSON to match frontend's ProductSize[] and ProductColor[]
    sizes: Mapped[list] = mapped_column(JSON, default=list)
    colors: Mapped[list] = mapped_column(JSON, default=list)
    care_instructions: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[float] = mapped_column(Numeric(2, 1), default=0.0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    is_new_arrival: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    meta_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships (string refs to avoid circular imports)
    category: Mapped["Category | None"] = relationship(
        back_populates="products", lazy="selectin"
    )
    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProductImage.position",
    )
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="product", lazy="noload"
    )


class ProductImage(Base, UUIDMixin):
    __tablename__ = "product_images"
    __table_args__ = (
        # At most one feature image per product
        Index(
            "uq_product_images_featured",
            "product_id",
            unique=True,
            postgresql_where=text("is_featured"),
            sqlite_where=text("is_featured"),
        ),
    )

    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE")
    )
    url: Mapped[str] = mapped_column(String(500))
    alt: Mapped[str] = mapped_column(String(255), default="")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)
    # Marks the hero image; excluded from the gallery in API responses
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="images")


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
