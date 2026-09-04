"""Change shipment sync source ID to string.

Revision ID: d7c9a4f12b8e
Revises: 868c653d8d3b
Create Date: 2026-09-04
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d7c9a4f12b8e"
down_revision: str | None = "868c653d8d3b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "shipment_sync",
        "source_id",
        existing_type=sa.Integer(),
        type_=sa.String(length=128),
        existing_nullable=False,
        schema="sos",
        postgresql_using="source_id::text",
    )


def downgrade() -> None:
    op.alter_column(
        "shipment_sync",
        "source_id",
        existing_type=sa.String(length=128),
        type_=sa.Integer(),
        existing_nullable=False,
        schema="sos",
        postgresql_using="source_id::integer",
    )
