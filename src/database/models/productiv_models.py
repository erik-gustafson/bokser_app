from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.database import Base

WAREHOUSE_SCHEMA = "warehouse_data"


class ProductivShipmentHeaders(Base):
    __tablename__ = "productiv_ship_headers"
    __table_args__ = (
        UniqueConstraint(
            "order_id",
            name="ux_productiv_ship_headers_order_id",
        ),
        {"schema": WAREHOUSE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # ------------------------------------------------------------------
    # body.readOnly
    # ------------------------------------------------------------------

    order_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    reference_num: Mapped[str | None] = mapped_column(String(128), index=True)
    po_num: Mapped[str | None] = mapped_column(String(128), index=True)
    external_id: Mapped[str | None] = mapped_column(String(128), index=True)

    fully_allocated: Mapped[bool | None]

    is_closed: Mapped[bool | None]

    process_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    pick_started: Mapped[bool | None]
    pick_done_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    pick_ticket_print_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )

    pack_started: Mapped[bool | None]
    pack_done_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    # Small Parcel specific
    small_parcel_ship_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )

    parcel_label_type: Mapped[int | None]

    ship_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    # Customer identifier
    customer_id: Mapped[int | None]
    customer_name: Mapped[str | None] = mapped_column(String(255))

    # Facility identifier
    facility_id: Mapped[int | None]
    facility_name: Mapped[str | None] = mapped_column(String(255))

    creation_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    created_by_id: Mapped[int | None]
    created_by_name: Mapped[str | None] = mapped_column(String(255))

    last_modified_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )

    last_modified_by_id: Mapped[int | None]
    last_modified_by_name: Mapped[str | None] = mapped_column(String(255))

    status: Mapped[int | None]
    charges_pending: Mapped[bool | None]

    # ------------------------------------------------------------------
    # body root
    # ------------------------------------------------------------------

    earliest_ship_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )

    notes: Mapped[str | None] = mapped_column(Text)

    num_units_1: Mapped[int | None]
    unit_1_name: Mapped[str | None] = mapped_column(String(64))

    num_units_2: Mapped[int | None]
    unit_2_name: Mapped[str | None] = mapped_column(String(64))

    total_weight: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    total_volume: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    billing_code: Mapped[str | None] = mapped_column(String(64))

    # ------------------------------------------------------------------
    # body.routingInfo
    # ------------------------------------------------------------------

    routing_scac_code: Mapped[str | None] = mapped_column(String(16))
    routing_carrier: Mapped[str | None] = mapped_column(String(128))
    routing_mode: Mapped[str | None] = mapped_column(String(32))

    # Mostly Small Parcel
    routing_account: Mapped[str | None] = mapped_column(String(64))
    routing_ship_point_zip: Mapped[str | None] = mapped_column(String(32))

    # Mostly LTL
    routing_bill_of_lading: Mapped[str | None] = mapped_column(
        String(128),
        index=True,
    )
    routing_pickup_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )

    # Both Small Parcel and LTL can have this
    routing_tracking_number: Mapped[str | None] = mapped_column(
        String(128),
        index=True,
    )

    # ------------------------------------------------------------------
    # body.shipTo
    # ------------------------------------------------------------------

    ship_to_contact_id: Mapped[int | None]
    ship_to_company_name: Mapped[str | None] = mapped_column(String(255))
    ship_to_name: Mapped[str | None] = mapped_column(String(255))
    ship_to_address_1: Mapped[str | None] = mapped_column(String(255))
    ship_to_address_2: Mapped[str | None] = mapped_column(String(255))
    ship_to_city: Mapped[str | None] = mapped_column(String(128))
    ship_to_state: Mapped[str | None] = mapped_column(String(64))
    ship_to_zip: Mapped[str | None] = mapped_column(String(32))
    ship_to_country: Mapped[str | None] = mapped_column(String(8))
    ship_to_phone: Mapped[str | None] = mapped_column(String(64))
    ship_to_email: Mapped[str | None] = mapped_column(String(255))
    ship_to_is_residential: Mapped[bool | None]
    ship_to_address_status: Mapped[int | None]

    # ------------------------------------------------------------------
    # body.billTo
    # ------------------------------------------------------------------

    bill_to_contact_id: Mapped[int | None]
    bill_to_company_name: Mapped[str | None] = mapped_column(String(255))
    bill_to_name: Mapped[str | None] = mapped_column(String(255))
    bill_to_address_1: Mapped[str | None] = mapped_column(String(255))
    bill_to_address_2: Mapped[str | None] = mapped_column(String(255))
    bill_to_city: Mapped[str | None] = mapped_column(String(128))
    bill_to_state: Mapped[str | None] = mapped_column(String(64))
    bill_to_zip: Mapped[str | None] = mapped_column(String(32))
    bill_to_country: Mapped[str | None] = mapped_column(String(8))
    bill_to_phone: Mapped[str | None] = mapped_column(String(64))
    bill_to_email: Mapped[str | None] = mapped_column(String(255))
    bill_to_is_residential: Mapped[bool | None]
    bill_to_address_status: Mapped[int | None]

    # ------------------------------------------------------------------
    # Tracking Numbers Outbound and Return
    # ------------------------------------------------------------------

    parcel_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------

    items: Mapped[list[ProductivShipmentItems]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )

    packages: Mapped[list[ProductivShipmentPackages]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )

    billing_charges: Mapped[list[ProductivShipmentBillingCharges]] = relationship(
        back_populates="header",
        cascade="all, delete-orphan",
    )


class ProductivShipmentItems(Base):
    __tablename__ = "productiv_ship_items"
    __table_args__ = (
        UniqueConstraint(
            "order_item_id",
            name="ux_productiv_ship_items_order_item_id",
        ),
        {"schema": WAREHOUSE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    header_id: Mapped[int] = mapped_column(
        ForeignKey(
            f"{WAREHOUSE_SCHEMA}.productiv_ship_headers.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # readOnly
    order_item_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    fully_allocated: Mapped[bool | None]

    unit_name: Mapped[str | None] = mapped_column(String(64))

    original_primary_qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    row_version: Mapped[str | None] = mapped_column(String(128))

    # itemIdentifier
    productiv_item_id: Mapped[int | None] = mapped_column(index=True)
    sku: Mapped[str | None] = mapped_column(String(128), index=True)

    external_id: Mapped[str | None] = mapped_column(String(128))

    qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    weight_imperial: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    weight_metric: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    fulfill_inv_sale_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    header: Mapped[ProductivShipmentHeaders] = relationship(back_populates="items")


class ProductivShipmentPackages(Base):
    __tablename__ = "productiv_ship_packages"
    __table_args__ = (
        UniqueConstraint(
            "productiv_package_id",
            name="ux_productiv_ship_packages_package_id",
        ),
        {"schema": WAREHOUSE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    header_id: Mapped[int] = mapped_column(
        ForeignKey(
            f"{WAREHOUSE_SCHEMA}.productiv_ship_headers.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    productiv_package_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    package_type_id: Mapped[int | None]

    length: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    width: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    height: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    weight: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))

    tracking_number: Mapped[str | None] = mapped_column(
        String(128),
        index=True,
    )

    create_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    oversize: Mapped[bool | None]

    ucc128: Mapped[int | None]

    carton_id: Mapped[str | None] = mapped_column(
        String(128),
        index=True,
    )

    header: Mapped[ProductivShipmentHeaders] = relationship(back_populates="packages")

    contents: Mapped[list[ProductivShipmentPackageContents]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
    )


class ProductivShipmentPackageContents(Base):
    __tablename__ = "productiv_ship_package_contents"
    __table_args__ = (
        UniqueConstraint(
            "productiv_package_content_id",
            name="ux_productiv_ship_package_contents_content_id",
        ),
        {"schema": WAREHOUSE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    package_id: Mapped[int] = mapped_column(
        ForeignKey(
            f"{WAREHOUSE_SCHEMA}.productiv_ship_packages.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    productiv_package_content_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    # Keep Productiv's IDs as data as well.
    productiv_package_id: Mapped[int | None] = mapped_column(index=True)
    productiv_order_item_id: Mapped[int | None] = mapped_column(index=True)
    productiv_receive_item_id: Mapped[int | None] = mapped_column(index=True)

    qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    create_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    productiv_item_id: Mapped[int | None] = mapped_column(index=True)
    sku: Mapped[str | None] = mapped_column(String(128), index=True)

    package: Mapped[ProductivShipmentPackages] = relationship(back_populates="contents")


class ProductivShipmentBillingCharges(Base):
    __tablename__ = "productiv_ship_billing_charges"
    __table_args__ = (
        UniqueConstraint(
            "header_id",
            "sequence",
            name="ux_productiv_ship_billing_charges_header_sequence",
        ),
        {"schema": WAREHOUSE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    header_id: Mapped[int] = mapped_column(
        ForeignKey(
            f"{WAREHOUSE_SCHEMA}.productiv_ship_headers.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    sequence: Mapped[int] = mapped_column(nullable=False)

    charge_type: Mapped[int | None]

    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    header: Mapped[ProductivShipmentHeaders] = relationship(
        back_populates="billing_charges"
    )

    details: Mapped[list[ProductivShipmentBillingChargeDetails]] = relationship(
        back_populates="billing_charge",
        cascade="all, delete-orphan",
    )


class ProductivShipmentBillingChargeDetails(Base):
    __tablename__ = "productiv_ship_billing_charge_details"
    __table_args__ = (
        UniqueConstraint(
            "billing_charge_id",
            "warehouse_transaction_price_calc_id",
            name="ux_productiv_ship_billing_charge_details_calc_id",
        ),
        {"schema": WAREHOUSE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    billing_charge_id: Mapped[int] = mapped_column(
        ForeignKey(
            f"{WAREHOUSE_SCHEMA}.productiv_ship_billing_charges.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    warehouse_transaction_price_calc_id: Mapped[int | None] = mapped_column(index=True)

    num_units: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    charge_label: Mapped[str | None] = mapped_column(String(255))
    unit_description: Mapped[str | None] = mapped_column(String(128))

    charge_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    sku: Mapped[str | None] = mapped_column(String(128))

    system_generated: Mapped[bool | None]

    billing_charge: Mapped[ProductivShipmentBillingCharges] = relationship(
        back_populates="details"
    )
