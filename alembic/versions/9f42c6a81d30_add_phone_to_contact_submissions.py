"""add phone to contact submissions

Revision ID: 9f42c6a81d30
Revises: 37a56a3ce867
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f42c6a81d30"
down_revision: Union[str, None] = "37a56a3ce867"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "contact_submissions", sa.Column("phone", sa.String(length=50), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("contact_submissions", "phone")
