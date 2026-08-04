from __future__ import annotations

from datetime import datetime
from typing import Any
from dataclasses import dataclass

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.database import Base

SOS_SCHEMA = "sos"


class SosSalesOrderHeader(Base):
    __tablename__ = "sales_order_headers"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    starred: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    sync_token: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_fullname: Mapped[str | None] = mapped_column(Text, nullable=True)

    location_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    billing_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_state_province: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_country: Mapped[str | None] = mapped_column(Text, nullable=True)

    shipping_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_state_province: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_country: Mapped[str | None] = mapped_column(Text, nullable=True)

    terms_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    terms_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    sales_rep_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    channel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to_user_raw: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )

    order_stage_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    order_stage_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    tax_code_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_code_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    currency_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    serial_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    transaction_location_quickbooks: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    exchange_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    customer_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_po: Mapped[str | None] = mapped_column(Text, nullable=True)
    deposit_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    sub_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    shipping_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    shipping_taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    drop_ship: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    closed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    archived: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    summary_only: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_signature: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    store_customer_token: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    force_save: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    earliest_due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    account_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    keys_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    values_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    lines: Mapped[list["SosSalesOrderLine"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    custom_fields: Mapped[list["SosSalesOrderCustomField"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    linked_transactions: Mapped[list["SosSalesOrderHeaderLinkedTransactions"]] = (
        relationship(
            back_populates="header",
            cascade="all, delete-orphan",
        )
    )


class SosSalesOrderLine(Base):
    __tablename__ = "sales_order_lines"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sales_order_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.sales_order_headers.id"),
        index=True,
        nullable=False,
    )
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    workcenter_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tax_tax_code_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_tax_exempt_reason_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    volume_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    alt_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    picked: Mapped[float | None] = mapped_column(Float, nullable=True)
    shipped: Mapped[float | None] = mapped_column(Float, nullable=True)
    invoiced: Mapped[float | None] = mapped_column(Float, nullable=True)
    produced: Mapped[float | None] = mapped_column(Float, nullable=True)
    returned: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    list_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    percent_discount: Mapped[float | None] = mapped_column(Float, nullable=True)
    back_ordered: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    uom_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uom_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bin: Mapped[str | None] = mapped_column(Text, nullable=True)
    lot: Mapped[str | None] = mapped_column(Text, nullable=True)
    header: Mapped["SosSalesOrderHeader"] = relationship(back_populates="lines")
    linked_transactions: Mapped[list["SosSalesOrderLineLinkedTransactions"]] = (
        relationship(
            back_populates="line",
            cascade="all, delete-orphan",
        )
    )


class SosSalesOrderCustomField(Base):
    __tablename__ = "sales_order_custom_fields"
    __table_args__ = {"schema": SOS_SCHEMA}

    sales_order_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.sales_order_headers.id"),
        primary_key=True,
    )
    custom_field_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    header: Mapped["SosSalesOrderHeader"] = relationship(back_populates="custom_fields")


class SosSalesOrderHeaderLinkedTransactions(Base):
    __tablename__ = "sales_order_header_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    sales_order_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.sales_order_headers.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    header: Mapped["SosSalesOrderHeader"] = relationship(
        back_populates="linked_transactions"
    )


class SosSalesOrderLineLinkedTransactions(Base):
    __tablename__ = "sales_order_line_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    sales_order_line_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.sales_order_lines.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    line: Mapped["SosSalesOrderLine"] = relationship(
        back_populates="linked_transactions"
    )


class SosInvoiceHeader(Base):
    __tablename__ = "invoice_headers"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    starred: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    sync_token: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_fullname: Mapped[str | None] = mapped_column(Text, nullable=True)

    billing_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_state_province: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_country: Mapped[str | None] = mapped_column(Text, nullable=True)

    shipping_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_state_province: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_country: Mapped[str | None] = mapped_column(Text, nullable=True)

    terms_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    terms_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sales_rep_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    channel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)

    tax_code_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_code_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    sos_payment_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    transaction_location_quickbooks: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    exchange_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    customer_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_po: Mapped[str | None] = mapped_column(Text, nullable=True)
    deposit_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    sub_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    shipping_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    ship_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipping_method_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shipping_method_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    shipping_taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    voided: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    archived: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    summary_only: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_signature: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    force_save: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sync_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    keys_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    values_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    lines: Mapped[list["SosInvoiceLine"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    custom_fields: Mapped[list["SosInvoiceCustomField"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    linked_transactions: Mapped[list["SosInvoiceHeaderLinkedTransactions"]] = (
        relationship(
            back_populates="header",
            cascade="all, delete-orphan",
        )
    )


class SosInvoiceLine(Base):
    __tablename__ = "invoice_lines"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.invoice_headers.id"),
        index=True,
        nullable=False,
    )
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    workcenter_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tax_tax_code_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_tax_exempt_reason_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    volume_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    alt_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    picked: Mapped[float | None] = mapped_column(Float, nullable=True)
    shipped: Mapped[float | None] = mapped_column(Float, nullable=True)
    invoiced: Mapped[float | None] = mapped_column(Float, nullable=True)
    produced: Mapped[float | None] = mapped_column(Float, nullable=True)
    returned: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    list_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    percent_discount: Mapped[float | None] = mapped_column(Float, nullable=True)
    back_ordered: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    uom_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uom_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bin: Mapped[str | None] = mapped_column(Text, nullable=True)
    lot: Mapped[str | None] = mapped_column(Text, nullable=True)
    header: Mapped["SosInvoiceHeader"] = relationship(back_populates="lines")
    linked_transactions: Mapped[list["SosInvoiceLineLinkedTransactions"]] = (
        relationship(
            back_populates="line",
            cascade="all, delete-orphan",
        )
    )


class SosInvoiceCustomField(Base):
    __tablename__ = "invoice_custom_fields"
    __table_args__ = {"schema": SOS_SCHEMA}

    invoice_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.invoice_headers.id"),
        primary_key=True,
    )
    custom_field_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    header: Mapped["SosInvoiceHeader"] = relationship(back_populates="custom_fields")


class SosInvoiceHeaderLinkedTransactions(Base):
    __tablename__ = "invoice_header_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    invoice_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.invoice_headers.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    header: Mapped["SosInvoiceHeader"] = relationship(
        back_populates="linked_transactions"
    )


class SosInvoiceLineLinkedTransactions(Base):
    __tablename__ = "invoice_line_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    invoice_line_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.invoice_lines.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    line: Mapped["SosInvoiceLine"] = relationship(back_populates="linked_transactions")


class SosSalesReceiptHeader(Base):
    __tablename__ = "sales_receipt_headers"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    starred: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    sync_token: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    fs_payment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_fullname: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    billing_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_state_province: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_country: Mapped[str | None] = mapped_column(Text, nullable=True)

    shipping_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_state_province: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_country: Mapped[str | None] = mapped_column(Text, nullable=True)

    payment_method_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_method_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_method_sync_token: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    payment_method_sos_pay_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    deposit_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deposit_account_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    sales_rep_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    channel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to_user_raw: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    order_stage_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    order_stage_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_code_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_code_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_method_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shipping_method_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    tracking_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    ship_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    transaction_location_quickbooks: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    exchange_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    customer_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    can_ship: Mapped[str | None] = mapped_column(String(64), nullable=True)
    account_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_po: Mapped[str | None] = mapped_column(Text, nullable=True)
    deposit_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    sub_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    shipping_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    shipping_taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    drop_ship: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    closed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    archived: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    summary_only: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_signature: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    store_customer_token: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    force_save: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    earliest_due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sos_pay_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    keys_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    values_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    lines: Mapped[list["SosSalesReceiptLine"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    custom_fields: Mapped[list["SosSalesReceiptCustomField"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    linked_transactions: Mapped[
        list["SosSalesReceiptHeaderLinkedTransactions"]
    ] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )


class SosSalesReceiptLine(Base):
    __tablename__ = "sales_receipt_lines"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sales_receipt_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.sales_receipt_headers.id"),
        index=True,
        nullable=False,
    )
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    workcenter_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tax_tax_code_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_tax_exempt_reason_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    volume_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    alt_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    picked: Mapped[float | None] = mapped_column(Float, nullable=True)
    shipped: Mapped[float | None] = mapped_column(Float, nullable=True)
    invoiced: Mapped[float | None] = mapped_column(Float, nullable=True)
    produced: Mapped[float | None] = mapped_column(Float, nullable=True)
    returned: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    list_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    percent_discount: Mapped[float | None] = mapped_column(Float, nullable=True)
    back_ordered: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    uom_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uom_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bin: Mapped[str | None] = mapped_column(Text, nullable=True)
    lot: Mapped[str | None] = mapped_column(Text, nullable=True)
    serials_raw: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)

    header: Mapped["SosSalesReceiptHeader"] = relationship(back_populates="lines")
    linked_transactions: Mapped[
        list["SosSalesReceiptLineLinkedTransactions"]
    ] = relationship(
        back_populates="line",
        cascade="all, delete-orphan",
    )


class SosSalesReceiptCustomField(Base):
    __tablename__ = "sales_receipt_custom_fields"
    __table_args__ = {"schema": SOS_SCHEMA}

    sales_receipt_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.sales_receipt_headers.id"),
        primary_key=True,
    )
    custom_field_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    header: Mapped["SosSalesReceiptHeader"] = relationship(
        back_populates="custom_fields"
    )


class SosSalesReceiptHeaderLinkedTransactions(Base):
    __tablename__ = "sales_receipt_header_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    sales_receipt_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.sales_receipt_headers.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    header: Mapped["SosSalesReceiptHeader"] = relationship(
        back_populates="linked_transactions"
    )


class SosSalesReceiptLineLinkedTransactions(Base):
    __tablename__ = "sales_receipt_line_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    sales_receipt_line_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.sales_receipt_lines.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    line: Mapped["SosSalesReceiptLine"] = relationship(
        back_populates="linked_transactions"
    )


class SosEstimateHeader(Base):
    __tablename__ = "estimate_headers"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    starred: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    sync_token: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_fullname: Mapped[str | None] = mapped_column(Text, nullable=True)

    billing_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_state_province: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_country: Mapped[str | None] = mapped_column(Text, nullable=True)

    shipping_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_state_province: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_country: Mapped[str | None] = mapped_column(Text, nullable=True)

    sales_rep_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    channel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_code_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_code_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    transaction_location_quickbooks: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    exchange_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    customer_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    deposit_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    sub_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    shipping_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    shipping_taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    accepted_by_raw: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    accepted_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expiration: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    summary_only: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_signature: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    force_save: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sync_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    keys_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    values_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    lines: Mapped[list["SosEstimateLine"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    custom_fields: Mapped[list["SosEstimateCustomField"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    linked_transactions: Mapped[list["SosEstimateHeaderLinkedTransactions"]] = (
        relationship(
            back_populates="header",
            cascade="all, delete-orphan",
        )
    )


class SosEstimateLine(Base):
    __tablename__ = "estimate_lines"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estimate_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.estimate_headers.id"),
        index=True,
        nullable=False,
    )
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    workcenter_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tax_tax_code_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_tax_exempt_reason_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    volume_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    alt_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    picked: Mapped[float | None] = mapped_column(Float, nullable=True)
    shipped: Mapped[float | None] = mapped_column(Float, nullable=True)
    invoiced: Mapped[float | None] = mapped_column(Float, nullable=True)
    produced: Mapped[float | None] = mapped_column(Float, nullable=True)
    returned: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    list_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    percent_discount: Mapped[float | None] = mapped_column(Float, nullable=True)
    back_ordered: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    uom_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uom_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bin: Mapped[str | None] = mapped_column(Text, nullable=True)
    lot: Mapped[str | None] = mapped_column(Text, nullable=True)
    serials_raw: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)

    header: Mapped["SosEstimateHeader"] = relationship(back_populates="lines")
    linked_transactions: Mapped[list["SosEstimateLineLinkedTransactions"]] = (
        relationship(
            back_populates="line",
            cascade="all, delete-orphan",
        )
    )


class SosEstimateCustomField(Base):
    __tablename__ = "estimate_custom_fields"
    __table_args__ = {"schema": SOS_SCHEMA}

    estimate_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.estimate_headers.id"),
        primary_key=True,
    )
    custom_field_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    header: Mapped["SosEstimateHeader"] = relationship(back_populates="custom_fields")


class SosEstimateHeaderLinkedTransactions(Base):
    __tablename__ = "estimate_header_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    estimate_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.estimate_headers.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    header: Mapped["SosEstimateHeader"] = relationship(
        back_populates="linked_transactions"
    )


class SosEstimateLineLinkedTransactions(Base):
    __tablename__ = "estimate_line_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    estimate_line_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.estimate_lines.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    line: Mapped["SosEstimateLine"] = relationship(
        back_populates="linked_transactions"
    )


class SosShipmentHeader(Base):
    __tablename__ = "shipment_headers"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    starred: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    sync_token: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_fullname: Mapped[str | None] = mapped_column(Text, nullable=True)

    location_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    billing_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_state_province: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_country: Mapped[str | None] = mapped_column(Text, nullable=True)

    shipping_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_state_province: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_country: Mapped[str | None] = mapped_column(Text, nullable=True)

    channel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to_user_raw: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    shipping_method_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shipping_method_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    customer_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_po: Mapped[str | None] = mapped_column(Text, nullable=True)
    ship_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipping_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)
    force_to_ship_station: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    create_bill_for_shipping_amount: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    archived: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    summary_only: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_signature: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tracking_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    keys_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    values_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    lines: Mapped[list["SosShipmentLine"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    custom_fields: Mapped[list["SosShipmentCustomField"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    linked_transactions: Mapped[list["SosShipmentHeaderLinkedTransactions"]] = (
        relationship(
            back_populates="header",
            cascade="all, delete-orphan",
        )
    )


class SosShipmentLine(Base):
    __tablename__ = "shipment_lines"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.shipment_headers.id"),
        index=True,
        nullable=False,
    )
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    workcenter_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tax_tax_code_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_tax_exempt_reason_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    volume_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    alt_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    picked: Mapped[float | None] = mapped_column(Float, nullable=True)
    shipped: Mapped[float | None] = mapped_column(Float, nullable=True)
    invoiced: Mapped[float | None] = mapped_column(Float, nullable=True)
    produced: Mapped[float | None] = mapped_column(Float, nullable=True)
    returned: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    list_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    percent_discount: Mapped[float | None] = mapped_column(Float, nullable=True)
    back_ordered: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    uom_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uom_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bin: Mapped[str | None] = mapped_column(Text, nullable=True)
    lot: Mapped[str | None] = mapped_column(Text, nullable=True)
    header: Mapped["SosShipmentHeader"] = relationship(back_populates="lines")
    linked_transactions: Mapped[list["SosShipmentLineLinkedTransactions"]] = (
        relationship(
            back_populates="line",
            cascade="all, delete-orphan",
        )
    )


class SosShipmentCustomField(Base):
    __tablename__ = "shipment_custom_fields"
    __table_args__ = {"schema": SOS_SCHEMA}

    shipment_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.shipment_headers.id"),
        primary_key=True,
    )
    custom_field_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    header: Mapped["SosShipmentHeader"] = relationship(back_populates="custom_fields")


class SosShipmentHeaderLinkedTransactions(Base):
    __tablename__ = "shipment_header_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    shipment_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.shipment_headers.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    header: Mapped["SosShipmentHeader"] = relationship(
        back_populates="linked_transactions"
    )


class SosShipmentLineLinkedTransactions(Base):
    __tablename__ = "shipment_line_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    shipment_line_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.shipment_lines.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    line: Mapped["SosShipmentLine"] = relationship(back_populates="linked_transactions")


class SosReturnHeader(Base):
    __tablename__ = "return_headers"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    populate_from_object_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    populate_from_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    starred: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    sync_token: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_fullname: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    sales_rep_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    channel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_method_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shipping_method_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    tracking_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    exchange_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    customer_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ship_by: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    shipping_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)
    create_credit_memo: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    create_bill_for_shipping_amount: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    archived: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    summary_only: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_signature: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    keys_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    values_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    lines: Mapped[list["SosReturnLine"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    custom_fields: Mapped[list["SosReturnCustomField"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    linked_transactions: Mapped[list["SosReturnHeaderLinkedTransactions"]] = (
        relationship(
            back_populates="header",
            cascade="all, delete-orphan",
        )
    )


class SosReturnLine(Base):
    __tablename__ = "return_lines"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    return_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.return_headers.id"),
        index=True,
        nullable=False,
    )
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    workcenter_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tax_tax_code_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_tax_exempt_reason_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    volume_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    alt_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    picked: Mapped[float | None] = mapped_column(Float, nullable=True)
    shipped: Mapped[float | None] = mapped_column(Float, nullable=True)
    invoiced: Mapped[float | None] = mapped_column(Float, nullable=True)
    produced: Mapped[float | None] = mapped_column(Float, nullable=True)
    returned: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    list_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    percent_discount: Mapped[float | None] = mapped_column(Float, nullable=True)
    back_ordered: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    uom_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uom_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bin: Mapped[str | None] = mapped_column(Text, nullable=True)
    lot: Mapped[str | None] = mapped_column(Text, nullable=True)
    serials_raw: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)

    header: Mapped["SosReturnHeader"] = relationship(back_populates="lines")
    linked_transactions: Mapped[list["SosReturnLineLinkedTransactions"]] = (
        relationship(
            back_populates="line",
            cascade="all, delete-orphan",
        )
    )


class SosReturnCustomField(Base):
    __tablename__ = "return_custom_fields"
    __table_args__ = {"schema": SOS_SCHEMA}

    return_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.return_headers.id"),
        primary_key=True,
    )
    custom_field_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    header: Mapped["SosReturnHeader"] = relationship(back_populates="custom_fields")


class SosReturnHeaderLinkedTransactions(Base):
    __tablename__ = "return_header_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    return_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.return_headers.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    header: Mapped["SosReturnHeader"] = relationship(
        back_populates="linked_transactions"
    )


class SosReturnLineLinkedTransactions(Base):
    __tablename__ = "return_line_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    return_line_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.return_lines.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    line: Mapped["SosReturnLine"] = relationship(back_populates="linked_transactions")


class SosRmaHeader(Base):
    __tablename__ = "rma_headers"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    starred: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    sync_token: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_fullname: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    billing_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_state_province: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_country: Mapped[str | None] = mapped_column(Text, nullable=True)

    shipping_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_state_province: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_country: Mapped[str | None] = mapped_column(Text, nullable=True)

    sales_rep_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    channel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expiration: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    shipping_method_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shipping_method_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)
    closed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    archived: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    summary_only: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_signature: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    keys_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    values_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    lines: Mapped[list["SosRmaLine"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    custom_fields: Mapped[list["SosRmaCustomField"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    linked_transactions: Mapped[list["SosRmaHeaderLinkedTransactions"]] = (
        relationship(
            back_populates="header",
            cascade="all, delete-orphan",
        )
    )


class SosRmaLine(Base):
    __tablename__ = "rma_lines"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rma_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.rma_headers.id"),
        index=True,
        nullable=False,
    )
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    workcenter_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tax_tax_code_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_tax_exempt_reason_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    volume_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    alt_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    picked: Mapped[float | None] = mapped_column(Float, nullable=True)
    shipped: Mapped[float | None] = mapped_column(Float, nullable=True)
    invoiced: Mapped[float | None] = mapped_column(Float, nullable=True)
    produced: Mapped[float | None] = mapped_column(Float, nullable=True)
    returned: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    list_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    percent_discount: Mapped[float | None] = mapped_column(Float, nullable=True)
    back_ordered: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    uom_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uom_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bin: Mapped[str | None] = mapped_column(Text, nullable=True)
    lot: Mapped[str | None] = mapped_column(Text, nullable=True)
    serials_raw: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)

    header: Mapped["SosRmaHeader"] = relationship(back_populates="lines")
    linked_transactions: Mapped[list["SosRmaLineLinkedTransactions"]] = (
        relationship(
            back_populates="line",
            cascade="all, delete-orphan",
        )
    )


class SosRmaCustomField(Base):
    __tablename__ = "rma_custom_fields"
    __table_args__ = {"schema": SOS_SCHEMA}

    rma_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.rma_headers.id"),
        primary_key=True,
    )
    custom_field_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    header: Mapped["SosRmaHeader"] = relationship(back_populates="custom_fields")


class SosRmaHeaderLinkedTransactions(Base):
    __tablename__ = "rma_header_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    rma_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.rma_headers.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    header: Mapped["SosRmaHeader"] = relationship(
        back_populates="linked_transactions"
    )


class SosRmaLineLinkedTransactions(Base):
    __tablename__ = "rma_line_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    rma_line_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.rma_lines.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    line: Mapped["SosRmaLine"] = relationship(back_populates="linked_transactions")


class SosPurchaseOrderHeader(Base):
    __tablename__ = "purchase_order_headers"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    starred: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    sync_token: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deleted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    vendor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vendor_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_fullname: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    billing_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_state_province: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_country: Mapped[str | None] = mapped_column(Text, nullable=True)

    shipping_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_state_province: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_country: Mapped[str | None] = mapped_column(Text, nullable=True)

    terms_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    terms_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to_user_raw: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    currency_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_code_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_code_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_method_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shipping_method_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    tracking_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    exchange_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    vendor_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    vendor_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expected_ship: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deposit_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    sub_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)
    open_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    drop_ship: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    blanket_po: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    contract_manufacturing: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    confirmed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    closed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    archived: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pending_approval: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    summary_only: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_signature: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    update_default_costs: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    sync_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    keys_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    values_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    lines: Mapped[list["SosPurchaseOrderLine"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    custom_fields: Mapped[list["SosPurchaseOrderCustomField"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    linked_transactions: Mapped[
        list["SosPurchaseOrderHeaderLinkedTransactions"]
    ] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )


class SosPurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.purchase_order_headers.id"),
        index=True,
        nullable=False,
    )
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    vendor_part_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    workcenter_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    customer_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tax_tax_code_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_tax_exempt_reason_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    volume_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    received: Mapped[float | None] = mapped_column(Float, nullable=True)
    uom_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uom_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bin: Mapped[str | None] = mapped_column(Text, nullable=True)
    lot: Mapped[str | None] = mapped_column(Text, nullable=True)
    lot_expiration: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    serials_raw: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)

    header: Mapped["SosPurchaseOrderHeader"] = relationship(back_populates="lines")
    linked_transactions: Mapped[
        list["SosPurchaseOrderLineLinkedTransactions"]
    ] = relationship(
        back_populates="line",
        cascade="all, delete-orphan",
    )


class SosPurchaseOrderCustomField(Base):
    __tablename__ = "purchase_order_custom_fields"
    __table_args__ = {"schema": SOS_SCHEMA}

    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.purchase_order_headers.id"),
        primary_key=True,
    )
    custom_field_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    header: Mapped["SosPurchaseOrderHeader"] = relationship(
        back_populates="custom_fields"
    )


class SosPurchaseOrderHeaderLinkedTransactions(Base):
    __tablename__ = "purchase_order_header_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.purchase_order_headers.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    header: Mapped["SosPurchaseOrderHeader"] = relationship(
        back_populates="linked_transactions"
    )


class SosPurchaseOrderLineLinkedTransactions(Base):
    __tablename__ = "purchase_order_line_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    purchase_order_line_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.purchase_order_lines.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    line: Mapped["SosPurchaseOrderLine"] = relationship(
        back_populates="linked_transactions"
    )


class SosItemReceiptHeader(Base):
    __tablename__ = "item_receipt_headers"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    starred: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    sync_token: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    vendor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vendor_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    terms_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_code_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_code_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    exchange_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    vendor_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    vendor_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vendor_invoice_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    vendor_invoice_due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deposit_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    sub_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)
    overhead: Mapped[float | None] = mapped_column(Float, nullable=True)
    archived: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    summary_only: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_signature: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    update_default_costs: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    auto_serial_lots: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    keys_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    values_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    lines: Mapped[list["SosItemReceiptLine"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    custom_fields: Mapped[list["SosItemReceiptCustomField"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    linked_transactions: Mapped[list["SosItemReceiptHeaderLinkedTransactions"]] = (
        relationship(
            back_populates="header",
            cascade="all, delete-orphan",
        )
    )
    other_costs: Mapped[list["SosItemReceiptOtherCost"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )


class SosItemReceiptLine(Base):
    __tablename__ = "item_receipt_lines"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_receipt_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.item_receipt_headers.id"),
        index=True,
        nullable=False,
    )
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    vendor_part_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    workcenter_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    customer_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tax_tax_code_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_tax_exempt_reason_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    volume_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    received: Mapped[float | None] = mapped_column(Float, nullable=True)
    uom_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uom_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bin: Mapped[str | None] = mapped_column(Text, nullable=True)
    lot: Mapped[str | None] = mapped_column(Text, nullable=True)
    lot_expiration: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    header: Mapped["SosItemReceiptHeader"] = relationship(back_populates="lines")
    linked_transactions: Mapped[list["SosItemReceiptLineLinkedTransactions"]] = (
        relationship(
            back_populates="line",
            cascade="all, delete-orphan",
        )
    )


class SosItemReceiptCustomField(Base):
    __tablename__ = "item_receipt_custom_fields"
    __table_args__ = {"schema": SOS_SCHEMA}

    item_receipt_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.item_receipt_headers.id"),
        primary_key=True,
    )
    custom_field_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    header: Mapped["SosItemReceiptHeader"] = relationship(
        back_populates="custom_fields"
    )


class SosItemReceiptHeaderLinkedTransactions(Base):
    __tablename__ = "item_receipt_header_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    item_receipt_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.item_receipt_headers.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    header: Mapped["SosItemReceiptHeader"] = relationship(
        back_populates="linked_transactions"
    )


class SosItemReceiptLineLinkedTransactions(Base):
    __tablename__ = "item_receipt_line_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    item_receipt_line_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.item_receipt_lines.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    line: Mapped["SosItemReceiptLine"] = relationship(
        back_populates="linked_transactions"
    )


class SosItemReceiptOtherCost(Base):
    __tablename__ = "item_receipt_other_costs"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_receipt_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.item_receipt_headers.id"),
        index=True,
        nullable=False,
    )
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    vendor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vendor_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    bill: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    header: Mapped["SosItemReceiptHeader"] = relationship(back_populates="other_costs")


class SosItem(Base):
    __tablename__ = "items"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    starred: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    sync_token: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    fullname: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(128), nullable=True)
    type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    purchase_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    vendor_part_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_part_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    vendor_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    bin: Mapped[str | None] = mapped_column(Text, nullable=True)
    warranty_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    category_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    class_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    income_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    income_account_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    cogs_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cogs_account_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    asset_account_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    expense_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expense_account_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    onhand: Mapped[float | None] = mapped_column(Float, nullable=True)
    available: Mapped[float | None] = mapped_column(Float, nullable=True)
    on_so: Mapped[float | None] = mapped_column(Float, nullable=True)
    on_sr: Mapped[float | None] = mapped_column(Float, nullable=True)
    rented: Mapped[float | None] = mapped_column(Float, nullable=True)
    on_wo: Mapped[float | None] = mapped_column(Float, nullable=True)
    on_po: Mapped[float | None] = mapped_column(Float, nullable=True)
    on_rma: Mapped[float | None] = mapped_column(Float, nullable=True)
    reorder_point: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_stock: Mapped[float | None] = mapped_column(Float, nullable=True)
    lead_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    sales_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_sales_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    markup_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    use_markup: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    minimum_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_purchase_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    purchase_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_basis: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    suggested_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    volume_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sublevel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sales_tax_code_raw: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    purchase_tax_code_raw: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    will_sync: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    update_shopify: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    update_big_commerce: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    always_shippable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_image: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    serial_tracking: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    lot_tracking: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    archived: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    show_on_sales_forms: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    show_on_purchasing_forms: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    show_on_manufacturing_forms: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    summary_only: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    image_as_base64_string: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_changed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    picture_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_variants: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    variant_master_raw: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    commission_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    commission_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    commission_exempt: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sync_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    keys_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    values_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    location_bins_raw: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    custom_fields: Mapped[list["SosItemCustomField"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
    )
    uoms: Mapped[list["SosItemUom"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
    )


class SosItemCustomField(Base):
    __tablename__ = "item_custom_fields"
    __table_args__ = {"schema": SOS_SCHEMA}

    item_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.items.id"),
        primary_key=True,
    )
    custom_field_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    item: Mapped["SosItem"] = relationship(back_populates="custom_fields")


class SosItemUom(Base):
    __tablename__ = "item_uoms"
    __table_args__ = {"schema": SOS_SCHEMA}

    item_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.items.id"),
        primary_key=True,
    )
    uom_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uom_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    conversion: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_base: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sales_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    purchase_cost: Mapped[float | None] = mapped_column(Float, nullable=True)

    item: Mapped["SosItem"] = relationship(back_populates="uoms")


class SosCustomer(Base):
    __tablename__ = "customers"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    starred: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    sync_token: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    fullname: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_fullname: Mapped[str | None] = mapped_column(Text, nullable=True)
    sublevel: Mapped[int | None] = mapped_column(Integer, nullable=True)

    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    mobile: Mapped[str | None] = mapped_column(Text, nullable=True)
    alt_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    fax: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    portal_password: Mapped[str | None] = mapped_column(Text, nullable=True)

    contact_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_middle_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_last_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_suffix: Mapped[str | None] = mapped_column(Text, nullable=True)

    billing_address_line_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_state_province: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_country: Mapped[str | None] = mapped_column(Text, nullable=True)

    shipping_address_line_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address_line_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_state_province: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_country: Mapped[str | None] = mapped_column(Text, nullable=True)

    terms_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    terms_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_tier_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_tier_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_method_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_method_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_method_sync_token: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    payment_method_sos_pay_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    sales_rep_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    customer_type_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_type_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    resale_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    contractor_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_license: Mapped[str | None] = mapped_column(Text, nullable=True)
    found_us_via_raw: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    currency_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    tax_taxable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tax_tax_code_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tax_tax_exempt_reason_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    credit_hold: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    bill_with_parent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_children: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    summary_only: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_in_quick_books: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sync_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    has_card_on_file: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_four: Mapped[str | None] = mapped_column(String(4), nullable=True)
    exp_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exp_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    keys_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    values_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    custom_fields: Mapped[list["SosCustomerCustomField"]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
    )
    alt_addresses: Mapped[list["SosCustomerAltAddress"]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
    )


class SosCustomerCustomField(Base):
    __tablename__ = "customer_custom_fields"
    __table_args__ = {"schema": SOS_SCHEMA}

    customer_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.customers.id"),
        primary_key=True,
    )
    custom_field_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    customer: Mapped["SosCustomer"] = relationship(back_populates="custom_fields")


class SosCustomerAltAddress(Base):
    __tablename__ = "customer_alt_addresses"
    __table_args__ = {"schema": SOS_SCHEMA}

    customer_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.customers.id"),
        primary_key=True,
    )
    address_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    company: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_line_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_line_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_line_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_line_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_province: Mapped[str | None] = mapped_column(Text, nullable=True)
    postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)

    customer: Mapped["SosCustomer"] = relationship(back_populates="alt_addresses")


class SosPaymentHeader(Base):
    __tablename__ = "payment_headers"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    starred: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    sync_token: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    sync_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_fullname: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_method_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_method_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_method_sync_token: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    payment_method_sos_pay_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    currency_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    deposit_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deposit_account_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    billing_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_address_line_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_state_province: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_country: Mapped[str | None] = mapped_column(Text, nullable=True)

    total: Mapped[float | None] = mapped_column(Float, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_signature: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    summary_only: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    exchange_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    documents_raw: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    check_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_customer_if_not_found: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    has_card_on_file: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sos_pay_raw: Mapped[Any | None] = mapped_column(JSON, nullable=True)

    lines: Mapped[list["SosPaymentLine"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    custom_fields: Mapped[list["SosPaymentCustomField"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    linked_transactions: Mapped[list["SosPaymentHeaderLinkedTransactions"]] = (
        relationship(
            back_populates="header",
            cascade="all, delete-orphan",
        )
    )


class SosPaymentLine(Base):
    __tablename__ = "payment_lines"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.payment_headers.id"),
        index=True,
        nullable=False,
    )
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    workcenter_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)

    header: Mapped["SosPaymentHeader"] = relationship(back_populates="lines")
    linked_transactions: Mapped[list["SosPaymentLineLinkedTransactions"]] = (
        relationship(
            back_populates="line",
            cascade="all, delete-orphan",
        )
    )


class SosPaymentCustomField(Base):
    __tablename__ = "payment_custom_fields"
    __table_args__ = {"schema": SOS_SCHEMA}

    payment_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.payment_headers.id"),
        primary_key=True,
    )
    custom_field_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    header: Mapped["SosPaymentHeader"] = relationship(back_populates="custom_fields")


class SosPaymentHeaderLinkedTransactions(Base):
    __tablename__ = "payment_header_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    payment_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.payment_headers.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    header: Mapped["SosPaymentHeader"] = relationship(
        back_populates="linked_transactions"
    )


class SosPaymentLineLinkedTransactions(Base):
    __tablename__ = "payment_line_linked_transactions"
    __table_args__ = {"schema": SOS_SCHEMA}

    payment_line_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.payment_lines.id"),
        primary_key=True,
    )
    linked_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    line: Mapped["SosPaymentLine"] = relationship(
        back_populates="linked_transactions"
    )


class SosAdjustmentHeader(Base):
    __tablename__ = "adjustment_headers"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    starred: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    sync_token: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)
    account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    account_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    summary_only: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_signature: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    force_save: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    keys_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    values_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    lines: Mapped[list["SosAdjustmentLine"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )
    custom_fields: Mapped[list["SosAdjustmentCustomField"]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )


class SosAdjustmentLine(Base):
    __tablename__ = "adjustment_lines"
    __table_args__ = {"schema": SOS_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    adjustment_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.adjustment_headers.id"),
        index=True,
        nullable=False,
    )
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    workcenter_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    lot: Mapped[str | None] = mapped_column(Text, nullable=True)
    bin: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity_diff: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_diff: Mapped[float | None] = mapped_column(Float, nullable=True)
    uom_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uom_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    serials_raw: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)

    header: Mapped["SosAdjustmentHeader"] = relationship(back_populates="lines")


class SosAdjustmentCustomField(Base):
    __tablename__ = "adjustment_custom_fields"
    __table_args__ = {"schema": SOS_SCHEMA}

    adjustment_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SOS_SCHEMA}.adjustment_headers.id"),
        primary_key=True,
    )
    custom_field_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    header: Mapped["SosAdjustmentHeader"] = relationship(
        back_populates="custom_fields"
    )


class SosSalesOrderSync(Base):
    """
    Track SOS order create posts for idempotency and external ID mapping.
    """

    __tablename__ = "sales_order_sync"
    __table_args__ = (
        UniqueConstraint(
            "source", "source_line_key", name="ux_sos_order_sync_source_line"
        ),
        {"schema": SOS_SCHEMA},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_header_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_line_key: Mapped[str] = mapped_column(String(512), nullable=False)

    payload_hash: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_error: Mapped[str | None] = mapped_column(Text)

    sos_order_id: Mapped[int | None] = mapped_column(Integer, index=True)
    sos_line_id: Mapped[int | None] = mapped_column(Integer)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


@dataclass
class SosSalesOrderSyncStats:
    since: datetime | None = None
    synced: int = 0
    posted: int = 0
    failed: int = 0
    errors: int = 0

    def to_payload(self) -> dict[str, Any]:
        return {
            "synced": self.synced,
            "posted": self.posted,
            "failed": self.failed,
            "errors": self.errors,
        }
