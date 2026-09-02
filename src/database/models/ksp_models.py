from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.database import Base

KSP_SCHEMA = "warehouse_data"


class KSPShipmentHeaders(Base):
    __tablename__ = "ksp_ship_headers"
    __table_args__ = {"schema": KSP_SCHEMA}

    cust_ref: Mapped[str] = mapped_column(
        String, index=True, unique=True, primary_key=True
    )
    cust_po_no: Mapped[str] = mapped_column(String, index=True, primary_key=True)
    delivered_to_wms_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=True,
    )
    order_status: Mapped[str] = mapped_column(String, index=True)

    ship_details: Mapped[list["KSPShipmentDetails"]] = relationship(
        back_populates="ship_headers",
        cascade="all, delete-orphan",
    )


class KSPShipmentDetails(Base):
    __tablename__ = "ksp_ship_details"
    __table_args__ = {"schema": KSP_SCHEMA}

    cust_ref: Mapped[str] = mapped_column(
        ForeignKey(f"{KSP_SCHEMA}.ksp_ship_headers.cust_ref"),
        index=True,
        nullable=False,
    )

    carrier: Mapped[str] = mapped_column(String, index=True)
    method: Mapped[str] = mapped_column(String)

    tracking_no: Mapped[str] = mapped_column(
        String, index=True, unique=True, primary_key=True
    )
    tracking_no_secondary: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )

    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    total_cost: Mapped[float] = mapped_column(default=0.0)
    package_weight_lbs: Mapped[float] = mapped_column(default=0.0)
    dim_weight_lbs: Mapped[float] = mapped_column(default=0.0)
    zone: Mapped[str | None] = mapped_column(String(128), nullable=True)
    delivery_surcharge_type: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )

    custom_1: Mapped[str | None] = mapped_column(String(128), nullable=True)
    custom_2: Mapped[str | None] = mapped_column(String(128), nullable=True)
    custom_3: Mapped[str | None] = mapped_column(String(128), nullable=True)

    ship_headers: Mapped["KSPShipmentHeaders"] = relationship(
        back_populates="ship_details",
    )

    items: Mapped[list["KSPShipmentDetailItems"]] = relationship(
        back_populates="ship_details",
        cascade="all, delete-orphan",
    )


class KSPShipmentDetailItems(Base):
    __tablename__ = "ksp_ship_detail_items"
    __table_args__ = {"schema": KSP_SCHEMA}

    tracking_no: Mapped[str] = mapped_column(
        ForeignKey(f"{KSP_SCHEMA}.ksp_ship_details.tracking_no"),
        index=True,
        nullable=False,
        primary_key=True,
    )
    item: Mapped[str] = mapped_column(String, index=True, primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer)
    carton_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    carton_num: Mapped[str | None] = mapped_column(String(128), nullable=True)
    box_length_in: Mapped[str | None] = mapped_column(String(128), nullable=True)
    box_width_in: Mapped[str | None] = mapped_column(String(128), nullable=True)
    box_height_in: Mapped[str | None] = mapped_column(String(128), nullable=True)
    package_weight_lbs: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lot_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    serial_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    custom_1: Mapped[str | None] = mapped_column(String(128), nullable=True)

    ship_details: Mapped["KSPShipmentDetails"] = relationship(
        back_populates="items",
    )
