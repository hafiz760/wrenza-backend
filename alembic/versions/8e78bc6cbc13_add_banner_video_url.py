"""add banner video url

Revision ID: 8e78bc6cbc13
Revises: 3b547c9ff109
Create Date: 2026-08-03 14:27:17.457183

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8e78bc6cbc13'
down_revision: Union[str, None] = '3b547c9ff109'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("banners", sa.Column("video_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("banners", "video_url")
