"""add product short description

Revision ID: f771438fe8db
Revises: 813c5817370e
Create Date: 2026-08-04 01:21:48.926496

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f771438fe8db'
down_revision: Union[str, None] = '813c5817370e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products", sa.Column("short_description", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("products", "short_description")
