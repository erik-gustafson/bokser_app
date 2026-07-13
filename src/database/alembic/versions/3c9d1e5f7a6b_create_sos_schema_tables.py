"""create sos schema tables

Revision ID: 3c9d1e5f7a6b
Revises: 2b8c0d4e5f6a
Create Date: 2026-07-13 22:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "3c9d1e5f7a6b"
down_revision: str | None = "2b8c0d4e5f6a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOS_SCHEMA = "sos"


def _address_columns(prefix: str) -> list[sa.Column]:
    return [
        sa.Column(f"{prefix}_company", sa.Text(), nullable=True),
        sa.Column(f"{prefix}_contact", sa.Text(), nullable=True),
        sa.Column(f"{prefix}_phone", sa.Text(), nullable=True),
        sa.Column(f"{prefix}_email", sa.Text(), nullable=True),
        sa.Column(f"{prefix}_address_name", sa.Text(), nullable=True),
        sa.Column(f"{prefix}_address_type", sa.Text(), nullable=True),
        sa.Column(f"{prefix}_address_line_1", sa.Text(), nullable=True),
        sa.Column(f"{prefix}_address_line_2", sa.Text(), nullable=True),
        sa.Column(f"{prefix}_address_line_3", sa.Text(), nullable=True),
        sa.Column(f"{prefix}_address_line_4", sa.Text(), nullable=True),
        sa.Column(f"{prefix}_address_line_5", sa.Text(), nullable=True),
        sa.Column(f"{prefix}_city", sa.Text(), nullable=True),
        sa.Column(f"{prefix}_state_province", sa.Text(), nullable=True),
        sa.Column(f"{prefix}_postal_code", sa.Text(), nullable=True),
        sa.Column(f"{prefix}_country", sa.Text(), nullable=True),
    ]


def _create_linked_transaction_table(
    table_name: str,
    parent_column: str,
    parent_table: str,
) -> None:
    op.create_table(
        table_name,
        sa.Column(parent_column, sa.Integer(), nullable=False),
        sa.Column("linked_transaction_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("ref_number", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            [parent_column],
            [f"{SOS_SCHEMA}.{parent_table}.id"],
        ),
        sa.PrimaryKeyConstraint(
            parent_column,
            "linked_transaction_id",
            "type",
            "line_number",
        ),
        schema=SOS_SCHEMA,
    )


def _line_common_columns(
    parent_fk_name: str, parent_table_name: str
) -> list[sa.Column]:
    return [
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(parent_fk_name, sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("item_name", sa.Text(), nullable=True),
        sa.Column("class_id", sa.Integer(), nullable=True),
        sa.Column("class_name", sa.Text(), nullable=True),
        sa.Column("job_raw", sa.JSON(), nullable=True),
        sa.Column("workcenter_raw", sa.JSON(), nullable=True),
        sa.Column("tax_taxable", sa.Boolean(), nullable=True),
        sa.Column("tax_tax_code_raw", sa.JSON(), nullable=True),
        sa.Column("tax_tax_exempt_reason_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("weight_unit", sa.String(length=32), nullable=True),
        sa.Column("volume_unit", sa.String(length=32), nullable=True),
        sa.Column("unit_price", sa.Float(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("alt_amount", sa.Float(), nullable=True),
        sa.Column("picked", sa.Float(), nullable=True),
        sa.Column("shipped", sa.Float(), nullable=True),
        sa.Column("invoiced", sa.Float(), nullable=True),
        sa.Column("produced", sa.Float(), nullable=True),
        sa.Column("returned", sa.Float(), nullable=True),
        sa.Column("cost", sa.Float(), nullable=True),
        sa.Column("margin", sa.Float(), nullable=True),
        sa.Column("list_price", sa.Float(), nullable=True),
        sa.Column("percent_discount", sa.Float(), nullable=True),
        sa.Column("back_ordered", sa.Float(), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uom_id", sa.Integer(), nullable=True),
        sa.Column("uom_name", sa.String(length=64), nullable=True),
        sa.Column("bin", sa.Text(), nullable=True),
        sa.Column("lot", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            [parent_fk_name],
            [f"{SOS_SCHEMA}.{parent_table_name}.id"],
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "sales_order_headers",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("starred", sa.Integer(), nullable=True),
        sa.Column("sync_token", sa.Integer(), nullable=True),
        sa.Column("number", sa.String(length=128), nullable=True),
        sa.Column("date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("customer_name", sa.Text(), nullable=True),
        sa.Column("customer_fullname", sa.Text(), nullable=True),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("location_name", sa.Text(), nullable=True),
        *_address_columns("billing"),
        *_address_columns("shipping"),
        sa.Column("terms_id", sa.Integer(), nullable=True),
        sa.Column("terms_name", sa.Text(), nullable=True),
        sa.Column("sales_rep_raw", sa.JSON(), nullable=True),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("priority", sa.Text(), nullable=True),
        sa.Column("assigned_to_user_raw", sa.JSON(), nullable=True),
        sa.Column("order_stage_id", sa.Integer(), nullable=True),
        sa.Column("order_stage_name", sa.Text(), nullable=True),
        sa.Column("tax_code_id", sa.Integer(), nullable=True),
        sa.Column("tax_code_name", sa.Text(), nullable=True),
        sa.Column("currency_id", sa.Integer(), nullable=True),
        sa.Column("currency_name", sa.Text(), nullable=True),
        sa.Column("serial_raw", sa.JSON(), nullable=True),
        sa.Column("transaction_location_quickbooks", sa.Text(), nullable=True),
        sa.Column("exchange_rate", sa.Float(), nullable=True),
        sa.Column("customer_message", sa.Text(), nullable=True),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("customer_notes", sa.Text(), nullable=True),
        sa.Column("customer_po", sa.Text(), nullable=True),
        sa.Column("deposit_amount", sa.Float(), nullable=True),
        sa.Column("sub_total", sa.Float(), nullable=True),
        sa.Column("discount_percent", sa.Float(), nullable=True),
        sa.Column("discount_amount", sa.Float(), nullable=True),
        sa.Column("tax_percent", sa.Float(), nullable=True),
        sa.Column("tax_amount", sa.Float(), nullable=True),
        sa.Column("shipping_amount", sa.Float(), nullable=True),
        sa.Column("total", sa.Float(), nullable=True),
        sa.Column("discount_taxable", sa.Boolean(), nullable=True),
        sa.Column("shipping_taxable", sa.Boolean(), nullable=True),
        sa.Column("drop_ship", sa.Boolean(), nullable=True),
        sa.Column("closed", sa.Boolean(), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=True),
        sa.Column("summary_only", sa.Boolean(), nullable=True),
        sa.Column("has_signature", sa.Boolean(), nullable=True),
        sa.Column("store_customer_token", sa.Boolean(), nullable=True),
        sa.Column("force_save", sa.Boolean(), nullable=True),
        sa.Column("earliest_due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("account_token", sa.Text(), nullable=True),
        sa.Column("status_link", sa.Text(), nullable=True),
        sa.Column("keys_raw", sa.JSON(), nullable=True),
        sa.Column("values_raw", sa.JSON(), nullable=True),
        schema=SOS_SCHEMA,
    )
    op.create_index(
        "ix_sales_order_headers_date",
        "sales_order_headers",
        ["date"],
        unique=False,
        schema=SOS_SCHEMA,
    )

    op.create_table(
        "sales_order_lines",
        *_line_common_columns("sales_order_id", "sales_order_headers"),
        schema=SOS_SCHEMA,
    )
    op.create_index(
        "ix_sales_order_lines_sales_order_id",
        "sales_order_lines",
        ["sales_order_id"],
        unique=False,
        schema=SOS_SCHEMA,
    )

    op.create_table(
        "sales_order_custom_fields",
        sa.Column("sales_order_id", sa.Integer(), nullable=False),
        sa.Column("custom_field_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("data_type", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["sales_order_id"], [f"{SOS_SCHEMA}.sales_order_headers.id"]
        ),
        sa.PrimaryKeyConstraint("sales_order_id", "custom_field_id"),
        schema=SOS_SCHEMA,
    )

    _create_linked_transaction_table(
        "sales_order_header_linked_transactions",
        "sales_order_id",
        "sales_order_headers",
    )
    _create_linked_transaction_table(
        "sales_order_line_linked_transactions",
        "sales_order_line_id",
        "sales_order_lines",
    )

    op.create_table(
        "invoice_headers",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("starred", sa.Integer(), nullable=True),
        sa.Column("sync_token", sa.Integer(), nullable=True),
        sa.Column("number", sa.String(length=128), nullable=True),
        sa.Column("date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("customer_name", sa.Text(), nullable=True),
        sa.Column("customer_fullname", sa.Text(), nullable=True),
        *_address_columns("billing"),
        *_address_columns("shipping"),
        sa.Column("terms_id", sa.Integer(), nullable=True),
        sa.Column("terms_name", sa.Text(), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sales_rep_raw", sa.JSON(), nullable=True),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("tax_code_id", sa.Integer(), nullable=True),
        sa.Column("tax_code_name", sa.Text(), nullable=True),
        sa.Column("currency_id", sa.Integer(), nullable=True),
        sa.Column("currency_name", sa.Text(), nullable=True),
        sa.Column("sos_payment_link", sa.Text(), nullable=True),
        sa.Column("transaction_location_quickbooks", sa.Text(), nullable=True),
        sa.Column("exchange_rate", sa.Float(), nullable=True),
        sa.Column("customer_message", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("customer_notes", sa.Text(), nullable=True),
        sa.Column("customer_po", sa.Text(), nullable=True),
        sa.Column("deposit_amount", sa.Float(), nullable=True),
        sa.Column("sub_total", sa.Float(), nullable=True),
        sa.Column("discount_percent", sa.Float(), nullable=True),
        sa.Column("discount_amount", sa.Float(), nullable=True),
        sa.Column("tax_percent", sa.Float(), nullable=True),
        sa.Column("tax_amount", sa.Float(), nullable=True),
        sa.Column("shipping_amount", sa.Float(), nullable=True),
        sa.Column("balance", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("tracking_number", sa.Text(), nullable=True),
        sa.Column("ship_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipping_method_id", sa.Integer(), nullable=True),
        sa.Column("shipping_method_name", sa.Text(), nullable=True),
        sa.Column("total", sa.Float(), nullable=True),
        sa.Column("discount_taxable", sa.Boolean(), nullable=True),
        sa.Column("shipping_taxable", sa.Boolean(), nullable=True),
        sa.Column("voided", sa.Boolean(), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=True),
        sa.Column("summary_only", sa.Boolean(), nullable=True),
        sa.Column("has_signature", sa.Boolean(), nullable=True),
        sa.Column("force_save", sa.Boolean(), nullable=True),
        sa.Column("sync_message", sa.Text(), nullable=True),
        sa.Column("last_sync", sa.DateTime(timezone=True), nullable=True),
        sa.Column("keys_raw", sa.JSON(), nullable=True),
        sa.Column("values_raw", sa.JSON(), nullable=True),
        schema=SOS_SCHEMA,
    )
    op.create_index(
        "ix_invoice_headers_date",
        "invoice_headers",
        ["date"],
        unique=False,
        schema=SOS_SCHEMA,
    )

    op.create_table(
        "invoice_lines",
        *_line_common_columns("invoice_id", "invoice_headers"),
        schema=SOS_SCHEMA,
    )
    op.create_index(
        "ix_invoice_lines_invoice_id",
        "invoice_lines",
        ["invoice_id"],
        unique=False,
        schema=SOS_SCHEMA,
    )

    op.create_table(
        "invoice_custom_fields",
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("custom_field_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("data_type", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["invoice_id"], [f"{SOS_SCHEMA}.invoice_headers.id"]),
        sa.PrimaryKeyConstraint("invoice_id", "custom_field_id"),
        schema=SOS_SCHEMA,
    )

    _create_linked_transaction_table(
        "invoice_header_linked_transactions",
        "invoice_id",
        "invoice_headers",
    )
    _create_linked_transaction_table(
        "invoice_line_linked_transactions",
        "invoice_line_id",
        "invoice_lines",
    )

    op.create_table(
        "shipment_headers",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("starred", sa.Integer(), nullable=True),
        sa.Column("sync_token", sa.Integer(), nullable=True),
        sa.Column("number", sa.String(length=128), nullable=True),
        sa.Column("date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("customer_name", sa.Text(), nullable=True),
        sa.Column("customer_fullname", sa.Text(), nullable=True),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("location_name", sa.Text(), nullable=True),
        *_address_columns("billing"),
        *_address_columns("shipping"),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("priority", sa.Text(), nullable=True),
        sa.Column("assigned_to_user_raw", sa.JSON(), nullable=True),
        sa.Column("shipping_method_id", sa.Integer(), nullable=True),
        sa.Column("shipping_method_name", sa.Text(), nullable=True),
        sa.Column("tracking_number", sa.Text(), nullable=True),
        sa.Column("customer_message", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("customer_notes", sa.Text(), nullable=True),
        sa.Column("customer_po", sa.Text(), nullable=True),
        sa.Column("ship_by", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipping_amount", sa.Float(), nullable=True),
        sa.Column("total", sa.Float(), nullable=True),
        sa.Column("force_to_ship_station", sa.Boolean(), nullable=True),
        sa.Column("create_bill_for_shipping_amount", sa.Boolean(), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=True),
        sa.Column("summary_only", sa.Boolean(), nullable=True),
        sa.Column("has_signature", sa.Boolean(), nullable=True),
        sa.Column("tracking_link", sa.Text(), nullable=True),
        sa.Column("keys_raw", sa.JSON(), nullable=True),
        sa.Column("values_raw", sa.JSON(), nullable=True),
        schema=SOS_SCHEMA,
    )
    op.create_index(
        "ix_shipment_headers_date",
        "shipment_headers",
        ["date"],
        unique=False,
        schema=SOS_SCHEMA,
    )

    op.create_table(
        "shipment_lines",
        *_line_common_columns("shipment_id", "shipment_headers"),
        schema=SOS_SCHEMA,
    )
    op.create_index(
        "ix_shipment_lines_shipment_id",
        "shipment_lines",
        ["shipment_id"],
        unique=False,
        schema=SOS_SCHEMA,
    )

    op.create_table(
        "shipment_custom_fields",
        sa.Column("shipment_id", sa.Integer(), nullable=False),
        sa.Column("custom_field_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("data_type", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["shipment_id"], [f"{SOS_SCHEMA}.shipment_headers.id"]
        ),
        sa.PrimaryKeyConstraint("shipment_id", "custom_field_id"),
        schema=SOS_SCHEMA,
    )

    _create_linked_transaction_table(
        "shipment_header_linked_transactions",
        "shipment_id",
        "shipment_headers",
    )
    _create_linked_transaction_table(
        "shipment_line_linked_transactions",
        "shipment_line_id",
        "shipment_lines",
    )

    op.create_table(
        "item_receipt_headers",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("starred", sa.Integer(), nullable=True),
        sa.Column("sync_token", sa.Integer(), nullable=True),
        sa.Column("number", sa.String(length=128), nullable=True),
        sa.Column("date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vendor_id", sa.Integer(), nullable=True),
        sa.Column("vendor_name", sa.Text(), nullable=True),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("location_name", sa.Text(), nullable=True),
        sa.Column("terms_id", sa.Integer(), nullable=True),
        sa.Column("terms_name", sa.Text(), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("currency_id", sa.Integer(), nullable=True),
        sa.Column("currency_name", sa.Text(), nullable=True),
        sa.Column("tax_code_id", sa.Integer(), nullable=True),
        sa.Column("tax_code_name", sa.Text(), nullable=True),
        sa.Column("exchange_rate", sa.Float(), nullable=True),
        sa.Column("vendor_message", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("vendor_notes", sa.Text(), nullable=True),
        sa.Column("payment", sa.String(length=64), nullable=True),
        sa.Column("vendor_invoice_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "vendor_invoice_due_date", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("deposit_amount", sa.Float(), nullable=True),
        sa.Column("sub_total", sa.Float(), nullable=True),
        sa.Column("tax_amount", sa.Float(), nullable=True),
        sa.Column("total", sa.Float(), nullable=True),
        sa.Column("overhead", sa.Float(), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=True),
        sa.Column("summary_only", sa.Boolean(), nullable=True),
        sa.Column("has_signature", sa.Boolean(), nullable=True),
        sa.Column("update_default_costs", sa.Boolean(), nullable=True),
        sa.Column("auto_serial_lots", sa.Boolean(), nullable=True),
        sa.Column("keys_raw", sa.JSON(), nullable=True),
        sa.Column("values_raw", sa.JSON(), nullable=True),
        schema=SOS_SCHEMA,
    )
    op.create_index(
        "ix_item_receipt_headers_date",
        "item_receipt_headers",
        ["date"],
        unique=False,
        schema=SOS_SCHEMA,
    )

    op.create_table(
        "item_receipt_lines",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("item_receipt_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("item_name", sa.Text(), nullable=True),
        sa.Column("vendor_part_number", sa.Text(), nullable=True),
        sa.Column("class_id", sa.Integer(), nullable=True),
        sa.Column("class_name", sa.Text(), nullable=True),
        sa.Column("job_raw", sa.JSON(), nullable=True),
        sa.Column("workcenter_raw", sa.JSON(), nullable=True),
        sa.Column("customer_raw", sa.JSON(), nullable=True),
        sa.Column("tax_taxable", sa.Boolean(), nullable=True),
        sa.Column("tax_tax_code_raw", sa.JSON(), nullable=True),
        sa.Column("tax_tax_exempt_reason_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("weight_unit", sa.String(length=32), nullable=True),
        sa.Column("volume_unit", sa.String(length=32), nullable=True),
        sa.Column("unit_price", sa.Float(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("received", sa.Float(), nullable=True),
        sa.Column("uom_id", sa.Integer(), nullable=True),
        sa.Column("uom_name", sa.String(length=64), nullable=True),
        sa.Column("bin", sa.Text(), nullable=True),
        sa.Column("lot", sa.Text(), nullable=True),
        sa.Column("lot_expiration", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["item_receipt_id"], [f"{SOS_SCHEMA}.item_receipt_headers.id"]
        ),
        schema=SOS_SCHEMA,
    )
    op.create_index(
        "ix_item_receipt_lines_item_receipt_id",
        "item_receipt_lines",
        ["item_receipt_id"],
        unique=False,
        schema=SOS_SCHEMA,
    )

    op.create_table(
        "item_receipt_custom_fields",
        sa.Column("item_receipt_id", sa.Integer(), nullable=False),
        sa.Column("custom_field_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("data_type", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["item_receipt_id"], [f"{SOS_SCHEMA}.item_receipt_headers.id"]
        ),
        sa.PrimaryKeyConstraint("item_receipt_id", "custom_field_id"),
        schema=SOS_SCHEMA,
    )

    _create_linked_transaction_table(
        "item_receipt_header_linked_transactions",
        "item_receipt_id",
        "item_receipt_headers",
    )
    _create_linked_transaction_table(
        "item_receipt_line_linked_transactions",
        "item_receipt_line_id",
        "item_receipt_lines",
    )

    op.create_table(
        "item_receipt_other_costs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("item_receipt_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("item_name", sa.Text(), nullable=True),
        sa.Column("vendor_id", sa.Integer(), nullable=True),
        sa.Column("vendor_name", sa.Text(), nullable=True),
        sa.Column("class_id", sa.Integer(), nullable=True),
        sa.Column("class_name", sa.Text(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("bill", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(
            ["item_receipt_id"], [f"{SOS_SCHEMA}.item_receipt_headers.id"]
        ),
        schema=SOS_SCHEMA,
    )
    op.create_index(
        "ix_item_receipt_other_costs_item_receipt_id",
        "item_receipt_other_costs",
        ["item_receipt_id"],
        unique=False,
        schema=SOS_SCHEMA,
    )

    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("starred", sa.Integer(), nullable=True),
        sa.Column("sync_token", sa.Integer(), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("fullname", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sku", sa.String(length=128), nullable=True),
        sa.Column("barcode", sa.String(length=128), nullable=True),
        sa.Column("type", sa.String(length=128), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("purchase_description", sa.Text(), nullable=True),
        sa.Column("vendor_part_number", sa.Text(), nullable=True),
        sa.Column("customer_part_number", sa.Text(), nullable=True),
        sa.Column("vendor_raw", sa.JSON(), nullable=True),
        sa.Column("bin", sa.Text(), nullable=True),
        sa.Column("warranty_raw", sa.JSON(), nullable=True),
        sa.Column("category_raw", sa.JSON(), nullable=True),
        sa.Column("class_id", sa.Integer(), nullable=True),
        sa.Column("class_name", sa.Text(), nullable=True),
        sa.Column("income_account_id", sa.Integer(), nullable=True),
        sa.Column("income_account_name", sa.Text(), nullable=True),
        sa.Column("cogs_account_id", sa.Integer(), nullable=True),
        sa.Column("cogs_account_name", sa.Text(), nullable=True),
        sa.Column("asset_account_id", sa.Integer(), nullable=True),
        sa.Column("asset_account_name", sa.Text(), nullable=True),
        sa.Column("expense_account_id", sa.Integer(), nullable=True),
        sa.Column("expense_account_name", sa.Text(), nullable=True),
        sa.Column("onhand", sa.Float(), nullable=True),
        sa.Column("available", sa.Float(), nullable=True),
        sa.Column("on_so", sa.Float(), nullable=True),
        sa.Column("on_sr", sa.Float(), nullable=True),
        sa.Column("rented", sa.Float(), nullable=True),
        sa.Column("on_wo", sa.Float(), nullable=True),
        sa.Column("on_po", sa.Float(), nullable=True),
        sa.Column("on_rma", sa.Float(), nullable=True),
        sa.Column("reorder_point", sa.Float(), nullable=True),
        sa.Column("max_stock", sa.Float(), nullable=True),
        sa.Column("lead_time", sa.Float(), nullable=True),
        sa.Column("sales_price", sa.Float(), nullable=True),
        sa.Column("base_sales_price", sa.Float(), nullable=True),
        sa.Column("markup_percent", sa.Float(), nullable=True),
        sa.Column("use_markup", sa.Boolean(), nullable=True),
        sa.Column("minimum_price", sa.Float(), nullable=True),
        sa.Column("base_purchase_cost", sa.Float(), nullable=True),
        sa.Column("purchase_cost", sa.Float(), nullable=True),
        sa.Column("cost_basis", sa.Float(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("suggested_quantity", sa.Float(), nullable=True),
        sa.Column("weight_unit", sa.String(length=32), nullable=True),
        sa.Column("volume_unit", sa.String(length=32), nullable=True),
        sa.Column("sublevel", sa.Integer(), nullable=True),
        sa.Column("taxable", sa.Boolean(), nullable=True),
        sa.Column("sales_tax_code_raw", sa.JSON(), nullable=True),
        sa.Column("purchase_tax_code_raw", sa.JSON(), nullable=True),
        sa.Column("will_sync", sa.Boolean(), nullable=True),
        sa.Column("update_shopify", sa.Boolean(), nullable=True),
        sa.Column("update_big_commerce", sa.Boolean(), nullable=True),
        sa.Column("always_shippable", sa.Boolean(), nullable=True),
        sa.Column("has_image", sa.Boolean(), nullable=True),
        sa.Column("serial_tracking", sa.Boolean(), nullable=True),
        sa.Column("lot_tracking", sa.Boolean(), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=True),
        sa.Column("show_on_sales_forms", sa.Boolean(), nullable=True),
        sa.Column("show_on_purchasing_forms", sa.Boolean(), nullable=True),
        sa.Column("show_on_manufacturing_forms", sa.Boolean(), nullable=True),
        sa.Column("summary_only", sa.Boolean(), nullable=True),
        sa.Column("image_as_base64_string", sa.Text(), nullable=True),
        sa.Column("image_changed", sa.Boolean(), nullable=True),
        sa.Column("picture_file", sa.Text(), nullable=True),
        sa.Column("has_variants", sa.Boolean(), nullable=True),
        sa.Column("variant_master_raw", sa.JSON(), nullable=True),
        sa.Column("commission_rate", sa.Float(), nullable=True),
        sa.Column("commission_amount", sa.Float(), nullable=True),
        sa.Column("commission_exempt", sa.Boolean(), nullable=True),
        sa.Column("sync_message", sa.Text(), nullable=True),
        sa.Column("last_sync", sa.DateTime(timezone=True), nullable=True),
        sa.Column("keys_raw", sa.JSON(), nullable=True),
        sa.Column("values_raw", sa.JSON(), nullable=True),
        sa.Column("location_bins_raw", sa.JSON(), nullable=True),
        schema=SOS_SCHEMA,
    )

    op.create_table(
        "item_custom_fields",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("custom_field_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("data_type", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["item_id"], [f"{SOS_SCHEMA}.items.id"]),
        sa.PrimaryKeyConstraint("item_id", "custom_field_id"),
        schema=SOS_SCHEMA,
    )

    op.create_table(
        "item_uoms",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("uom_id", sa.Integer(), nullable=False),
        sa.Column("uom_name", sa.String(length=64), nullable=True),
        sa.Column("conversion", sa.Float(), nullable=True),
        sa.Column("is_base", sa.Boolean(), nullable=True),
        sa.Column("sales_price", sa.Float(), nullable=True),
        sa.Column("purchase_cost", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["item_id"], [f"{SOS_SCHEMA}.items.id"]),
        sa.PrimaryKeyConstraint("item_id", "uom_id"),
        schema=SOS_SCHEMA,
    )


def downgrade() -> None:
    for table_name in (
        "item_uoms",
        "item_custom_fields",
        "items",
        "item_receipt_other_costs",
        "item_receipt_line_linked_transactions",
        "item_receipt_header_linked_transactions",
        "item_receipt_custom_fields",
        "item_receipt_lines",
        "item_receipt_headers",
        "shipment_line_linked_transactions",
        "shipment_header_linked_transactions",
        "shipment_custom_fields",
        "shipment_lines",
        "shipment_headers",
        "invoice_line_linked_transactions",
        "invoice_header_linked_transactions",
        "invoice_custom_fields",
        "invoice_lines",
        "invoice_headers",
        "sales_order_line_linked_transactions",
        "sales_order_header_linked_transactions",
        "sales_order_custom_fields",
        "sales_order_lines",
        "sales_order_headers",
    ):
        op.drop_table(table_name, schema=SOS_SCHEMA)
