"""checkout by variation

Revision ID: 3b547c9ff109
Revises: 5ba540e0043d
Create Date: 2026-08-03 13:14:28.764763

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b547c9ff109'
down_revision: Union[str, None] = '5ba540e0043d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Orders reference a variation instead of free-text size/colour
    op.add_column("order_items", sa.Column("variation_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_order_items_variation",
        "order_items",
        "product_variations",
        ["variation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_column("order_items", "size")
    op.drop_column("order_items", "color")

    # Replaced by the attribute/variation system
    op.drop_column("products", "sizes")
    op.drop_column("products", "colors")


def downgrade() -> None:
    op.add_column("products", sa.Column("colors", sa.JSON(), nullable=True))
    op.add_column("products", sa.Column("sizes", sa.JSON(), nullable=True))

    op.add_column(
        "order_items",
        sa.Column("color", sa.String(length=50), nullable=False, server_default=""),
    )
    op.add_column(
        "order_items",
        sa.Column("size", sa.String(length=10), nullable=False, server_default=""),
    )
    op.drop_constraint("fk_order_items_variation", "order_items", type_="foreignkey")
    op.drop_column("order_items", "variation_id")
