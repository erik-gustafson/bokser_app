"""add Acenda fulfillment tables

Revision ID: d4f6a8b2c913
Revises: 814b23355530
Create Date: 2026-08-20 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d4f6a8b2c913"
down_revision: str | None = "814b23355530"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fulfillments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=True),
        sa.Column("ship_advice_id", sa.Integer(), nullable=False),
        sa.Column("carrier", sa.Text(), nullable=True),
        sa.Column("date_shipped", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shipping_method", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("fulfillment_type", sa.Text(), nullable=True),
        sa.Column("cost", sa.Float(), nullable=False),
        sa.Column("is_ltl", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="acenda",
    )
    op.create_index(
        op.f("ix_acenda_fulfillments_created_at"),
        "fulfillments",
        ["created_at"],
        unique=False,
        schema="acenda",
    )
    op.create_index(
        op.f("ix_acenda_fulfillments_date_shipped"),
        "fulfillments",
        ["date_shipped"],
        unique=False,
        schema="acenda",
    )
    op.create_index(
        op.f("ix_acenda_fulfillments_id"),
        "fulfillments",
        ["id"],
        unique=False,
        schema="acenda",
    )
    op.create_index(
        op.f("ix_acenda_fulfillments_ship_advice_id"),
        "fulfillments",
        ["ship_advice_id"],
        unique=False,
        schema="acenda",
    )
    op.create_index(
        op.f("ix_acenda_fulfillments_updated_at"),
        "fulfillments",
        ["updated_at"],
        unique=False,
        schema="acenda",
    )

    op.create_table(
        "fulfillment_tracking",
        sa.Column("tracking_number", sa.Text(), nullable=False),
        sa.Column("fulfillment_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["fulfillment_id"],
            ["acenda.fulfillments.id"],
        ),
        sa.PrimaryKeyConstraint("tracking_number", "fulfillment_id"),
        schema="acenda",
    )
    op.create_index(
        op.f("ix_acenda_fulfillment_tracking_fulfillment_id"),
        "fulfillment_tracking",
        ["fulfillment_id"],
        unique=False,
        schema="acenda",
    )

    op.create_table(
        "fulfillment_items",
        sa.Column("fulfillment_id", sa.Integer(), nullable=False),
        sa.Column("ship_advice_item_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["fulfillment_id"],
            ["acenda.fulfillments.id"],
        ),
        sa.PrimaryKeyConstraint("fulfillment_id", "ship_advice_item_id"),
        schema="acenda",
    )
    op.create_index(
        op.f("ix_acenda_fulfillment_items_fulfillment_id"),
        "fulfillment_items",
        ["fulfillment_id"],
        unique=False,
        schema="acenda",
    )
    op.create_index(
        op.f("ix_acenda_fulfillment_items_ship_advice_item_id"),
        "fulfillment_items",
        ["ship_advice_item_id"],
        unique=False,
        schema="acenda",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_acenda_fulfillment_items_ship_advice_item_id"),
        table_name="fulfillment_items",
        schema="acenda",
    )
    op.drop_index(
        op.f("ix_acenda_fulfillment_items_fulfillment_id"),
        table_name="fulfillment_items",
        schema="acenda",
    )
    op.drop_table("fulfillment_items", schema="acenda")

    op.drop_index(
        op.f("ix_acenda_fulfillment_tracking_fulfillment_id"),
        table_name="fulfillment_tracking",
        schema="acenda",
    )
    op.drop_table("fulfillment_tracking", schema="acenda")

    op.drop_index(
        op.f("ix_acenda_fulfillments_updated_at"),
        table_name="fulfillments",
        schema="acenda",
    )
    op.drop_index(
        op.f("ix_acenda_fulfillments_ship_advice_id"),
        table_name="fulfillments",
        schema="acenda",
    )
    op.drop_index(
        op.f("ix_acenda_fulfillments_id"),
        table_name="fulfillments",
        schema="acenda",
    )
    op.drop_index(
        op.f("ix_acenda_fulfillments_date_shipped"),
        table_name="fulfillments",
        schema="acenda",
    )
    op.drop_index(
        op.f("ix_acenda_fulfillments_created_at"),
        table_name="fulfillments",
        schema="acenda",
    )
    op.drop_table("fulfillments", schema="acenda")
