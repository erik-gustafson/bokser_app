"""Normalize SOS channel and priority references.

Revision ID: c4e8a1d2f903
Revises: a782ff62aca0
Create Date: 2026-07-30
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c4e8a1d2f903"
down_revision: str | None = "a782ff62aca0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOS_SCHEMA = "sos"
REFERENCE_FIELDS: dict[str, tuple[str, ...]] = {
    "sales_order_headers": ("channel", "priority"),
    "invoice_headers": ("channel",),
    "shipment_headers": ("channel", "priority"),
}


def upgrade() -> None:
    for table_name, field_names in REFERENCE_FIELDS.items():
        for field_name in field_names:
            op.add_column(
                table_name,
                sa.Column(f"{field_name}_id", sa.Integer(), nullable=True),
                schema=SOS_SCHEMA,
            )
            op.add_column(
                table_name,
                sa.Column(f"{field_name}_name", sa.Text(), nullable=True),
                schema=SOS_SCHEMA,
            )
            op.execute(
                sa.text(
                    f"UPDATE {SOS_SCHEMA}.{table_name} "
                    f"SET {field_name}_name = {field_name} "
                    f"WHERE {field_name} IS NOT NULL"
                )
            )
            op.drop_column(table_name, field_name, schema=SOS_SCHEMA)


def downgrade() -> None:
    for table_name, field_names in REFERENCE_FIELDS.items():
        for field_name in field_names:
            op.add_column(
                table_name,
                sa.Column(field_name, sa.Text(), nullable=True),
                schema=SOS_SCHEMA,
            )
            op.execute(
                sa.text(
                    f"UPDATE {SOS_SCHEMA}.{table_name} "
                    f"SET {field_name} = {field_name}_name "
                    f"WHERE {field_name}_name IS NOT NULL"
                )
            )
            op.drop_column(
                table_name,
                f"{field_name}_name",
                schema=SOS_SCHEMA,
            )
            op.drop_column(
                table_name,
                f"{field_name}_id",
                schema=SOS_SCHEMA,
            )
