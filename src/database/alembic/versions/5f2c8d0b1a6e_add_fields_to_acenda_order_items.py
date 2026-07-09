"""add fields column to acenda_order_items

Revision ID: 5f2c8d0b1a6e
Revises: cbc26543cd4c
Create Date: 2026-07-08 22:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "5f2c8d0b1a6e"
down_revision: str | None = "cbc26543cd4c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "acenda_order_items",
        sa.Column("fields", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("acenda_order_items", "fields")
