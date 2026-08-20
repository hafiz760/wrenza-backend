"""Allow guest reviews and hold them for moderation

Reviews no longer require an account, so `user_id` becomes nullable and the
reviewer's own name and email are stored alongside. Because anyone can now
post, `is_approved` defaults to false and nothing reaches the storefront until
an admin approves it.

Existing reviews keep `is_approved = true`: they were written under the old
rules, where only signed-in customers could review, and retroactively hiding
them would blank the ratings already on the site.

Revision ID: a1c7d9e42b10
Revises: 0ecc43407f5c
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.db.base import UniversalUUID

revision: str = "a1c7d9e42b10"
down_revision: Union[str, None] = "0ecc43407f5c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column("guest_name", sa.String(100), nullable=True))
    op.add_column("reviews", sa.Column("guest_email", sa.String(255), nullable=True))
    op.alter_column(
        "reviews", "user_id", existing_type=UniversalUUID(), nullable=True
    )
    # Applies to rows inserted from here on; the rows already in the table keep
    # whatever they had.
    op.alter_column(
        "reviews",
        "is_approved",
        existing_type=sa.Boolean(),
        server_default=sa.false(),
    )


def downgrade() -> None:
    # Guest reviews have no user to attribute them to, so they cannot survive a
    # NOT NULL user_id. Dropped rather than left to break the constraint.
    op.execute("DELETE FROM reviews WHERE user_id IS NULL")
    op.alter_column(
        "reviews",
        "is_approved",
        existing_type=sa.Boolean(),
        server_default=sa.true(),
    )
    op.alter_column(
        "reviews", "user_id", existing_type=UniversalUUID(), nullable=False
    )
    op.drop_column("reviews", "guest_email")
    op.drop_column("reviews", "guest_name")
