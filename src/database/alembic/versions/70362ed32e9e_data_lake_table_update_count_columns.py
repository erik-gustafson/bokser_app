"""Data Lake Table Update Count Columns

Revision ID: 70362ed32e9e
Revises: c8d8c436f3fc
Create Date: 2026-07-07 16:49:11.163901
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "70362ed32e9e"
down_revision: str | None = "c8d8c436f3fc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        UPDATE data_lake_files
        SET loaded_count = 0
        WHERE loaded_count IS NULL
    """)

    op.execute("""
        UPDATE data_lake_files
        SET skipped_count = 0
        WHERE skipped_count IS NULL
    """)

    op.execute("""
        UPDATE data_lake_files
        SET failed_count = 0
        WHERE failed_count IS NULL
    """)

    op.execute("""
        UPDATE data_lake_files
        SET attempt_count = 0
        WHERE attempt_count IS NULL
    """)

    op.alter_column(
        "data_lake_files",
        "loaded_count",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("0"),
    )

    op.alter_column(
        "data_lake_files",
        "skipped_count",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("0"),
    )

    op.alter_column(
        "data_lake_files",
        "failed_count",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("0"),
    )

    op.alter_column(
        "data_lake_files",
        "attempt_count",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("0"),
    )


def downgrade() -> None:
    op.alter_column(
        "data_lake_files",
        "attempt_count",
        existing_type=sa.Integer(),
        server_default=None,
    )

    op.alter_column(
        "data_lake_files",
        "failed_count",
        existing_type=sa.Integer(),
        server_default=None,
    )

    op.alter_column(
        "data_lake_files",
        "skipped_count",
        existing_type=sa.Integer(),
        server_default=None,
    )

    op.alter_column(
        "data_lake_files",
        "loaded_count",
        existing_type=sa.Integer(),
        server_default=None,
    )
