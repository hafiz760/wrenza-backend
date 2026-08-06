"""drop brand columns from store settings

Revision ID: 433958e164bb
Revises: 44e0868a42f7
Create Date: 2026-08-04 01:57:44.120411

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '433958e164bb'
down_revision: Union[str, None] = '44e0868a42f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Brand identity lives in the storefront, not the database.

    Logo, phone, address and social URLs are edited by a developer at deploy
    time and are read by Organization schema. Holding them in two places
    guarantees they eventually disagree, and inconsistent brand facts are
    exactly what weakens the entity signal these fields were meant to build.
    """
    for column in (
        "logo_url",
        "phone",
        "address",
        "facebook_url",
        "instagram_url",
    ):
        op.drop_column("store_settings", column)


def downgrade() -> None:
    for column in ("logo_url", "address", "facebook_url", "instagram_url"):
        op.add_column(
            "store_settings",
            sa.Column(column, sa.String(length=500), nullable=False, server_default=""),
        )
    op.add_column(
        "store_settings",
        sa.Column("phone", sa.String(length=30), nullable=False, server_default=""),
    )
