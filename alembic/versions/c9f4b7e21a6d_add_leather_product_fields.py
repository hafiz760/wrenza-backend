"""add leather product fields

Revision ID: c9f4b7e21a6d
Revises: 61023f5f0bf6
Create Date: 2026-04-04 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c9f4b7e21a6d"
down_revision: Union[str, Sequence[str], None] = "61023f5f0bf6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products", sa.Column("product_type", sa.String(length=30), nullable=True)
    )
    op.add_column(
        "products", sa.Column("material", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "products", sa.Column("leather_type", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "products",
        sa.Column(
            "dimensions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "products", sa.Column("hardware_finish", sa.String(length=50), nullable=True)
    )
    op.add_column(
        "products", sa.Column("closure_type", sa.String(length=100), nullable=True)
    )
    op.create_index(
        op.f("ix_products_product_type"), "products", ["product_type"], unique=False
    )
    op.alter_column("products", "dimensions", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_products_product_type"), table_name="products")
    op.drop_column("products", "closure_type")
    op.drop_column("products", "hardware_finish")
    op.drop_column("products", "dimensions")
    op.drop_column("products", "leather_type")
    op.drop_column("products", "material")
    op.drop_column("products", "product_type")
