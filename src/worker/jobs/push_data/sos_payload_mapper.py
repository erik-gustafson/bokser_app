from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Sequence
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import inspect, select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.base import NO_VALUE

from src.core.config import settings

from src.database.database import async_session
from src.database.models import AcendaOrderHeaders, AcendaOrderItems, SosItem

ACENDA_SALES_CHANNEL_TO_SOS_IDS = {
    "Target Plus US Marketplace": {"acenda": 1, "sos": 15},
    "Macys": {"acenda": 2, "sos": 49},
    "Kohls": {"acenda": 3, "sos": 66},
    "bokserhome.myshopify.com": {"acenda": 4, "sos": 12},
    "Overstock": {"acenda": 5, "sos": 37},
    "Walmart US": {"acenda": 6, "sos": 206},
    "Wayfair": {"acenda": 7, "sos": 135},
}


def add_time(**kwargs):
    return datetime.now(timezone.utc) + timedelta(**kwargs)


class SosItemsForLoad:

    def __init__(self):
        self.item_dict: dict[str, SosItem] = {}

    async def load_sos_items_by_sku(
        self,
        skus: Sequence[str | None],
    ) -> None:
        if not skus:
            return

        async with async_session() as session:
            stmt = (
                select(SosItem)
                .options(selectinload(SosItem.uoms))
                .where(SosItem.sku.in_(skus))
            )

            items = list((await session.scalars(stmt)).all())

        self.item_dict = {str(item.sku): item for item in items if item.sku is not None}

    def clear_dict(self):
        self.item_dict.clear()


class _SosPayloadModel(BaseModel):
    """Base model for outbound SOS API payloads."""

    model_config = ConfigDict(validate_by_name=True, extra="forbid")


class SosReference(_SosPayloadModel):
    id: int = Field(gt=0)


class SosPostalAddress(_SosPayloadModel):
    name: str | None = None
    type: str | None = None
    line_1: str | None = Field(default=None, serialization_alias="line1")
    line_2: str | None = Field(default=None, serialization_alias="line2")
    line_3: str | None = Field(default=None, serialization_alias="line3")
    line_4: str | None = Field(default=None, serialization_alias="line4")
    line_5: str | None = Field(default=None, serialization_alias="line5")
    city: str | None = None
    state_province: str | None = Field(
        default=None,
        serialization_alias="stateProvince",
    )
    postal_code: str | None = Field(default=None, serialization_alias="postalCode")
    country: str | None = None


class SosTransactionAddress(_SosPayloadModel):
    company: str | None = None
    contact: str | None = None
    phone: str | None = None
    email: str | None = None
    address: SosPostalAddress | None = None


class SosSalesOrderLineCreate(_SosPayloadModel):
    id: str
    line_number: int = Field(
        ge=1,
        serialization_alias="lineNumber",
    )
    item: dict[str, int | str]
    sos_class: dict[str, int | str] = Field(serialization_alias="class")
    description: str | None = None
    quantity: float = Field(gt=0)
    uom: dict[str, int | str]
    unit_price: float | None = Field(default=None, serialization_alias="unitprice")
    amount: float
    due_date: str  # <- Use headers expected delviery date or today + 5?
    tax: dict[str, bool]  # <- if tax amount on order is 0 then false else true

    def to_payload(self) -> dict[str, Any]:
        """Return the JSON-safe dictionary."""

        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


class SosSalesOrderCreate(_SosPayloadModel):
    number: str
    date: str | None = None
    customer: dict[str, int]
    location: dict[str, int | str] | None = None
    customer_po: str | None = Field(default=None, serialization_alias="customerPO")
    comment: str | None = None
    billing: SosTransactionAddress | None = None
    shipping: SosTransactionAddress | None = None

    order_stage: dict[str, int | str] = Field(serialization_alias="orderStage")
    channel: dict[str, int | str]
    terms: dict[str, int | str]
    shipping_amount: float | None = Field(
        default=None, serialization_alias="shippingAmount"
    )
    discount_amount: float | None = Field(
        default=None, serialization_alias="discountAmount"
    )
    tax_amount: float | None = Field(default=None, serialization_alias="taxAmount")

    lines: list[SosSalesOrderLineCreate] = Field(min_length=1)

    def to_payload(self) -> dict[str, Any]:
        """Return the JSON-safe dictionary."""

        return self.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
            exclude={
                "lines": {
                    "__all__": {"id"},
                }
            },
        )


class SosSalesOrderPayloadMapper:

    def __init__(self, sos_items: SosItemsForLoad) -> None:
        self.sos_items = sos_items

    def map_acenda_order(
        self,
        order: AcendaOrderHeaders,
    ) -> SosSalesOrderCreate:

        items = self._loaded_collection(order, "items", source="Acenda Order")
        sorted_items = sorted(items, key=lambda item: item.id)
        lines = [
            self._map_acenda_line(
                line=item,
                line_number=line_number,
                sos_items=self.sos_items,
            )
            for line_number, item in enumerate(sorted_items, start=1)
        ]

        shipping_amount = sum([x.total_handling_price for x in order.items])
        discount_amount = sum([x.total_item_discount for x in order.items])
        tax_amount = sum([x.total_item_tax for x in order.items])

        if order.sales_channel_name:
            try:
                sales_channel_customer_dict = ACENDA_SALES_CHANNEL_TO_SOS_IDS[
                    order.sales_channel_name
                ]
            except:
                raise KeyError(
                    f"Sales channel name provided for Acenda order {order.id} not valid!"
                )
        else:
            raise ValueError(
                f"No sales shannel name provided for Acenda order {order.id}!"
            )

        sos_customer_dict = {"id": sales_channel_customer_dict["sos"]}
        order_stage = self._set_order_stage(order.sales_channel_id)

        return SosSalesOrderCreate(
            number=str(order.order_number),
            date=settings.sos_timestamp_format(order.ordered_at),
            customer=sos_customer_dict,
            location=settings.sos_ksp_location_dict,
            customer_po=order.purchase_order,
            comment=self._acenda_comment(order.fields),
            billing=self._acenda_address(order, "bill"),
            shipping=self._acenda_address(order, "ship"),
            order_stage=order_stage,
            channel=settings.sos_dtc_channel_dict,
            terms=settings.sos_default_terms_dict,
            shipping_amount=shipping_amount,
            discount_amount=discount_amount,
            tax_amount=tax_amount,
            lines=lines,
        )

    @staticmethod
    def _loaded_collection(
        instance: Any,
        relationship_name: str,
        *,
        source: str,
    ) -> list[Any]:
        state = inspect(instance)
        relationship = state.attrs[relationship_name]
        if relationship.loaded_value is NO_VALUE:
            identity = getattr(instance, "id", None)
            raise ValueError(
                f"{source} {identity!r} relationship "
                f"{relationship_name!r} must be loaded before mapping"
            )
        return list(relationship.loaded_value)

    @staticmethod
    def _map_acenda_line(
        line: AcendaOrderItems, line_number: int, sos_items: SosItemsForLoad
    ) -> SosSalesOrderLineCreate:
        sos_item = sos_items.item_dict.get(line.sku)

        if sos_item is None:
            raise ValueError(
                f"Acenda order item {line.id!r} has no valid SOS item mapping to {line.sku!r}",
                line,
            )

        item_id_dict = {"id": sos_item.id} if sos_item.id else {}
        item_name_dict = {"name": sos_item.name} if sos_item.name else {}

        due_date = (
            settings.sos_timestamp_format(line.expected_delivery_date)
            if line.expected_delivery_date
            else settings.sos_timestamp_format(add_time(days=7))
        )

        taxable = (
            settings.sos_item_taxable_dict
            if line.total_item_tax
            else settings.sos_item_non_taxable_dict
        )

        return SosSalesOrderLineCreate(
            id=str(line.id),
            line_number=line_number,
            item=item_id_dict | item_name_dict,
            sos_class=settings.sos_dtc_class_dict,
            description=sos_item.description,
            quantity=line.quantity,
            unit_price=line.unit_price,
            uom=settings.sos_uom_ea_dict,
            amount=line.total_price,
            due_date=due_date,
            tax=taxable,
        )

    @classmethod
    def _acenda_address(
        cls,
        order: AcendaOrderHeaders,
        prefix: str,
    ) -> SosTransactionAddress | None:
        contact = cls._join_contact(
            getattr(order, f"{prefix}_first_name"),
            getattr(order, f"{prefix}_last_name"),
        )
        postal = cls._optional_postal_address(
            line_1=getattr(order, f"{prefix}_address_1"),
            line_2=getattr(order, f"{prefix}_address_2"),
            city=getattr(order, f"{prefix}_city"),
            state_province=getattr(order, f"{prefix}_state"),
            postal_code=getattr(order, f"{prefix}_postal_code"),
            country=getattr(order, f"{prefix}_country"),
        )
        return cls._optional_transaction_address(
            company=getattr(order, f"{prefix}_company"),
            contact=contact,
            phone=getattr(order, f"{prefix}_phone_number"),
            email=getattr(order, f"{prefix}_email"),
            address=postal,
        )

    @staticmethod
    def _optional_postal_address(**values: str | None) -> SosPostalAddress | None:
        return SosPostalAddress(**values) if any(values.values()) else None

    @staticmethod
    def _optional_transaction_address(
        *,
        company: str | None,
        contact: str | None,
        phone: str | None,
        email: str | None,
        address: SosPostalAddress | None,
    ) -> SosTransactionAddress | None:
        if not any((company, contact, phone, email, address)):
            return None
        return SosTransactionAddress(
            company=company,
            contact=contact,
            phone=phone,
            email=email,
            address=address,
        )

    @staticmethod
    def _join_contact(first_name: str | None, last_name: str | None) -> str | None:
        contact = " ".join(
            part.strip() for part in (first_name, last_name) if part and part.strip()
        )
        return contact or None

    @staticmethod
    def _acenda_comment(fields: dict[str, Any] | None) -> str | None:
        if not fields:
            return None
        comment = fields.get("comment")
        return comment if isinstance(comment, str) else None

    @staticmethod
    def _set_order_stage(customer_id: int) -> dict[str, int | str]:
        if customer_id in settings.acenda_send_to_wms.values():
            return settings.sos_ready_to_send_order_stage_dict
        else:
            return settings.sos_marketplace_order_stage_dict


__all__ = [
    "SosPostalAddress",
    "SosReference",
    "SosSalesOrderCreate",
    "SosSalesOrderLineCreate",
    "SosSalesOrderPayloadMapper",
    "SosTransactionAddress",
]
