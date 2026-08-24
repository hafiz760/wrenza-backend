"""Add optional A+ marketing content to products

One JSON column holding a desktop image, a mobile image and alt text. Two
compositions rather than one: the copy is baked into the pixels, so scaling a
desktop layout down to a phone leaves the text too small to read.

Nullable with no backfill — a product without it simply renders no section.

Revision ID: b3e8f1a927c4
Revises: a1c7d9e42b10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3e8f1a927c4"
down_revision: Union[str, None] = "a1c7d9e42b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("a_plus_content", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "a_plus_content")
