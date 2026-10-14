"""add Instagram settings switch and business id

Revision ID: aa71c602a419
Revises: 9f42c6a81d30
Create Date: 2026-10-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aa71c602a419"
down_revision: Union[str, None] = "9f42c6a81d30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "store_settings",
        sa.Column(
            "instagram_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "store_settings",
        sa.Column("instagram_business_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("store_settings", "instagram_business_id")
    op.drop_column("store_settings", "instagram_enabled")
