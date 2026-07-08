"""relax acenda source field constraints

Revision ID: cbc26543cd4c
Revises: 70362ed32e9e
Create Date: 2026-07-07 21:54:41.187915
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "cbc26543cd4c"
down_revision: str | None = "70362ed32e9e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _alter_type_nullable(
    table_name: str,
    column_name: str,
    *,
    existing_type: sa.types.TypeEngine,
    new_type: sa.types.TypeEngine,
) -> None:
    op.alter_column(
        table_name,
        column_name,
        existing_type=existing_type,
        type_=new_type,
        nullable=True,
    )


def _alter_nullable(
    table_name: str,
    column_name: str,
    *,
    existing_type: sa.types.TypeEngine,
) -> None:
    op.alter_column(
        table_name,
        column_name,
        existing_type=existing_type,
        nullable=True,
    )


def upgrade() -> None:
    # acenda_order_headers: widen source strings and nullable source fields.
    for column_name in [
        "created_by",
        "updated_by",
    ]:
        _alter_type_nullable(
            "acenda_order_headers",
            column_name,
            existing_type=sa.String(length=64),
            new_type=sa.String(length=128),
        )

    for column_name in [
        "purchase_order",
        "external_order_id",
        "shipping_method",
        "ship_first_name",
        "ship_last_name",
        "ship_company",
        "ship_address_1",
        "ship_address_2",
        "ship_city",
        "ship_email",
        "ship_phone_number",
        "bill_first_name",
        "bill_last_name",
        "bill_company",
        "bill_address_1",
        "bill_address_2",
        "bill_city",
        "bill_email",
        "bill_phone_number",
    ]:
        _alter_type_nullable(
            "acenda_order_headers",
            column_name,
            existing_type=sa.String(length=64),
            new_type=sa.Text(),
        )

    for column_name in [
        "sales_channel_name",
        "sales_channel_type",
        "sales_channel_subtype",
        "shipping_code",
    ]:
        _alter_type_nullable(
            "acenda_order_headers",
            column_name,
            existing_type=sa.String(length=64),
            new_type=sa.String(length=128),
        )

    for column_name in [
        "ordered_at",
        "requested_ship_date",
        "requested_delivery_date",
    ]:
        _alter_nullable(
            "acenda_order_headers",
            column_name,
            existing_type=sa.DateTime(timezone=True),
        )

    for column_name in [
        "status",
        "sales_channel_country",
        "ship_state",
        "ship_postal_code",
        "ship_country",
        "bill_state",
        "bill_postal_code",
        "bill_country",
    ]:
        _alter_nullable(
            "acenda_order_headers",
            column_name,
            existing_type=sa.String(length=64),
        )

    for column_name in [
        "sales_channel_id",
    ]:
        _alter_nullable(
            "acenda_order_headers",
            column_name,
            existing_type=sa.Integer(),
        )

    for column_name in [
        "send_email",
        "create_routings",
    ]:
        _alter_nullable(
            "acenda_order_headers",
            column_name,
            existing_type=sa.Boolean(),
        )

    # acenda_order_items
    for column_name in [
        "created_by",
        "updated_by",
    ]:
        _alter_type_nullable(
            "acenda_order_items",
            column_name,
            existing_type=sa.String(length=64),
            new_type=sa.String(length=128),
        )

    for column_name in [
        "line_id",
        "product_name",
        "shipping_method",
    ]:
        _alter_type_nullable(
            "acenda_order_items",
            column_name,
            existing_type=sa.String(length=64),
            new_type=sa.Text(),
        )

    for column_name in [
        "external_sku",
        "sku",
        "upc",
        "external_warehouse_id",
    ]:
        _alter_type_nullable(
            "acenda_order_items",
            column_name,
            existing_type=sa.String(length=64),
            new_type=sa.String(length=128),
        )

    for column_name in [
        "subscription_id",
        "product_id",
    ]:
        _alter_nullable(
            "acenda_order_items",
            column_name,
            existing_type=sa.Integer(),
        )

    for column_name in [
        "two_day_shipping",
    ]:
        _alter_nullable(
            "acenda_order_items",
            column_name,
            existing_type=sa.Boolean(),
        )

    for column_name in [
        "status",
    ]:
        _alter_nullable(
            "acenda_order_items",
            column_name,
            existing_type=sa.String(length=64),
        )

    # acenda_order_line_discounts
    for column_name in [
        "created_by",
        "updated_by",
    ]:
        _alter_type_nullable(
            "acenda_order_line_discounts",
            column_name,
            existing_type=sa.String(length=64),
            new_type=sa.String(length=128),
        )

    for column_name in [
        "promotion_code",
        "promotion_text",
    ]:
        _alter_type_nullable(
            "acenda_order_line_discounts",
            column_name,
            existing_type=sa.String(length=64),
            new_type=sa.Text(),
        )

    _alter_nullable(
        "acenda_order_line_discounts",
        "affects",
        existing_type=sa.String(length=64),
    )

    # acenda_order_line_kit_items
    for column_name in [
        "created_by",
        "updated_by",
    ]:
        _alter_type_nullable(
            "acenda_order_line_kit_items",
            column_name,
            existing_type=sa.String(length=64),
            new_type=sa.String(length=128),
        )

    _alter_type_nullable(
        "acenda_order_line_kit_items",
        "sku",
        existing_type=sa.String(length=64),
        new_type=sa.String(length=128),
    )

    _alter_nullable(
        "acenda_order_line_kit_items",
        "product_id",
        existing_type=sa.Integer(),
    )

    # acenda_order_returns
    for column_name in [
        "created_by",
        "updated_by",
    ]:
        _alter_type_nullable(
            "acenda_order_returns",
            column_name,
            existing_type=sa.String(length=64),
            new_type=sa.String(length=128),
        )

    for column_name in [
        "rma",
        "license_plate_number",
        "reason",
        "method",
        "carrier",
    ]:
        _alter_type_nullable(
            "acenda_order_returns",
            column_name,
            existing_type=sa.String(length=64),
            new_type=sa.Text(),
        )

    _alter_nullable(
        "acenda_order_returns",
        "status",
        existing_type=sa.String(length=64),
    )

    for column_name in [
        "restock_inventory",
        "return_required",
        "advance_refund",
    ]:
        _alter_nullable(
            "acenda_order_returns",
            column_name,
            existing_type=sa.Boolean(),
        )

    # acenda_ship_advice_headers
    for column_name in [
        "delivery_info_first_name",
        "delivery_info_last_name",
        "delivery_info_company",
        "delivery_info_address_1",
        "delivery_info_address_2",
        "delivery_info_city",
        "delivery_info_email",
        "delivery_info_phone_number",
    ]:
        _alter_type_nullable(
            "acenda_ship_advice_headers",
            column_name,
            existing_type=sa.String(length=64),
            new_type=sa.Text(),
        )

    for column_name in [
        "order_routing_status",
        "delivery_info_state",
        "delivery_info_postal_code",
        "delivery_info_country",
    ]:
        _alter_nullable(
            "acenda_ship_advice_headers",
            column_name,
            existing_type=sa.String(length=64),
        )

    for column_name in [
        "fulfillment_provider_id",
        "warehouse_id",
    ]:
        _alter_nullable(
            "acenda_ship_advice_headers",
            column_name,
            existing_type=sa.Integer(),
        )

    # acenda_ship_advice_items
    _alter_nullable(
        "acenda_ship_advice_items",
        "inventory_detail_id",
        existing_type=sa.Integer(),
    )


def downgrade() -> None:
    raise NotImplementedError(
        "Downgrade is unsafe because existing Acenda data may contain NULLs "
        "or strings longer than the old varchar(64) limits."
    )
