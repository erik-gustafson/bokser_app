"""
shared/models/sutton.py

Database models for Sutton Reports and Files
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
from sqlalchemy import (
    String,
    Date,
    Integer,
    Float,
    DateTime,
    Index,
    PrimaryKeyConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.database.database import Base

SUTTON_SCHEMA = "sutton"


class SuttonInventoryReport(Base):
    """
    Sutton Inventory Report data.
    Tracks inventory levels, costs, and product information.

    Column Mappings (Python attribute -> Database column):
    All database columns use lowercase snake_case for consistency.
    Data is received in UPPERCASE but stored in lowercase.
    """

    __tablename__ = "inv_report"

    # Primary Key
    style: Mapped[str] = mapped_column(String, primary_key=True)

    # Product Info
    mstyle: Mapped[str | None] = mapped_column(String)
    control: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String)
    unit_of_measure: Mapped[str | None] = mapped_column(String)
    season: Mapped[str | None] = mapped_column(String)

    # Pricing
    selling_price: Mapped[float | None] = mapped_column(Float)
    first_cost: Mapped[float | None] = mapped_column(Float)
    landed_cost: Mapped[float | None] = mapped_column(Float)

    # Packaging
    pack: Mapped[int | None] = mapped_column(Integer)
    carton_weight: Mapped[float | None] = mapped_column(Float)

    # Inventory Quantities
    backordered_qty: Mapped[int | None] = mapped_column(Integer)
    allocated_qty: Mapped[int | None] = mapped_column(Integer)
    balance_prepaid: Mapped[int | None] = mapped_column(Integer)
    on_hand_qty: Mapped[int | None] = mapped_column(Integer)
    available_to_sell: Mapped[int | None] = mapped_column(Integer)
    prepaid: Mapped[int | None] = mapped_column(Integer)
    received: Mapped[int | None] = mapped_column(Integer)
    on_water: Mapped[int | None] = mapped_column(Integer)

    # Dates
    last_received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_shipped_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    eta: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_sutton_inv_mstyle", "mstyle"),
        Index("idx_sutton_inv_control", "control"),
        Index("idx_sutton_inv_season", "season"),
        {"schema": SUTTON_SCHEMA},
    )

    def __repr__(self) -> str:
        return f"<SuttonInventoryReport(style={self.style}, description={self.description})>"

    def to_dict(self) -> dict[str, Any]:
        return {
            "style": self.style,
            "mstyle": self.mstyle,
            "control": self.control,
            "selling_price": self.selling_price,
            "pack": self.pack,
            "carton_weight": self.carton_weight,
            "description": self.description,
            "first_cost": self.first_cost,
            "landed_cost": self.landed_cost,
            "unit_of_measure": self.unit_of_measure,
            "season": self.season,
            "backordered_qty": self.backordered_qty,
            "allocated_qty": self.allocated_qty,
            "balance_prepaid": self.balance_prepaid,
            "on_hand_qty": self.on_hand_qty,
            "available_to_sell": self.available_to_sell,
            "prepaid": self.prepaid,
            "received": self.received,
            "on_water": self.on_water,
            "last_received_date": (
                self.last_received_date.isoformat() if self.last_received_date else None
            ),
            "last_shipped_date": (
                self.last_shipped_date.isoformat() if self.last_shipped_date else None
            ),
            "eta": self.eta.isoformat() if self.eta else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @staticmethod
    def map_uppercase_to_model(data: dict[str, Any]) -> dict[str, Any]:
        mapping = {
            "STYLE": "style",
            "MSTYLE": "mstyle",
            "CTRL": "control",
            "ETA": "eta",
            "SELLNGPRC": "selling_price",
            "PACK": "pack",
            "CARTON WEIGHT": "carton_weight",
            "DESC": "description",
            "FIRST_COST": "first_cost",
            "LAND_COST": "landed_cost",
            "UNIT OF MEASURE": "unit_of_measure",
            "SEASON": "season",
            "BKORD": "backordered_qty",
            "ALCTD": "allocated_qty",
            "BAL_PP": "balance_prepaid",
            "ON_HAND": "on_hand_qty",
            "AVL_2_SELL": "available_to_sell",
            "PP": "prepaid",
            "RCV": "received",
            "O_W": "on_water",
            "LAST RCV DATE": "last_received_date",
            "LAST SHP DATE": "last_shipped_date",
        }
        return {mapping.get(k, k.lower()): v for k, v in data.items() if k in mapping}

    @staticmethod
    def dataframe_drop_rename(df: pd.DataFrame) -> pd.DataFrame:
        df.rename(
            columns={
                "STYLE": "style",
                "MSTYLE": "mstyle",
                "CTRL": "control",
                "ETA": "eta",
                "SELLNGPRC": "selling_price",
                "PACK": "pack",
                "CARTON WEIGHT": "carton_weight",
                "DESC": "description",
                "FIRST_COST": "first_cost",
                "LAND_COST": "landed_cost",
                "UNIT OF MEASURE": "unit_of_measure",
                "SEASON": "season",
                "BKORD": "backordered_qty",
                "ALCTD": "allocated_qty",
                "BAL_PP": "balance_prepaid",
                "ON_HAND": "on_hand_qty",
                "AVL_2_SELL": "available_to_sell",
                "PP": "prepaid",
                "RCV": "received",
                "O_W": "on_water",
                "LAST RCV DATE": "last_received_date",
                "LAST SHP DATE": "last_shipped_date",
            },
            inplace=True,
        )

        # Normalize null-like text values
        df.replace(
            {
                "": None,
                "Null": None,
                "NULL": None,
                "null": None,
                "nan": None,
                "NaN": None,
                "00/00/00": None,
                "0000-00-00": None,
            },
            inplace=True,
        )

        # Date columns
        date_cols = ["eta", "last_received_date", "last_shipped_date"]
        for col in date_cols:
            if col in df.columns:
                # Parse dates
                parsed = pd.to_datetime(df[col], errors="coerce")
                df[col] = parsed
                df[col] = df[col].apply(lambda x: None if pd.isna(x) else x)
                df.replace({pd.NaT: None}, inplace=True)

        # Numeric columns
        int_cols = [
            "pack",
            "backordered_qty",
            "allocated_qty",
            "balance_prepaid",
            "on_hand_qty",
            "available_to_sell",
            "prepaid",
            "received",
            "on_water",
        ]
        float_cols = [
            "selling_price",
            "carton_weight",
            "first_cost",
            "landed_cost",
        ]

        for col in int_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        for col in float_cols:
            if col in df.columns:
                df[col] = (
                    pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)
                )

        df = df.where(df.notna(), None)
        return df


class SuttonOrderSubmission(Base):
    """
    Sutton Order Submission data.
    Tracks customer orders submitted to Sutton.

    Composite Primary Key: (customer, purchase_order, sku)
    """

    __tablename__ = "order_submission"

    # Composite Primary Key Components
    customer: Mapped[str] = mapped_column(String, nullable=False)
    purchase_order: Mapped[str] = mapped_column(String, nullable=False)
    sku: Mapped[str] = mapped_column(String, nullable=False)

    # Company & Location
    company: Mapped[str | None] = mapped_column(String)
    location: Mapped[str | None] = mapped_column(String)
    department: Mapped[str | None] = mapped_column(String)

    # Dates
    start_date: Mapped[date | None] = mapped_column(Date)
    cancel_date: Mapped[date | None] = mapped_column(Date)

    # Product Info
    customer_sku: Mapped[str | None] = mapped_column(String)

    # Order Details
    quantity: Mapped[int | None] = mapped_column(Integer)
    unit_price: Mapped[float | None] = mapped_column(Float)

    # Messages
    message_1: Mapped[str | None] = mapped_column(String)
    message_2: Mapped[str | None] = mapped_column(String)
    message_3: Mapped[str | None] = mapped_column(String)

    # Sales Info
    salesperson: Mapped[str | None] = mapped_column(String)
    smartsheet_row_id: Mapped[str | None] = mapped_column(String)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "customer", "purchase_order", "sku", name="pk_sutton_order_submission"
        ),
        Index("idx_sutton_order_customer", "customer"),
        Index("idx_sutton_order_po", "purchase_order"),
        Index("idx_sutton_order_sku", "sku"),
        Index("idx_sutton_order_start_date", "start_date"),
        Index("idx_sutton_order_salesperson", "salesperson"),
        {"schema": SUTTON_SCHEMA},
    )

    def __repr__(self) -> str:
        return (
            f"<SuttonOrderSubmission(customer={self.customer}, "
            f"po={self.purchase_order}, sku={self.sku})>"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "customer": self.customer,
            "location": self.location,
            "purchase_order": self.purchase_order,
            "department": self.department,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "cancel_date": self.cancel_date.isoformat() if self.cancel_date else None,
            "sku": self.sku,
            "customer_sku": self.customer_sku,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "message_1": self.message_1,
            "message_2": self.message_2,
            "message_3": self.message_3,
            "salesperson": self.salesperson,
            "smartsheet_row_id": self.smartsheet_row_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @staticmethod
    def dataframe_drop_rename(df: pd.DataFrame) -> pd.DataFrame:
        df = df.astype(object).where(df.notna(), None)
        df.replace({"": None, "00/00/00": None, "0000-00-00": None}, inplace=True)
        return df


class SuttonEDILoad(Base):
    """
    EDI Load data.
    Tracks EDI order information from customers.

    Composite Primary Key: (cust_acct, cust_order, style, order_num)
    """

    __tablename__ = "edi_load"

    # Composite Primary Key Components
    cust_acct: Mapped[str] = mapped_column(String, nullable=False)
    cust_order: Mapped[str] = mapped_column(String, nullable=False)
    style: Mapped[str] = mapped_column(String, nullable=False)
    order_num: Mapped[str] = mapped_column(String, nullable=False)

    # Company & Customer Info
    company: Mapped[str | None] = mapped_column(String)
    customer: Mapped[str | None] = mapped_column(String)

    # Location Info
    store_dc: Mapped[str | None] = mapped_column(String, nullable=True)
    dc: Mapped[str | None] = mapped_column(String, nullable=True)
    dept: Mapped[str | None] = mapped_column(String, nullable=True)

    # Dates
    date_edi: Mapped[date | None] = mapped_column(Date, nullable=True)
    ship_date: Mapped[date | None] = mapped_column(Date)
    cxl_date: Mapped[date | None] = mapped_column(Date)

    # Order Details
    qty_ord: Mapped[int | None] = mapped_column(Integer)
    uom: Mapped[str | None] = mapped_column(String)
    ctns: Mapped[int | None] = mapped_column(Integer)

    # Product Info
    cust_item: Mapped[str | None] = mapped_column(String)
    item_desc: Mapped[str | None] = mapped_column(String)

    # Pricing
    price: Mapped[float | None] = mapped_column(Float)
    ext_price: Mapped[float | None] = mapped_column(Float)

    # Order Line Info
    ord_line: Mapped[int | None] = mapped_column(Integer)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "cust_acct",
            "cust_order",
            "style",
            "order_num",
            name="pk_edi_load",
        ),
        Index("idx_edi_cust_acct", "cust_acct"),
        Index("idx_edi_cust_order", "cust_order"),
        Index("idx_edi_style", "style"),
        Index("idx_edi_order_num", "order_num"),
        Index("idx_edi_ship_date", "ship_date"),
        Index("idx_edi_customer", "customer"),
        {"schema": SUTTON_SCHEMA},
    )

    def __repr__(self) -> str:
        return (
            f"<EDILoad(cust_acct={self.cust_acct}, "
            f"order={self.cust_order}, style={self.style})>"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "cust_acct": self.cust_acct,
            "customer": self.customer,
            "store_dc": self.store_dc,
            "dc": self.dc,
            "dept": self.dept,
            "cust_order": self.cust_order,
            "date_edi": self.date_edi.isoformat() if self.date_edi else None,
            "ship_date": self.ship_date.isoformat() if self.ship_date else None,
            "cxl_date": self.cxl_date.isoformat() if self.cxl_date else None,
            "qty_ord": self.qty_ord,
            "uom": self.uom,
            "ctns": self.ctns,
            "style": self.style,
            "cust_item": self.cust_item,
            "item_desc": self.item_desc,
            "price": self.price,
            "ext_price": self.ext_price,
            "order_num": self.order_num,
            "ord_line": self.ord_line,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @staticmethod
    def map_uppercase_to_model(data: dict[str, Any]) -> dict[str, Any]:
        mapping = {
            "COMPANY": "company",
            "CUST_ACCT#": "cust_acct",
            "CUSTOMER": "customer",
            "STORE_DC": "store_dc",
            "DC": "dc",
            "DEPT": "dept",
            "CUST_ORDER#": "cust_order",
            "DATE_EDI": "date_edi",
            "SHIP_DATE": "ship_date",
            "CXL_DATE": "cxl_date",
            "QTY_ORD": "qty_ord",
            "UOM": "uom",
            "CTNS": "ctns",
            "STYLE": "style",
            "CUST_ITEM#": "cust_item",
            "ITEM_DESC": "item_desc",
            "PRICE": "price",
            "EXT_PRICE": "ext_price",
            "ORDER#": "order_num",
            "ORD_LINE#": "ord_line",
        }
        return {mapping.get(k, k.lower()): v for k, v in data.items() if k in mapping}

    @staticmethod
    def dataframe_drop_rename(df: pd.DataFrame) -> pd.DataFrame:
        # 1) Rename to model field names
        df.rename(
            columns={
                "COMPANY": "company",
                "CUST_ACCT#": "cust_acct",
                "CUSTOMER": "customer",
                "STORE_DC": "store_dc",
                "DC": "dc",
                "DEPT": "dept",
                "CUST_ORDER#": "cust_order",
                "DATE_EDI": "date_edi",
                "SHIP_DATE": "ship_date",
                "CXL_DATE": "cxl_date",
                "QTY_ORD": "qty_ord",
                "UOM": "uom",
                "CTNS": "ctns",
                "STYLE": "style",
                "CUST_ITEM#": "cust_item",
                "ITEM_DESC": "item_desc",
                "PRICE": "price",
                "EXT_PRICE": "ext_price",
                "ORDER#": "order_num",
                "ORD_LINE#": "ord_line",
            },
            inplace=True,
        )

        # 2) Normalize obvious null-like text values *before* type coercion
        df.replace(
            {
                "": None,
                "Null": None,
                "NULL": None,
                "null": None,
                "nan": None,
                "NaN": None,
                "00/00/00": None,
                "0000-00-00": None,
            },
            inplace=True,
        )

        # 3) Date columns: parse + normalize
        date_cols = ["date_edi", "ship_date", "cxl_date"]

        for col in date_cols:
            if col in df.columns:
                # Parse dates
                parsed = pd.to_datetime(df[col], errors="coerce")
                df[col] = parsed

                # Force NaT -> None (reliable for SQLAlchemy)
                df[col] = df[col].apply(lambda x: None if pd.isna(x) else x)
                df.replace({pd.NaT: None}, inplace=True)

        # 4) Numeric columns
        int_cols = ["qty_ord", "ctns", "ord_line"]
        float_cols = ["price", "ext_price"]

        for col in int_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        for col in float_cols:
            if col in df.columns:
                df[col] = (
                    pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)
                )

        # 5) Final pass: any remaining NaN → None for non-numeric cells
        df = df.where(df.notna(), None)

        return df


class SuttonOpenOrderReport(Base):
    """
    Sutton Open Order Report data.
    Tracks currently open orders in the Sutton system.

    Composite Primary Key: (company, customer_acct, purchase_order, warehouse_batch, sku)
    """

    __tablename__ = "open_order_report"

    # Composite Primary Key Components
    company: Mapped[str] = mapped_column(String, nullable=False)
    customer_acct: Mapped[str] = mapped_column(String, nullable=False)
    purchase_order: Mapped[str] = mapped_column(String, nullable=False)
    warehouse_batch: Mapped[str] = mapped_column(String, nullable=False)
    sku: Mapped[str] = mapped_column(String, nullable=False)

    # Customer Info
    location: Mapped[str | None] = mapped_column(String)
    customer_name: Mapped[str | None] = mapped_column(String)

    # Order Status
    status: Mapped[str | None] = mapped_column(String)
    warehouse_order_number: Mapped[str | None] = mapped_column(String)
    warehouse_order_line: Mapped[str | None] = mapped_column(String)

    # Product Info
    original_style: Mapped[str | None] = mapped_column(String)
    customer_sku: Mapped[str | None] = mapped_column(String)

    # Order Details
    quantity: Mapped[int | None] = mapped_column(Integer)
    unit_of_measure: Mapped[str | None] = mapped_column(String)
    unit_cost: Mapped[float | None] = mapped_column(Float)
    extended_cost: Mapped[float | None] = mapped_column(Float)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "company",
            "customer_acct",
            "purchase_order",
            "warehouse_batch",
            "sku",
            name="pk_sutton_open_order",
        ),
        Index("idx_sutton_oo_customer", "customer_acct"),
        Index("idx_sutton_oo_po", "purchase_order"),
        Index("idx_sutton_oo_sku", "sku"),
        Index("idx_sutton_oo_status", "status"),
        Index("idx_sutton_oo_warehouse_batch", "warehouse_batch"),
        {"schema": SUTTON_SCHEMA},
    )

    def __repr__(self) -> str:
        return (
            f"<SuttonOpenOrderReport(company={self.company}, "
            f"customer={self.customer_acct}, po={self.purchase_order})>"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "customer_acct": self.customer_acct,
            "location": self.location,
            "customer_name": self.customer_name,
            "purchase_order": self.purchase_order,
            "warehouse_batch": self.warehouse_batch,
            "status": self.status,
            "warehouse_order_number": self.warehouse_order_number,
            "warehouse_order_line": self.warehouse_order_line,
            "sku": self.sku,
            "original_style": self.original_style,
            "customer_sku": self.customer_sku,
            "quantity": self.quantity,
            "unit_of_measure": self.unit_of_measure,
            "unit_cost": self.unit_cost,
            "extended_cost": self.extended_cost,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @staticmethod
    def map_uppercase_to_model(data: dict[str, Any]) -> dict[str, Any]:
        mapping = {
            "Co": "company",
            "Acct": "customer_acct",
            "Store": "location",
            "Customer Name": "customer_name",
            "Cust_Ord": "purchase_order",
            "Batch": "warehouse_batch",
            "Status": "status",
            "Order #": "warehouse_order_number",
            "Line #": "warehouse_order_line",
            "Style to Ship": "sku",
            "Orig Style": "original_style",
            "CSTSKU": "customer_sku",
            "QTY": "quantity",
            "UOM": "unit_of_measure",
            "Unit cost": "unit_cost",
            "Extended": "extended_cost",
        }
        return {mapping.get(k, k.lower()): v for k, v in data.items() if k in mapping}

    @staticmethod
    def dataframe_drop_rename(df: pd.DataFrame) -> pd.DataFrame:
        # Drop unused columns
        df.drop(
            [
                "CD",
                "Salesman",
                "Line",
                "Dept",
                "Pick Date",
                "Start Date",
                "Cancel Date",
                "Call-In Date",
                "Ship-on Date",
                "Load/ARN",
                "PO_TYPE",
                "Allocator",
                "Showroom_Contact",
            ],
            axis=1,
            inplace=True,
            errors="ignore",
        )

        # Rename to model-friendly names
        df.rename(
            columns={
                "Co": "company",
                "Acct": "customer_acct",
                "Store": "location",
                "Customer Name": "customer_name",
                "Cust_Ord": "purchase_order",
                "Batch": "warehouse_batch",
                "Status": "status",
                "Order #": "warehouse_order_number",
                "Line #": "warehouse_order_line",
                "Style to Ship": "sku",
                "Orig Style": "original_style",
                "CSTSKU": "customer_sku",
                "QTY": "quantity",
                "UOM": "unit_of_measure",
                "Unit cost": "unit_cost",
                "Extended": "extended_cost",
            },
            inplace=True,
        )

        # Normalize null-like text values
        df.replace(
            {
                "": None,
                "Null": None,
                "NULL": None,
                "null": None,
                "nan": None,
                "NaN": None,
                "00/00/00": None,
                "0000-00-00": None,
            },
            inplace=True,
        )

        # Numeric columns
        int_cols = ["quantity"]
        float_cols = ["unit_cost", "extended_cost"]

        for col in int_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        for col in float_cols:
            if col in df.columns:
                df[col] = (
                    pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)
                )

        # Final pass: any remaining NaN → None
        df = df.where(df.notna(), None)

        return df


class SuttonSalesReport(Base):
    """
    Sutton Sales Report data.
    Tracks completed sales and shipments.

    Composite Primary Key: (invoice, purchase_order, style, warehouse_batch_number)
    """

    __tablename__ = "sales_report"

    # Composite Primary Key Components
    invoice: Mapped[int] = mapped_column(Integer, nullable=False)
    purchase_order: Mapped[str] = mapped_column(String, nullable=False)
    style: Mapped[str] = mapped_column(String, nullable=False)
    warehouse_batch_number: Mapped[str] = mapped_column(String, nullable=False)

    # Customer Info
    customer_number: Mapped[str | None] = mapped_column(String)
    customer_name: Mapped[str | None] = mapped_column(String)

    # Sales Rep Info
    salesman: Mapped[str | None] = mapped_column(String)
    salesman_code: Mapped[str | None] = mapped_column(String)

    # Date
    date: Mapped[date | None] = mapped_column(Date)

    # Product Info
    item_description: Mapped[str | None] = mapped_column(String)
    customer_sku: Mapped[str | None] = mapped_column(String)

    # Pricing
    selling_price: Mapped[float | None] = mapped_column(Float)
    sales_total: Mapped[float | None] = mapped_column(Float)

    # Quantities
    qty_shipped: Mapped[int | None] = mapped_column(Integer)
    cartons_shipped: Mapped[int | None] = mapped_column(Integer)

    # Shipping Info
    warehouse: Mapped[str | None] = mapped_column(String)
    carrier: Mapped[str | None] = mapped_column(String)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "invoice",
            "purchase_order",
            "style",
            "warehouse_batch_number",
            name="pk_sutton_sales",
        ),
        Index("idx_sutton_sales_customer", "customer_number"),
        Index("idx_sutton_sales_date", "date"),
        Index("idx_sutton_sales_invoice", "invoice"),
        Index("idx_sutton_sales_po", "purchase_order"),
        Index("idx_sutton_sales_style", "style"),
        Index("idx_sutton_sales_salesman", "salesman_code"),
        Index("idx_sutton_sales_warehouse", "warehouse"),
        {"schema": SUTTON_SCHEMA},
    )

    def __repr__(self) -> str:
        return (
            f"<SuttonSalesReport(invoice={self.invoice}, "
            f"po={self.purchase_order}, style={self.style})>"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_number": self.customer_number,
            "customer_name": self.customer_name,
            "salesman": self.salesman,
            "salesman_code": self.salesman_code,
            "date": self.date.isoformat() if self.date else None,
            "invoice": self.invoice,
            "purchase_order": self.purchase_order,
            "style": self.style,
            "item_description": self.item_description,
            "customer_sku": self.customer_sku,
            "selling_price": self.selling_price,
            "qty_shipped": self.qty_shipped,
            "sales_total": self.sales_total,
            "cartons_shipped": self.cartons_shipped,
            "warehouse_batch_number": self.warehouse_batch_number,
            "warehouse": self.warehouse,
            "carrier": self.carrier,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @staticmethod
    def map_uppercase_to_model(data: dict[str, Any]) -> dict[str, Any]:
        mapping = {
            "CUST#": "customer_number",
            "CUSTOMER": "customer_name",
            "SALESMAN": "salesman",
            "SALSMAN_CODE": "salesman_code",
            "DATE": "date",
            "INV": "invoice",
            "PO#": "purchase_order",
            "STYLE": "style",
            "ITEM_DESCRIP": "item_description",
            "CUST_SKU": "customer_sku",
            "SELLING_PRICE": "selling_price",
            "SHIPPED": "qty_shipped",
            "SALES": "sales_total",
            "CTNS": "cartons_shipped",
            "WHSBATCH#": "warehouse_batch_number",
            "WHSE": "warehouse",
            "CARRIER": "carrier",
        }
        return {mapping.get(k, k.lower()): v for k, v in data.items() if k in mapping}

    @staticmethod
    def dataframe_drop_rename(df: pd.DataFrame) -> pd.DataFrame:
        df.rename(
            columns={
                "CUST#": "customer_number",
                "CUSTOMER": "customer_name",
                "SALESMAN": "salesman",
                "SALSMAN_CODE": "salesman_code",
                "DATE": "date",
                "INV": "invoice",
                "PO#": "purchase_order",
                "STYLE": "style",
                "ITEM_DESCRIP": "item_description",
                "CUST_SKU": "customer_sku",
                "SELLING_PRICE": "selling_price",
                "SHIPPED": "qty_shipped",
                "SALES": "sales_total",
                "CTNS": "cartons_shipped",
                "WHSBATCH#": "warehouse_batch_number",
                "WHSE": "warehouse",
                "CARRIER": "carrier",
            },
            inplace=True,
        )

        # Normalize null-like text values
        df.replace(
            {
                "": None,
                "Null": None,
                "NULL": None,
                "null": None,
                "nan": None,
                "NaN": None,
                "00/00/00": None,
                "0000-00-00": None,
            },
            inplace=True,
        )

        # Date column
        # 3) Date columns: parse + normalize
        date_cols = ["date"]

        for col in date_cols:
            if col in df.columns:
                # Parse dates
                parsed = pd.to_datetime(df[col], errors="coerce")
                df[col] = parsed

                # Force NaT -> None (reliable for SQLAlchemy)
                df[col] = df[col].apply(lambda x: None if pd.isna(x) else x)
                df.replace({pd.NaT: None}, inplace=True)

        # Numeric columns
        int_cols = ["qty_shipped", "cartons_shipped"]
        float_cols = ["selling_price", "sales_total"]

        for col in int_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        for col in float_cols:
            if col in df.columns:
                df[col] = (
                    pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)
                )

        df = df.where(df.notna(), None)
        return df
