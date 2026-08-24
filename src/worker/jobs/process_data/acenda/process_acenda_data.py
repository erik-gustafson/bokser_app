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
    AcendaFulfillmentItems,
    AcendaFulfillments,
    AcendaFulfillmentTracking,
    AcendaOrderHeaders,
    AcendaOrderItems,
    AcendaOrderLineDiscounts,
    AcendaOrderLineKitItems,
    AcendaOrderReturns,
    AcendaShipAdviceHeaders,
    AcendaShipAdviceItems,
)
from src.database.models.data_lake_models import DataLakeFile

from src.core.config import settings

logger = logging.getLogger(__name__)

RETRYABLE_LAKE_FILE_STATUSES = ("LANDED", "FAILED", "PARTIAL")


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


def require_positive_int(data: dict[str, Any], field_name: str) -> int:
    value = data.get(field_name)

    if value is None or isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer") from exc

    if parsed <= 0 or (isinstance(value, float) and not value.is_integer()):
        raise ValueError(f"{field_name} must be a positive integer")

    return parsed


def require_datetime(data: dict[str, Any], field_name: str) -> datetime:
    value = data.get(field_name)

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a timezone-aware timestamp")

    try:
        parsed = parse_dt(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a timezone-aware timestamp") from exc

    if parsed is None or parsed.tzinfo is None:
        raise ValueError(f"{field_name} must be a timezone-aware timestamp")

    return parsed


### End Helpers ###

### Entrypoint ###


async def acenda_load_to_db() -> None:
    order_entities = ["new_orders", "updated_orders", "acenda_orders"]
    return_entities = ["acenda_returns"]

    ship_advice_entities = [
        "new_ship_advices",
        "updated_ship_advices",
        "acenda_ship_advices",
    ]

    fulfillment_entities = ["acenda_fulfillments"]

    total_results = []

    for entity_name in order_entities:
        result = await load_acenda_lake_files(
            entity_name=entity_name,
            limit=50,
        )
        total_results.append((entity_name, result))

    for entity_name in return_entities:
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

    for entity_name in fulfillment_entities:
        result = await load_acenda_lake_files(
            entity_name=entity_name,
            limit=50,
        )
        total_results.append((entity_name, result))

    logger.info("Acenda lake load results: %s", total_results)


### --- ###


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

            payload_type = settings.acenda_payload_type(lake_file.entity_name)

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

                    elif failed_count + skipped_count > 0:
                        db_file.status = "PARTIAL"
                        if failed_count > 0:
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
                DataLakeFile.status.in_(RETRYABLE_LAKE_FILE_STATUSES),
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


async def load_acenda_records(
    session: AsyncSession,
    records: list[dict[str, Any]],
    payload_type: str,
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

            elif payload_type == "fulfillment":
                data = mapper.map_acenda_fulfillment(data=raw_record)
                model = AcendaFulfillments

            elif payload_type == "return":
                data = mapper.map_acenda_return(data=raw_record)
                model = AcendaOrderReturns

            else:
                raise ValueError(f"Unsupported Acenda payload type: {payload_type}")

            async with session.begin_nested():
                existing_updated_at = await session.scalar(
                    select(model.updated_at).where(model.id == data.id)
                )

                if existing_updated_at and data.updated_at < existing_updated_at:
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

    def map_acenda_fulfillment(self, data: dict[str, Any]) -> AcendaFulfillments:
        fulfillment = AcendaFulfillments(
            id=as_int(data.get("id")),
            created_at=parse_dt(data.get("created_at")),
            updated_at=parse_dt(data.get("updated_at")),
            fields=data.get("fields") or {},
            ship_advice_id=as_int(data.get("ship_advice_id")),
            carrier=data.get("carrier"),
            date_shipped=parse_dt(data.get("date_shipped")),
            shipping_method=data.get("shipping_method"),
            status=data.get("status"),
            fulfillment_type=data.get("type"),
            cost=as_float(data.get("cost")),
            is_ltl=bool(data.get("is_ltl", False)),
        )

        fulfillment.tracking = [
            self.map_acenda_fulfillment_tracking(
                tracking,
                fulfillment_id=fulfillment.id,
            )
            for tracking in data.get("tracking_info") or []
        ]
        fulfillment.items = [
            self.map_acenda_fulfillment_item(
                item,
                fulfillment_id=fulfillment.id,
            )
            for item in data.get("fulfillment_items") or []
        ]

        return fulfillment

    def map_acenda_fulfillment_tracking(
        self,
        data: dict[str, Any],
        *,
        fulfillment_id: int,
    ) -> AcendaFulfillmentTracking:
        return AcendaFulfillmentTracking(
            fulfillment_id=fulfillment_id,
            tracking_number=as_str(data.get("number")),
        )

    def map_acenda_fulfillment_item(
        self,
        data: dict[str, Any],
        *,
        fulfillment_id: int,
    ) -> AcendaFulfillmentItems:
        return AcendaFulfillmentItems(
            fulfillment_id=fulfillment_id,
            ship_advice_item_id=as_int(data.get("ship_advice_item_id")),
            quantity=as_int(data.get("quantity")),
        )

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
            quantity_canceled=as_int(data.get("quantity_canceled")),
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
            id=require_positive_int(data, "id"),
            created_at=parse_dt(data.get("created_at")),
            created_by=as_str(data.get("created_by")),
            updated_at=require_datetime(data, "updated_at"),
            updated_by=as_str(data.get("updated_by")),
            fields=data.get("fields") or {},
            order_id=require_positive_int(data, "order_id"),
            order_item_id=require_positive_int(data, "order_item_id"),
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
        delivery = data.get("delivery_information") or data.get("delivery_info") or {}

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
            self.map_ship_advice_item(item)
            for item in (data.get("ship_advice_item") or data.get("items") or [])
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
