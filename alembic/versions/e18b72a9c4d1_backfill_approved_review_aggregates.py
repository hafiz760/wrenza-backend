"""Reconcile product ratings with approved reviews.

Revision ID: e18b72a9c4d1
Revises: d7a2c941fe30
"""

from typing import Sequence, Union

from alembic import op


revision: str = "e18b72a9c4d1"
down_revision: Union[str, None] = "d7a2c941fe30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Product.rating and review_count are denormalized fields used in product
    # responses and structured data. Rebuild them from the authoritative,
    # approved review rows so existing records also start in sync.
    op.execute(
        """
        UPDATE products AS p
        SET rating = stats.average_rating,
            review_count = stats.review_count
        FROM (
            SELECT product_id,
                   ROUND(AVG(rating)::numeric, 1) AS average_rating,
                   COUNT(*)::integer AS review_count
            FROM reviews
            WHERE is_approved IS TRUE
            GROUP BY product_id
        ) AS stats
        WHERE p.id = stats.product_id
        """
    )
    op.execute(
        """
        UPDATE products AS p
        SET rating = 0,
            review_count = 0
        WHERE NOT EXISTS (
            SELECT 1
            FROM reviews AS r
            WHERE r.product_id = p.id
              AND r.is_approved IS TRUE
        )
          AND (p.rating <> 0 OR p.review_count <> 0)
        """
    )


def downgrade() -> None:
    # Derived values cannot be safely restored to their former, potentially
    # stale values. The schema is unchanged, so this data reconciliation is
    # intentionally irreversible.
    pass
