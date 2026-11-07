"""Preserve product slugs for permanent storefront redirects.

Revision ID: a92d14e6f308
Revises: f1a2b3c4d5e6
"""
from alembic import op
import sqlalchemy as sa
from app.db.base import UniversalUUID
import uuid

revision = "a92d14e6f308"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if not sa.inspect(conn).has_table("product_slug_history"):
        op.create_table(
            "product_slug_history",
            sa.Column("id", UniversalUUID(), primary_key=True),
            sa.Column("slug", sa.String(255), nullable=False),
            sa.Column("product_id", UniversalUUID(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        )
        op.create_index("ix_product_slug_history_slug", "product_slug_history", ["slug"], unique=True)
        op.create_index("ix_product_slug_history_product_id", "product_slug_history", ["product_id"])
    # The Heritage rename happened before slug history existed. Record it only
    # if the new product exists and the old URL has not been reassigned.
    product_id = conn.execute(sa.text("SELECT id FROM products WHERE slug = :slug"), {"slug": "heritage-leather-long-wallet"}).scalar()
    occupied = conn.execute(sa.text("SELECT id FROM products WHERE slug = :slug"), {"slug": "genuine-leather-long-wallet-men"}).scalar()
    alias = conn.execute(sa.text("SELECT id FROM product_slug_history WHERE slug = :slug"), {"slug": "genuine-leather-long-wallet-men"}).scalar()
    if product_id and not occupied and not alias:
        history = sa.table("product_slug_history", sa.column("id", UniversalUUID()), sa.column("slug", sa.String()), sa.column("product_id", UniversalUUID()))
        conn.execute(history.insert().values(id=str(uuid.uuid4()), slug="genuine-leather-long-wallet-men", product_id=product_id))


def downgrade() -> None:
    op.drop_index("ix_product_slug_history_product_id", table_name="product_slug_history")
    op.drop_index("ix_product_slug_history_slug", table_name="product_slug_history")
    op.drop_table("product_slug_history")
