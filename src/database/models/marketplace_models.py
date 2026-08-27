from __future__ import annotations

import re

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from math import isnan
from typing import Any, Optional

from dateutil import parser as dt_parser
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from src.database.database import Base, FieldMap

# --- shared parsing helpers -------------------------------------------------- #


def _strip_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized_text = str(value).strip()
    if normalized_text.startswith("'"):
        normalized_text = normalized_text[1:]
    normalized_text = normalized_text.strip()
    return normalized_text or None


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    normalized_text = str(value).replace(",", "").strip().lower()
    numeric_match = _NUM_RE.search(normalized_text)
    if not numeric_match:
        return None
    try:
        return Decimal(numeric_match.group())
    except InvalidOperation:
        return None


def _parse_int(value: Any) -> int | None:
    dec = _parse_decimal(value)
    if dec is None:
        return None
    try:
        return int(dec)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    normalized_text = str(value).strip()
    if not normalized_text:
        return None
    # Avoid parsing pure times like "00:00.0"
    if ":" in normalized_text and all(
        separator not in normalized_text for separator in ("/", "-")
    ):
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized_text, fmt).date()
        except ValueError:
            pass
    try:
        return dt_parser.parse(normalized_text).date()
    except Exception:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    def _to_aware_utc(value: Any) -> datetime:
        to_pydatetime = getattr(value, "to_pydatetime", None)

        if callable(to_pydatetime):
            value = to_pydatetime()

        if not isinstance(value, datetime):
            raise TypeError(
                f"Expected datetime-compatible value, got {type(value).__name__}"
            )

        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    if value is None:
        return None
    if isinstance(value, datetime):
        return _to_aware_utc(value)
    if isinstance(value, date):
        return _to_aware_utc(datetime.combine(value, datetime.min.time()))
    if isinstance(value, (int, float)):
        numeric_value = float(value)
        if isnan(numeric_value):
            return None
        parsed = datetime(1899, 12, 30) + timedelta(days=numeric_value)
        return _to_aware_utc(parsed)

    normalized_text = _strip_text(value)
    if not normalized_text:
        return None
    try:
        parsed = dt_parser.parse(normalized_text)
        return _to_aware_utc(parsed)
    except Exception:
        return None


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]

    iso = getattr(value, "isoformat", None)
    if callable(iso):
        try:
            return iso()
        except Exception:
            pass

    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except Exception:
            pass

    return str(value)


class _BasePayoutSchema(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload", mode="before")
    def _ensure_payload(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        payload = value if isinstance(value, dict) else {"raw": value}
        return _json_safe(payload)

    class Config:
        extra = "ignore"


# --- Master Table ------------------------------------------------------------ #


class ProcessedPayout(Base):
    __tablename__ = "processed_payouts"
    __table_args__ = (UniqueConstraint("payout_id", name="ux_payout_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    payout_id: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    currency: Mapped[Optional[str]] = mapped_column(String(8))
    payout_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    destination: Mapped[Optional[str]] = mapped_column(String(128))
    failure_code: Mapped[Optional[str]] = mapped_column(String(128))
    failure_message: Mapped[Optional[str]] = mapped_column(Text)

    report_created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    report_start_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    report_end_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    source_file: Mapped[Optional[str]] = mapped_column(String(255))
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)

    payload: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, nullable=False, default=dict
    )

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# --- Wayfair ----------------------------------------------------------------- #


class WayfairPaymentSchema(_BasePayoutSchema):
    remittance_number: str
    remittance_date: Optional[date] = None

    invoice_number: str
    po_number: Optional[str] = None
    invoice_date: Optional[date] = None

    product_amount: Optional[Decimal] = None
    birch_lane_allowance: Optional[Decimal] = None
    joss_main_allowance: Optional[Decimal] = None
    all_modern_allowance: Optional[Decimal] = None
    wayfair_allowance: Optional[Decimal] = None
    shipping_amount: Optional[Decimal] = None
    other_amount: Optional[Decimal] = None
    tax_vat_amount: Optional[Decimal] = None
    payment_amount: Optional[Decimal] = None

    business: Optional[str] = None
    order_type: Optional[str] = None

    source_file: str
    source_row: int

    @field_validator(
        "remittance_number",
        "invoice_number",
        "po_number",
        "business",
        "order_type",
        "source_file",
        mode="before",
    )
    def _clean_text(cls, value: Any) -> Optional[str]:
        return _strip_text(value)

    @field_validator("remittance_date", "invoice_date", mode="before")
    def _clean_date(cls, value: Any) -> Optional[date]:
        return _parse_date(value)

    @field_validator(
        "product_amount",
        "birch_lane_allowance",
        "joss_main_allowance",
        "all_modern_allowance",
        "wayfair_allowance",
        "shipping_amount",
        "other_amount",
        "tax_vat_amount",
        "payment_amount",
        mode="before",
    )
    def _clean_decimal(cls, value: Any) -> Optional[Decimal]:
        return _parse_decimal(value)

    @field_validator("source_row", mode="before")
    def _clean_int(cls, value: Any) -> Optional[int]:
        return _parse_int(value)


class WayfairPayment(Base):
    __tablename__ = "wayfair_payments"
    __table_args__ = (
        UniqueConstraint(
            "remittance_number",
            "source_file",
            "source_row",
            name="ux_wayfair_payments_file_row",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    remittance_number: Mapped[str] = mapped_column(String(64), nullable=False)
    remittance_date: Mapped[Optional[date]] = mapped_column(Date)

    invoice_number: Mapped[str] = mapped_column(String(128), nullable=False)
    po_number: Mapped[Optional[str]] = mapped_column(String(128))
    invoice_date: Mapped[Optional[date]] = mapped_column(Date)

    product_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    birch_lane_allowance: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    joss_main_allowance: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    all_modern_allowance: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    wayfair_allowance: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    shipping_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    other_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    tax_vat_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    payment_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))

    business: Mapped[Optional[str]] = mapped_column(String(64))
    order_type: Mapped[Optional[str]] = mapped_column(String(64))

    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)

    payload: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, nullable=False, default=dict
    )

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    class Ingest:
        name = "wayfair_payments"
        key_fields = ["remittance_number", "source_file", "source_row"]
        field_map = [
            FieldMap("remittance_number", "remittance_number"),
            FieldMap("remittance_date", "remittance_date"),
            FieldMap("invoice_number", "invoice_number"),
            FieldMap("po_number", "po_number"),
            FieldMap("invoice_date", "invoice_date"),
            FieldMap("product_amount", "product_amount"),
            FieldMap("birch_lane_allowance", "birch_lane_allowance"),
            FieldMap("joss_main_allowance", "joss_main_allowance"),
            FieldMap("all_modern_allowance", "all_modern_allowance"),
            FieldMap("wayfair_allowance", "wayfair_allowance"),
            FieldMap("shipping_amount", "shipping_amount"),
            FieldMap("other_amount", "other_amount"),
            FieldMap("tax_vat_amount", "tax_vat_amount"),
            FieldMap("payment_amount", "payment_amount"),
            FieldMap("business", "business"),
            FieldMap("order_type", "order_type"),
            FieldMap("source_file", "source_file"),
            FieldMap("source_row", "source_row"),
            FieldMap(".", "payload"),
        ]
        schema = WayfairPaymentSchema


class WayfairDeductionSchema(_BasePayoutSchema):
    remittance_number: str
    remittance_date: Optional[date] = None

    deduction_invoice_number: str
    deduction_date: Optional[date] = None
    deduction_amount: Optional[Decimal] = None

    item_sku: Optional[str] = None
    credit_id: Optional[str] = None
    memo: Optional[str] = None
    reason: Optional[str] = None
    description: Optional[str] = None

    source_file: str
    source_row: int

    @field_validator(
        "remittance_number",
        "deduction_invoice_number",
        "item_sku",
        "credit_id",
        "memo",
        "reason",
        "description",
        "source_file",
        mode="before",
    )
    def _clean_text(cls, value: Any) -> Optional[str]:
        return _strip_text(value)

    @field_validator("remittance_date", "deduction_date", mode="before")
    def _clean_date(cls, value: Any) -> Optional[date]:
        return _parse_date(value)

    @field_validator("deduction_amount", mode="before")
    def _clean_decimal(cls, value: Any) -> Optional[Decimal]:
        return _parse_decimal(value)

    @field_validator("source_row", mode="before")
    def _clean_int(cls, value: Any) -> Optional[int]:
        return _parse_int(value)


class WayfairDeduction(Base):
    __tablename__ = "wayfair_deductions"
    __table_args__ = (
        UniqueConstraint(
            "remittance_number",
            "source_file",
            "source_row",
            name="ux_wayfair_deductions_file_row",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    remittance_number: Mapped[str] = mapped_column(String(64), nullable=False)
    remittance_date: Mapped[Optional[date]] = mapped_column(Date)

    deduction_invoice_number: Mapped[str] = mapped_column(String(128), nullable=False)
    deduction_date: Mapped[Optional[date]] = mapped_column(Date)
    deduction_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))

    item_sku: Mapped[Optional[str]] = mapped_column(String(128))
    credit_id: Mapped[Optional[str]] = mapped_column(String(128))
    memo: Mapped[Optional[str]] = mapped_column(String(255))
    reason: Mapped[Optional[str]] = mapped_column(String(128))
    description: Mapped[Optional[str]] = mapped_column(Text)

    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)

    payload: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, nullable=False, default=dict
    )

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    class Ingest:
        name = "wayfair_deductions"
        key_fields = ["remittance_number", "source_file", "source_row"]
        field_map = [
            FieldMap("remittance_number", "remittance_number"),
            FieldMap("remittance_date", "remittance_date"),
            FieldMap("deduction_invoice_number", "deduction_invoice_number"),
            FieldMap("deduction_date", "deduction_date"),
            FieldMap("deduction_amount", "deduction_amount"),
            FieldMap("item_sku", "item_sku"),
            FieldMap("credit_id", "credit_id"),
            FieldMap("memo", "memo"),
            FieldMap("reason", "reason"),
            FieldMap("description", "description"),
            FieldMap("source_file", "source_file"),
            FieldMap("source_row", "source_row"),
            FieldMap(".", "payload"),
        ]
        schema = WayfairDeductionSchema


# --- Target ------------------------------------------------------------------ #


class TargetPayoutSchema(_BasePayoutSchema):
    payout_id: str
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    payout_date: Optional[datetime] = None
    destination: Optional[str] = None
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None

    report_created_at: Optional[datetime] = None
    report_start_at: Optional[datetime] = None
    report_end_at: Optional[datetime] = None

    source_file: Optional[str] = None
    source_row: int

    @field_validator(
        "payout_id",
        "currency",
        "destination",
        "failure_code",
        "failure_message",
        "source_file",
        mode="before",
    )
    def _clean_text(cls, value: Any) -> Optional[str]:
        return _strip_text(value)

    @field_validator("amount", mode="before")
    def _clean_decimal(cls, value: Any) -> Optional[Decimal]:
        return _parse_decimal(value)

    @field_validator(
        "payout_date",
        "report_created_at",
        "report_start_at",
        "report_end_at",
        mode="before",
    )
    def _clean_datetime(cls, value: Any) -> Optional[datetime]:
        return _parse_datetime(value)

    @field_validator("source_row", mode="before")
    def _clean_int(cls, value: Any) -> Optional[int]:
        return _parse_int(value)


class TargetPayout(Base):
    __tablename__ = "target_payouts"
    __table_args__ = (UniqueConstraint("payout_id", name="ux_target_payout_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    payout_id: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    currency: Mapped[Optional[str]] = mapped_column(String(8))
    payout_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    destination: Mapped[Optional[str]] = mapped_column(String(128))
    failure_code: Mapped[Optional[str]] = mapped_column(String(128))
    failure_message: Mapped[Optional[str]] = mapped_column(Text)

    report_created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    report_start_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    report_end_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    source_file: Mapped[Optional[str]] = mapped_column(String(255))
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)

    payload: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, nullable=False, default=dict
    )

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    class Ingest:
        name = "target_payouts"
        key_fields = ["payout_id"]
        field_map = [
            FieldMap("payout_id", "payout_id"),
            FieldMap("amount", "amount"),
            FieldMap("currency", "currency"),
            FieldMap("payout_date", "payout_date"),
            FieldMap("destination", "destination"),
            FieldMap("failure_code", "failure_code"),
            FieldMap("failure_message", "failure_message"),
            FieldMap("report_created_at", "report_created_at"),
            FieldMap("report_start_at", "report_start_at"),
            FieldMap("report_end_at", "report_end_at"),
            FieldMap("source_file", "source_file"),
            FieldMap("source_row", "source_row"),
            FieldMap(".", "payload"),
        ]
        schema = TargetPayoutSchema


class TargetTransferSchema(_BasePayoutSchema):
    transfer_id: str
    transfer_type: Optional[str] = None
    payout_id: str
    payment_id: Optional[str] = None
    tcin: Optional[str] = None
    seller_sku: Optional[str] = None
    order_number: Optional[str] = None
    original_order_date: Optional[datetime] = None
    return_date: Optional[datetime] = None

    unit_price: Optional[Decimal] = None
    quantity: Optional[Decimal] = None
    line_total_less_discounts: Optional[Decimal] = None
    referral_fee: Optional[Decimal] = None
    shipping_and_services: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    referral_percent: Optional[Decimal] = None
    payment_amount: Optional[Decimal] = None

    order_id: Optional[str] = None
    tracking_number: Optional[str] = None
    notes: Optional[str] = None

    source_file: Optional[str] = None
    source_row: int

    @field_validator(
        "transfer_id",
        "transfer_type",
        "payout_id",
        "payment_id",
        "tcin",
        "seller_sku",
        "order_number",
        "order_id",
        "tracking_number",
        "notes",
        "source_file",
        mode="before",
    )
    def _clean_text(cls, value: Any) -> Optional[str]:
        return _strip_text(value)

    @field_validator("original_order_date", "return_date", mode="before")
    def _clean_datetime(cls, value: Any) -> Optional[datetime]:
        return _parse_datetime(value)

    @field_validator(
        "unit_price",
        "quantity",
        "line_total_less_discounts",
        "referral_fee",
        "shipping_and_services",
        "tax_amount",
        "referral_percent",
        "payment_amount",
        mode="before",
    )
    def _clean_decimal(cls, value: Any) -> Optional[Decimal]:
        return _parse_decimal(value)

    @field_validator("source_row", mode="before")
    def _clean_int(cls, value: Any) -> Optional[int]:
        return _parse_int(value)


class TargetTransfer(Base):
    __tablename__ = "target_transfers"
    __table_args__ = (UniqueConstraint("transfer_id", name="ux_target_transfer_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    transfer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    transfer_type: Mapped[Optional[str]] = mapped_column(String(32))
    payout_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("target_payouts.payout_id"),
        nullable=False,
    )
    payment_id: Mapped[Optional[str]] = mapped_column(String(64))
    tcin: Mapped[Optional[str]] = mapped_column(String(64))
    seller_sku: Mapped[Optional[str]] = mapped_column(String(128))
    order_number: Mapped[Optional[str]] = mapped_column(String(64))
    original_order_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    return_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    line_total_less_discounts: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    referral_fee: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    shipping_and_services: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    tax_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    referral_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    payment_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))

    order_id: Mapped[Optional[str]] = mapped_column(String(128))
    tracking_number: Mapped[Optional[str]] = mapped_column(String(128))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    source_file: Mapped[Optional[str]] = mapped_column(String(255))
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)

    payload: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, nullable=False, default=dict
    )

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    class Ingest:
        name = "target_transfers"
        key_fields = ["transfer_id"]
        field_map = [
            FieldMap("transfer_id", "transfer_id"),
            FieldMap("transfer_type", "transfer_type"),
            FieldMap("payout_id", "payout_id"),
            FieldMap("payment_id", "payment_id"),
            FieldMap("tcin", "tcin"),
            FieldMap("seller_sku", "seller_sku"),
            FieldMap("order_number", "order_number"),
            FieldMap("original_order_date", "original_order_date"),
            FieldMap("return_date", "return_date"),
            FieldMap("unit_price", "unit_price"),
            FieldMap("quantity", "quantity"),
            FieldMap("line_total_less_discounts", "line_total_less_discounts"),
            FieldMap("referral_fee", "referral_fee"),
            FieldMap("shipping_and_services", "shipping_and_services"),
            FieldMap("tax_amount", "tax_amount"),
            FieldMap("referral_percent", "referral_percent"),
            FieldMap("payment_amount", "payment_amount"),
            FieldMap("order_id", "order_id"),
            FieldMap("tracking_number", "tracking_number"),
            FieldMap("notes", "notes"),
            FieldMap("source_file", "source_file"),
            FieldMap("source_row", "source_row"),
            FieldMap(".", "payload"),
        ]
        schema = TargetTransferSchema


# --- Bed Bath & Beyond ------------------------------------------------------- #


class BbbPayoutSchema(_BasePayoutSchema):
    check_number: Optional[str] = None
    check_date: Optional[date] = None

    line_type: str
    invoice_date: Optional[date] = None
    os_sku: Optional[str] = None
    description: Optional[str] = None
    os_order_number: Optional[str] = None
    sofs_order_number: Optional[str] = None
    supplier_invoice_number: Optional[str] = None
    supplier_sku: Optional[str] = None
    order_date: Optional[date] = None
    quantity: Optional[int] = None
    unit_price: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None

    source_file: str
    source_row: int

    @field_validator(
        "check_number",
        "line_type",
        "os_sku",
        "description",
        "os_order_number",
        "sofs_order_number",
        "supplier_invoice_number",
        "supplier_sku",
        "source_file",
        mode="before",
    )
    def _clean_text(cls, value: Any) -> Optional[str]:
        return _strip_text(value)

    @field_validator("check_date", "invoice_date", "order_date", mode="before")
    def _clean_date(cls, value: Any) -> Optional[date]:
        return _parse_date(value)

    @field_validator("quantity", "source_row", mode="before")
    def _clean_int(cls, value: Any) -> Optional[int]:
        return _parse_int(value)

    @field_validator("unit_price", "total_amount", mode="before")
    def _clean_decimal(cls, value: Any) -> Optional[Decimal]:
        return _parse_decimal(value)


class BbbPayout(Base):
    __tablename__ = "bbb_payouts"
    __table_args__ = (
        UniqueConstraint(
            "source_file",
            "source_row",
            name="ux_bbb_payout_file_row",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    check_number: Mapped[Optional[str]] = mapped_column(String(64))
    check_date: Mapped[Optional[date]] = mapped_column(Date)

    line_type: Mapped[str] = mapped_column(String(32), nullable=False)
    invoice_date: Mapped[Optional[date]] = mapped_column(Date)
    os_sku: Mapped[Optional[str]] = mapped_column(String(64))
    description: Mapped[Optional[str]] = mapped_column(Text)
    os_order_number: Mapped[Optional[str]] = mapped_column(String(64))
    sofs_order_number: Mapped[Optional[str]] = mapped_column(String(64))
    supplier_invoice_number: Mapped[Optional[str]] = mapped_column(String(128))
    supplier_sku: Mapped[Optional[str]] = mapped_column(String(64))
    order_date: Mapped[Optional[date]] = mapped_column(Date)
    quantity: Mapped[Optional[int]] = mapped_column(Integer)
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))

    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)

    payload: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, nullable=False, default=dict
    )

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    class Ingest:
        name = "bbb_payouts"
        key_fields = ["source_file", "source_row"]
        field_map = [
            FieldMap("check_number", "check_number"),
            FieldMap("check_date", "check_date"),
            FieldMap("line_type", "line_type"),
            FieldMap("invoice_date", "invoice_date"),
            FieldMap("os_sku", "os_sku"),
            FieldMap("description", "description"),
            FieldMap("os_order_number", "os_order_number"),
            FieldMap("sofs_order_number", "sofs_order_number"),
            FieldMap("supplier_invoice_number", "supplier_invoice_number"),
            FieldMap("supplier_sku", "supplier_sku"),
            FieldMap("order_date", "order_date"),
            FieldMap("quantity", "quantity"),
            FieldMap("unit_price", "unit_price"),
            FieldMap("total_amount", "total_amount"),
            FieldMap("source_file", "source_file"),
            FieldMap("source_row", "source_row"),
            FieldMap(".", "payload"),
        ]
        schema = BbbPayoutSchema
