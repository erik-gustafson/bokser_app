import logging

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import String, cast, exists, literal, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from src.database.utils.formatter_tools import *
from src.database.database import async_session
from src.database.models import *
from src.integrations.sos_client import SOSClient
from src.worker.jobs.process_data.sos.sos_payload_mappers import SosPayloadMapper

logger = logging.getLogger(__name__)


@dataclass
class ShipmentLine:
    item: str
    sos_line_id: int | None
    quantity: int
    date: str | None


@dataclass
class ShipmentData:
    sos_sales_order_id: int
    tracking_no: str | None
    carrier: str | None
    number: str
    date: str
    lines: list[ShipmentLine]


class SosShipmentSyncTasks:

    def __init__(self):
        self.sos_client = SOSClient()
        self.sos_mapper = SosPayloadMapper()

    async def process_shipment_sync(self) -> None:

        shipments_to_sync = await self.get_shipments_to_sync()

        async with async_session() as session:

            for _sync in shipments_to_sync:

                ship_data = None
                _ship_data: ShipmentData | None = None

                try:
                    async with session.begin_nested():

                        # =====================================================
                        # SUTTON
                        # =====================================================
                        if _sync.source == "sutton":

                            stmt = select(SuttonSalesReport).where(
                                cast(SuttonSalesReport.invoice, String)
                                == _sync.source_id
                            )

                            result = await session.scalars(stmt)
                            ship_data = list(result.all())

                            if not ship_data:
                                logger.error(
                                    f"Sutton Ship Data Not Found in DB: "
                                    f"source_id={_sync.source_id}"
                                )
                                continue

                            mapped_sales_order_list = await self.get_sos_so_id_by_po(
                                ship_data[0].purchase_order
                            )

                            if not mapped_sales_order_list:
                                logger.error(
                                    f"Sales Order Not Found with Sutton PO: "
                                    f"{ship_data[0].purchase_order}"
                                )
                                continue

                            if len(mapped_sales_order_list) > 1:
                                logger.error(
                                    f"Multiple Sales Orders Found with Sutton PO: "
                                    f"{ship_data[0].purchase_order}"
                                )
                                continue

                            lines: list[ShipmentLine] = []

                            for record in ship_data:

                                item = record.customer_sku

                                if not item:
                                    item = await self.get_upc(record.style)

                                if not item:
                                    logger.error(
                                        f"Unable to determine item for "
                                        f"Sutton invoice={_sync.source_id}, "
                                        f"style={record.style}"
                                    )
                                    continue

                                lines.append(
                                    ShipmentLine(
                                        item=item,
                                        sos_line_id=None,
                                        quantity=record.qty_shipped or 0,
                                        date=None,
                                    )
                                )

                            if not lines:
                                logger.error(
                                    f"No valid Sutton shipment lines found: "
                                    f"source_id={_sync.source_id}"
                                )
                                continue

                            _ship_data = ShipmentData(
                                sos_sales_order_id=(mapped_sales_order_list[0].id),
                                date=self._serialize_datetime(ship_data[0].date),
                                tracking_no=None,
                                carrier=ship_data[0].carrier,
                                number=str(ship_data[0].invoice),
                                lines=lines,
                            )

                        # =====================================================
                        # KSP
                        # =====================================================
                        # elif _sync.source == "ksp":

                        #     stmt = (
                        #         select(KSPShipmentHeaders)
                        #         .options(
                        #             selectinload(
                        #                 KSPShipmentHeaders.ship_details
                        #             ).selectinload(KSPShipmentDetails.items)
                        #         )
                        #         .where(
                        #             cast(
                        #                 KSPShipmentHeaders.cust_ref,
                        #                 String,
                        #             )
                        #             == _sync.source_id
                        #         )
                        #     )

                        #     ship_data = await session.scalar(stmt)

                        #     if ship_data is None:
                        #         logger.error(
                        #             f"KSP Ship Data Not Found in DB: "
                        #             f"source_id={_sync.source_id}"
                        #         )
                        #         continue

                        #     mapped_sales_order_list = await self.get_sos_so_id_by_po(
                        #         ship_data.cust_po_no
                        #     )

                        #     if not mapped_sales_order_list:
                        #         logger.error(
                        #             f"Sales Order Not Found with KSP PO: "
                        #             f"{ship_data.cust_po_no}"
                        #         )
                        #         continue

                        #     if len(mapped_sales_order_list) > 1:
                        #         logger.error(
                        #             f"Multiple Sales Orders Found with KSP PO: "
                        #             f"{ship_data.cust_po_no}"
                        #         )
                        #         continue

                        #     lines = [
                        #         ShipmentLine(
                        #             item=item.item,
                        #             sos_line_id=None,
                        #             quantity=item.quantity,
                        #             date=self._serialize_datetime(detail.date)
                        #         )
                        #         for detail in ship_data.ship_details
                        #         for item in detail.items
                        #     ]

                        #     _ship_data = ShipmentData(
                        #         sos_sales_order_id=(mapped_sales_order_list[0].id),
                        #         date=self._serialize_datetime(lines[0].date),
                        #         tracking_no=str(
                        #             [num.tracking_no for num in ship_data.ship_details][
                        #                 0
                        #             ]
                        #         ),
                        #         carrier=str(
                        #             [num.carrier for num in ship_data.ship_details][0]
                        #         ),
                        #         number=f"KSP-{ship_data.cust_ref}",
                        #         lines=lines,
                        #     )

                        # =====================================================
                        # PRODUCTIV
                        # =====================================================
                        elif _sync.source == "productiv":

                            stmt = (
                                select(ProductivShipmentHeaders)
                                .options(selectinload(ProductivShipmentHeaders.items))
                                .where(
                                    cast(
                                        ProductivShipmentHeaders.order_id,
                                        String,
                                    )
                                    == _sync.source_id
                                )
                            )

                            ship_data = await session.scalar(stmt)

                            if ship_data is None:
                                logger.error(
                                    f"Productiv Ship Data Not Found in DB: "
                                    f"source_id={_sync.source_id}"
                                )
                                continue

                            lines = [
                                ShipmentLine(
                                    item=str(item.sku),
                                    sos_line_id=as_int(item.external_id),
                                    quantity=as_int(item.qty),
                                    date=None,
                                )
                                for item in ship_data.items
                            ]

                            _ship_data = ShipmentData(
                                sos_sales_order_id=as_int(ship_data.external_id),
                                date=self._serialize_datetime(ship_data.ship_date),
                                tracking_no=ship_data.routing_tracking_number,
                                carrier=ship_data.routing_carrier,
                                number=str(ship_data.order_id),
                                lines=lines,
                            )

                        # =====================================================
                        # INVALID SOURCE
                        # =====================================================
                        else:
                            logger.error(f"Sync Source Not Valid: {_sync.source}")
                            continue

                        # =====================================================
                        # VALIDATE MAPPING
                        # =====================================================
                        if _ship_data is None:
                            logger.error(
                                f"Unable to build shipment data for "
                                f"source={_sync.source}, "
                                f"source_id={_sync.source_id}"
                            )
                            continue

                        # =====================================================
                        # GET SOS SHIPMENT TEMPLATE
                        # =====================================================
                        template = await self.get_sos_shipment_template(
                            _ship_data.sos_sales_order_id
                        )

                        if not template:
                            logger.error(
                                f"No SOS Template Returned for "
                                f"{_ship_data.sos_sales_order_id}"
                            )

                            _sync.status = "failed"
                            _sync.last_error = (
                                f"No SOS shipment template returned for "
                                f"sales_order_id={_ship_data.sos_sales_order_id}"
                            )
                            _sync.last_sent_at = datetime.now(timezone.utc)
                            _sync.attempts += 1

                            continue

                        # =====================================================
                        # HEADER VALUES
                        # =====================================================
                        template["trackingNumber"] = _ship_data.tracking_no
                        template["number"] = _ship_data.number
                        template["date"] = _ship_data.date
                        # Only include carrier if one is available.
                        if _ship_data.carrier:
                            template["carrier"] = {"name": _ship_data.carrier}

                        # =====================================================
                        # MAP SHIPMENT LINES
                        # =====================================================
                        template_lines = template.get("lines", [])

                        new_lines: list[dict[str, Any]] = []

                        next_line_number = len(template_lines) + 1

                        for ship_line in _ship_data.lines:

                            matched = False

                            for template_line in template_lines:

                                linked_transaction = (
                                    template_line.get("linkedTransaction") or {}
                                )

                                template_sos_line_id = linked_transaction.get("id")

                                template_item_data = template_line.get("item") or {}

                                template_item = template_item_data.get("name")

                                # -----------------------------------------
                                # Match using SOS sales order line ID first
                                # -----------------------------------------
                                if (
                                    ship_line.sos_line_id is not None
                                    and ship_line.sos_line_id == template_sos_line_id
                                ):

                                    template_line["shipped"] = (
                                        template_line.get(
                                            "shipped",
                                            0,
                                        )
                                        + ship_line.quantity
                                    )

                                    matched = True
                                    break

                                # -----------------------------------------
                                # Fall back to item / UPC matching
                                # -----------------------------------------
                                if template_item == ship_line.item:

                                    template_line["shipped"] = (
                                        template_line.get(
                                            "shipped",
                                            0,
                                        )
                                        + ship_line.quantity
                                    )

                                    matched = True
                                    break

                            # ---------------------------------------------
                            # Item isn't represented by an SOS template line
                            # ---------------------------------------------
                            if not matched:

                                new_lines.append(
                                    {
                                        "item": {
                                            "name": ship_line.item,
                                        },
                                        "lineNumber": (next_line_number),
                                        "shipped": (ship_line.quantity),
                                        "uom": {
                                            "name": "EA",
                                        },
                                    }
                                )

                                next_line_number += 1

                        # Add unmatched shipment lines after matching is done.
                        template_lines.extend(new_lines)

                        # Keep only lines that actually shipped.
                        template["lines"] = [
                            line
                            for line in template_lines
                            if line.get("shipped", 0) > 0
                        ]

                        if not template["lines"]:
                            logger.error(
                                f"No shipment lines remaining after mapping: "
                                f"source={_sync.source}, "
                                f"source_id={_sync.source_id}"
                            )
                            continue

                        # =====================================================
                        # POST TO SOS
                        # =====================================================
                        response = await self.sos_client.post(
                            path_or_url="shipment",
                            json_data=template,
                        )

                        if response.status_code != 200:
                            logger.error(
                                f"SOS Shipment Create Failed: "
                                f"source={_sync.source}, "
                                f"source_id={_sync.source_id}, "
                                f"status={response.status_code}, "
                                f"response={response.text}"
                            )

                            _sync.status = "failed"
                            _sync.last_error = response.text

                            continue

                        shipment_response = response.json()

                        # =====================================================
                        # UPDATE SYNC RECORD
                        # =====================================================
                        _sync.status = "sent"

                        _sync.sos_shipment_id = shipment_response.get("id")

                        _sync.last_error = None
                        _sync.last_sent_at = datetime.now(timezone.utc)
                        _sync.attempts += 1

                except Exception as exc:

                    logger.exception(
                        f"Failed to sync shipment: "
                        f"source={_sync.source}, "
                        f"source_id={_sync.source_id}"
                    )

                    _sync.status = "failed"
                    _sync.last_error = str(exc)
                    _sync.last_sent_at = datetime.now(timezone.utc)
                    _sync.attempts += 1

            await session.commit()

    async def get_shipments_to_sync(
        self,
    ) -> list[SosShipmentSync]:

        sync_delay = datetime.now(timezone.utc) - timedelta(minutes=15)

        async with async_session() as session:

            stmt = select(SosShipmentSync).where(
                SosShipmentSync.status == "pending",
                SosShipmentSync.created_at <= sync_delay,
            )

            result = await session.scalars(stmt)

            return list(result.all())

    async def direct_load_to_sync_table(self) -> None:

        async with async_session() as session:

            sources = [
                ("sutton", SuttonSalesReport),
                ("ksp", KSPShipmentHeaders),
                ("productiv", ProductivShipmentHeaders),
            ]

            cutoff_date = datetime(2026, 8, 27)

            for source_name, model in sources:

                if source_name == "sutton":
                    source_id = model.invoice
                    _date = model.date

                elif source_name == "ksp":
                    source_id = model.cust_ref
                    _date = model.delivered_to_wms_date

                elif source_name == "productiv":
                    source_id = model.order_id
                    _date = model.ship_date

                else:
                    logger.error(f"Source name invalid: {source_name}")
                    continue

                source_id_str = cast(source_id, String)

                source_rows = select(
                    literal(source_name),
                    source_id_str,
                ).where(
                    _date >= cutoff_date,
                    ~exists(
                        select(1).where(
                            SosShipmentSync.source == source_name,
                            SosShipmentSync.source_id == source_id_str,
                        )
                    ),
                )

                stmt = (
                    insert(SosShipmentSync)
                    .from_select(
                        [
                            "source",
                            "source_id",
                        ],
                        source_rows,
                    )
                    .on_conflict_do_nothing(
                        constraint="ux_sos_shipment_sync_source_key"
                    )
                )

                await session.execute(stmt)

            await session.commit()

    async def get_sos_so_id_by_po(
        self,
        purchase_order: str,
    ) -> list[SosSalesOrderHeader] | None:

        mapped_list: list[SosSalesOrderHeader] = []

        try:
            result = await self.sos_client.get(
                path_or_url="/salesorder/",
                params={
                    "query": purchase_order,
                    "status": "open",
                },
            )

            if result.status_code != 200:
                logger.error(
                    f"SOS Sales Order Lookup Failed: "
                    f"PO={purchase_order}, "
                    f"status={result.status_code}, "
                    f"response={result.text}"
                )
                return None

            response_data: dict[str, Any] = result.json()

            data = response_data.get("data", [])

            for record in data:
                mapped_record = self.sos_mapper.map_sales_order(data=record)

                mapped_list.append(mapped_record)

            return mapped_list

        except Exception as exc:
            logger.exception(f"Get SOS ID by PO Failed: {exc}")
            return None

    async def get_sos_shipment_template(
        self,
        id: int,
    ) -> dict[str, Any]:

        response = await self.sos_client.get(
            path_or_url=(f"/shipment/populateFromsalesorder/{id}")
        )

        if response.status_code != 200:
            logger.error(
                f"SOS Shipment Template Request Failed: "
                f"sales_order_id={id}, "
                f"status={response.status_code}, "
                f"response={response.text}"
            )
            return {}

        template = response.json().get("data")

        if not isinstance(template, dict):
            return {}

        return template

    async def get_upc(
        self,
        sku: str,
    ) -> str | None:

        if not sku:
            return None

        _sku = sku[:6]

        response = await self.sos_client.get(
            path_or_url="/item",
            params={
                "query": _sku,
            },
        )

        if response.status_code != 200:
            logger.error(f"No SOS Item Found for sku: {_sku}")
            return None

        data = response.json().get("data", [])

        if not data:
            logger.error(f"No SOS Item Data Returned for sku: {_sku}")
            return None

        item: dict[str, Any] = data[0]

        return item.get("name")

    def _serialize_datetime(self, value: date | datetime | None) -> str:
        if value is None:
            return datetime.now(timezone.utc).isoformat()
        if isinstance(value, datetime):
            dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        dt = datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
        return dt.isoformat()
