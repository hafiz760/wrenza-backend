"""add seo fields faqs and brand settings

Revision ID: 44e0868a42f7
Revises: f771438fe8db
Create Date: 2026-08-04 01:34:46.645222

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '44e0868a42f7'
down_revision: Union[str, None] = 'f771438fe8db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Product SEO fields
    op.add_column("products", sa.Column("sku", sa.String(length=100), nullable=True))
    op.create_index("ix_products_sku", "products", ["sku"], unique=True)
    op.add_column(
        "products", sa.Column("canonical_url", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "products", sa.Column("og_image", sa.String(length=500), nullable=True)
    )

    # Per-product FAQs, feeding the FAQPage structured data
    op.create_table(
        "product_faqs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_faqs_product", "product_faqs", ["product_id"])

    # Organization schema data
    for column in ("logo_url", "address", "facebook_url", "instagram_url"):
        op.add_column(
            "store_settings",
            sa.Column(column, sa.String(length=500), nullable=False, server_default=""),
        )
    op.add_column(
        "store_settings",
        sa.Column("phone", sa.String(length=30), nullable=False, server_default=""),
    )


def downgrade() -> None:
    for column in ("phone", "instagram_url", "facebook_url", "address", "logo_url"):
        op.drop_column("store_settings", column)

    op.drop_index("ix_product_faqs_product", table_name="product_faqs")
    op.drop_table("product_faqs")

    op.drop_column("products", "og_image")
    op.drop_column("products", "canonical_url")
    op.drop_index("ix_products_sku", table_name="products")
    op.drop_column("products", "sku")
