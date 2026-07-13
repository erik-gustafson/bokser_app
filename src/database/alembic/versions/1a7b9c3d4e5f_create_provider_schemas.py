"""create provider schemas

Revision ID: 1a7b9c3d4e5f
Revises: f3b1e2a4c9d7
Create Date: 2026-07-13 22:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "1a7b9c3d4e5f"
down_revision: str | None = "f3b1e2a4c9d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS acenda")
    op.execute("CREATE SCHEMA IF NOT EXISTS sos")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS sos")
    op.execute("DROP SCHEMA IF EXISTS acenda")
