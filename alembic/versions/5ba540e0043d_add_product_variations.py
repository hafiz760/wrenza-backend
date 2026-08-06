"""add product variations

Revision ID: 5ba540e0043d
Revises: ce4af2adfbd2
Create Date: 2026-08-03 12:57:20.728716

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ba540e0043d'
down_revision: Union[str, None] = 'ce4af2adfbd2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="simple"),
    )
    op.create_index("ix_products_kind", "products", ["kind"])

    op.create_table(
        "product_variations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("compare_at_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("stock", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_variations_sku", "product_variations", ["sku"], unique=True)

    op.create_table(
        "product_attributes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("attribute_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("used_for_variations", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attribute_id"], ["attributes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "attribute_id", name="uq_product_attribute"),
    )

    op.create_table(
        "product_attribute_terms",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("product_attribute_id", sa.UUID(), nullable=False),
        sa.Column("term_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["product_attribute_id"], ["product_attributes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["term_id"], ["attribute_terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_attribute_id", "term_id", name="uq_product_attribute_term"),
    )

    op.create_table(
        "variation_attribute_values",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("variation_id", sa.UUID(), nullable=False),
        sa.Column("attribute_id", sa.UUID(), nullable=False),
        sa.Column("term_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["variation_id"], ["product_variations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attribute_id"], ["attributes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["term_id"], ["attribute_terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("variation_id", "attribute_id", name="uq_variation_attribute"),
    )

    # Variation-scoped images
    op.add_column(
        "product_images", sa.Column("variation_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "fk_product_images_variation",
        "product_images",
        "product_variations",
        ["variation_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Rescope the featured-image uniqueness: one hero per product gallery AND
    # one per variation gallery. Two indexes because NULLs are distinct.
    op.drop_index("uq_product_images_featured", table_name="product_images")
    op.create_index(
        "uq_product_images_featured",
        "product_images",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("is_featured AND variation_id IS NULL"),
    )
    op.create_index(
        "uq_variation_images_featured",
        "product_images",
        ["variation_id"],
        unique=True,
        postgresql_where=sa.text("is_featured AND variation_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_variation_images_featured", table_name="product_images")
    op.drop_index("uq_product_images_featured", table_name="product_images")
    op.create_index(
        "uq_product_images_featured",
        "product_images",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("is_featured"),
    )
    op.drop_constraint("fk_product_images_variation", "product_images", type_="foreignkey")
    op.drop_column("product_images", "variation_id")

    op.drop_table("variation_attribute_values")
    op.drop_table("product_attribute_terms")
    op.drop_table("product_attributes")
    op.drop_index("ix_product_variations_sku", table_name="product_variations")
    op.drop_table("product_variations")
    op.drop_index("ix_products_kind", table_name="products")
    op.drop_column("products", "kind")
