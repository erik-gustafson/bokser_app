"""move acenda tables to provider schema

Revision ID: 2b8c0d4e5f6a
Revises: 1a7b9c3d4e5f
Create Date: 2026-07-13 22:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "2b8c0d4e5f6a"
down_revision: str | None = "1a7b9c3d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACENDA_TABLES = (
    {
        "old_table": "acenda_order_headers",
        "new_table": "order_headers",
        "indexes": (
            ("ix_acenda_order_headers_created_at", "ix_order_headers_created_at"),
            ("ix_acenda_order_headers_id", "ix_order_headers_id"),
            ("ix_acenda_order_headers_order_number", "ix_order_headers_order_number"),
            ("ix_acenda_order_headers_ordered_at", "ix_order_headers_ordered_at"),
            ("ix_acenda_order_headers_status", "ix_order_headers_status"),
            ("ix_acenda_order_headers_updated_at", "ix_order_headers_updated_at"),
        ),
        "constraints": (),
    },
    {
        "old_table": "acenda_order_items",
        "new_table": "order_items",
        "indexes": (
            ("ix_acenda_order_items_created_at", "ix_order_items_created_at"),
            ("ix_acenda_order_items_id", "ix_order_items_id"),
            ("ix_acenda_order_items_order_id", "ix_order_items_order_id"),
            ("ix_acenda_order_items_updated_at", "ix_order_items_updated_at"),
        ),
        "constraints": (
            ("acenda_order_items_order_id_fkey", "order_items_order_id_fkey"),
        ),
    },
    {
        "old_table": "acenda_ship_advice_headers",
        "new_table": "ship_advice_headers",
        "indexes": (
            (
                "ix_acenda_ship_advice_headers_created_at",
                "ix_ship_advice_headers_created_at",
            ),
            ("ix_acenda_ship_advice_headers_id", "ix_ship_advice_headers_id"),
            (
                "ix_acenda_ship_advice_headers_order_id",
                "ix_ship_advice_headers_order_id",
            ),
            (
                "ix_acenda_ship_advice_headers_updated_at",
                "ix_ship_advice_headers_updated_at",
            ),
        ),
        "constraints": (),
    },
    {
        "old_table": "acenda_order_line_discounts",
        "new_table": "order_line_discounts",
        "indexes": (
            (
                "ix_acenda_order_line_discounts_created_at",
                "ix_order_line_discounts_created_at",
            ),
            ("ix_acenda_order_line_discounts_id", "ix_order_line_discounts_id"),
            (
                "ix_acenda_order_line_discounts_order_item_id",
                "ix_order_line_discounts_order_item_id",
            ),
            (
                "ix_acenda_order_line_discounts_updated_at",
                "ix_order_line_discounts_updated_at",
            ),
        ),
        "constraints": (
            (
                "acenda_order_line_discounts_order_item_id_fkey",
                "order_line_discounts_order_item_id_fkey",
            ),
        ),
    },
    {
        "old_table": "acenda_order_line_kit_items",
        "new_table": "order_line_kit_items",
        "indexes": (
            (
                "ix_acenda_order_line_kit_items_created_at",
                "ix_order_line_kit_items_created_at",
            ),
            ("ix_acenda_order_line_kit_items_id", "ix_order_line_kit_items_id"),
            (
                "ix_acenda_order_line_kit_items_order_item_id",
                "ix_order_line_kit_items_order_item_id",
            ),
            (
                "ix_acenda_order_line_kit_items_updated_at",
                "ix_order_line_kit_items_updated_at",
            ),
        ),
        "constraints": (
            (
                "acenda_order_line_kit_items_order_item_id_fkey",
                "order_line_kit_items_order_item_id_fkey",
            ),
        ),
    },
    {
        "old_table": "acenda_order_returns",
        "new_table": "order_returns",
        "indexes": (
            ("ix_acenda_order_returns_created_at", "ix_order_returns_created_at"),
            ("ix_acenda_order_returns_id", "ix_order_returns_id"),
            ("ix_acenda_order_returns_order_id", "ix_order_returns_order_id"),
            (
                "ix_acenda_order_returns_order_item_id",
                "ix_order_returns_order_item_id",
            ),
            ("ix_acenda_order_returns_updated_at", "ix_order_returns_updated_at"),
        ),
        "constraints": (
            ("acenda_order_returns_order_id_fkey", "order_returns_order_id_fkey"),
            (
                "acenda_order_returns_order_item_id_fkey",
                "order_returns_order_item_id_fkey",
            ),
        ),
    },
    {
        "old_table": "acenda_ship_advice_items",
        "new_table": "ship_advice_items",
        "indexes": (
            ("ix_acenda_ship_advice_items_id", "ix_ship_advice_items_id"),
            (
                "ix_acenda_ship_advice_items_order_item_id",
                "ix_ship_advice_items_order_item_id",
            ),
            (
                "ix_acenda_ship_advice_items_ship_advice_id",
                "ix_ship_advice_items_ship_advice_id",
            ),
        ),
        "constraints": (
            (
                "acenda_ship_advice_items_ship_advice_id_fkey",
                "ship_advice_items_ship_advice_id_fkey",
            ),
        ),
    },
)


def _rename_forward(
    *,
    old_table: str,
    new_table: str,
    indexes: tuple[tuple[str, str], ...],
    constraints: tuple[tuple[str, str], ...],
) -> None:
    op.execute(f"ALTER TABLE public.{old_table} RENAME TO {new_table}")
    op.execute(
        f"ALTER TABLE public.{new_table} "
        f"RENAME CONSTRAINT {old_table}_pkey TO {new_table}_pkey"
    )

    for old_name, new_name in constraints:
        op.execute(
            f"ALTER TABLE public.{new_table} "
            f"RENAME CONSTRAINT {old_name} TO {new_name}"
        )

    for old_name, new_name in indexes:
        op.execute(f"ALTER INDEX public.{old_name} RENAME TO {new_name}")

    op.execute(
        f"ALTER SEQUENCE IF EXISTS public.{old_table}_id_seq RENAME TO {new_table}_id_seq"
    )
    op.execute(f"ALTER TABLE public.{new_table} SET SCHEMA acenda")


def _rename_backward(
    *,
    old_table: str,
    new_table: str,
    indexes: tuple[tuple[str, str], ...],
    constraints: tuple[tuple[str, str], ...],
) -> None:
    op.execute(f"ALTER TABLE acenda.{new_table} SET SCHEMA public")
    op.execute(
        f"ALTER TABLE public.{new_table} "
        f"RENAME CONSTRAINT {new_table}_pkey TO {old_table}_pkey"
    )

    for old_name, new_name in constraints:
        op.execute(
            f"ALTER TABLE public.{new_table} "
            f"RENAME CONSTRAINT {new_name} TO {old_name}"
        )

    for old_name, new_name in indexes:
        op.execute(f"ALTER INDEX public.{new_name} RENAME TO {old_name}")

    op.execute(f"ALTER TABLE public.{new_table} RENAME TO {old_table}")
    op.execute(
        f"ALTER SEQUENCE IF EXISTS public.{new_table}_id_seq RENAME TO {old_table}_id_seq"
    )


def upgrade() -> None:
    for table in ACENDA_TABLES:
        _rename_forward(**table)


def downgrade() -> None:
    for table in reversed(ACENDA_TABLES):
        _rename_backward(**table)
