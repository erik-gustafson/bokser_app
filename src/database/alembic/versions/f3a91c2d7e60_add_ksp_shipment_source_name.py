"""Store the cart source on KSP shipment headers.

Revision ID: f3a91c2d7e60
Revises: e8b2c6d19a40
"""

from alembic import op
import sqlalchemy as sa

revision = "f3a91c2d7e60"
down_revision = "e8b2c6d19a40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ksp_ship_headers",
        sa.Column("source_name", sa.String(), nullable=True),
        schema="warehouse_data",
    )


def downgrade() -> None:
    op.drop_column("ksp_ship_headers", "source_name", schema="warehouse_data")
