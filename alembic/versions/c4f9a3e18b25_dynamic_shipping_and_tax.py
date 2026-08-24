"""Make shipping and tax dynamic store settings

Shipping was two hardcoded constants (SHIPPING_COST, FREE_SHIPPING_THRESHOLD)
in order_service.py with no admin control at all, duplicated again in the
storefront's checkout and cart components. Tax rate already existed as a
setting but nothing ever read it — this migration gives it something to
apply to.

`orders.tax` is stored, not derived: the rate can change after an order is
placed, and the order must keep the tax it was actually charged.

Revision ID: c4f9a3e18b25
Revises: b3e8f1a927c4
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4f9a3e18b25"
down_revision: Union[str, None] = "b3e8f1a927c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "store_settings",
        sa.Column("shipping_cost", sa.Numeric(10, 2), nullable=False, server_default="250"),
    )
    op.add_column(
        "store_settings",
        sa.Column(
            "free_shipping_threshold",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="5000",
        ),
    )
    op.add_column(
        "orders",
        sa.Column("tax", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("orders", "tax")
    op.drop_column("store_settings", "free_shipping_threshold")
    op.drop_column("store_settings", "shipping_cost")
