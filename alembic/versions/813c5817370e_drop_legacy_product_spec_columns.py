"""drop legacy product spec columns

Revision ID: 813c5817370e
Revises: d613e7d77e34
Create Date: 2026-08-04 00:50:32.994499

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '813c5817370e'
down_revision: Union[str, None] = 'd613e7d77e34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop spec columns now handled by the attribute system.

    Colour, material, finish and the like are selectable options — attributes
    model them better because they are reusable and filterable. Dimensions,
    tags and care instructions stay as columns: they are measurements and free
    text, not enumerated options.
    """
    for column in (
        "material",
        "leather_type",
        "hardware_finish",
        "closure_type",
        "fabric",
        "gender",
    ):
        op.drop_column("products", column)


def downgrade() -> None:
    op.add_column("products", sa.Column("gender", sa.String(length=10), nullable=True))
    op.add_column("products", sa.Column("fabric", sa.String(length=100), nullable=True))
    op.add_column(
        "products", sa.Column("closure_type", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "products", sa.Column("hardware_finish", sa.String(length=50), nullable=True)
    )
    op.add_column(
        "products", sa.Column("leather_type", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "products", sa.Column("material", sa.String(length=100), nullable=True)
    )
