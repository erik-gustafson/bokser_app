from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, TypeAlias, TypeVar, cast

from sqlalchemy import DateTime, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from src.database.database import async_session
from src.database.models.data_lake_models import DataLakeFile

from src.database.models.sos_models import *

logger = logging.getLogger(__name__)

PayloadType = Literal[
    "sales_order",
    "invoice",
    "shipment",
    "item_receipt",
    "item",
    "purchase_order",
    "sales_receipt",
    "estimate",
    "adjustment",
    "return",
    "rma",
    "payment",
]

SosRootRecord: TypeAlias = (
    SosSalesOrderHeader
    | SosInvoiceHeader
    | SosShipmentHeader
    | SosItemReceiptHeader
    | SosItem
    | SosPurchaseOrderHeader
    | SosSalesReceiptHeader
    | SosEstimateHeader
    | SosReturnHeader
    | SosRmaHeader
    | SosPaymentHeader
    | SosAdjustmentHeader
)

SOS_ENTITY_TYPES: dict[str, PayloadType] = {
    "updated_sales_orders": "sales_order",
    "updated_invoices": "invoice",
    "updated_shipments": "shipment",
    "updated_item_receipts": "item_receipt",
    "updated_items": "item",
    "updated_purchase_orders": "purchase_order",
    "purchase_orders": "purchase_order",
    "sales_receipts": "sales_receipt",
    "estimates": "estimate",
    "adjustments": "adjustment",
    "returns": "return",
    "rmas": "rma",
    "payments": "payment",
}

PAYLOAD_MODELS: dict[PayloadType, type[SosRootRecord]] = {
    "sales_order": SosSalesOrderHeader,
    "invoice": SosInvoiceHeader,
    "shipment": SosShipmentHeader,
    "item_receipt": SosItemReceiptHeader,
    "item": SosItem,
    "purchase_order": SosPurchaseOrderHeader,
    "sales_receipt": SosSalesReceiptHeader,
    "estimate": SosEstimateHeader,
    "adjustment": SosAdjustmentHeader,
    "return": SosReturnHeader,
    "rma": SosRmaHeader,
    "payment": SosPaymentHeader,
}


@dataclass(frozen=True)
class ClaimedLakeFile:
    id: int
    file_path: str
    source_name: str
    entity_name: str


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def as_int(value: Any) -> int:
    return 0 if value is None else int(value)


def as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _snake_to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


SOURCE_ALIASES = {
    "customer_po": "customerPO",
    "due_date": "duedate",
    "on_po": "onPO",
    "on_rma": "onRMA",
    "on_so": "onSO",
    "on_sr": "onSR",
    "on_wo": "onWO",
    "percent_discount": "percentdiscount",
    "transaction_location_quickbooks": "transactionLocationQuickBooks",
    "unit_price": "unitprice",
    "volume_unit": "volumeunit",
    "weight_unit": "weightunit",
}

ModelT = TypeVar("ModelT", bound=DeclarativeBase)
LineModelT = TypeVar("LineModelT", bound=DeclarativeBase)
TransactionModelT = TypeVar("TransactionModelT", bound=DeclarativeBase)


def _source_key(column_name: str) -> str:
    base_name = column_name.removesuffix("_raw")
    return SOURCE_ALIASES.get(column_name, _snake_to_camel(base_name))


def _model_values(
    model: type[ModelT],
    data: dict[str, Any],
    *,
    exclude: set[str] | None = None,
) -> dict[str, Any]:
    excluded = exclude or set()
    values: dict[str, Any] = {}

    for column in model.__table__.columns:
        if column.name in excluded or column.foreign_keys:
            continue

        source_key = _source_key(column.name)
        if source_key not in data:
            continue

        value = data[source_key]
        if isinstance(column.type, DateTime):
            value = parse_dt(value)
        values[column.name] = value

    return values


def _add_reference(
    values: dict[str, Any],
    prefix: str,
    reference: Any,
    *,
    include_fullname: bool = False,
) -> None:
    if isinstance(reference, dict):
        values[f"{prefix}_id"] = reference.get("id")
        values[f"{prefix}_name"] = reference.get("name")
        if include_fullname:
            values[f"{prefix}_fullname"] = reference.get("fullname")
    elif isinstance(reference, str):
        values[f"{prefix}_name"] = reference


def _add_payment_method(values: dict[str, Any], reference: Any) -> None:
    _add_reference(values, "payment_method", reference)
    if isinstance(reference, dict):
        values["payment_method_sync_token"] = reference.get("syncToken")
        values["payment_method_sos_pay_type"] = reference.get("sosPayType")


def _add_address(values: dict[str, Any], prefix: str, source: Any) -> None:
    if not isinstance(source, dict):
        return

    address = source.get("address") or {}
    values.update(
        {
            f"{prefix}_company": source.get("company"),
            f"{prefix}_contact": source.get("contact"),
            f"{prefix}_phone": source.get("phone"),
            f"{prefix}_email": source.get("email"),
            f"{prefix}_address_name": source.get("addressName"),
            f"{prefix}_address_type": source.get("addressType"),
            f"{prefix}_address_line_1": address.get("line1"),
            f"{prefix}_address_line_2": address.get("line2"),
            f"{prefix}_address_line_3": address.get("line3"),
            f"{prefix}_address_line_4": address.get("line4"),
            f"{prefix}_address_line_5": address.get("line5"),
            f"{prefix}_city": address.get("city"),
            f"{prefix}_state_province": address.get("stateProvince"),
            f"{prefix}_postal_code": address.get("postalCode"),
            f"{prefix}_country": address.get("country"),
        }
    )


def _iter_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


async def sos_load_to_db() -> None:
    entity_names = tuple(SOS_ENTITY_TYPES)
    results = await asyncio.gather(
        *(
            load_sos_lake_files(entity_name=entity_name, limit=50)
            for entity_name in entity_names
        )
    )
    total_results = list(zip(entity_names, results, strict=True))

    logger.info("SOS lake load results: %s", total_results)


async def load_sos_lake_files(
    *,
    entity_name: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    if entity_name is not None and entity_name not in SOS_ENTITY_TYPES:
        raise ValueError(f"Unsupported SOS entity_name: {entity_name}")

    total_loaded = 0
    total_skipped = 0
    failed_files: list[dict[str, Any]] = []

    async with async_session() as session:
        async with session.begin():
            claimed_files = await claim_lake_files(
                session,
                entity_name=entity_name,
                limit=limit,
            )

    for lake_file in claimed_files:
        try:
            path = Path(lake_file.file_path)
            with path.open("r", encoding="utf-8") as file:
                file_data = json.load(file)

            records = extract_json_records(
                file_data,
                path=path,
                expected_entity_name=lake_file.entity_name,
            )
            payload_type = SOS_ENTITY_TYPES[lake_file.entity_name]

            async with async_session() as session:
                async with session.begin():
                    result = await load_sos_records(
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
                        db_file.last_error = None
                    elif failed_count + skipped_count > 0:
                        db_file.status = "PARTIAL"
                        db_file.last_error = (
                            json.dumps(result["failed"])[:5000]
                            if failed_count
                            else None
                        )
                    else:
                        db_file.status = "LOADED"
                        db_file.last_error = None

        except Exception as exc:
            logger.exception(
                "Failed to load SOS lake file id=%s path=%s",
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
    entity_name: str | None = None,
    limit: int = 25,
) -> list[ClaimedLakeFile]:
    stale_processing_before = datetime.now(timezone.utc) - timedelta(minutes=30)

    stmt = (
        select(DataLakeFile)
        .where(
            DataLakeFile.source_name == "sos_inventory",
            DataLakeFile.entity_name.in_(SOS_ENTITY_TYPES),
            or_(
                DataLakeFile.status.in_(["LANDED", "FAILED"]),
                and_(
                    DataLakeFile.status == "PROCESSING",
                    DataLakeFile.claimed_at < stale_processing_before,
                ),
            ),
        )
        .order_by(DataLakeFile.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )

    if entity_name:
        stmt = stmt.where(DataLakeFile.entity_name == entity_name)

    result = await session.execute(stmt)
    files = list(result.scalars().all())
    claimed_files: list[ClaimedLakeFile] = []

    for lake_file in files:
        lake_file.status = "PROCESSING"
        lake_file.attempt_count += 1
        lake_file.claimed_at = datetime.now(timezone.utc)
        claimed_files.append(
            ClaimedLakeFile(
                id=lake_file.id,
                file_path=lake_file.file_path,
                source_name=lake_file.source_name,
                entity_name=lake_file.entity_name,
            )
        )

    return claimed_files


async def load_sos_records(
    session: AsyncSession,
    records: list[dict[str, Any]],
    payload_type: PayloadType,
) -> dict[str, Any]:
    mapper = SosPayloadMapper()
    model = PAYLOAD_MODELS[payload_type]
    loaded = 0
    skipped = 0
    failed: list[dict[str, Any]] = []

    for raw_record in records:
        record_id = raw_record.get("id")
        try:
            data = mapper.map_record(payload_type, raw_record)

            async with session.begin_nested():
                existing_sync_token = await session.scalar(
                    select(model.sync_token).where(model.id == data.id)
                )
                incoming_sync_token = data.sync_token or 0

                # if (
                #     existing_sync_token is not None
                #     and incoming_sync_token <= existing_sync_token
                # ):
                #     skipped += 1
                #     continue

                await session.merge(data)

            loaded += 1

        except Exception as exc:
            logger.exception("Failed to load SOS %s id=%s", payload_type, record_id)
            failed.append({"id": record_id, "error": str(exc)})

    return {"loaded": loaded, "skipped": skipped, "failed": failed}


def extract_json_records(
    payload: Any,
    *,
    path: Path,
    expected_entity_name: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError(f"Expected wrapped lake JSON object in {path}")

    metadata = payload.get("metadata")
    records = payload.get("payload")
    if not isinstance(metadata, dict):
        raise ValueError(f"Missing or invalid metadata in {path}")

    if expected_entity_name and metadata.get("entity_name") != expected_entity_name:
        raise ValueError(
            f"Entity mismatch in {path}: manifest={expected_entity_name}, "
            f"file={metadata.get('entity_name')}"
        )

    if not isinstance(records, list):
        raise ValueError(f"Expected payload list in {path}")
    if any(not isinstance(record, dict) for record in records):
        raise ValueError(f"Payload contains non-object records in {path}")
    return records


class SosPayloadMapper:
    def map_record(
        self,
        payload_type: PayloadType,
        data: dict[str, Any],
    ) -> SosRootRecord:
        if payload_type == "sales_order":
            return self.map_sales_order(data)
        if payload_type == "invoice":
            return self.map_invoice(data)
        if payload_type == "shipment":
            return self.map_shipment(data)
        if payload_type == "item_receipt":
            return self.map_item_receipt(data)
        if payload_type == "item":
            return self.map_item(data)
        if payload_type == "purchase_order":
            return self.map_purchase_order(data)
        if payload_type == "sales_receipt":
            return self.map_sales_receipt(data)
        if payload_type == "estimate":
            return self.map_estimate(data)
        if payload_type == "adjustment":
            return self.map_adjustment(data)
        if payload_type == "return":
            return self.map_return(data)
        if payload_type == "rma":
            return self.map_rma(data)
        if payload_type == "payment":
            return self.map_payment(data)
        raise ValueError(f"Unsupported SOS payload type: {payload_type}")

    def map_sales_order(self, data: dict[str, Any]) -> SosSalesOrderHeader:
        values = _model_values(SosSalesOrderHeader, data)
        self._add_common_customer_header(values, data, include_location=True)
        _add_reference(values, "order_stage", data.get("orderStage"))
        _add_reference(values, "channel", data.get("channel"))
        _add_reference(values, "priority", data.get("priority"))
        header = SosSalesOrderHeader(**values)
        header.lines = [
            self._map_line(
                SosSalesOrderLine,
                SosSalesOrderLineLinkedTransactions,
                "sales_order_id",
                "sales_order_line_id",
                as_int(data.get("id")),
                line,
            )
            for line in _iter_dicts(data.get("lines"))
        ]
        header.custom_fields = self._map_custom_fields(
            SosSalesOrderCustomField,
            "sales_order_id",
            as_int(data.get("id")),
            data.get("customFields"),
        )
        header.linked_transactions = self._map_header_transactions(
            SosSalesOrderHeaderLinkedTransactions,
            "sales_order_id",
            as_int(data.get("id")),
            data,
            collection_keys=("linkedInvoices", "linkedShipments", "linkedPayments"),
        )
        return header

    def map_invoice(self, data: dict[str, Any]) -> SosInvoiceHeader:
        values = _model_values(SosInvoiceHeader, data)
        self._add_common_customer_header(values, data)
        _add_reference(values, "shipping_method", data.get("shippingMethod"))
        _add_reference(values, "channel", data.get("channel"))
        header = SosInvoiceHeader(**values)
        header.lines = [
            self._map_line(
                SosInvoiceLine,
                SosInvoiceLineLinkedTransactions,
                "invoice_id",
                "invoice_line_id",
                as_int(data.get("id")),
                line,
            )
            for line in _iter_dicts(data.get("lines"))
        ]
        header.custom_fields = self._map_custom_fields(
            SosInvoiceCustomField,
            "invoice_id",
            as_int(data.get("id")),
            data.get("customFields"),
        )
        header.linked_transactions = self._map_header_transactions(
            SosInvoiceHeaderLinkedTransactions,
            "invoice_id",
            as_int(data.get("id")),
            data,
            collection_keys=("linkedPayments",),
        )
        return header

    def map_shipment(self, data: dict[str, Any]) -> SosShipmentHeader:
        values = _model_values(SosShipmentHeader, data)
        self._add_common_customer_header(values, data, include_location=True)
        _add_reference(values, "shipping_method", data.get("shippingMethod"))
        _add_reference(values, "channel", data.get("channel"))
        _add_reference(values, "priority", data.get("priority"))
        header = SosShipmentHeader(**values)
        header.lines = [
            self._map_line(
                SosShipmentLine,
                SosShipmentLineLinkedTransactions,
                "shipment_id",
                "shipment_line_id",
                as_int(data.get("id")),
                line,
            )
            for line in _iter_dicts(data.get("lines"))
        ]
        header.custom_fields = self._map_custom_fields(
            SosShipmentCustomField,
            "shipment_id",
            as_int(data.get("id")),
            data.get("customFields"),
        )
        header.linked_transactions = self._map_header_transactions(
            SosShipmentHeaderLinkedTransactions,
            "shipment_id",
            as_int(data.get("id")),
            data,
        )
        return header

    def map_item_receipt(self, data: dict[str, Any]) -> SosItemReceiptHeader:
        values = _model_values(SosItemReceiptHeader, data)
        for prefix in ("vendor", "location", "terms", "currency", "tax_code"):
            _add_reference(values, prefix, data.get(_snake_to_camel(prefix)))

        header = SosItemReceiptHeader(**values)
        receipt_id = as_int(data.get("id"))
        header.lines = [
            self._map_line(
                SosItemReceiptLine,
                SosItemReceiptLineLinkedTransactions,
                "item_receipt_id",
                "item_receipt_line_id",
                receipt_id,
                line,
            )
            for line in _iter_dicts(data.get("lines"))
        ]
        header.custom_fields = self._map_custom_fields(
            SosItemReceiptCustomField,
            "item_receipt_id",
            receipt_id,
            data.get("customFields"),
        )
        header.linked_transactions = self._map_header_transactions(
            SosItemReceiptHeaderLinkedTransactions,
            "item_receipt_id",
            receipt_id,
            data,
        )
        header.other_costs = [
            self._map_other_cost(receipt_id, item)
            for item in _iter_dicts(data.get("otherCosts"))
        ]
        return header

    def map_item(self, data: dict[str, Any]) -> SosItem:
        values = _model_values(SosItem, data)
        for prefix, source_key in (
            ("class", "class"),
            ("income_account", "incomeAccount"),
            ("cogs_account", "cogsAccount"),
            ("asset_account", "assetAccount"),
            ("expense_account", "expenseAccount"),
        ):
            _add_reference(values, prefix, data.get(source_key))

        item = SosItem(**values)
        item_id = as_int(data.get("id"))
        item.custom_fields = self._map_custom_fields(
            SosItemCustomField,
            "item_id",
            item_id,
            data.get("customFields"),
        )
        item.uoms = [
            self._map_uom(item_id, uom) for uom in _iter_dicts(data.get("uoms"))
        ]
        return item

    def map_purchase_order(self, data: dict[str, Any]) -> SosPurchaseOrderHeader:
        values = _model_values(SosPurchaseOrderHeader, data)
        _add_reference(values, "vendor", data.get("vendor"))
        _add_reference(
            values,
            "customer",
            data.get("customer"),
            include_fullname=True,
        )
        for prefix in (
            "location",
            "terms",
            "currency",
            "tax_code",
            "shipping_method",
        ):
            _add_reference(values, prefix, data.get(_snake_to_camel(prefix)))
        _add_address(values, "billing", data.get("billing"))
        _add_address(values, "shipping", data.get("shipping"))

        header = SosPurchaseOrderHeader(**values)
        purchase_order_id = as_int(data.get("id"))
        header.lines = [
            self._map_line(
                SosPurchaseOrderLine,
                SosPurchaseOrderLineLinkedTransactions,
                "purchase_order_id",
                "purchase_order_line_id",
                purchase_order_id,
                line,
            )
            for line in _iter_dicts(data.get("lines"))
        ]
        header.custom_fields = self._map_custom_fields(
            SosPurchaseOrderCustomField,
            "purchase_order_id",
            purchase_order_id,
            data.get("customFields"),
        )
        header.linked_transactions = self._map_header_transactions(
            SosPurchaseOrderHeaderLinkedTransactions,
            "purchase_order_id",
            purchase_order_id,
            data,
            collection_keys=("linkedReceipts",),
        )
        return header

    def map_sales_receipt(self, data: dict[str, Any]) -> SosSalesReceiptHeader:
        values = _model_values(SosSalesReceiptHeader, data)
        self._add_common_customer_header(values, data, include_location=True)
        _add_payment_method(values, data.get("paymentMethod"))
        for prefix in (
            "deposit_account",
            "channel",
            "priority",
            "order_stage",
            "shipping_method",
        ):
            _add_reference(values, prefix, data.get(_snake_to_camel(prefix)))

        header = SosSalesReceiptHeader(**values)
        sales_receipt_id = as_int(data.get("id"))
        header.lines = [
            self._map_line(
                SosSalesReceiptLine,
                SosSalesReceiptLineLinkedTransactions,
                "sales_receipt_id",
                "sales_receipt_line_id",
                sales_receipt_id,
                line,
            )
            for line in _iter_dicts(data.get("lines"))
        ]
        header.custom_fields = self._map_custom_fields(
            SosSalesReceiptCustomField,
            "sales_receipt_id",
            sales_receipt_id,
            data.get("customFields"),
        )
        header.linked_transactions = self._map_header_transactions(
            SosSalesReceiptHeaderLinkedTransactions,
            "sales_receipt_id",
            sales_receipt_id,
            data,
        )
        return header

    def map_estimate(self, data: dict[str, Any]) -> SosEstimateHeader:
        values = _model_values(SosEstimateHeader, data)
        self._add_common_customer_header(values, data)
        _add_reference(values, "channel", data.get("channel"))

        header = SosEstimateHeader(**values)
        estimate_id = as_int(data.get("id"))
        header.lines = [
            self._map_line(
                SosEstimateLine,
                SosEstimateLineLinkedTransactions,
                "estimate_id",
                "estimate_line_id",
                estimate_id,
                line,
            )
            for line in _iter_dicts(data.get("lines"))
        ]
        header.custom_fields = self._map_custom_fields(
            SosEstimateCustomField,
            "estimate_id",
            estimate_id,
            data.get("customFields"),
        )
        header.linked_transactions = self._map_header_transactions(
            SosEstimateHeaderLinkedTransactions,
            "estimate_id",
            estimate_id,
            data,
        )
        return header

    def map_adjustment(self, data: dict[str, Any]) -> SosAdjustmentHeader:
        values = _model_values(SosAdjustmentHeader, data)
        _add_reference(values, "account", data.get("account"))
        _add_reference(values, "location", data.get("location"))

        header = SosAdjustmentHeader(**values)
        adjustment_id = as_int(data.get("id"))
        header.lines = [
            self._map_adjustment_line(adjustment_id, line)
            for line in _iter_dicts(data.get("lines"))
        ]
        header.custom_fields = self._map_custom_fields(
            SosAdjustmentCustomField,
            "adjustment_id",
            adjustment_id,
            data.get("customFields"),
        )
        return header

    def map_return(self, data: dict[str, Any]) -> SosReturnHeader:
        values = _model_values(SosReturnHeader, data)
        _add_reference(
            values,
            "customer",
            data.get("customer"),
            include_fullname=True,
        )
        for prefix in ("currency", "location", "channel", "shipping_method"):
            _add_reference(values, prefix, data.get(_snake_to_camel(prefix)))

        header = SosReturnHeader(**values)
        return_id = as_int(data.get("id"))
        header.lines = [
            self._map_line(
                SosReturnLine,
                SosReturnLineLinkedTransactions,
                "return_id",
                "return_line_id",
                return_id,
                line,
            )
            for line in _iter_dicts(data.get("lines"))
        ]
        header.custom_fields = self._map_custom_fields(
            SosReturnCustomField,
            "return_id",
            return_id,
            data.get("customFields"),
        )
        header.linked_transactions = self._map_header_transactions(
            SosReturnHeaderLinkedTransactions,
            "return_id",
            return_id,
            data,
        )
        return header

    def map_rma(self, data: dict[str, Any]) -> SosRmaHeader:
        values = _model_values(SosRmaHeader, data)
        _add_reference(
            values,
            "customer",
            data.get("customer"),
            include_fullname=True,
        )
        for prefix in ("location", "channel", "shipping_method"):
            _add_reference(values, prefix, data.get(_snake_to_camel(prefix)))
        _add_address(values, "billing", data.get("billing"))
        _add_address(values, "shipping", data.get("shipping"))

        header = SosRmaHeader(**values)
        rma_id = as_int(data.get("id"))
        header.lines = [
            self._map_line(
                SosRmaLine,
                SosRmaLineLinkedTransactions,
                "rma_id",
                "rma_line_id",
                rma_id,
                line,
            )
            for line in _iter_dicts(data.get("lines"))
        ]
        header.custom_fields = self._map_custom_fields(
            SosRmaCustomField,
            "rma_id",
            rma_id,
            data.get("customFields"),
        )
        header.linked_transactions = self._map_header_transactions(
            SosRmaHeaderLinkedTransactions,
            "rma_id",
            rma_id,
            data,
        )
        return header

    def map_payment(self, data: dict[str, Any]) -> SosPaymentHeader:
        values = _model_values(SosPaymentHeader, data)
        _add_reference(
            values,
            "customer",
            data.get("customer"),
            include_fullname=True,
        )
        _add_payment_method(values, data.get("paymentMethod"))
        for prefix in (
            "location",
            "currency",
            "channel",
            "deposit_account",
            "class",
        ):
            _add_reference(values, prefix, data.get(_snake_to_camel(prefix)))
        _add_address(values, "billing", data.get("billing"))

        header = SosPaymentHeader(**values)
        payment_id = as_int(data.get("id"))
        header.lines = [
            self._map_line(
                SosPaymentLine,
                SosPaymentLineLinkedTransactions,
                "payment_id",
                "payment_line_id",
                payment_id,
                line,
            )
            for line in _iter_dicts(data.get("lines"))
        ]
        header.custom_fields = self._map_custom_fields(
            SosPaymentCustomField,
            "payment_id",
            payment_id,
            data.get("customFields"),
        )
        header.linked_transactions = self._map_header_transactions(
            SosPaymentHeaderLinkedTransactions,
            "payment_id",
            payment_id,
            data,
        )
        return header

    def _add_common_customer_header(
        self,
        values: dict[str, Any],
        data: dict[str, Any],
        *,
        include_location: bool = False,
    ) -> None:
        _add_reference(
            values,
            "customer",
            data.get("customer"),
            include_fullname=True,
        )
        if include_location:
            _add_reference(values, "location", data.get("location"))
        _add_reference(values, "terms", data.get("terms"))
        _add_reference(values, "tax_code", data.get("taxCode"))
        _add_reference(values, "currency", data.get("currency"))
        _add_address(values, "billing", data.get("billing"))
        _add_address(values, "shipping", data.get("shipping"))

    def _map_line(
        self,
        line_model: type[LineModelT],
        transaction_model: type[TransactionModelT],
        parent_field: str,
        transaction_parent_field: str,
        parent_id: int,
        data: dict[str, Any],
    ) -> LineModelT:
        values = _model_values(line_model, data)
        values[parent_field] = parent_id
        _add_reference(values, "item", data.get("item"))
        _add_reference(values, "class", data.get("class"))
        _add_reference(values, "uom", data.get("uom"))

        tax = data.get("tax")
        if isinstance(tax, dict):
            values["tax_taxable"] = tax.get("taxable")
            values["tax_tax_code_raw"] = tax.get("taxCode")
            values["tax_tax_exempt_reason_id"] = tax.get("taxExemptReasonId")

        line = line_model(**values)
        linked_transaction = data.get("linkedTransaction")
        if isinstance(linked_transaction, dict):
            cast(Any, line).linked_transactions = [
                self._map_linked_transaction(
                    transaction_model,
                    transaction_parent_field,
                    as_int(data.get("id")),
                    linked_transaction,
                )
            ]
        else:
            cast(Any, line).linked_transactions = []
        return line

    def _map_custom_fields(
        self,
        model: type[ModelT],
        parent_field: str,
        parent_id: int,
        data: Any,
    ) -> list[ModelT]:
        return [
            model(
                **{
                    parent_field: parent_id,
                    "custom_field_id": as_int(item.get("id")),
                    "name": item.get("name"),
                    "value": item.get("value"),
                    "data_type": item.get("dataType"),
                }
            )
            for item in _iter_dicts(data)
        ]

    def _map_header_transactions(
        self,
        model: type[ModelT],
        parent_field: str,
        parent_id: int,
        data: dict[str, Any],
        *,
        collection_keys: tuple[str, ...] = (),
    ) -> list[ModelT]:
        transactions: list[dict[str, Any]] = []
        linked_transaction = data.get("linkedTransaction")
        if isinstance(linked_transaction, dict):
            transactions.append(linked_transaction)
        for key in collection_keys:
            transactions.extend(_iter_dicts(data.get(key)))

        unique: dict[tuple[int, str, int], dict[str, Any]] = {}
        for transaction in transactions:
            identity = (
                as_int(transaction.get("id")),
                as_str(transaction.get("transactionType")),
                as_int(transaction.get("lineNumber")),
            )
            unique[identity] = transaction

        return [
            self._map_linked_transaction(model, parent_field, parent_id, transaction)
            for transaction in unique.values()
        ]

    def _map_linked_transaction(
        self,
        model: type[ModelT],
        parent_field: str,
        parent_id: int,
        data: dict[str, Any],
    ) -> ModelT:
        return model(
            **{
                parent_field: parent_id,
                "linked_transaction_id": as_int(data.get("id")),
                "type": as_str(data.get("transactionType")),
                "line_number": as_int(data.get("lineNumber")),
                "ref_number": data.get("refNumber"),
            }
        )

    def _map_other_cost(
        self,
        item_receipt_id: int,
        data: dict[str, Any],
    ) -> SosItemReceiptOtherCost:
        values = _model_values(SosItemReceiptOtherCost, data)
        values["item_receipt_id"] = item_receipt_id
        _add_reference(values, "item", data.get("item"))
        _add_reference(values, "vendor", data.get("vendor"))
        _add_reference(values, "class", data.get("class"))
        return SosItemReceiptOtherCost(**values)

    def _map_adjustment_line(
        self,
        adjustment_id: int,
        data: dict[str, Any],
    ) -> SosAdjustmentLine:
        values = _model_values(SosAdjustmentLine, data)
        values["adjustment_id"] = adjustment_id
        _add_reference(values, "item", data.get("item"))
        _add_reference(values, "class", data.get("class"))
        _add_reference(values, "uom", data.get("uom"))
        return SosAdjustmentLine(**values)

    def _map_uom(self, item_id: int, data: dict[str, Any]) -> SosItemUom:
        values = _model_values(SosItemUom, data)
        values["item_id"] = item_id
        _add_reference(values, "uom", data.get("uom"))
        return SosItemUom(**values)
