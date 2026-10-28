"""Add customer email verification state.

Revision ID: b8d1f4c6a2e9
Revises: e18b72a9c4d1
Create Date: 2026-10-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8d1f4c6a2e9"
down_revision: Union[str, None] = "e18b72a9c4d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Keep all accounts that existed before OTP enforcement usable.
    op.execute(sa.text("UPDATE users SET email_verified_at = CURRENT_TIMESTAMP"))


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
