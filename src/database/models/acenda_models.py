from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from src.database.database import Base

ACENDA_SCHEMA = "acenda"


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _json_safe_column_dict(model: Any) -> dict[str, Any]:
    return {
        column.name: _json_safe(getattr(model, column.name))
        for column in model.__table__.columns
    }


class AcendaOrderHeaders(Base):
    __tablename__ = "order_headers"
    __table_args__ = {"schema": ACENDA_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, index=True, primary_key=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    fields: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        default=dict,
        nullable=True,
    )

    ordered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=True,
    )

    order_number: Mapped[int] = mapped_column(Integer, index=True)

    status: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
    )

    purchase_order: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_order_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    sales_channel_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sales_channel_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sales_channel_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sales_channel_subtype: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    sales_channel_country: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    send_email: Mapped[bool | None] = mapped_column(default=False, nullable=True)
    create_routings: Mapped[bool | None] = mapped_column(default=False, nullable=True)

    shipping_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_code: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Shipping Information
    ship_first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    ship_last_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    ship_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    ship_address_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    ship_address_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    ship_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    ship_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ship_postal_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ship_country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ship_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    ship_phone_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Billing Information
    bill_first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    bill_last_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    bill_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    bill_address_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    bill_address_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    bill_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    bill_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bill_postal_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bill_country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bill_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    bill_phone_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    item_tax: Mapped[float] = mapped_column(default=0.0)
    ship_tax: Mapped[float] = mapped_column(default=0.0)
    shipping: Mapped[float] = mapped_column(default=0.0)
    total_item_discount: Mapped[float] = mapped_column(default=0.0)
    total_shipping_discount: Mapped[float] = mapped_column(default=0.0)
    subtotal: Mapped[float] = mapped_column(default=0.0)
    total: Mapped[float] = mapped_column(default=0.0)
    item_count: Mapped[int] = mapped_column(default=0)
    line_count: Mapped[int] = mapped_column(default=0)
    tax_total: Mapped[float] = mapped_column(default=0.0)

    requested_ship_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    requested_delivery_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    items: Mapped[list["AcendaOrderItems"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )

    returns: Mapped[list["AcendaOrderReturns"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )

    ship_advice_headers: Mapped[list["AcendaShipAdviceHeaders"]] = relationship(
        "AcendaShipAdviceHeaders",
        primaryjoin="foreign(AcendaShipAdviceHeaders.order_id) == AcendaOrderHeaders.id",
        foreign_keys="AcendaShipAdviceHeaders.order_id",
        viewonly=True,
        back_populates="order",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            column.name: getattr(self, column.name) for column in self.__table__.columns
        }

    def to_json(self) -> dict[str, Any]:
        return _json_safe_column_dict(self)


class AcendaOrderItems(Base):
    __tablename__ = "order_items"
    __table_args__ = {"schema": ACENDA_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    order_id: Mapped[int] = mapped_column(
        ForeignKey(f"{ACENDA_SCHEMA}.order_headers.id"),
        index=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    fields: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        default=dict,
        nullable=True,
    )

    line_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    subscription_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    external_sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    product_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    sku: Mapped[str] = mapped_column(String(128), nullable=False)
    upc: Mapped[str | None] = mapped_column(String(128), nullable=True)

    unit_price: Mapped[float] = mapped_column(default=0.0)
    gift_message_price: Mapped[float] = mapped_column(default=0.0)
    gift_message_tax_price: Mapped[float] = mapped_column(default=0.0)
    total_customization_price: Mapped[float] = mapped_column(default=0.0)
    total_customization_tax_price: Mapped[float] = mapped_column(default=0.0)
    total_shipping_price: Mapped[float] = mapped_column(default=0.0)
    total_shipping_tax_price: Mapped[float] = mapped_column(default=0.0)
    total_handling_price: Mapped[float] = mapped_column(default=0.0)
    total_item_tax: Mapped[float] = mapped_column(default=0.0)
    total_tax_price: Mapped[float] = mapped_column(default=0.0)
    total_price: Mapped[float] = mapped_column(default=0.0)
    other_fees: Mapped[float] = mapped_column(default=0.0)
    tax_rate: Mapped[float] = mapped_column(default=0.0)
    total_item_discount: Mapped[float] = mapped_column(default=0.0)
    total_shipping_discount: Mapped[float] = mapped_column(default=0.0)
    total_gift_option_price: Mapped[float] = mapped_column(default=0.0)
    total_gift_option_tax_price: Mapped[float] = mapped_column(default=0.0)

    expected_shipping_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    expected_delivery_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    shipping_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_warehouse_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    two_day_shipping: Mapped[bool | None] = mapped_column(
        default=False,
        nullable=True,
    )

    status: Mapped[str | None] = mapped_column(String(64), nullable=True)

    quantity: Mapped[int] = mapped_column(default=0)
    quantity_fulfilled: Mapped[int] = mapped_column(default=0)
    quantity_canceled: Mapped[int] = mapped_column(default=0)
    quantity_routed: Mapped[int] = mapped_column(default=0)

    order: Mapped["AcendaOrderHeaders"] = relationship(
        back_populates="items",
    )

    discounts: Mapped[list["AcendaOrderLineDiscounts"]] = relationship(
        back_populates="order_item",
        cascade="all, delete-orphan",
    )

    kit_items: Mapped[list["AcendaOrderLineKitItems"]] = relationship(
        back_populates="order_item",
        cascade="all, delete-orphan",
    )

    ship_advice_items: Mapped[list["AcendaShipAdviceItems"]] = relationship(
        "AcendaShipAdviceItems",
        primaryjoin="foreign(AcendaShipAdviceItems.order_item_id) == AcendaOrderItems.id",
        foreign_keys="AcendaShipAdviceItems.order_item_id",
        viewonly=True,
        back_populates="order_item",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            column.name: getattr(self, column.name) for column in self.__table__.columns
        }

    def to_json(self) -> dict[str, Any]:
        return _json_safe_column_dict(self)


class AcendaOrderLineDiscounts(Base):
    __tablename__ = "order_line_discounts"
    __table_args__ = {"schema": ACENDA_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    order_item_id: Mapped[int] = mapped_column(
        ForeignKey(f"{ACENDA_SCHEMA}.order_items.id"),
        index=True,
        nullable=False,
    )

    order_item: Mapped["AcendaOrderItems"] = relationship(
        back_populates="discounts",
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    fields: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        default=dict,
        nullable=True,
    )

    promotion_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    promotion_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    affects: Mapped[str | None] = mapped_column(String(64), nullable=True)

    price: Mapped[float] = mapped_column(default=0.0)


class AcendaOrderLineKitItems(Base):
    __tablename__ = "order_line_kit_items"
    __table_args__ = {"schema": ACENDA_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    order_item_id: Mapped[int] = mapped_column(
        ForeignKey(f"{ACENDA_SCHEMA}.order_items.id"),
        index=True,
        nullable=False,
    )

    order_item: Mapped["AcendaOrderItems"] = relationship(
        back_populates="kit_items",
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    fields: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        default=dict,
        nullable=True,
    )

    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sku: Mapped[str | None] = mapped_column(String(128), nullable=True)

    quantity: Mapped[int] = mapped_column(default=0)


class AcendaOrderReturns(Base):
    __tablename__ = "order_returns"
    __table_args__ = {"schema": ACENDA_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    order_id: Mapped[int] = mapped_column(
        ForeignKey(f"{ACENDA_SCHEMA}.order_headers.id"),
        index=True,
        nullable=False,
    )

    order_item_id: Mapped[int] = mapped_column(
        ForeignKey(f"{ACENDA_SCHEMA}.order_items.id"),
        index=True,
        nullable=False,
    )

    order: Mapped["AcendaOrderHeaders"] = relationship(
        back_populates="returns",
    )

    order_item: Mapped["AcendaOrderItems"] = relationship()

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    fields: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        default=dict,
        nullable=True,
    )

    quantity: Mapped[int] = mapped_column(default=0)

    rma: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_plate_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)

    restock_inventory: Mapped[bool | None] = mapped_column(
        default=False,
        nullable=True,
    )
    return_required: Mapped[bool | None] = mapped_column(
        default=False,
        nullable=True,
    )
    advance_refund: Mapped[bool | None] = mapped_column(
        default=False,
        nullable=True,
    )

    method: Mapped[str | None] = mapped_column(Text, nullable=True)
    carrier: Mapped[str | None] = mapped_column(Text, nullable=True)

    return_tracking: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        default=list,
        nullable=True,
    )


class AcendaShipAdviceHeaders(Base):
    __tablename__ = "ship_advice_headers"
    __table_args__ = {"schema": ACENDA_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    order_id: Mapped[int] = mapped_column(
        Integer,
        index=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    order: Mapped["AcendaOrderHeaders"] = relationship(
        "AcendaOrderHeaders",
        primaryjoin="foreign(AcendaShipAdviceHeaders.order_id) == AcendaOrderHeaders.id",
        foreign_keys=[order_id],
        viewonly=True,
        back_populates="ship_advice_headers",
    )

    ship_advice_items: Mapped[list["AcendaShipAdviceItems"]] = relationship(
        back_populates="ship_advice",
        cascade="all, delete-orphan",
    )

    fields: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        default=dict,
        nullable=True,
    )

    order_routing_status: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    fulfillment_provider_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    warehouse_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    delivery_info_first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_info_last_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_info_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_info_address_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_info_address_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_info_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_info_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivery_info_postal_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    delivery_info_country: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    delivery_info_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_info_phone_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    fulfillments: Mapped[list["AcendaFulfillments"]] = relationship(
        "AcendaFulfillments",
        primaryjoin=(
            "AcendaShipAdviceHeaders.id == "
            "foreign(AcendaFulfillments.ship_advice_id)"
        ),
        foreign_keys="AcendaFulfillments.ship_advice_id",
        back_populates="ship_advice",
        viewonly=True,
    )

    fulfillment_tracking: Mapped[list["AcendaFulfillmentTracking"]] = relationship(
        "AcendaFulfillmentTracking",
        secondary=lambda: AcendaFulfillments.__table__,
        primaryjoin=lambda: AcendaShipAdviceHeaders.id
        == foreign(AcendaFulfillments.ship_advice_id),
        secondaryjoin=lambda: AcendaFulfillments.id
        == foreign(AcendaFulfillmentTracking.fulfillment_id),
        viewonly=True,
    )


class AcendaShipAdviceItems(Base):
    __tablename__ = "ship_advice_items"
    __table_args__ = {"schema": ACENDA_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    order_item_id: Mapped[int] = mapped_column(
        Integer,
        index=True,
        nullable=False,
    )

    ship_advice_id: Mapped[int] = mapped_column(
        ForeignKey(f"{ACENDA_SCHEMA}.ship_advice_headers.id"),
        index=True,
        nullable=False,
    )

    order_item: Mapped["AcendaOrderItems"] = relationship(
        "AcendaOrderItems",
        primaryjoin="foreign(AcendaShipAdviceItems.order_item_id) == AcendaOrderItems.id",
        foreign_keys=[order_item_id],
        viewonly=True,
        back_populates="ship_advice_items",
    )

    ship_advice: Mapped["AcendaShipAdviceHeaders"] = relationship(
        back_populates="ship_advice_items",
    )

    inventory_detail_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantity_rerouted: Mapped[int] = mapped_column(default=0)

    fulfillment_items: Mapped[list["AcendaFulfillmentItems"]] = relationship(
        "AcendaFulfillmentItems",
        primaryjoin=(
            "AcendaShipAdviceItems.id == "
            "foreign(AcendaFulfillmentItems.ship_advice_item_id)"
        ),
        foreign_keys="AcendaFulfillmentItems.ship_advice_item_id",
        back_populates="ship_advice_item",
        viewonly=True,
    )


class AcendaFulfillments(Base):
    __tablename__ = "fulfillments"
    __table_args__ = {"schema": ACENDA_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    fields: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        default=dict,
        nullable=True,
    )

    ship_advice_id: Mapped[int] = mapped_column(
        Integer,
        index=True,
        nullable=False,
    )

    ship_advice: Mapped["AcendaShipAdviceHeaders"] = relationship(
        "AcendaShipAdviceHeaders",
        primaryjoin=(
            "foreign(AcendaFulfillments.ship_advice_id) == "
            "AcendaShipAdviceHeaders.id"
        ),
        foreign_keys=[ship_advice_id],
        back_populates="fulfillments",
        viewonly=True,
    )

    carrier: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_shipped: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    shipping_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    fulfillment_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost: Mapped[float] = mapped_column(default=0.0)
    is_ltl: Mapped[bool] = mapped_column(default=False)

    items: Mapped[list["AcendaFulfillmentItems"]] = relationship(
        back_populates="fulfillment",
        cascade="all, delete-orphan",
    )

    tracking: Mapped[list["AcendaFulfillmentTracking"]] = relationship(
        back_populates="fulfillment",
        cascade="all, delete-orphan",
    )


class AcendaFulfillmentTracking(Base):
    __tablename__ = "fulfillment_tracking"
    __table_args__ = {"schema": ACENDA_SCHEMA}

    tracking_number: Mapped[str] = mapped_column(Text, primary_key=True)

    fulfillment_id: Mapped[int] = mapped_column(
        ForeignKey(f"{ACENDA_SCHEMA}.fulfillments.id"),
        index=True,
        nullable=False,
        primary_key=True,
    )

    fulfillment: Mapped["AcendaFulfillments"] = relationship(
        back_populates="tracking",
    )


class AcendaFulfillmentItems(Base):
    __tablename__ = "fulfillment_items"
    __table_args__ = {"schema": ACENDA_SCHEMA}

    fulfillment_id: Mapped[int] = mapped_column(
        ForeignKey(f"{ACENDA_SCHEMA}.fulfillments.id"),
        index=True,
        nullable=False,
        primary_key=True,
    )

    ship_advice_item_id: Mapped[int] = mapped_column(
        Integer,
        index=True,
        nullable=False,
        primary_key=True,
    )

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    ship_advice_item: Mapped["AcendaShipAdviceItems"] = relationship(
        "AcendaShipAdviceItems",
        primaryjoin=(
            "foreign(AcendaFulfillmentItems.ship_advice_item_id) == "
            "AcendaShipAdviceItems.id"
        ),
        foreign_keys=[ship_advice_item_id],
        back_populates="fulfillment_items",
        viewonly=True,
    )

    fulfillment: Mapped["AcendaFulfillments"] = relationship(
        back_populates="items",
    )
