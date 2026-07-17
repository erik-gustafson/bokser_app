from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.orm.base import NO_VALUE

from src.database.models.acenda_models import AcendaOrderHeaders, AcendaOrderItems
from src.database.models.sos import SosSalesOrderHeader, SosSalesOrderLine


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
    item: SosReference
    description: str | None = None
    quantity: float = Field(gt=0)
    unit_price: float | None = Field(default=None, serialization_alias="unitprice")


class SosSalesOrderCreate(_SosPayloadModel):
    number: str | None = None
    date: datetime | None = None
    customer: SosReference
    location: SosReference | None = None
    customer_po: str | None = Field(default=None, serialization_alias="customerPO")
    comment: str | None = None
    billing: SosTransactionAddress | None = None
    shipping: SosTransactionAddress | None = None
    lines: list[SosSalesOrderLineCreate] = Field(min_length=1)

    def to_payload(self) -> dict[str, Any]:
        """Return the JSON-safe dictionary expected by ``SOSClient.post``."""

        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


class SosOrderReferences(_SosPayloadModel):
    """SOS identifiers resolved by the caller for an Acenda order."""

    customer_id: int = Field(gt=0)
    item_ids: dict[int, int]
    location_id: int | None = Field(default=None, gt=0)


class SosSalesOrderPayloadMapper:
    def map_acenda_order(
        self,
        order: AcendaOrderHeaders,
        references: SosOrderReferences,
    ) -> SosSalesOrderCreate:
        items = self._loaded_collection(order, "items", source="Acenda Order")
        lines = [self._map_acenda_line(item, references.item_ids) for item in items]

        return SosSalesOrderCreate(
            number=str(order.order_number),
            date=order.ordered_at,
            customer=SosReference(id=references.customer_id),
            location=(
                SosReference(id=references.location_id)
                if references.location_id is not None
                else None
            ),
            customer_po=order.purchase_order,
            comment=self._acenda_comment(order.fields),
            billing=self._acenda_address(order, "bill"),
            shipping=self._acenda_address(order, "ship"),
            lines=lines,
        )

    @staticmethod
    def _loaded_collection(
        instance: Any,
        relationship_name: str,
        *,
        source: str,
    ) -> list[Any]:
        state = sqlalchemy_inspect(instance)
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
        line: AcendaOrderItems,
        item_ids: dict[int, int],
    ) -> SosSalesOrderLineCreate:
        sos_item_id = item_ids.get(line.id)
        if sos_item_id is None or sos_item_id <= 0:
            raise ValueError(
                f"Acenda order item {line.id!r} has no valid SOS item mapping"
            )

        return SosSalesOrderLineCreate(
            item=SosReference(id=sos_item_id),
            description=line.product_name,
            quantity=line.quantity,
            unit_price=line.unit_price,
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


__all__ = [
    "SosOrderReferences",
    "SosPostalAddress",
    "SosReference",
    "SosSalesOrderCreate",
    "SosSalesOrderLineCreate",
    "SosSalesOrderPayloadMapper",
    "SosTransactionAddress",
]
