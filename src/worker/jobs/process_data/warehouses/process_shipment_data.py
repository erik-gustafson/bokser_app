from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from src.worker.jobs.process_data.utils import data_lake_tools

from src.database.models import *
from src.database.utils import model_tools
from src.database.utils.formatter_tools import parse_dt, as_str, as_float, as_int

from src.database.database import async_session

logger = logging.getLogger(__name__)


SHIPMENT_ENTITIES = [("ksp", "order_update"), ("productiv", "orderconfirm")]

### local dev begin ###


def resolve_lake_path(file_path: str) -> Path:
    container_root = Path("/app/data_lake")
    local_root = Path(r"X:\data_lake\prod")

    path = Path(file_path)

    if str(path).startswith(str(container_root)):
        relative_path = path.relative_to(container_root)
        return local_root / relative_path

    return path


### local dev end ###


async def shipment_load_to_db(limit: int = 50) -> None:

    total_results = []

    for entity in SHIPMENT_ENTITIES:
        result = await load_whse_shipment_lake_files(
            entity=entity,
            limit=limit,
        )
        total_results.append((entity, result))

    logger.info("Warehouse shipment lake load results: %s", total_results)


async def load_whse_shipment_lake_files(
    *,
    entity: tuple[str, str],
    limit: int = 25,
) -> dict[str, Any]:
    total_loaded = 0
    total_skipped = 0
    failed_files: list[dict[str, Any]] = []

    source_name = entity[0]
    entity_name = entity[1]
    # Step 1: claim files in a short transaction.
    async with async_session() as session:
        async with session.begin():
            claimed_files = await data_lake_tools.claim_lake_files(
                session,
                source_name=source_name,
                entity_name=entity_name,
                limit=limit,
            )

    # Step 2: process each claimed file independently.
    for lake_file in claimed_files:
        try:
            # path = Path(lake_file.file_path)

            path = resolve_lake_path(lake_file.file_path)

            with path.open("r", encoding="utf-8") as f:
                file_data = json.load(f)

            records = data_lake_tools.extract_json_records(
                file_data,
                path=path,
                expected_entity_name=lake_file.entity_name,
            )

            ####------####

            async with async_session() as session:
                async with session.begin():
                    result = await load_shipment_records(
                        session=session,
                        records=records,
                        warehouse=source_name,
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


async def load_shipment_records(
    session: AsyncSession,
    records: list[dict[str, Any]],
    warehouse: str,
) -> dict[str, Any]:

    mapper = ShipmentPayloadMapper()

    loaded = 0
    skipped = 0
    failed: list[dict[str, Any]] = []

    for raw_record in records:

        try:
            if warehouse == "ksp":
                record_id = raw_record.get("cust_ref", "No cust_ref provided!")
                data = mapper.map_ksp_shipment(data=raw_record)

                async with session.begin_nested():
                    await post_ksp_shipment_data(session, data)

            elif warehouse == "productiv":
                record_id = raw_record.get("cust_ref", "No cust_ref provided!")
                data = mapper.map_ksp_shipment(data=raw_record)

                async with session.begin_nested():
                    await post_ksp_shipment_data(session, data)

            else:
                raise ValueError(f"Unsupported warehouse type: {warehouse}")

            loaded += 1

        except Exception as exc:
            logger.exception(
                "Failed to process record %s",
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


async def post_ksp_shipment_data(session: AsyncSession, data: KSPShipmentHeaders):

    existing_shipment = await session.get(
        KSPShipmentHeaders,
        (data.cust_ref, data.cust_po_no),
        options=[
            selectinload(KSPShipmentHeaders.ship_details).selectinload(
                KSPShipmentDetails.items
            )
        ],
    )

    if existing_shipment is None:
        session.add(data)
        return

    incoming_details = list(data.ship_details)
    data.ship_details.clear()

    model_tools.update_model(
        existing_shipment,
        data,
        exclude={"cust_ref", "cust_po_no"},
    )

    existing_details = {
        detail.tracking_no: detail for detail in existing_shipment.ship_details
    }

    for incoming_detail in incoming_details:
        incoming_items = list(incoming_detail.items)
        incoming_detail.items.clear()

        existing_detail = existing_details.get(incoming_detail.tracking_no)

        if existing_detail is None:
            incoming_detail.items.extend(incoming_items)
            existing_shipment.ship_details.append(incoming_detail)
            existing_details[incoming_detail.tracking_no] = incoming_detail
            continue

        model_tools.update_model(
            existing_detail,
            incoming_detail,
            exclude={"tracking_no", "cust_ref"},
        )

        existing_items = {item.item: item for item in existing_detail.items}

        for incoming_item in incoming_items:
            existing_item = existing_items.get(incoming_item.item)

            if existing_item is None:
                existing_detail.items.append(incoming_item)
                existing_items[incoming_item.item] = incoming_item
                continue

            model_tools.update_model(
                existing_item,
                incoming_item,
                exclude={"item", "tracking_no"},
            )


class ShipmentPayloadMapper:

    def map_ksp_shipment(self, data: dict[str, Any]) -> KSPShipmentHeaders:

        ksp_shipment = KSPShipmentHeaders(
            cust_ref=as_str(data.get("cust_ref")),
            cust_po_no=as_str(data.get("cust_po_no")),
            delivered_to_wms_date=parse_dt(data.get("delivered_to_wms_date")),
            order_status=as_str(data.get("order_status")),
        )

        ksp_shipment.ship_details = [
            self.map_ksp_shipment_details(
                detail,
                cust_ref=ksp_shipment.cust_ref,
            )
            for detail in data.get("shipments") or []
        ]

        return ksp_shipment

    def map_ksp_shipment_details(
        self,
        data: dict[str, Any],
        *,
        cust_ref: str,
    ) -> KSPShipmentDetails:

        shipment_details = KSPShipmentDetails(
            cust_ref=as_str(cust_ref),
            carrier=as_str(data.get("carrier")),
            method=as_str(data.get("method")),
            tracking_no=as_str(data.get("tracking_no")),
            tracking_no_secondary=as_str(data.get("tracking_no_secondary")),
            total_cost=as_float(data.get("total_cost")),
            package_weight_lbs=as_float(data.get("package_weight_lbs")),
            dim_weight_lbs=as_float(data.get("dim_weight_lbs")),
            zone=as_str(data.get("zone")),
            delivery_surcharge_type=as_str(data.get("delivery_surcharge_type")),
            date=parse_dt(data.get("date")),
            custom_1=data.get("custom_1"),
            custom_2=data.get("custom_2"),
            custom_3=data.get("custom_3"),
        )

        shipment_details.items = [
            self.map_ksp_shipment_detail_items(
                item, tracking_no=shipment_details.tracking_no
            )
            for item in data.get("items") or []
        ]

        return shipment_details

    def map_ksp_shipment_detail_items(
        self,
        data: dict[str, Any],
        *,
        tracking_no: str,
    ) -> KSPShipmentDetailItems:

        return KSPShipmentDetailItems(
            tracking_no=as_str(tracking_no),
            item=as_str(data.get("item")),
            quantity=as_int(data.get("quantity")),
            carton_code=as_str(data.get("carton_code")),
            carton_num=as_str(data.get("carton_num")),
            box_length_in=as_str(data.get("box_length_in")),
            box_width_in=as_str(data.get("box_width_in")),
            box_height_in=as_str(data.get("box_height_in")),
            package_weight_lbs=as_str(data.get("package_weight_lbs")),
            lot_code=as_str(data.get("lot_code")),
            serial_no=as_str(data.get("serial_no")),
            custom_1=as_str(data.get("custom_1")),
        )
