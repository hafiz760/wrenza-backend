"""add feature image flag to product images

Revision ID: 7fbb7a2247da
Revises: c9f4b7e21a6d
Create Date: 2026-08-03 09:38:20.119752

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7fbb7a2247da'
down_revision: Union[str, None] = 'c9f4b7e21a6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "product_images",
        sa.Column(
            "is_featured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # At most one feature image per product
    op.create_index(
        "uq_product_images_featured",
        "product_images",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("is_featured"),
        sqlite_where=sa.text("is_featured"),
    )


def downgrade() -> None:
    op.drop_index("uq_product_images_featured", table_name="product_images")
    op.drop_column("product_images", "is_featured")
