### Reconcile KSP shipments with Acenda Shipments to flag any discrepnacies

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Literal
from pathlib import Path
from dataclasses import dataclass


from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.database import async_session
from src.database.models.acenda_models import (
    AcendaOrderHeaders,
    AcendaOrderItems,
    AcendaOrderLineDiscounts,
    AcendaOrderLineKitItems,
    AcendaOrderReturns,
    AcendaShipAdviceHeaders,
    AcendaShipAdviceItems,
)
from src.database.models.data_lake_models import DataLakeFile

logger = logging.getLogger(__name__)

PayloadType = Literal["order", "ship_advice"]


@dataclass(frozen=True)
class ClaimedLakeFile:
    id: int
    file_path: str
    source_name: str
    entity_name: str


### Start Helpers ###
def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def as_str(value: Any) -> str:
    return "" if value is None else str(value)


def as_float(value: Any) -> float:
    return 0.0 if value is None else float(value)


def as_int(value: Any) -> int:
    return 0 if value is None else int(value)


def _acenda_payload_type_from_entity(entity_name: str) -> PayloadType:
    if entity_name in {"new_orders", "updated_orders", "all_orders"}:
        return "order"

    if entity_name in {"new_ship_advices", "updated_ship_advices", "all_ship_advices"}:
        return "ship_advice"

    raise ValueError(f"Unsupported Acenda entity_name: {entity_name}")


### End Helpers ###

### Entrypoint ###


async def load_acenda_lake_job() -> None:
    order_entities = [
        "new_orders",
        "updated_orders",
        "all_orders",
    ]

    ship_advice_entities = [
        "new_ship_advices",
        "updated_ship_advices",
        "all_ship_advices",
    ]

    total_results = []

    for entity_name in order_entities:
        result = await load_acenda_lake_files(
            entity_name=entity_name,
            limit=50,
        )
        total_results.append((entity_name, result))

    for entity_name in ship_advice_entities:
        result = await load_acenda_lake_files(
            entity_name=entity_name,
            limit=50,
        )
        total_results.append((entity_name, result))

    logger.info("Acenda lake load results: %s", total_results)


### --- ###


async def claim_lake_files(
    session: AsyncSession,
    *,
    source_name: str | None = None,
    entity_name: str | None = None,
    limit: int = 25,
) -> list[ClaimedLakeFile]:

    stale_processing_before = datetime.now(timezone.utc) - timedelta(minutes=30)

    stmt = (
        select(DataLakeFile)
        .where(
            or_(
                DataLakeFile.status.in_(["LANDED", "FAILED"]),
                and_(
                    DataLakeFile.status == "PROCESSING",
                    DataLakeFile.claimed_at < stale_processing_before,
                ),
            )
        )
        .order_by(DataLakeFile.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )

    if source_name:
        stmt = stmt.where(DataLakeFile.source_name == source_name)

    if entity_name:
        stmt = stmt.where(DataLakeFile.entity_name == entity_name)

    result = await session.execute(stmt)
    files = list(result.scalars().all())

    claimed_files: list[ClaimedLakeFile] = []

    for file in files:
        file.status = "PROCESSING"
        file.attempt_count += 1
        file.claimed_at = datetime.now(timezone.utc)

        claimed_files.append(
            ClaimedLakeFile(
                id=file.id,
                file_path=file.file_path,
                source_name=file.source_name,
                entity_name=file.entity_name,
            )
        )

    return claimed_files


async def load_acenda_lake_files(
    *,
    entity_name: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    total_loaded = 0
    total_skipped = 0
    failed_files: list[dict[str, Any]] = []

    # Step 1: claim files in a short transaction.
    async with async_session() as session:
        async with session.begin():
            claimed_files = await claim_lake_files(
                session,
                source_name="acenda",
                entity_name=entity_name,
                limit=limit,
            )

    # Step 2: process each claimed file independently.
    for lake_file in claimed_files:
        try:
            path = Path(lake_file.file_path)

            with path.open("r", encoding="utf-8") as f:
                file_data = json.load(f)

            records = extract_json_records(
                file_data,
                path=path,
                expected_entity_name=lake_file.entity_name,
            )

            payload_type = _acenda_payload_type_from_entity(lake_file.entity_name)

            async with async_session() as session:
                async with session.begin():
                    result = await load_acenda_records(
                        session=session,
                        records=records,
                        payload_type=payload_type,
                    )

                    db_file = await session.get(
                        DataLakeFile,
                        lake_file.id,
                        with_for_update=True,
                    )

                    if db_file is None:
                        raise RuntimeError(
                            f"DataLakeFile id={lake_file.id} disappeared"
                        )

                    failed_count = len(result["failed"])
                    loaded_count = result["loaded"]
                    skipped_count = result["skipped"]
                    record_count = len(records)

                    db_file.processed_at = datetime.now(timezone.utc)
                    db_file.loaded_count = loaded_count
                    db_file.skipped_count = skipped_count
                    db_file.failed_count = failed_count

                    total_loaded += loaded_count
                    total_skipped += skipped_count

                    if record_count == 0:
                        db_file.status = "EMPTY"
                        db_file.last_error = None

                    elif failed_count == record_count:
                        db_file.status = "FAILED"
                        db_file.last_error = json.dumps(result["failed"])[:5000]

                    elif skipped_count == record_count:
                        db_file.status = "SKIPPED"

                    elif failed_count > 0:
                        db_file.status = "PARTIAL"
                        db_file.last_error = json.dumps(result["failed"])[:5000]

                    else:
                        db_file.status = "LOADED"
                        db_file.last_error = None

        except Exception as exc:
            logger.exception(
                "Failed to load Acenda lake file id=%s path=%s",
                lake_file.id,
                lake_file.file_path,
            )

            failed_files.append(
                {
                    "file_id": lake_file.id,
                    "file_path": lake_file.file_path,
                    "error": str(exc),
                }
            )

            async with async_session() as session:
                async with session.begin():
                    db_file = await session.get(
                        DataLakeFile,
                        lake_file.id,
                        with_for_update=True,
                    )

                    if db_file is not None:
                        db_file.status = "FAILED"
                        db_file.last_error = str(exc)

    return {
        "claimed": len(claimed_files),
        "loaded": total_loaded,
        "skipped": total_skipped,
        "failed_files": failed_files,
    }


async def load_acenda_records(
    session: AsyncSession,
    records: list[dict[str, Any]],
    payload_type: PayloadType,
) -> dict[str, Any]:
    mapper = AcendaPayloadMapper()

    loaded = 0
    skipped = 0
    failed: list[dict[str, Any]] = []

    for raw_record in records:
        record_id = raw_record.get("id")

        try:
            if payload_type == "order":
                data = mapper.map_acenda_order(data=raw_record)
                model = AcendaOrderHeaders

            elif payload_type == "ship_advice":
                data = mapper.map_ship_advice_header(data=raw_record)
                model = AcendaShipAdviceHeaders

            else:
                raise ValueError(f"Unsupported Acenda payload type: {payload_type}")

            async with session.begin_nested():
                existing_updated_at = await session.scalar(
                    select(model.updated_at).where(model.id == data.id)
                )

                if existing_updated_at and data.updated_at <= existing_updated_at:
                    skipped += 1
                    continue

                await session.merge(data)

            loaded += 1

        except Exception as exc:
            logger.exception(
                "Failed to load Acenda %s id=%s",
                payload_type,
                record_id,
            )

            failed.append(
                {
                    "id": record_id,
                    "error": str(exc),
                }
            )

            continue

    return {
        "loaded": loaded,
        "skipped": skipped,
        "failed": failed,
    }


def extract_json_records(
    payload: Any, *, path: Path, expected_entity_name: str | None = None
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError(f"Expected wrapped lake JSON object in {path}")

    metadata = payload.get("metadata")
    records = payload.get("payload")

    if not isinstance(metadata, dict):
        raise ValueError(f"Missing or invalid metadata in {path}")

    if expected_entity_name and metadata.get("entity_name") != expected_entity_name:
        raise ValueError(
            f"Entity mismatch in {path}: "
            f"manifest={expected_entity_name}, file={metadata.get('entity_name')}"
        )

    if not isinstance(records, list):
        raise ValueError(f"Expected payload list in {path}")

    if any(not isinstance(record, dict) for record in records):
        raise ValueError(f"Payload contains non-object records in {path}")

    return records


class AcendaPayloadMapper:

    def map_acenda_order(self, data: dict[str, Any]) -> AcendaOrderHeaders:
        ship = data.get("shipping_information") or {}
        bill = data.get("billing_information") or {}

        order = AcendaOrderHeaders(
            id=as_int(data.get("id")),
            created_at=parse_dt(data.get("created_at")),
            created_by=as_str(data.get("created_by")),
            updated_at=parse_dt(data.get("updated_at")),
            updated_by=as_str(data.get("updated_by")),
            fields=data.get("fields") or {},
            ordered_at=parse_dt(data.get("ordered_at")),
            order_number=as_int(data.get("order_number")),
            status=as_str(data.get("status")),
            purchase_order=as_str(data.get("purchase_order")),
            external_order_id=as_str(data.get("external_order_id")),
            sales_channel_id=as_int(data.get("sales_channel_id")),
            sales_channel_name=as_str(data.get("sales_channel_name")),
            sales_channel_type=as_str(data.get("sales_channel_type")),
            sales_channel_subtype=as_str(data.get("sales_channel_subtype")),
            sales_channel_country=as_str(data.get("sales_channel_country")),
            send_email=bool(data.get("send_email", False)),
            create_routings=bool(data.get("create_routings", False)),
            shipping_method=as_str(data.get("shipping_method")),
            shipping_code=data.get("shipping_code"),
            # shipping_information.*
            ship_first_name=as_str(ship.get("first_name")),
            ship_last_name=as_str(ship.get("last_name")),
            ship_company=as_str(ship.get("company")),
            ship_address_1=as_str(ship.get("address_1")),
            ship_address_2=as_str(ship.get("address_2")),
            ship_city=as_str(ship.get("city")),
            ship_state=as_str(ship.get("state")),
            ship_postal_code=as_str(ship.get("postal_code")),
            ship_country=as_str(ship.get("country")),
            ship_email=as_str(ship.get("email")),
            ship_phone_number=as_str(ship.get("phone_number")),
            # billing_information.*
            bill_first_name=as_str(bill.get("first_name")),
            bill_last_name=as_str(bill.get("last_name")),
            bill_company=as_str(bill.get("company")),
            bill_address_1=as_str(bill.get("address_1")),
            bill_address_2=as_str(bill.get("address_2")),
            bill_city=as_str(bill.get("city")),
            bill_state=as_str(bill.get("state")),
            bill_postal_code=as_str(bill.get("postal_code")),
            bill_country=as_str(bill.get("country")),
            bill_email=as_str(bill.get("email")),
            bill_phone_number=as_str(bill.get("phone_number")),
            item_tax=as_float(data.get("item_tax")),
            ship_tax=as_float(data.get("ship_tax")),
            shipping=as_float(data.get("shipping")),
            total_item_discount=as_float(data.get("total_item_discount")),
            total_shipping_discount=as_float(data.get("total_shipping_discount")),
            subtotal=as_float(data.get("subtotal")),
            total=as_float(data.get("total")),
            item_count=as_int(data.get("item_count")),
            line_count=as_int(data.get("line_count")),
            tax_total=as_float(data.get("tax_total")),
            requested_ship_date=parse_dt(data.get("requested_ship_date")),
            requested_delivery_date=parse_dt(data.get("requested_delivery_date")),
        )

        order.items = [
            self.map_acenda_order_item(item) for item in data.get("order_item", [])
        ]

        order.returns = [self.map_acenda_return(ret) for ret in data.get("returns", [])]

        return order

    def map_acenda_order_item(self, data: dict[str, Any]) -> AcendaOrderItems:
        item = AcendaOrderItems(
            id=as_int(data.get("id")),
            created_at=parse_dt(data.get("created_at")),
            created_by=as_str(data.get("created_by")),
            updated_at=parse_dt(data.get("updated_at")),
            updated_by=as_str(data.get("updated_by")),
            order_id=as_int(data.get("order_id")),
            line_id=as_str(data.get("line_id")),
            subscription_id=as_int(data.get("subscription_id")),
            external_sku=as_str(data.get("external_sku")),
            product_id=as_int(data.get("product_id")),
            product_name=as_str(data.get("product_name")),
            sku=as_str(data.get("sku")),
            upc=as_str(data.get("upc")),
            unit_price=as_float(data.get("unit_price")),
            gift_message_price=as_float(data.get("gift_message_price")),
            gift_message_tax_price=as_float(data.get("gift_message_tax_price")),
            total_customization_price=as_float(data.get("total_customization_price")),
            total_customization_tax_price=as_float(
                data.get("total_customization_tax_price")
            ),
            total_shipping_price=as_float(data.get("total_shipping_price")),
            total_shipping_tax_price=as_float(data.get("total_shipping_tax_price")),
            total_handling_price=as_float(data.get("total_handling_price")),
            total_item_tax=as_float(data.get("total_item_tax")),
            total_tax_price=as_float(data.get("total_tax_price")),
            total_price=as_float(data.get("total_price")),
            other_fees=as_float(data.get("other_fees")),
            tax_rate=as_float(data.get("tax_rate")),
            total_item_discount=as_float(data.get("total_item_discount")),
            total_shipping_discount=as_float(data.get("total_shipping_discount")),
            total_gift_option_price=as_float(data.get("total_gift_option_price")),
            total_gift_option_tax_price=as_float(
                data.get("total_gift_option_tax_price")
            ),
            expected_shipping_date=parse_dt(data.get("expected_shipping_date")),
            expected_delivery_date=parse_dt(data.get("expected_delivery_date")),
            shipping_method=as_str(data.get("shipping_method")),
            external_warehouse_id=as_str(data.get("external_warehouse_id")),
            two_day_shipping=bool(data.get("two_day_shipping", False)),
            status=as_str(data.get("status")),
            quantity=as_int(data.get("quantity")),
            quantity_fulfilled=as_int(data.get("quantity_fulfilled")),
            quantity_cancelled=as_int(data.get("quantity_canceled")),
            quantity_routed=as_int(data.get("quantity_routed")),
        )

        item.discounts = [
            self.map_acenda_discount(discount, order_item_id=item.id)
            for discount in data.get("discounts", [])
        ]

        item.kit_items = [
            self.map_acenda_kit_item(kit_item, order_item_id=item.id)
            for kit_item in data.get("kit_items", [])
        ]

        return item

    def map_acenda_discount(
        self,
        data: dict[str, Any],
        *,
        order_item_id: int,
    ) -> AcendaOrderLineDiscounts:
        return AcendaOrderLineDiscounts(
            id=as_int(data.get("id")),
            created_at=parse_dt(data.get("created_at")),
            created_by=as_str(data.get("created_by")),
            updated_at=parse_dt(data.get("updated_at")),
            updated_by=as_str(data.get("updated_by")),
            fields=data.get("fields") or {},
            order_item_id=as_int(
                data.get("order_item_id") or data.get("order_item") or order_item_id
            ),
            promotion_code=as_str(data.get("promotion_code")),
            promotion_text=as_str(data.get("promotion_text")),
            affects=as_str(data.get("affects")),
            price=as_float(data.get("price")),
        )

    def map_acenda_kit_item(
        self,
        data: dict[str, Any],
        *,
        order_item_id: int,
    ) -> AcendaOrderLineKitItems:
        return AcendaOrderLineKitItems(
            id=as_int(data.get("id")),
            created_at=parse_dt(data.get("created_at")),
            created_by=as_str(data.get("created_by")),
            updated_at=parse_dt(data.get("updated_at")),
            updated_by=as_str(data.get("updated_by")),
            fields=data.get("fields") or {},
            order_item_id=as_int(data.get("order_item_id") or order_item_id),
            product_id=as_int(data.get("product_id")),
            sku=as_str(data.get("sku")),
            quantity=as_int(data.get("quantity")),
        )

    def map_acenda_return(self, data: dict[str, Any]) -> AcendaOrderReturns:
        return AcendaOrderReturns(
            id=as_int(data.get("id")),
            created_at=parse_dt(data.get("created_at")),
            created_by=as_str(data.get("created_by")),
            updated_at=parse_dt(data.get("updated_at")),
            updated_by=as_str(data.get("updated_by")),
            fields=data.get("fields") or {},
            order_id=as_int(data.get("order_id")),
            order_item_id=as_int(data.get("order_item_id")),
            quantity=as_int(data.get("quantity")),
            rma=as_str(data.get("rma")),
            license_plate_number=as_str(data.get("license_plate_number")),
            reason=as_str(data.get("reason")),
            status=as_str(data.get("status")),
            restock_inventory=bool(data.get("restock_inventory", False)),
            return_required=bool(data.get("return_required", False)),
            advance_refund=bool(data.get("advance_refund", False)),
            method=as_str(data.get("method")),
            carrier=as_str(data.get("carrier")),
            return_tracking=data.get("return_tracking") or [],
        )

    ### Ship Advice ###

    def map_ship_advice_header(self, data: dict[str, Any]) -> AcendaShipAdviceHeaders:
        delivery = data.get("delivery_info") or {}

        advice = AcendaShipAdviceHeaders(
            id=as_int(data.get("id")),
            created_at=parse_dt(data.get("created_at")),
            updated_at=parse_dt(data.get("updated_at")),
            fields=data.get("fields") or {},
            order_id=as_int(data.get("order_id")),
            order_routing_status=as_str(data.get("order_routing_status")),
            fulfillment_provider_id=as_int(data.get("fulfillment_provider_id")),
            warehouse_id=as_int(data.get("warehouse_id")),
            delivery_info_first_name=as_str(delivery.get("first_name")),
            delivery_info_last_name=as_str(delivery.get("last_name")),
            delivery_info_company=as_str(delivery.get("company")),
            delivery_info_address_1=as_str(delivery.get("address_1")),
            delivery_info_address_2=as_str(delivery.get("address_2")),
            delivery_info_city=as_str(delivery.get("city")),
            delivery_info_state=as_str(delivery.get("state")),
            delivery_info_postal_code=as_str(delivery.get("postal_code")),
            delivery_info_country=as_str(delivery.get("country")),
            delivery_info_email=as_str(delivery.get("email")),
            delivery_info_phone_number=as_str(delivery.get("phone_number")),
        )

        advice.ship_advice_items = [
            self.map_ship_advice_item(item) for item in data.get("items", [])
        ]

        return advice

    def map_ship_advice_item(self, data: dict[str, Any]) -> AcendaShipAdviceItems:
        return AcendaShipAdviceItems(
            id=as_int(data.get("id")),
            inventory_detail_id=as_int(data.get("inventory_detail_id")),
            order_item_id=as_int(data.get("order_item_id")),
            ship_advice_id=as_int(data.get("ship_advice_id")),
            quantity_rerouted=as_int(data.get("quantity_rerouted")),
        )


###---------------------###


"""
Load data from raw files to table
    - Define fields
    - Use . separators for nesting, _ for naming


METADATA FIELDS:
    - Ingestion ID
    -

NEW ORDERS

UPDATED ORDERS

-- HEADERS --
Fields Array:

    {
        "packing_slip_url": null,
        "shopify_source": "amazon"
    }
    {
        "packing_slip_url": null,
        "shopify_source": "web"
    }

Returns Array:

    {
        "id": 5589,
        "created_at": "2026-05-24T22:17:56.697Z",
        "created_by": "service-account-channel_integration_system",
        "updated_at": "2026-05-24T22:17:56.697Z",
        "updated_by": "service-account-channel_integration_system",
        "fields": {},
        "order_id": 50886,
        "order_item_id": 57730,
        "quantity": 1,
        "rma": "ec632608-e3a1-47be-8ee1-7e6818aa19bc-4749039429-1",
        "license_plate_number": "",
        "reason": "RETURN_CM_QUALITY",
        "status": "pending",
        "restock_inventory": false,
        "return_required": true,
        "advance_refund": false,
        "method": "RETURN_METHOD_BY_MAIL",
        "carrier": "UPS",
        "return_tracking": [
            {
                "number": "1Z1804F10320567077",
                "url": "https://www.ups.com/us/en/Home.page"
            }
        ]
    }


-- Order Items --

Discounts Array:

order_item.discounts
    {
        "id": 65315,
        "created_at": "2026-06-27T02:01:31.759Z",
        "created_by": "service-account-channel_integration_system",
        "updated_at": "2026-06-27T02:01:31.759Z",
        "updated_by": "service-account-channel_integration_system",
        "fields": {},
        "order_item": 61204,
        "promotion_code": "RedCard",
        "promotion_text": "Target Circle Card 5%",
        "affects": "items",
        "price": 12
    }



Kit Items Array:
    [
    {
        "id": 1389,
        "created_at": "2026-06-29T17:07:18.341Z",
        "created_by": "service-account-channel_integration_system",
        "updated_at": "2026-06-29T17:07:21.424Z",
        "updated_by": "service-account-channel_integration_system",
        "fields": {},
        "order_item": 61444,
        "product_id": 20,
        "sku": "BH50168",
        "quantity": 1
    },
    {
        "id": 1390,
        "created_at": "2026-06-29T17:07:18.341Z",
        "created_by": "service-account-channel_integration_system",
        "updated_at": "2026-06-29T17:07:21.424Z",
        "updated_by": "service-account-channel_integration_system",
        "fields": {},
        "order_item": 61444,
        "product_id": 206,
        "sku": "BH50176",
        "quantity": 1
    }
]



"""

# relevant_new_data = {
#     "id": 53843,
#     "created_at": "2026-06-25T20:31:10.877Z",  ##created_at = datetime.fromisoformat("2026-06-25T20:31:10.877Z")
#     "created_by": "service-account-channel_integration_system",
#     "updated_at": "2026-06-26T14:03:35.968Z",
#     "updated_by": "service-account-channel_integration_system",
#     "fields": {},
#     "ordered_at": "2026-06-25T19:57:32Z",
#     "order_number": 10053843,
#     "status": "shipped",
#     "purchase_order": "912003363206641",
#     "external_order_id": "912003363206641-8786676962",
#     "sales_channel_id": 1,
#     "sales_channel_name": "Target Plus US Marketplace",
#     "sales_channel_type": "target_pus",
#     "sales_channel_subtype": "3P",
#     "sales_channel_country": "US",
#     "send_email": false,
#     "create_routings": true,
#     "shipping_method": "GROUND",
#     "shipping_code": null,
#     "shipping_information": {
#         # "id": 53835,
#         "first_name": "Nancy",
#         "last_name": "Lewis",
#         "company": "",
#         "address_1": "3938 Fox Glen Dr",
#         "address_2": "",
#         "city": "Ann Arbor",
#         "state": "MI",
#         "postal_code": "48108-5011",
#         # "county": "",
#         "country": "US",
#         "email": "no-reply@acenda.com",
#         "phone_number": "(734) 276-1732",
#         # "location": {"type": "Point", "coordinates": [42.2328, -83.7015]},
#         # "order_id": 53843,
#     },
#     "billing_information": {
#         # "id": 53835,
#         "first_name": "Nancy",
#         "last_name": "Lewis",
#         "company": "",
#         "address_1": "3938 Fox Glen Dr",
#         "address_2": "",
#         "city": "Ann Arbor",
#         "state": "MI",
#         "postal_code": "48108-5011",
#         # "county": "",
#         "country": "US",
#         "email": "no-reply@acenda.com",
#         "phone_number": "(734) 276-1732",
#         # "location": {"type": "Point", "coordinates": [42.2328, -83.7015]},
#         # "order_id": 53843,
#     },
#     "item_tax": 0,
#     "ship_tax": 0,
#     "shipping": 0,
#     "total_item_discount": 0,
#     "total_shipping_discount": 0,
#     "subtotal": 162.49,
#     "total": 162.49,
#     "item_count": 1,
#     "line_count": 1,
#     "tax_total": 0,
#     "order_item": [
#         {
#             "id": 61092,
#             "created_at": "2026-06-25T20:31:10.893Z",
#             "created_by": "service-account-channel_integration_system",
#             "updated_at": "2026-06-26T14:03:35.968Z",
#             "updated_by": "service-account-channel_integration_system",
#             "fields": {},
#             "order_id": 53843,
#             "line_id": "2",
#             "subscription_id": 282,
#             "external_sku": "BH50195",
#             "product_id": 233,
#             "product_name": "All Season Premium Down Alternative Duvet Comforter Insert - King/Cal King | BOKSER HOME",
#             "sku": "BH50195",
#             "upc": "810045149837",
#             "ean": null,
#             "isbn": null,
#             "unit_price": 162.49,
#             "giftwrap": false,
#             "giftwrap_price": 0,
#             "giftwrap_tax_price": 0,
#             "gift_message": "",
#             "gift_message_price": 0,
#             "gift_message_tax_price": 0,
#             "total_customization_price": 0,
#             "total_customization_tax_price": 0,
#             "total_shipping_price": 0,
#             "total_shipping_tax_price": 0,
#             "total_handling_price": 0,
#             "total_item_tax": 0,
#             "total_tax_price": 0,
#             "total_item_price": 162.49,
#             "total_price": 162.49,
#             "other_fees": 0,
#             "tax_rate": 0,
#             "total_item_discount": 0,
#             "total_shipping_discount": 0,
#             "total_gift_option_price": 0,
#             "total_gift_option_tax_price": 0,
#             "expected_shipping_date": null,
#             "expected_delivery_date": null,
#             "shipping_method": null,
#             "external_warehouse_id": "qm9i1h",
#             "two_day_shipping": false,
#             "status": "fulfilled",
#             "quantity": 1,
#             "quantity_fulfilled": 1,
#             "quantity_canceled": 0,
#             "quantity_routed": 1,
#             "discounts": [],
#             "customization": [],
#             "kit_items": [],
#         }
#     ],
#     "requested_ship_date": "2026-06-26T23:00:00Z",
#     "requested_delivery_date": "2026-07-02T05:00:00Z",
#     "returns": [],
#     "payment": [
#         {
#             "id": 53834,
#             "created_at": "2026-06-25T20:31:10.91Z",
#             "created_by": "service-account-channel_integration_system",
#             "updated_at": "2026-06-25T20:31:10.923Z",
#             "updated_by": "service-account-channel_integration_system",
#             "fields": {},
#             "order_id": 53843,
#             "platform": "",
#             "status": "success",
#             "amount": 162.49,
#             "charged": 162.49,
#             "charged_last4": "",
#             "transactions": [
#                 {
#                     "id": 54155,
#                     "created_at": "2026-06-25T20:31:10.912Z",
#                     "created_by": "service-account-channel_integration_system",
#                     "updated_at": "2026-06-25T20:31:10.918Z",
#                     "updated_by": "service-account-channel_integration_system",
#                     "fields": {},
#                     "payment_id": 53834,
#                     "external_transaction_id": "",
#                     "type": "sale",
#                     "amount": 162.49,
#                     "reason": "",
#                     "transaction_items": [
#                         {
#                             "id": 61410,
#                             "created_at": "2026-06-25T20:31:10.915Z",
#                             "created_by": "service-account-channel_integration_system",
#                             "updated_at": "2026-06-25T20:31:10.915Z",
#                             "updated_by": "service-account-channel_integration_system",
#                             "fields": {},
#                             "transaction_id": 54155,
#                             "order_item_id": 61092,
#                             "unit_price": 162.49,
#                             "giftwrap_price": 0,
#                             "giftwrap_tax_price": 0,
#                             "gift_message_price": 0,
#                             "gift_message_tax_price": 0,
#                             "total_customization_price": 0,
#                             "total_customization_tax_price": 0,
#                             "total_shipping_price": 0,
#                             "total_shipping_tax_price": 0,
#                             "total_handling_price": 0,
#                             "total_item_tax": 0,
#                             "total_tax_price": 0,
#                             "total_item_price": 162.49,
#                             "total_price": 162.49,
#                             "other_fees": 0,
#                             "tax_rate": 0,
#                             "total_item_discount": 0,
#                             "total_shipping_discount": 0,
#                             "total_gift_option_price": 0,
#                             "total_gift_option_tax_price": 0,
#                             "total": 162.49,
#                             "quantity": 1,
#                         }
#                     ],
#                 }
#             ],
#         }
#     ],
#     "channel_order_status": null,
# }

# raw_new_data = {
#     "id": 53843,
#     "created_at": "2026-06-25T20:31:10.877Z",
#     "created_by": "service-account-channel_integration_system",
#     "updated_at": "2026-06-26T14:03:35.968Z",
#     "updated_by": "service-account-channel_integration_system",
#     "fields": {},
#     "ordered_at": "2026-06-25T19:57:32Z",
#     "order_number": 10053843,
#     "status": "shipped",
#     "purchase_order": "912003363206641",
#     "external_order_id": "912003363206641-8786676962",
#     "sales_channel_id": 1,
#     "sales_channel_name": "Target Plus US Marketplace",
#     "sales_channel_type": "target_pus",
#     "sales_channel_subtype": "3P",
#     "sales_channel_country": "US",
#     "send_email": false,
#     "create_routings": true,
#     "shipping_method": "GROUND",
#     "shipping_code": null,
#     "shipping_information": {
#         "id": 53835,
#         "first_name": "Nancy",
#         "last_name": "Lewis",
#         "company": "",
#         "address_1": "3938 Fox Glen Dr",
#         "address_2": "",
#         "city": "Ann Arbor",
#         "state": "MI",
#         "postal_code": "48108-5011",
#         "county": "",
#         "country": "US",
#         "email": "no-reply@acenda.com",
#         "phone_number": "(734) 276-1732",
#         "location": {"type": "Point", "coordinates": [42.2328, -83.7015]},
#         "order_id": 53843,
#     },
#     "billing_information": {
#         "id": 53835,
#         "first_name": "Nancy",
#         "last_name": "Lewis",
#         "company": "",
#         "address_1": "3938 Fox Glen Dr",
#         "address_2": "",
#         "city": "Ann Arbor",
#         "state": "MI",
#         "postal_code": "48108-5011",
#         "county": "",
#         "country": "US",
#         "email": "no-reply@acenda.com",
#         "phone_number": "(734) 276-1732",
#         "location": {"type": "Point", "coordinates": [42.2328, -83.7015]},
#         "order_id": 53843,
#     },
#     "item_tax": 0,
#     "ship_tax": 0,
#     "shipping": 0,
#     "total_item_discount": 0,
#     "total_shipping_discount": 0,
#     "subtotal": 162.49,
#     "total": 162.49,
#     "item_count": 1,
#     "line_count": 1,
#     "tax_total": 0,
#     "order_item": [
#         {
#             "id": 61092,
#             "created_at": "2026-06-25T20:31:10.893Z",
#             "created_by": "service-account-channel_integration_system",
#             "updated_at": "2026-06-26T14:03:35.968Z",
#             "updated_by": "service-account-channel_integration_system",
#             "fields": {},
#             "order_id": 53843,
#             "line_id": "2",
#             "subscription_id": 282,
#             "external_sku": "BH50195",
#             "product_id": 233,
#             "product_name": "All Season Premium Down Alternative Duvet Comforter Insert - King/Cal King | BOKSER HOME",
#             "sku": "BH50195",
#             "upc": "810045149837",
#             "ean": null,
#             "isbn": null,
#             "unit_price": 162.49,
#             "giftwrap": false,
#             "giftwrap_price": 0,
#             "giftwrap_tax_price": 0,
#             "gift_message": "",
#             "gift_message_price": 0,
#             "gift_message_tax_price": 0,
#             "total_customization_price": 0,
#             "total_customization_tax_price": 0,
#             "total_shipping_price": 0,
#             "total_shipping_tax_price": 0,
#             "total_handling_price": 0,
#             "total_item_tax": 0,
#             "total_tax_price": 0,
#             "total_item_price": 162.49,
#             "total_price": 162.49,
#             "other_fees": 0,
#             "tax_rate": 0,
#             "total_item_discount": 0,
#             "total_shipping_discount": 0,
#             "total_gift_option_price": 0,
#             "total_gift_option_tax_price": 0,
#             "expected_shipping_date": null,
#             "expected_delivery_date": null,
#             "shipping_method": null,
#             "external_warehouse_id": "qm9i1h",
#             "two_day_shipping": false,
#             "status": "fulfilled",
#             "quantity": 1,
#             "quantity_fulfilled": 1,
#             "quantity_canceled": 0,
#             "quantity_routed": 1,
#             "discounts": [],
#             "customization": [],
#             "kit_items": [],
#         }
#     ],
#     "requested_ship_date": "2026-06-26T23:00:00Z",
#     "requested_delivery_date": "2026-07-02T05:00:00Z",
#     "returns": [],
#     "payment": [
#         {
#             "id": 53834,
#             "created_at": "2026-06-25T20:31:10.91Z",
#             "created_by": "service-account-channel_integration_system",
#             "updated_at": "2026-06-25T20:31:10.923Z",
#             "updated_by": "service-account-channel_integration_system",
#             "fields": {},
#             "order_id": 53843,
#             "platform": "",
#             "status": "success",
#             "amount": 162.49,
#             "charged": 162.49,
#             "charged_last4": "",
#             "transactions": [
#                 {
#                     "id": 54155,
#                     "created_at": "2026-06-25T20:31:10.912Z",
#                     "created_by": "service-account-channel_integration_system",
#                     "updated_at": "2026-06-25T20:31:10.918Z",
#                     "updated_by": "service-account-channel_integration_system",
#                     "fields": {},
#                     "payment_id": 53834,
#                     "external_transaction_id": "",
#                     "type": "sale",
#                     "amount": 162.49,
#                     "reason": "",
#                     "transaction_items": [
#                         {
#                             "id": 61410,
#                             "created_at": "2026-06-25T20:31:10.915Z",
#                             "created_by": "service-account-channel_integration_system",
#                             "updated_at": "2026-06-25T20:31:10.915Z",
#                             "updated_by": "service-account-channel_integration_system",
#                             "fields": {},
#                             "transaction_id": 54155,
#                             "order_item_id": 61092,
#                             "unit_price": 162.49,
#                             "giftwrap_price": 0,
#                             "giftwrap_tax_price": 0,
#                             "gift_message_price": 0,
#                             "gift_message_tax_price": 0,
#                             "total_customization_price": 0,
#                             "total_customization_tax_price": 0,
#                             "total_shipping_price": 0,
#                             "total_shipping_tax_price": 0,
#                             "total_handling_price": 0,
#                             "total_item_tax": 0,
#                             "total_tax_price": 0,
#                             "total_item_price": 162.49,
#                             "total_price": 162.49,
#                             "other_fees": 0,
#                             "tax_rate": 0,
#                             "total_item_discount": 0,
#                             "total_shipping_discount": 0,
#                             "total_gift_option_price": 0,
#                             "total_gift_option_tax_price": 0,
#                             "total": 162.49,
#                             "quantity": 1,
#                         }
#                     ],
#                 }
#             ],
#         }
#     ],
#     "channel_order_status": null,
# }


# updated_data = {
#     "id": 53825,
#     "created_at": "2026-06-25T16:01:28.848Z",
#     "created_by": "service-account-channel_integration_system",
#     "updated_at": "2026-06-25T23:04:25.094Z",
#     "updated_by": "service-account-channel_integration_system",
#     "fields": {},
#     "ordered_at": "2026-06-25T15:15:25Z",
#     "order_number": 10053825,
#     "status": "shipped",
#     "purchase_order": "912003555805378",
#     "external_order_id": "912003555805378-8786551278",
#     "sales_channel_id": 1,
#     "sales_channel_name": "Target Plus US Marketplace",
#     "sales_channel_type": "target_pus",
#     "sales_channel_subtype": "3P",
#     "sales_channel_country": "US",
#     "send_email": false,
#     "create_routings": true,
#     "shipping_method": "GROUND",
#     "shipping_code": null,
#     "shipping_information": {
#         "id": 53817,
#         "first_name": "WEBSTER",
#         "last_name": "MARQUEZ",
#         "company": "",
#         "address_1": "6111 Vine Hill Rd",
#         "address_2": "",
#         "city": "Sebastopol",
#         "state": "CA",
#         "postal_code": "95472-2048",
#         "county": "",
#         "country": "US",
#         "email": "no-reply@acenda.com",
#         "phone_number": "(707) 968-7823",
#         "location": {"type": "Point", "coordinates": [38.3941, -122.8433]},
#         "order_id": 53825,
#     },
#     "billing_information": {
#         "id": 53817,
#         "first_name": "WEBSTER",
#         "last_name": "MARQUEZ",
#         "company": "",
#         "address_1": "6111 Vine Hill Rd",
#         "address_2": "",
#         "city": "Sebastopol",
#         "state": "CA",
#         "postal_code": "95472-2048",
#         "county": "",
#         "country": "US",
#         "email": "no-reply@acenda.com",
#         "phone_number": "(707) 968-7823",
#         "location": {"type": "Point", "coordinates": [38.3941, -122.8433]},
#         "order_id": 53825,
#     },
#     "item_tax": 0,
#     "ship_tax": 0,
#     "shipping": 5.99,
#     "total_item_discount": 0,
#     "total_shipping_discount": 5.99,
#     "subtotal": 39.99,
#     "total": 39.99,
#     "item_count": 1,
#     "line_count": 1,
#     "tax_total": 0,
#     "order_item": [
#         {
#             "id": 61071,
#             "created_at": "2026-06-25T16:01:28.866Z",
#             "created_by": "service-account-channel_integration_system",
#             "updated_at": "2026-06-25T23:04:25.094Z",
#             "updated_by": "service-account-channel_integration_system",
#             "fields": {},
#             "order_id": 53825,
#             "line_id": "1",
#             "subscription_id": 282,
#             "external_sku": "BH50001",
#             "product_id": 284,
#             "product_name": '26" x 26" Euro Down Alternative White Bed Pillow Insert | BOKSER HOME',
#             "sku": "BH50001",
#             "upc": "810045147895",
#             "ean": null,
#             "isbn": null,
#             "unit_price": 39.99,
#             "giftwrap": false,
#             "giftwrap_price": 0,
#             "giftwrap_tax_price": 0,
#             "gift_message": "",
#             "gift_message_price": 0,
#             "gift_message_tax_price": 0,
#             "total_customization_price": 0,
#             "total_customization_tax_price": 0,
#             "total_shipping_price": 5.99,
#             "total_shipping_tax_price": 0,
#             "total_handling_price": 0,
#             "total_item_tax": 0,
#             "total_tax_price": 0,
#             "total_item_price": 39.99,
#             "total_price": 39.99,
#             "other_fees": 0,
#             "tax_rate": 0,
#             "total_item_discount": 0,
#             "total_shipping_discount": 5.99,
#             "total_gift_option_price": 0,
#             "total_gift_option_tax_price": 0,
#             "expected_shipping_date": null,
#             "expected_delivery_date": null,
#             "shipping_method": null,
#             "external_warehouse_id": "qm9i1h",
#             "two_day_shipping": false,
#             "status": "fulfilled",
#             "quantity": 1,
#             "quantity_fulfilled": 1,
#             "quantity_canceled": 0,
#             "quantity_routed": 1,
#             "discounts": [
#                 {
#                     "id": 65232,
#                     "created_at": "2026-06-25T16:01:28.87Z",
#                     "created_by": "service-account-channel_integration_system",
#                     "updated_at": "2026-06-25T16:01:28.87Z",
#                     "updated_by": "service-account-channel_integration_system",
#                     "fields": {},
#                     "order_item": 61071,
#                     "promotion_code": "RedCard",
#                     "promotion_text": "",
#                     "affects": "shipping",
#                     "price": 5.99,
#                 }
#             ],
#             "customization": [],
#             "kit_items": [],
#         }
#     ],
#     "requested_ship_date": "2026-06-25T23:00:00Z",
#     "requested_delivery_date": "2026-07-01T05:00:00Z",
#     "returns": [],
#     "payment": [
#         {
#             "id": 53816,
#             "created_at": "2026-06-25T16:01:28.892Z",
#             "created_by": "service-account-channel_integration_system",
#             "updated_at": "2026-06-25T16:01:28.906Z",
#             "updated_by": "service-account-channel_integration_system",
#             "fields": {},
#             "order_id": 53825,
#             "platform": "",
#             "status": "success",
#             "amount": 39.99,
#             "charged": 39.99,
#             "charged_last4": "",
#             "transactions": [
#                 {
#                     "id": 54137,
#                     "created_at": "2026-06-25T16:01:28.895Z",
#                     "created_by": "service-account-channel_integration_system",
#                     "updated_at": "2026-06-25T16:01:28.901Z",
#                     "updated_by": "service-account-channel_integration_system",
#                     "fields": {},
#                     "payment_id": 53816,
#                     "external_transaction_id": "",
#                     "type": "sale",
#                     "amount": 39.99,
#                     "reason": "",
#                     "transaction_items": [
#                         {
#                             "id": 61389,
#                             "created_at": "2026-06-25T16:01:28.898Z",
#                             "created_by": "service-account-channel_integration_system",
#                             "updated_at": "2026-06-25T16:01:28.898Z",
#                             "updated_by": "service-account-channel_integration_system",
#                             "fields": {},
#                             "transaction_id": 54137,
#                             "order_item_id": 61071,
#                             "unit_price": 39.99,
#                             "giftwrap_price": 0,
#                             "giftwrap_tax_price": 0,
#                             "gift_message_price": 0,
#                             "gift_message_tax_price": 0,
#                             "total_customization_price": 0,
#                             "total_customization_tax_price": 0,
#                             "total_shipping_price": 5.99,
#                             "total_shipping_tax_price": 0,
#                             "total_handling_price": 0,
#                             "total_item_tax": 0,
#                             "total_tax_price": 0,
#                             "total_item_price": 39.99,
#                             "total_price": 39.99,
#                             "other_fees": 0,
#                             "tax_rate": 0,
#                             "total_item_discount": 0,
#                             "total_shipping_discount": 5.99,
#                             "total_gift_option_price": 0,
#                             "total_gift_option_tax_price": 0,
#                             "total": 39.99,
#                             "quantity": 1,
#                         }
#                     ],
#                 }
#             ],
#         }
#     ],
#     "channel_order_status": null,
# }


# ship_advice_53854 = [
#     {
#         "id": 53750,
#         "created_at": "2026-06-25T23:01:35.871Z",
#         "created_by": "service-account-channel_integration_system",
#         "updated_at": "2026-06-26T14:03:36.992Z",
#         "updated_by": "service-account-channel_integration_system",
#         "fields": {},
#         "order_id": 53854,
#         "purchase_order": "912003556510778",
#         "status": "shipped",
#         "external_order_id": "912003556510778-8767759331",
#         "sales_channel_id": 1,
#         "sales_channel_name": "Target Plus US Marketplace",
#         "sales_channel_type": "target_pus",
#         "sales_channel_subtype": "3P",
#         "sales_channel_country": "US",
#         "order_routing_status": null,
#         "fulfillment_provider_id": 1,
#         "warehouse_id": 1,
#         "shipping_method": "GROUND",
#         "shipping_code": null,
#         "delivery_information": {
#             "id": 53750,
#             "first_name": "Lynne",
#             "last_name": "Hed",
#             "company": "",
#             "address_1": "1077 Pond Curv",
#             "address_2": "",
#             "city": "Waconia",
#             "state": "MN",
#             "postal_code": "55387-3100",
#             "county": "",
#             "country": "US",
#             "email": "no-reply@acenda.com",
#             "phone_number": "(651) 219-1212",
#             "location": {"type": "Point", "coordinates": [44.851, -93.7784]},
#             "ship_advice_id": 53750,
#         },
#         "requested_ship_date": "2026-06-26T23:00:00Z",
#         "requested_delivery_date": "2026-07-02T05:00:00Z",
#         "ship_advice_item": [
#             {
#                 "id": 61751,
#                 "created_at": "2026-06-25T23:01:35.876Z",
#                 "created_by": "service-account-channel_integration_system",
#                 "updated_at": "2026-06-26T14:03:36.992Z",
#                 "updated_by": "service-account-channel_integration_system",
#                 "fields": {},
#                 "inventory_detail_id": 2317,
#                 "order_item_id": 61104,
#                 "ship_advice_id": 53750,
#                 "line_id": "1",
#                 "subscription_id": 282,
#                 "external_sku": "BH50194",
#                 "product_id": 232,
#                 "product_name": "All Season Premium Down Alternative Duvet Comforter Insert - Full/Queen | BOKSER HOME",
#                 "sku": "BH50194",
#                 "upc": "810045149820",
#                 "ean": null,
#                 "isbn": null,
#                 "unit_price": 154.04,
#                 "giftwrap": false,
#                 "giftwrap_price": 0,
#                 "giftwrap_tax_price": 0,
#                 "gift_message": "",
#                 "gift_message_price": 0,
#                 "gift_message_tax_price": 0,
#                 "total_customization_price": 0,
#                 "total_customization_tax_price": 0,
#                 "total_shipping_price": 2.99,
#                 "total_shipping_tax_price": 0,
#                 "total_handling_price": 0,
#                 "total_item_tax": 0,
#                 "total_tax_price": 0,
#                 "total_item_price": 146.34,
#                 "total_price": 146.34,
#                 "other_fees": 0,
#                 "tax_rate": 0,
#                 "total_item_discount": 7.7,
#                 "total_shipping_discount": 2.99,
#                 "total_gift_option_price": 0,
#                 "total_gift_option_tax_price": 0,
#                 "expected_shipping_date": null,
#                 "expected_delivery_date": null,
#                 "shipping_method": null,
#                 "external_warehouse_id": "qm9i1h",
#                 "two_day_shipping": false,
#                 "status": "fulfilled",
#                 "quantity": 1,
#                 "quantity_fulfilled": 1,
#                 "quantity_canceled": 0,
#                 "quantity_rerouted": 0,
#                 "discounts": [
#                     {
#                         "id": 65250,
#                         "created_at": "2026-06-25T23:01:35.879Z",
#                         "created_by": "service-account-channel_integration_system",
#                         "updated_at": "2026-06-25T23:01:35.879Z",
#                         "updated_by": "service-account-channel_integration_system",
#                         "fields": {},
#                         "ship_advice_item": 61751,
#                         "promotion_code": "RedCard",
#                         "promotion_text": "Target Circle Card free shipping",
#                         "affects": "shipping",
#                         "price": 2.99,
#                     },
#                     {
#                         "id": 65251,
#                         "created_at": "2026-06-25T23:01:35.879Z",
#                         "created_by": "service-account-channel_integration_system",
#                         "updated_at": "2026-06-25T23:01:35.879Z",
#                         "updated_by": "service-account-channel_integration_system",
#                         "fields": {},
#                         "ship_advice_item": 61751,
#                         "promotion_code": "RedCard",
#                         "promotion_text": "Target Circle Card 5%",
#                         "affects": "items",
#                         "price": 7.7,
#                     },
#                 ],
#                 "customization": [],
#                 "kit_items": [],
#             }
#         ],
#     }
# ]

# order_52664 = {
#     "id": 53854,
#     "created_at": "2026-06-25T23:01:35.842Z",
#     "created_by": "service-account-channel_integration_system",
#     "updated_at": "2026-06-26T14:03:36.992Z",
#     "updated_by": "service-account-channel_integration_system",
#     "fields": {},
#     "ordered_at": "2026-06-25T22:19:02Z",
#     "order_number": 10053854,
#     "status": "shipped",
#     "purchase_order": "912003556510778",
#     "external_order_id": "912003556510778-8767759331",
#     "sales_channel_id": 1,
#     "sales_channel_name": "Target Plus US Marketplace",
#     "sales_channel_type": "target_pus",
#     "sales_channel_subtype": "3P",
#     "sales_channel_country": "US",
#     "send_email": false,
#     "create_routings": true,
#     "shipping_method": "GROUND",
#     "shipping_code": null,
#     "shipping_information": {
#         "id": 53846,
#         "first_name": "Lynne",
#         "last_name": "Hed",
#         "company": "",
#         "address_1": "1077 Pond Curv",
#         "address_2": "",
#         "city": "Waconia",
#         "state": "MN",
#         "postal_code": "55387-3100",
#         "county": "",
#         "country": "US",
#         "email": "no-reply@acenda.com",
#         "phone_number": "(651) 219-1212",
#         "location": {"type": "Point", "coordinates": [44.851, -93.7784]},
#         "order_id": 53854,
#     },
#     "billing_information": {
#         "id": 53846,
#         "first_name": "Lynne",
#         "last_name": "Hed",
#         "company": "",
#         "address_1": "1077 Pond Curv",
#         "address_2": "",
#         "city": "Waconia",
#         "state": "MN",
#         "postal_code": "55387-3100",
#         "county": "",
#         "country": "US",
#         "email": "no-reply@acenda.com",
#         "phone_number": "(651) 219-1212",
#         "location": {"type": "Point", "coordinates": [44.851, -93.7784]},
#         "order_id": 53854,
#     },
#     "item_tax": 0,
#     "ship_tax": 0,
#     "shipping": 2.99,
#     "total_item_discount": 7.7,
#     "total_shipping_discount": 2.99,
#     "subtotal": 154.04,
#     "total": 146.34,
#     "item_count": 1,
#     "line_count": 1,
#     "tax_total": 0,
#     "order_item": [
#         {
#             "id": 61104,
#             "created_at": "2026-06-25T23:01:35.848Z",
#             "created_by": "service-account-channel_integration_system",
#             "updated_at": "2026-06-26T14:03:36.992Z",
#             "updated_by": "service-account-channel_integration_system",
#             "fields": {},
#             "order_id": 53854,
#             "line_id": "1",
#             "subscription_id": 282,
#             "external_sku": "BH50194",
#             "product_id": 232,
#             "product_name": "All Season Premium Down Alternative Duvet Comforter Insert - Full/Queen | BOKSER HOME",
#             "sku": "BH50194",
#             "upc": "810045149820",
#             "ean": null,
#             "isbn": null,
#             "unit_price": 154.04,
#             "giftwrap": false,
#             "giftwrap_price": 0,
#             "giftwrap_tax_price": 0,
#             "gift_message": "",
#             "gift_message_price": 0,
#             "gift_message_tax_price": 0,
#             "total_customization_price": 0,
#             "total_customization_tax_price": 0,
#             "total_shipping_price": 2.99,
#             "total_shipping_tax_price": 0,
#             "total_handling_price": 0,
#             "total_item_tax": 0,
#             "total_tax_price": 0,
#             "total_item_price": 146.34,
#             "total_price": 146.34,
#             "other_fees": 0,
#             "tax_rate": 0,
#             "total_item_discount": 7.7,
#             "total_shipping_discount": 2.99,
#             "total_gift_option_price": 0,
#             "total_gift_option_tax_price": 0,
#             "expected_shipping_date": null,
#             "expected_delivery_date": null,
#             "shipping_method": null,
#             "external_warehouse_id": "qm9i1h",
#             "two_day_shipping": false,
#             "status": "fulfilled",
#             "quantity": 1,
#             "quantity_fulfilled": 1,
#             "quantity_canceled": 0,
#             "quantity_routed": 1,
#             "discounts": [
#                 {
#                     "id": 65248,
#                     "created_at": "2026-06-25T23:01:35.85Z",
#                     "created_by": "service-account-channel_integration_system",
#                     "updated_at": "2026-06-25T23:01:35.85Z",
#                     "updated_by": "service-account-channel_integration_system",
#                     "fields": {},
#                     "order_item": 61104,
#                     "promotion_code": "RedCard",
#                     "promotion_text": "Target Circle Card free shipping",
#                     "affects": "shipping",
#                     "price": 2.99,
#                 },
#                 {
#                     "id": 65249,
#                     "created_at": "2026-06-25T23:01:35.85Z",
#                     "created_by": "service-account-channel_integration_system",
#                     "updated_at": "2026-06-25T23:01:35.85Z",
#                     "updated_by": "service-account-channel_integration_system",
#                     "fields": {},
#                     "order_item": 61104,
#                     "promotion_code": "RedCard",
#                     "promotion_text": "Target Circle Card 5%",
#                     "affects": "items",
#                     "price": 7.7,
#                 },
#             ],
#             "customization": [],
#             "kit_items": [],
#         }
#     ],
#     "requested_ship_date": "2026-06-26T23:00:00Z",
#     "requested_delivery_date": "2026-07-02T05:00:00Z",
#     "returns": [],
#     "payment": [
#         {
#             "id": 53845,
#             "created_at": "2026-06-25T23:01:35.855Z",
#             "created_by": "service-account-channel_integration_system",
#             "updated_at": "2026-06-25T23:01:35.86Z",
#             "updated_by": "service-account-channel_integration_system",
#             "fields": {},
#             "order_id": 53854,
#             "platform": "",
#             "status": "success",
#             "amount": 146.34,
#             "charged": 146.34,
#             "charged_last4": "",
#             "transactions": [
#                 {
#                     "id": 54166,
#                     "created_at": "2026-06-25T23:01:35.856Z",
#                     "created_by": "service-account-channel_integration_system",
#                     "updated_at": "2026-06-25T23:01:35.858Z",
#                     "updated_by": "service-account-channel_integration_system",
#                     "fields": {},
#                     "payment_id": 53845,
#                     "external_transaction_id": "",
#                     "type": "sale",
#                     "amount": 146.34,
#                     "reason": "",
#                     "transaction_items": [
#                         {
#                             "id": 61422,
#                             "created_at": "2026-06-25T23:01:35.857Z",
#                             "created_by": "service-account-channel_integration_system",
#                             "updated_at": "2026-06-25T23:01:35.857Z",
#                             "updated_by": "service-account-channel_integration_system",
#                             "fields": {},
#                             "transaction_id": 54166,
#                             "order_item_id": 61104,
#                             "unit_price": 154.04,
#                             "giftwrap_price": 0,
#                             "giftwrap_tax_price": 0,
#                             "gift_message_price": 0,
#                             "gift_message_tax_price": 0,
#                             "total_customization_price": 0,
#                             "total_customization_tax_price": 0,
#                             "total_shipping_price": 2.99,
#                             "total_shipping_tax_price": 0,
#                             "total_handling_price": 0,
#                             "total_item_tax": 0,
#                             "total_tax_price": 0,
#                             "total_item_price": 146.34,
#                             "total_price": 146.34,
#                             "other_fees": 0,
#                             "tax_rate": 0,
#                             "total_item_discount": 7.7,
#                             "total_shipping_discount": 2.99,
#                             "total_gift_option_price": 0,
#                             "total_gift_option_tax_price": 0,
#                             "total": 146.34,
#                             "quantity": 1,
#                         }
#                     ],
#                 }
#             ],
#         }
#     ],
#     "channel_order_status": null,
# }
