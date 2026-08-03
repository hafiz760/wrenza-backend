"""add attribute taxonomy

Revision ID: ce4af2adfbd2
Revises: 7fbb7a2247da
Create Date: 2026-08-03 09:55:45.886339

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce4af2adfbd2'
down_revision: Union[str, None] = '7fbb7a2247da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attributes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_filterable", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_attributes_slug", "attributes", ["slug"], unique=True)

    op.create_table(
        "attribute_terms",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("attribute_id", sa.UUID(), nullable=False),
        sa.Column("value", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["attribute_id"], ["attributes.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attribute_id", "slug", name="uq_attribute_term_slug"),
    )


def downgrade() -> None:
    op.drop_table("attribute_terms")
    op.drop_index("ix_attributes_slug", table_name="attributes")
    op.drop_table("attributes")
