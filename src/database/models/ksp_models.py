from __future__ import annotations

from datetime import datetime
from typing import Any
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.database import Base
from src.database.utils.model_tools import _json_safe_column_dict

WAREHOUSE_SCHEMA = "warehouse_data"


class KSPShipmentHeaders(Base):
    __tablename__ = "ksp_ship_headers"
    __table_args__ = (
        UniqueConstraint(
            "cust_ref",
            "cust_po_no",
            name="uq_ksp_ship_headers_cust_ref_po",
        ),
        {"schema": WAREHOUSE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    cust_ref: Mapped[str] = mapped_column(String)
    cust_po_no: Mapped[str] = mapped_column(String, index=True)

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

    def to_json(self) -> dict[str, Any]:
        return {
            **_json_safe_column_dict(self),
            "ship_details": [
                {
                    **_json_safe_column_dict(detail),
                    "items": [
                        _json_safe_column_dict(item)
                        for item in sorted(detail.items, key=lambda x: x.id)
                    ],
                }
                for detail in sorted(self.ship_details, key=lambda x: x.id)
            ],
        }


class KSPShipmentDetails(Base):
    __tablename__ = "ksp_ship_details"
    __table_args__ = (
        UniqueConstraint(
            "tracking_no",
            name="uq_ksp_ship_details_tracking_no",
        ),
        Index(
            "ix_warehouse_data_ksp_ship_details_shipment_header_id",
            "ship_header_id",
        ),
        {"schema": WAREHOUSE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    ship_header_id: Mapped[int] = mapped_column(
        ForeignKey(
            f"{WAREHOUSE_SCHEMA}.ksp_ship_headers.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    carrier: Mapped[str] = mapped_column(String, index=True)
    method: Mapped[str] = mapped_column(String)

    tracking_no: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )

    package_weight_lbs: Mapped[float] = mapped_column(default=0.0)
    dim_weight_lbs: Mapped[float] = mapped_column(default=0.0)

    ship_headers: Mapped["KSPShipmentHeaders"] = relationship(
        back_populates="ship_details",
    )

    items: Mapped[list["KSPShipmentDetailItems"]] = relationship(
        back_populates="ship_details",
        cascade="all, delete-orphan",
    )


class KSPShipmentDetailItems(Base):
    __tablename__ = "ksp_ship_detail_items"
    __table_args__ = (
        UniqueConstraint(
            "ship_detail_id",
            "item",
            name="uq_ksp_ship_detail_items_detail_item",
        ),
        {"schema": WAREHOUSE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    ship_detail_id: Mapped[int] = mapped_column(
        ForeignKey(
            f"{WAREHOUSE_SCHEMA}.ksp_ship_details.id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )

    item: Mapped[str] = mapped_column(String, index=True)
    quantity: Mapped[int] = mapped_column(Integer)

    ship_details: Mapped["KSPShipmentDetails"] = relationship(
        back_populates="items",
    )
