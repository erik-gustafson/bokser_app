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
from src.database.utils.formatter_tools import (
    parse_dt,
    as_str,
    as_float,
    as_int,
    as_decimal,
)

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
                "Failed to load warehouse shipment lake file "
                "id=%s source=%s path=%s",
                lake_file.id,
                source_name,
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

    loaded = 0
    skipped = 0
    failed: list[dict[str, Any]] = []

    for raw_record in records:
        record_id: Any = None

        try:
            if warehouse == "ksp":
                record_id = raw_record.get(
                    "cust_ref",
                    "No cust_ref provided!",
                )

                shipment = KSPShipmentMapper.map_shipment(raw_record)

                async with session.begin_nested():
                    await post_ksp_shipment_data(
                        session,
                        shipment,
                    )

            elif warehouse == "productiv":
                body = raw_record.get("resource", {}).get("body", {})

                record_id = body.get(
                    "readOnly",
                    {},
                ).get(
                    "orderId",
                    "No Productiv orderId provided!",
                )

                shipment = ProductivShipmentMapper.map_shipment(raw_record)

                async with session.begin_nested():
                    await post_productiv_shipment_data(
                        session,
                        shipment,
                    )

            else:
                raise ValueError(f"Unsupported warehouse type: {warehouse}")

            loaded += 1

        except Exception as exc:
            logger.exception(
                "Failed to process %s shipment record %s",
                warehouse,
                record_id,
            )

            failed.append(
                {
                    "id": record_id,
                    "error": str(exc),
                }
            )

    return {
        "loaded": loaded,
        "skipped": skipped,
        "failed": failed,
    }


async def post_ksp_shipment_data(
    session: AsyncSession,
    data: KSPShipmentHeaders,
) -> None:

    stmt = (
        select(KSPShipmentHeaders)
        .where(
            KSPShipmentHeaders.cust_ref == data.cust_ref,
            KSPShipmentHeaders.cust_po_no == data.cust_po_no,
        )
        .options(
            selectinload(KSPShipmentHeaders.ship_details).selectinload(
                KSPShipmentDetails.items
            )
        )
    )

    existing = await session.scalar(stmt)

    if existing is None:
        session.add(data)
        return

    incoming_details = list(data.ship_details)
    data.ship_details.clear()

    model_tools.update_model(
        existing,
        data,
        exclude={
            "cust_ref",
            "cust_po_no",
        },
    )

    _merge_ksp_ship_details(
        existing,
        incoming_details,
    )


def _merge_ksp_ship_details(
    existing: KSPShipmentHeaders,
    incoming_details: list[KSPShipmentDetails],
) -> None:

    existing_by_tracking = {
        detail.tracking_no: detail for detail in existing.ship_details
    }

    for incoming in incoming_details:
        incoming_items = list(incoming.items)
        incoming.items.clear()

        current = existing_by_tracking.get(incoming.tracking_no)

        if current is None:
            incoming.items.extend(incoming_items)
            existing.ship_details.append(incoming)

            existing_by_tracking[incoming.tracking_no] = incoming

            continue

        model_tools.update_model(
            current,
            incoming,
            exclude={"tracking_no"},
        )

        model_tools.merge_model_collection(
            current.items,
            incoming_items,
            key=lambda item: item.item,
            exclude={"item"},
        )


async def post_productiv_shipment_data(
    session: AsyncSession,
    data: ProductivShipmentHeaders,
) -> None:

    stmt = (
        select(ProductivShipmentHeaders)
        .where(ProductivShipmentHeaders.order_id == data.order_id)
        .options(
            selectinload(ProductivShipmentHeaders.items),
            selectinload(ProductivShipmentHeaders.packages).selectinload(
                ProductivShipmentPackages.contents
            ),
            selectinload(ProductivShipmentHeaders.billing_charges).selectinload(
                ProductivShipmentBillingCharges.details
            ),
        )
    )

    existing = await session.scalar(stmt)

    if existing is None:
        session.add(data)
        return

    incoming_items = list(data.items)
    incoming_packages = list(data.packages)
    incoming_charges = list(data.billing_charges)

    data.items.clear()
    data.packages.clear()
    data.billing_charges.clear()

    model_tools.update_model(
        existing,
        data,
        exclude={"order_id"},
    )

    model_tools.merge_model_collection(
        existing.items,
        incoming_items,
        key=lambda item: item.order_item_id,
        exclude={"order_item_id"},
    )

    _merge_productiv_packages(
        existing,
        incoming_packages,
    )

    _merge_productiv_billing(
        existing,
        incoming_charges,
    )


def _merge_productiv_packages(
    existing: ProductivShipmentHeaders,
    incoming_packages: list[ProductivShipmentPackages],
) -> None:

    existing_by_package_id = {
        package.productiv_package_id: package for package in existing.packages
    }

    for incoming in incoming_packages:
        incoming_contents = list(incoming.contents)
        incoming.contents.clear()

        current = existing_by_package_id.get(incoming.productiv_package_id)

        if current is None:
            incoming.contents.extend(incoming_contents)
            existing.packages.append(incoming)

            existing_by_package_id[incoming.productiv_package_id] = incoming

            continue

        model_tools.update_model(
            current,
            incoming,
            exclude={"productiv_package_id"},
        )

        model_tools.merge_model_collection(
            current.contents,
            incoming_contents,
            key=lambda content: (content.productiv_package_content_id),
            exclude={
                "productiv_package_content_id",
            },
        )


def _merge_productiv_billing(
    existing: ProductivShipmentHeaders,
    incoming_charges: list[ProductivShipmentBillingCharges],
) -> None:

    existing_by_sequence = {
        charge.sequence: charge for charge in existing.billing_charges
    }

    for incoming in incoming_charges:
        incoming_details = list(incoming.details)
        incoming.details.clear()

        current = existing_by_sequence.get(incoming.sequence)

        if current is None:
            incoming.details.extend(incoming_details)
            existing.billing_charges.append(incoming)

            existing_by_sequence[incoming.sequence] = incoming

            continue

        model_tools.update_model(
            current,
            incoming,
            exclude={"sequence"},
        )

        model_tools.merge_model_collection(
            current.details,
            incoming_details,
            key=lambda detail: (detail.warehouse_transaction_price_calc_id),
            exclude={
                "warehouse_transaction_price_calc_id",
            },
        )


class KSPShipmentMapper:

    @classmethod
    def map_shipment(
        cls,
        data: dict[str, Any],
    ) -> KSPShipmentHeaders:

        shipment = KSPShipmentHeaders(
            cust_ref=as_str(data.get("cust_ref")),
            cust_po_no=as_str(data.get("cust_po_no")),
            delivered_to_wms_date=parse_dt(data.get("delivered_to_wms_date")),
            order_status=as_str(data.get("order_status")),
        )

        shipment.ship_details = [
            cls._map_detail(detail) for detail in data.get("shipments") or []
        ]

        return shipment

    @classmethod
    def _map_detail(
        cls,
        data: dict[str, Any],
    ) -> KSPShipmentDetails:

        detail = KSPShipmentDetails(
            carrier=as_str(data.get("carrier")),
            method=as_str(data.get("method")),
            tracking_no=as_str(data.get("tracking_no")),
            package_weight_lbs=as_float(data.get("package_weight_lbs")),
            dim_weight_lbs=as_float(data.get("dim_weight_lbs")),
            date=parse_dt(data.get("date")),
        )

        detail.items = [cls._map_detail_item(item) for item in data.get("items") or []]

        return detail

    @staticmethod
    def _map_detail_item(
        data: dict[str, Any],
    ) -> KSPShipmentDetailItems:

        return KSPShipmentDetailItems(
            item=as_str(data.get("item")),
            quantity=as_int(data.get("quantity")),
        )


class ProductivShipmentMapper:

    ITEM_REL = "http://api.3plCentral.com/rels/orders/item"

    @classmethod
    def map_shipment(
        cls,
        data: dict[str, Any],
    ) -> ProductivShipmentHeaders:

        body = cls._get_body(data)

        shipment = cls._map_header(body)

        shipment.items = cls._map_items(body)
        shipment.packages = cls._map_packages(body)
        shipment.billing_charges = cls._map_billing_charges(body)

        return shipment

    @staticmethod
    def _get_body(
        data: dict[str, Any],
    ) -> dict[str, Any]:

        resource = data.get("resource") or {}
        body = resource.get("body")

        if not isinstance(body, dict):
            raise ValueError("Productiv OrderConfirm record missing resource.body")

        return body

    @classmethod
    def _map_header(
        cls,
        body: dict[str, Any],
    ) -> ProductivShipmentHeaders:

        read_only = body.get("readOnly") or {}
        routing = body.get("routingInfo") or {}
        ship_to = body.get("shipTo") or {}
        bill_to = body.get("billTo") or {}

        customer = read_only.get("customerIdentifier") or {}
        facility = read_only.get("facilityIdentifier") or {}
        created_by = read_only.get("createdByIdentifier") or {}
        modified_by = read_only.get("lastModifiedByIdentifier") or {}

        unit_1 = body.get("unit1Identifier") or {}
        unit_2 = body.get("unit2Identifier") or {}

        return ProductivShipmentHeaders(
            order_id=read_only["orderId"],
            reference_num=body.get("referenceNum"),
            po_num=body.get("poNum"),
            external_id=body.get("externalId"),
            fully_allocated=read_only.get("fullyAllocated"),
            is_closed=read_only.get("isClosed"),
            process_date=parse_dt(read_only.get("processDate")),
            pick_started=read_only.get("pickStarted"),
            pick_done_date=parse_dt(read_only.get("pickDoneDate")),
            pick_ticket_print_date=parse_dt(read_only.get("pickTicketPrintDate")),
            pack_started=read_only.get("packStarted"),
            pack_done_date=parse_dt(read_only.get("packDoneDate")),
            small_parcel_ship_date=parse_dt(read_only.get("smallParcelShipDate")),
            parcel_label_type=read_only.get("parcelLabelType"),
            ship_date=parse_dt(read_only.get("shipDate")),
            customer_id=customer.get("id"),
            customer_name=customer.get("name"),
            facility_id=facility.get("id"),
            facility_name=facility.get("name"),
            creation_date=parse_dt(read_only.get("creationDate")),
            created_by_id=created_by.get("id"),
            created_by_name=created_by.get("name"),
            last_modified_date=parse_dt(read_only.get("lastModifiedDate")),
            last_modified_by_id=modified_by.get("id"),
            last_modified_by_name=modified_by.get("name"),
            status=read_only.get("status"),
            charges_pending=read_only.get("chargesPending"),
            earliest_ship_date=parse_dt(body.get("earliestShipDate")),
            notes=body.get("notes"),
            num_units_1=body.get("numUnits1"),
            unit_1_name=unit_1.get("name"),
            num_units_2=body.get("numUnits2"),
            unit_2_name=unit_2.get("name"),
            total_weight=as_decimal(body.get("totalWeight")),
            total_volume=as_decimal(body.get("totalVolume")),
            billing_code=body.get("billingCode"),
            routing_scac_code=routing.get("scacCode"),
            routing_carrier=routing.get("carrier"),
            routing_mode=routing.get("mode"),
            routing_account=routing.get("account"),
            routing_ship_point_zip=routing.get("shipPointZip"),
            routing_bill_of_lading=routing.get("billOfLading"),
            routing_pickup_date=parse_dt(routing.get("pickupDate")),
            routing_tracking_number=routing.get("trackingNumber"),
            ship_to_contact_id=ship_to.get("contactId"),
            ship_to_company_name=ship_to.get("companyName"),
            ship_to_name=ship_to.get("name"),
            ship_to_address_1=ship_to.get("address1"),
            ship_to_address_2=ship_to.get("address2"),
            ship_to_city=ship_to.get("city"),
            ship_to_state=ship_to.get("state"),
            ship_to_zip=ship_to.get("zip"),
            ship_to_country=ship_to.get("country"),
            ship_to_phone=ship_to.get("phoneNumber"),
            ship_to_email=ship_to.get("emailAddress"),
            ship_to_is_residential=ship_to.get("isAddressResidential"),
            ship_to_address_status=ship_to.get("addressStatus"),
            bill_to_contact_id=bill_to.get("contactId"),
            bill_to_company_name=bill_to.get("companyName"),
            bill_to_name=bill_to.get("name"),
            bill_to_address_1=bill_to.get("address1"),
            bill_to_address_2=bill_to.get("address2"),
            bill_to_city=bill_to.get("city"),
            bill_to_state=bill_to.get("state"),
            bill_to_zip=bill_to.get("zip"),
            bill_to_country=bill_to.get("country"),
            bill_to_phone=bill_to.get("phoneNumber"),
            bill_to_email=bill_to.get("emailAddress"),
            bill_to_is_residential=bill_to.get("isAddressResidential"),
            bill_to_address_status=bill_to.get("addressStatus"),
            parcel_response=body.get("parcelResponse"),
        )

    @classmethod
    def _map_items(
        cls,
        body: dict[str, Any],
    ) -> list[ProductivShipmentItems]:

        embedded = body.get("_embedded") or {}

        return [cls._map_item(item) for item in embedded.get(cls.ITEM_REL) or []]

    @staticmethod
    def _map_item(
        data: dict[str, Any],
    ) -> ProductivShipmentItems:

        read_only = data.get("readOnly") or {}
        identifier = data.get("itemIdentifier") or {}
        unit = read_only.get("unitIdentifier") or {}

        return ProductivShipmentItems(
            order_item_id=read_only["orderItemId"],
            fully_allocated=read_only.get("fullyAllocated"),
            unit_name=unit.get("name"),
            original_primary_qty=as_decimal(read_only.get("originalPrimaryQty")),
            row_version=read_only.get("rowVersion"),
            productiv_item_id=identifier.get("id"),
            sku=identifier.get("sku"),
            external_id=data.get("externalId"),
            qty=as_decimal(data.get("qty")),
            weight_imperial=as_decimal(data.get("weightImperial")),
            weight_metric=as_decimal(data.get("weightMetric")),
            fulfill_inv_sale_price=as_decimal(data.get("fulfillInvSalePrice")),
        )

    @classmethod
    def _map_packages(
        cls,
        body: dict[str, Any],
    ) -> list[ProductivShipmentPackages]:

        read_only = body.get("readOnly") or {}

        return [
            cls._map_package(package) for package in read_only.get("packages") or []
        ]

    @classmethod
    def _map_package(
        cls,
        data: dict[str, Any],
    ) -> ProductivShipmentPackages:

        package = ProductivShipmentPackages(
            productiv_package_id=data["packageId"],
            package_type_id=data.get("packageTypeId"),
            length=as_decimal(data.get("length")),
            width=as_decimal(data.get("width")),
            height=as_decimal(data.get("height")),
            weight=as_decimal(data.get("weight")),
            tracking_number=data.get("trackingNumber"),
            create_date=parse_dt(data.get("createDate")),
            oversize=data.get("oversize"),
            ucc128=data.get("ucc128"),
            carton_id=data.get("cartonId"),
        )

        package.contents = [
            cls._map_package_content(content)
            for content in data.get("packageContents") or []
        ]

        return package

    @staticmethod
    def _map_package_content(
        data: dict[str, Any],
    ) -> ProductivShipmentPackageContents:

        identifier = data.get("itemIdentifier") or {}

        return ProductivShipmentPackageContents(
            productiv_package_content_id=data["packageContentId"],
            productiv_package_id=data.get("packageId"),
            productiv_order_item_id=data.get("orderItemId"),
            productiv_receive_item_id=data.get("receiveItemId"),
            qty=as_decimal(data.get("qty")),
            create_date=parse_dt(data.get("createDate")),
            productiv_item_id=identifier.get("id"),
            sku=identifier.get("sku"),
        )

    @classmethod
    def _map_billing_charges(
        cls,
        body: dict[str, Any],
    ) -> list[ProductivShipmentBillingCharges]:

        billing = body.get("billing") or {}

        return [
            cls._map_billing_charge(
                charge,
                sequence=sequence,
            )
            for sequence, charge in enumerate(billing.get("billingCharges") or [])
        ]

    @classmethod
    def _map_billing_charge(
        cls,
        data: dict[str, Any],
        *,
        sequence: int,
    ) -> ProductivShipmentBillingCharges:

        charge = ProductivShipmentBillingCharges(
            sequence=sequence,
            charge_type=data.get("chargeType"),
            subtotal=as_decimal(data.get("subtotal")),
        )

        charge.details = [
            cls._map_billing_detail(detail) for detail in data.get("details") or []
        ]

        return charge

    @staticmethod
    def _map_billing_detail(
        data: dict[str, Any],
    ) -> ProductivShipmentBillingChargeDetails:

        return ProductivShipmentBillingChargeDetails(
            warehouse_transaction_price_calc_id=data.get(
                "warehouseTransactionPriceCalcId"
            ),
            num_units=as_decimal(data.get("numUnits")),
            charge_label=data.get("chargeLabel"),
            unit_description=data.get("unitDescription"),
            charge_per_unit=as_decimal(data.get("chargePerUnit")),
            sku=data.get("sku"),
            system_generated=data.get("systemGenerated"),
        )
