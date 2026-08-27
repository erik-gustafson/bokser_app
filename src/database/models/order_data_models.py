from datetime import date, datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel
from sqlalchemy import (
    BigInteger,
    String,
    Integer,
    Float,
    Date,
    DateTime,
    Text,
    Index,
    PrimaryKeyConstraint,
    ForeignKey,
    cast,
    literal,
)

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, ColumnElement
from sqlalchemy.sql.elements import SQLColumnExpression

from src.database.database import Base, FieldMap

ORDER_DATA_SCHEMA = "order_data"


class GuestSupplyPOHeader(Base):
    """
    Guest Supply Purchase Order header from PDFs.
    One row per PO.
    """

    __tablename__ = "guest_supply_po_headers"
    __table_args__ = {"schema": ORDER_DATA_SCHEMA}

    po_number: Mapped[str] = mapped_column(String(50), primary_key=True)
    source_file: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    po_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    buyer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    tax_exempt_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    supplier_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    supplier_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    supplier_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    ship_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ship_address_1: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ship_address_2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ship_city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ship_state: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    ship_zip: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    ship_country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ship_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    bill_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    bill_address_1: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    bill_address_2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    bill_city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bill_state: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    bill_zip: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    bill_country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    bill_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    terms_payment: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    terms_freight: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    terms_carrier: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )

    class Ingest:
        name = "guest_supply_po_headers"
        key_fields = ["po_number"]
        field_map = [
            FieldMap("po_number", "po_number"),
            FieldMap("source_file", "source_file"),
            FieldMap("po_date", "po_date"),
            FieldMap("buyer", "buyer"),
            FieldMap("currency", "currency"),
            FieldMap("tax_exempt_id", "tax_exempt_id"),
            FieldMap("supplier_id", "supplier_id"),
            FieldMap("supplier_name", "supplier_name"),
            FieldMap("supplier_address", "supplier_address"),
            FieldMap("ship_name", "ship_name"),
            FieldMap("ship_address_1", "ship_address_1"),
            FieldMap("ship_address_2", "ship_address_2"),
            FieldMap("ship_city", "ship_city"),
            FieldMap("ship_state", "ship_state"),
            FieldMap("ship_zip", "ship_zip"),
            FieldMap("ship_country", "ship_country"),
            FieldMap("ship_phone", "ship_phone"),
            FieldMap("bill_name", "bill_name"),
            FieldMap("bill_address_1", "bill_address_1"),
            FieldMap("bill_address_2", "bill_address_2"),
            FieldMap("bill_city", "bill_city"),
            FieldMap("bill_state", "bill_state"),
            FieldMap("bill_zip", "bill_zip"),
            FieldMap("bill_country", "bill_country"),
            FieldMap("bill_phone", "bill_phone"),
            FieldMap("contact_name", "contact_name"),
            FieldMap("contact_phone", "contact_phone"),
            FieldMap("contact_email", "contact_email"),
            FieldMap("terms_payment", "terms_payment"),
            FieldMap("terms_freight", "terms_freight"),
            FieldMap("terms_carrier", "terms_carrier"),
        ]

    def sos_customer_name(self) -> str:
        return "Guest Supply"

    def sos_customer_po(self) -> str:
        return self.po_number

    def sos_order_date(self) -> date:
        return self.po_date

    def sos_billing(self) -> Dict[str, Any]:
        return {
            "company": "AP@guestsupply.com",
            "contact": None,
            "phone": None,
            "email": "AP@guestsupply.com",
            "address": {
                "line1": "300 DAVIDSON AVE",
                "line2": "PO BOX 6782",
                "line3": None,
                "line4": None,
                "city": "SOMERSET",
                "stateProvince": "NJ",
                "postalCode": "08875",
                "country": "USA",
            },
        }

    def sos_shipping(self) -> Dict[str, Any]:
        return {
            "company": self.ship_name,
            "contact": self.contact_name,
            "phone": self.ship_phone,
            "email": self.contact_email,
            "address": {
                "line1": self.ship_address_1,
                "line2": self.ship_address_2,
                "line3": None,
                "line4": None,
                "city": self.ship_city,
                "stateProvince": self.ship_state,
                "postalCode": self.ship_zip,
                "country": self.ship_country or "USA",
            },
        }


class GuestSupplyPODetail(Base):
    """
    Guest Supply Purchase Order line items from PDFs.
    One row per line item.
    """

    __tablename__ = "guest_supply_po_details"

    po_number: Mapped[str] = mapped_column(
        String(50),
        ForeignKey(
            f"{ORDER_DATA_SCHEMA}.guest_supply_po_headers.po_number",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    line_num: Mapped[int] = mapped_column(Integer, nullable=False)
    sku: Mapped[str] = mapped_column(String(50), nullable=False)

    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    uom: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False)
    line_total: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "po_number",
            "line_num",
            "sku",
            name="pk_guest_supply_po_detail",
        ),
        Index("idx_guest_supply_po_detail_po_number", "po_number"),
        Index("idx_guest_supply_po_detail_sku", "sku"),
        {"schema": ORDER_DATA_SCHEMA},
    )

    class Ingest:
        name = "guest_supply_po_details"
        key_fields = ["po_number", "line_num", "sku"]
        field_map = [
            FieldMap("po_number", "po_number"),
            FieldMap("line_num", "line_num"),
            FieldMap("sku", "sku"),
            FieldMap("quantity", "quantity"),
            FieldMap("uom", "uom"),
            FieldMap("unit_cost", "unit_cost"),
            FieldMap("line_total", "line_total"),
        ]

    @classmethod
    def source_line_key_expr(cls) -> ColumnElement[str]:
        return (
            cast(cls.po_number, String)
            + literal("|")
            + cast(cls.line_num, String)
            + literal("|")
            + cast(cls.sku, String)
        )

    def detail_line_key(self) -> str:
        return f"{self.po_number}|{self.line_num}|{self.sku}"

    def sos_line_fields(self) -> Dict[str, Any]:
        return {
            "lineNumber": self.line_num,
            "sku": self.sku,
            "quantity": self.quantity,
            "unitprice": self.unit_cost,
            "amount": self.line_total,
            "uom": self.uom,
        }


class RithumPOHeader(Base):
    __tablename__ = "rithum_po_headers"
    __table_args__ = {"schema": ORDER_DATA_SCHEMA}

    hub_order_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    file_type: Mapped[Optional[str]] = mapped_column(String)
    record_type: Mapped[Optional[str]] = mapped_column(String)
    merchant_order_id: Mapped[Optional[str]] = mapped_column(String)
    po_type_code: Mapped[Optional[str]] = mapped_column(String)
    merchant_id: Mapped[Optional[str]] = mapped_column(String)
    merchant_vendor_id: Mapped[Optional[str]] = mapped_column(String)
    order_date: Mapped[Optional[date]] = mapped_column(Date)
    order_item_count: Mapped[Optional[int]] = mapped_column(BigInteger)
    packing_slip_message: Mapped[Optional[str]] = mapped_column(String)
    vendor_notes: Mapped[Optional[str]] = mapped_column(String)
    customer_order_id: Mapped[Optional[str]] = mapped_column(String)
    customer_order_date: Mapped[Optional[date]] = mapped_column(Date)
    shipping_method: Mapped[Optional[str]] = mapped_column(String)
    ship_to_company_name: Mapped[Optional[str]] = mapped_column(String)
    ship_to_name: Mapped[Optional[str]] = mapped_column(String)
    ship_to_address_1: Mapped[Optional[str]] = mapped_column(String)
    ship_to_address_2: Mapped[Optional[str]] = mapped_column(String)
    ship_to_city: Mapped[Optional[str]] = mapped_column(String)
    ship_to_state: Mapped[Optional[str]] = mapped_column(String)
    ship_to_postal_code: Mapped[Optional[str]] = mapped_column(String)
    ship_to_country: Mapped[Optional[str]] = mapped_column(String)
    ship_to_day_phone: Mapped[Optional[str]] = mapped_column(String)
    ship_to_email: Mapped[Optional[str]] = mapped_column(String)
    bill_to_company_name: Mapped[Optional[str]] = mapped_column(String)
    bill_to_name: Mapped[Optional[str]] = mapped_column(String)
    bill_to_address_1: Mapped[Optional[str]] = mapped_column(String)
    bill_to_city: Mapped[Optional[str]] = mapped_column(String)
    bill_to_state: Mapped[Optional[str]] = mapped_column(String)
    bill_to_postal_code: Mapped[Optional[str]] = mapped_column(String)
    bill_to_country: Mapped[Optional[str]] = mapped_column(String)
    buying_contract: Mapped[Optional[str]] = mapped_column(String)
    buyer_name: Mapped[Optional[str]] = mapped_column(String)
    order_currency: Mapped[Optional[str]] = mapped_column(String)
    freight_payment_terms: Mapped[Optional[str]] = mapped_column(String)
    erp_customer_order_number: Mapped[Optional[str]] = mapped_column(String)

    class RithumPOHeaderSchema(BaseModel):
        file_type: Optional[str] = None
        record_type: Optional[str] = None
        hub_order_id: int
        merchant_order_id: Optional[str] = None
        po_type_code: Optional[str] = None
        merchant_id: Optional[str] = None
        merchant_vendor_id: Optional[str] = None
        order_date: Optional[date] = None
        order_item_count: Optional[int] = None
        packing_slip_message: Optional[str] = None
        vendor_notes: Optional[str] = None
        customer_order_id: Optional[str] = None
        customer_order_date: Optional[date] = None
        shipping_method: Optional[str] = None
        ship_to_company_name: Optional[str] = None
        ship_to_name: Optional[str] = None
        ship_to_address_1: Optional[str] = None
        ship_to_address_2: Optional[str] = None
        ship_to_city: Optional[str] = None
        ship_to_state: Optional[str] = None
        ship_to_postal_code: Optional[str] = None
        ship_to_country: Optional[str] = None
        ship_to_day_phone: Optional[str] = None
        ship_to_email: Optional[str] = None
        bill_to_company_name: Optional[str] = None
        bill_to_name: Optional[str] = None
        bill_to_address_1: Optional[str] = None
        bill_to_city: Optional[str] = None
        bill_to_state: Optional[str] = None
        bill_to_postal_code: Optional[str] = None
        bill_to_country: Optional[str] = None
        buying_contract: Optional[str] = None
        buyer_name: Optional[str] = None
        order_currency: Optional[str] = None
        freight_payment_terms: Optional[str] = None
        erp_customer_order_number: Optional[str] = None

    class Ingest:
        name = "rithum_po_headers"
        key_fields = ["hub_order_id"]
        field_map = [
            FieldMap("file_type", "file_type"),
            FieldMap("record_type", "record_type"),
            FieldMap("hub_order_id", "hub_order_id"),
            FieldMap("merchant_order_id", "merchant_order_id"),
            FieldMap("po_type_code", "po_type_code"),
            FieldMap("merchant_id", "merchant_id"),
            FieldMap("merchant_vendor_id", "merchant_vendor_id"),
            FieldMap("order_date", "order_date"),
            FieldMap("order_item_count", "order_item_count"),
            FieldMap("packing_slip_message", "packing_slip_message"),
            FieldMap("vendor_notes", "vendor_notes"),
            FieldMap("customer_order_id", "customer_order_id"),
            FieldMap("customer_order_date", "customer_order_date"),
            FieldMap("shipping_method", "shipping_method"),
            FieldMap("ship_to_company_name", "ship_to_company_name"),
            FieldMap("ship_to_name", "ship_to_name"),
            FieldMap("ship_to_address_1", "ship_to_address_1"),
            FieldMap("ship_to_address_2", "ship_to_address_2"),
            FieldMap("ship_to_city", "ship_to_city"),
            FieldMap("ship_to_state", "ship_to_state"),
            FieldMap("ship_to_postal_code", "ship_to_postal_code"),
            FieldMap("ship_to_country", "ship_to_country"),
            FieldMap("ship_to_day_phone", "ship_to_day_phone"),
            FieldMap("ship_to_email", "ship_to_email"),
            FieldMap("bill_to_company_name", "bill_to_company_name"),
            FieldMap("bill_to_name", "bill_to_name"),
            FieldMap("bill_to_address_1", "bill_to_address_1"),
            FieldMap("bill_to_city", "bill_to_city"),
            FieldMap("bill_to_state", "bill_to_state"),
            FieldMap("bill_to_postal_code", "bill_to_postal_code"),
            FieldMap("bill_to_country", "bill_to_country"),
            FieldMap("buying_contract", "buying_contract"),
            FieldMap("buyer_name", "buyer_name"),
            FieldMap("order_currency", "order_currency"),
            FieldMap("freight_payment_terms", "freight_payment_terms"),
            FieldMap("erp_customer_order_number", "erp_customer_order_number"),
        ]

    def sos_customer_name(self) -> str:
        return "HD Supply - Rithum"

    def sos_customer_po(self) -> str:
        return self.merchant_order_id or str(self.hub_order_id)

    def sos_order_date(self) -> date:
        return self.order_date or date.today()

    def sos_billing(self) -> Dict[str, Any]:
        return {
            "company": self.bill_to_company_name,
            "contact": self.bill_to_name,
            "phone": None,  # you don't appear to have billing phone fields
            "email": None,
            "address": {
                "line1": self.bill_to_address_1,
                "line2": None,  # you don't have bill_to_address_2
                "line3": None,
                "line4": None,
                "city": self.bill_to_city,
                "stateProvince": self.bill_to_state,
                "postalCode": self.bill_to_postal_code,
                "country": self.bill_to_country or "USA",
            },
        }

    def sos_shipping(self) -> Dict[str, Any]:
        return {
            "company": self.ship_to_company_name,
            "contact": self.ship_to_name,
            "phone": self.ship_to_day_phone,
            "email": self.ship_to_email,
            "address": {
                "line1": self.ship_to_address_1,
                "line2": self.ship_to_address_2,
                "line3": None,
                "line4": None,
                "city": self.ship_to_city,
                "stateProvince": self.ship_to_state,
                "postalCode": self.ship_to_postal_code,
                "country": self.ship_to_country or "USA",
            },
        }


class RithumPODetail(Base):
    __tablename__ = "rithum_po_details"
    __table_args__ = {"schema": ORDER_DATA_SCHEMA}

    hub_line_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    file_type: Mapped[Optional[str]] = mapped_column(String)
    record_type: Mapped[Optional[str]] = mapped_column(String)
    hub_order_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    merchant_order_id: Mapped[Optional[str]] = mapped_column(String)
    order_line_item_number: Mapped[Optional[int]] = mapped_column(BigInteger)
    merchant_line_item_number: Mapped[Optional[int]] = mapped_column(BigInteger)
    merchant_sku: Mapped[Optional[str]] = mapped_column(String)
    vendor_sku: Mapped[Optional[str]] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(String)
    quantity: Mapped[Optional[int]] = mapped_column(BigInteger)
    unit_of_measure: Mapped[Optional[str]] = mapped_column(String)
    unit_cost: Mapped[Optional[float]] = mapped_column(Float)
    packing_slip_line_message: Mapped[Optional[str]] = mapped_column(String)
    vendor_line_note: Mapped[Optional[str]] = mapped_column(String)
    personalization_data: Mapped[Optional[str]] = mapped_column(String)
    required_delivery_date: Mapped[Optional[date]] = mapped_column(Date)

    class RithumPODetailSchema(BaseModel):
        file_type: Optional[str] = None
        record_type: Optional[str] = None
        hub_order_id: Optional[int] = None
        merchant_order_id: Optional[str] = None
        order_line_item_number: Optional[int] = None
        merchant_line_item_number: Optional[int] = None
        hub_line_id: int
        merchant_sku: Optional[str] = None
        vendor_sku: Optional[str] = None
        description: Optional[str] = None
        quantity: Optional[int] = None
        unit_of_measure: Optional[str] = None
        unit_cost: Optional[float] = None
        packing_slip_line_message: Optional[str] = None
        vendor_line_note: Optional[str] = None
        personalization_data: Optional[str] = None
        required_delivery_date: Optional[date] = None

    class Ingest:
        name = "rithum_po_details"
        key_fields = ["hub_line_id"]
        field_map = [
            FieldMap("file_type", "file_type"),
            FieldMap("record_type", "record_type"),
            FieldMap("hub_order_id", "hub_order_id"),
            FieldMap("merchant_order_id", "merchant_order_id"),
            FieldMap("order_line_item_number", "order_line_item_number"),
            FieldMap("merchant_line_item_number", "merchant_line_item_number"),
            FieldMap("hub_line_id", "hub_line_id"),
            FieldMap("merchant_sku", "merchant_sku"),
            FieldMap("vendor_sku", "vendor_sku"),
            FieldMap("description", "description"),
            FieldMap("quantity", "quantity"),
            FieldMap("unit_of_measure", "unit_of_measure"),
            FieldMap("unit_cost", "unit_cost"),
            FieldMap("packing_slip_line_message", "packing_slip_line_message"),
            FieldMap("vendor_line_note", "vendor_line_note"),
            FieldMap("personalization_data", "personalization_data"),
            FieldMap("required_delivery_date", "required_delivery_date"),
        ]

    @classmethod
    def source_line_key_expr(cls) -> SQLColumnExpression[str]:
        return cast(cls.hub_line_id, String)

    def detail_line_key(self) -> str:
        return str(self.hub_line_id)

    def sos_line_fields(self) -> Dict[str, Any]:
        qty = float(self.quantity or 0)
        unit = float(self.unit_cost or 0)
        return {
            "lineNumber": int(
                self.order_line_item_number
                or self.merchant_line_item_number
                or self.hub_line_id
            ),
            "sku": (self.vendor_sku or self.merchant_sku or "").strip(),
            "quantity": qty,
            "unitprice": unit,
            "amount": qty * unit,
            "uom": self.unit_of_measure,
            "description": self.description,
        }
