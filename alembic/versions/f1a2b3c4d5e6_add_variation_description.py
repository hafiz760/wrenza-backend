"""Add an optional customer-facing description to product variations.

Revision ID: f1a2b3c4d5e6
Revises: b8d1f4c6a2e9
"""
from alembic import op
import sqlalchemy as sa

revision = "f1a2b3c4d5e6"
down_revision = "b8d1f4c6a2e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("product_variations", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("product_variations", "description")
