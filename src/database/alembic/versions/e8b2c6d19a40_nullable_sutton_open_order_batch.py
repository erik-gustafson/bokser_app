"""Allow Sutton open orders without a warehouse batch.

Revision ID: e8b2c6d19a40
Revises: d7c9a4f12b8e
"""

from alembic import op
import sqlalchemy as sa

revision = "e8b2c6d19a40"
down_revision = "d7c9a4f12b8e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("open_order_report", sa.Column("id", sa.Integer(), sa.Identity(), nullable=False), schema="sutton")
    op.drop_constraint("pk_sutton_open_order", "open_order_report", schema="sutton", type_="primary")
    op.create_primary_key("pk_sutton_open_order", "open_order_report", ["id"], schema="sutton")
    op.alter_column("open_order_report", "warehouse_batch", existing_type=sa.String(), nullable=True, schema="sutton")
    op.create_index(
        "uq_sutton_open_order_with_batch", "open_order_report",
        ["company", "customer_acct", "purchase_order", "warehouse_batch", "sku"],
        unique=True, schema="sutton", postgresql_where=sa.text("warehouse_batch IS NOT NULL"),
    )
    op.create_index(
        "uq_sutton_open_order_without_batch", "open_order_report",
        ["company", "customer_acct", "purchase_order", "sku"],
        unique=True, schema="sutton", postgresql_where=sa.text("warehouse_batch IS NULL"),
    )


def downgrade() -> None:
    # Refuse to restore NOT NULL while batchless rows exist; preserve their data.
    op.alter_column("open_order_report", "warehouse_batch", existing_type=sa.String(), nullable=False, schema="sutton")
    op.drop_index("uq_sutton_open_order_without_batch", table_name="open_order_report", schema="sutton")
    op.drop_index("uq_sutton_open_order_with_batch", table_name="open_order_report", schema="sutton")
    op.drop_constraint("pk_sutton_open_order", "open_order_report", schema="sutton", type_="primary")
    op.create_primary_key("pk_sutton_open_order", "open_order_report", ["company", "customer_acct", "purchase_order", "warehouse_batch", "sku"], schema="sutton")
    op.drop_column("open_order_report", "id", schema="sutton")
