"""drop acenda ship advice cross entity foreign keys

Revision ID: 9b8d6f4c2e11
Revises: 5f2c8d0b1a6e
Create Date: 2026-07-09 16:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "9b8d6f4c2e11"
down_revision: str | None = "5f2c8d0b1a6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "acenda_ship_advice_headers_order_id_fkey",
        "acenda_ship_advice_headers",
        type_="foreignkey",
    )
    op.drop_constraint(
        "acenda_ship_advice_items_order_item_id_fkey",
        "acenda_ship_advice_items",
        type_="foreignkey",
    )


def downgrade() -> None:
    op.create_foreign_key(
        "acenda_ship_advice_headers_order_id_fkey",
        "acenda_ship_advice_headers",
        "acenda_order_headers",
        ["order_id"],
        ["id"],
    )
    op.create_foreign_key(
        "acenda_ship_advice_items_order_item_id_fkey",
        "acenda_ship_advice_items",
        "acenda_order_items",
        ["order_item_id"],
        ["id"],
    )
