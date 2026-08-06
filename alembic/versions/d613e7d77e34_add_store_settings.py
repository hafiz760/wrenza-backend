"""add store settings

Revision ID: d613e7d77e34
Revises: 8e78bc6cbc13
Create Date: 2026-08-03 20:35:54.372375

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd613e7d77e34'
down_revision: Union[str, None] = '8e78bc6cbc13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "store_settings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("store_name", sa.String(length=255), nullable=False, server_default="Wrenza"),
        sa.Column("contact_email", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="PKR"),
        sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), nullable=False, server_default="0"),
        sa.Column("auto_fulfill_orders", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("low_stock_threshold", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("maintenance_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("store_settings")
