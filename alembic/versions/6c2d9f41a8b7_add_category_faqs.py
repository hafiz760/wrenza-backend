"""Add editable FAQs to product categories.

Revision ID: 6c2d9f41a8b7
Revises: a92d14e6f308
"""

from alembic import op
import sqlalchemy as sa


revision = "6c2d9f41a8b7"
down_revision = "a92d14e6f308"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("categories")}
    if "faqs" not in columns:
        op.add_column(
            "categories",
            sa.Column("faqs", sa.JSON(), nullable=False, server_default="[]"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("categories")}
    if "faqs" in columns:
        op.drop_column("categories", "faqs")
