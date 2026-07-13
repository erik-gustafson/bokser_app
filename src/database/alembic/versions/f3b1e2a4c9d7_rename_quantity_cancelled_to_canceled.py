"""rename quantity_cancelled to quantity_canceled

Revision ID: f3b1e2a4c9d7
Revises: 9b8d6f4c2e11
Create Date: 2026-07-13 21:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "f3b1e2a4c9d7"
down_revision: str | None = "9b8d6f4c2e11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "acenda_order_items",
        "quantity_cancelled",
        new_column_name="quantity_canceled",
    )


def downgrade() -> None:
    op.alter_column(
        "acenda_order_items",
        "quantity_canceled",
        new_column_name="quantity_cancelled",
    )
