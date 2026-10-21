"""Store customer photos with product reviews.

Revision ID: d7a2c941fe30
Revises: aa71c602a419
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d7a2c941fe30"
down_revision: Union[str, None] = "aa71c602a419"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The local database can be repaired directly when its Alembic revision
    # history is out of sync. Keep this migration safe to run afterward too.
    op.execute(
        "ALTER TABLE reviews ADD COLUMN IF NOT EXISTS "
        "images JSON NOT NULL DEFAULT '[]'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE reviews DROP COLUMN IF EXISTS images")
