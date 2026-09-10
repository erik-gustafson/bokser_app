import logging


from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import String, cast, exists, literal, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from src.database.utils.formatter_tools import *
from src.database.database import async_session
from src.database.models import *
from src.integrations.sos_client import SOSClient
from src.integrations._base_client.base_client import RetryConfig
from src.worker.jobs.process_data.sos.sos_payload_mappers import SosPayloadMapper

from src.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ShipmentLine:
    item: str
    sos_line_id: int | None
    quantity: int
    date: str | None


@dataclass
class ShipmentData:
    warehouse: str
    sos_sales_order_id: int
    tracking_no: str | None
    carrier: str | None
    number: str
    date: str
    lines: list[ShipmentLine]


class SosShipmentSyncTasks:

    def __init__(self):
        self.sos_client = SOSClient(
            retry=RetryConfig(max_attempts=1)
        )  # Do not automatically retry after an uncertain response.
        self.sos_mapper = SosPayloadMapper()

    async def process_shipment_sync(self) -> None:
        for candidate in await self.get_shipments_to_sync():
            # An atomic claim prevents concurrent workers and crash recovery from reposting.
            async with async_session() as session:
                claimed = await session.scalar(
                    update(SosShipmentSync)
                    .where(
                        SosShipmentSync.id == candidate.id,
                        SosShipmentSync.status == "pending",
                    )
                    .values(
                        status="processing",
                        attempts=SosShipmentSync.attempts + 1,
                        last_sent_at=datetime.now(timezone.utc),
                        last_error=None,
                    )
                    .returning(SosShipmentSync)
                )
                await session.commit()
            if claimed is None:
                continue

            post_started = False
            shipment_id = None
            try:
                async with async_session() as session:
                    template = await self._build_shipment_template(session, claimed)
                post_started = True
                response = await self.sos_client.post(
                    path_or_url="shipment", json_data=template
                )
                if not 200 <= response.status_code < 300:
                    # Server errors and timeouts may occur after remote creation.
                    if (
                        400 <= response.status_code < 500
                        and response.status_code != 408
                    ):
                        post_started = False
                    raise ValueError(
                        f"SOS shipment create returned {response.status_code}: {response.text}"
                    )
                shipment_id = self._shipment_id(response.json())
                logger.info(
                    "SOS shipment accepted: queue_id=%s shipment_id=%s",
                    claimed.id,
                    shipment_id,
                )
                await self._finish_attempt(claimed, "sent", None, shipment_id)
                logger.info(
                    "Shipment queue completion committed: queue_id=%s", claimed.id
                )
            except Exception as exc:
                status = "reconcile" if post_started else "failed"
                error = str(exc)
                if post_started:
                    error = f"SOS post outcome requires reconciliation; shipment_id={shipment_id}: {error}"
                logger.exception(
                    "Shipment sync %s: queue_id=%s: %s", status, claimed.id, error
                )
                try:
                    # Use a fresh transaction even when the completion commit failed.
                    await self._finish_attempt(claimed, status, error, shipment_id)
                except Exception:
                    logger.exception(
                        "Unable to persist shipment outcome; queue_id=%s remains held for reconciliation",
                        claimed.id,
                    )

    async def _finish_attempt(
        self,
        claimed: SosShipmentSync,
        status: str,
        error: str | None,
        shipment_id: int | None = None,
    ) -> None:
        async with async_session() as session:
            row = await session.scalar(
                select(SosShipmentSync)
                .where(SosShipmentSync.id == claimed.id)
                .with_for_update()
            )
            if row is None:
                raise ValueError(f"Shipment queue record {claimed.id} disappeared")
            # The commit may have succeeded even if the connection dropped on acknowledgement.
            if row.status == "sent" and row.sos_shipment_id == shipment_id:
                return
            if row.status != "processing" or row.payload_hash != claimed.payload_hash:
                row.status = "reconcile"
                row.last_error = (
                    error
                    or "Source changed during shipment processing; reconcile against SOS"
                )
            else:
                row.status = status
                row.last_error = error
            if shipment_id is not None:
                row.sos_shipment_id = shipment_id
            await session.commit()
            if status == "sent" and row.status != "sent":
                raise ValueError(
                    "Source changed during posting; queue held for reconciliation"
                )

    @staticmethod
    def _shipment_id(payload: Any) -> int:
        data = payload.get("data", payload) if isinstance(payload, dict) else None
        value = data.get("id") if isinstance(data, dict) else None
        if isinstance(value, bool):
            raise ValueError("SOS shipment response has no valid shipment ID")
        try:
            shipment_id = int(str(value))
        except (ValueError, TypeError) as exc:
            raise ValueError("SOS shipment response has no valid shipment ID") from exc
        if shipment_id <= 0:
            raise ValueError("SOS shipment response has no valid shipment ID")
        return shipment_id

    async def _build_shipment_template(
        self,
        session: AsyncSession,
        _sync: SosShipmentSync,
    ) -> dict[str, Any]:
        # =====================================================
        # SUTTON
        # =====================================================
        if _sync.source == "sutton":

            stmt = select(SuttonSalesReport).where(
                cast(SuttonSalesReport.invoice, String) == _sync.source_id
            )

            result = await session.scalars(stmt)
            ship_data = list(result.all())

            if not ship_data:
                raise ValueError(
                    f"Sutton Ship Data Not Found in DB: " f"source_id={_sync.source_id}"
                )

            mapped_sales_order_list = await self.get_sos_so_id_by_po(
                ship_data[0].purchase_order
            )

            if not mapped_sales_order_list:
                raise ValueError(
                    f"Sales Order Not Found with Sutton PO: "
                    f"{ship_data[0].purchase_order}"
                )

            if len(mapped_sales_order_list) > 1:
                raise ValueError(
                    f"Multiple Sales Orders Found with Sutton PO: "
                    f"{ship_data[0].purchase_order}"
                )

            lines: list[ShipmentLine] = []

            for record in ship_data:

                if record.style[-2:] == "CD":
                    _warehouse = "CDC"
                else:
                    _warehouse = "SAY"

                # item = record.customer_sku

                # if not item:
                item = await self.get_upc(record.style)

                if not item:
                    raise ValueError(
                        f"Unable to determine item for "
                        f"Sutton invoice={_sync.source_id}, "
                        f"style={record.style}"
                    )

                lines.append(
                    ShipmentLine(
                        item=item,
                        sos_line_id=None,
                        quantity=record.qty_shipped or 0,
                        date=None,
                    )
                )

            if not lines:
                raise ValueError(
                    f"No valid Sutton shipment lines found: "
                    f"source_id={_sync.source_id}"
                )

            _ship_data = ShipmentData(
                warehouse=_warehouse,
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
        # Mapping is testable, but KSP is excluded by get_shipments_to_sync().
        elif _sync.source == "ksp":

            stmt = (
                select(KSPShipmentHeaders)
                .options(
                    selectinload(KSPShipmentHeaders.ship_details).selectinload(
                        KSPShipmentDetails.items
                    )
                )
                .where(
                    cast(
                        KSPShipmentHeaders.cust_ref,
                        String,
                    )
                    == _sync.source_id
                )
            )

            ship_data = await session.scalar(stmt)

            if ship_data is None:
                raise ValueError(
                    f"KSP Ship Data Not Found in DB: " f"source_id={_sync.source_id}"
                )

            mapped_sales_order_list = await self.get_sos_so_id_by_po(
                ship_data.cust_po_no
            )

            if not mapped_sales_order_list:
                raise ValueError(
                    f"Sales Order Not Found with KSP PO: " f"{ship_data.cust_po_no}"
                )

            if len(mapped_sales_order_list) > 1:
                raise ValueError(
                    f"Multiple Sales Orders Found with KSP PO: "
                    f"{ship_data.cust_po_no}"
                )

            lines = [
                ShipmentLine(
                    item=item.item,
                    sos_line_id=None,
                    quantity=item.quantity,
                    date=self._serialize_datetime(detail.date),
                )
                for detail in ship_data.ship_details
                for item in detail.items
            ]

            if not lines:
                raise ValueError("No KSP shipment items found")

            _carrier = str([num.carrier for num in ship_data.ship_details][0]).lower()

            if _carrier in settings.KSP_SMALL_PARCEL_CODES:
                carrier = settings.KSP_SMALL_PARCEL_CODES.get(_carrier, ("Missing"))[0]
            elif (
                str([num.method for num in ship_data.ship_details][0]).lower()
                == "shipstore"
            ):
                carrier = "Small Parcel"
            else:
                carrier = "LTL"

            _ship_data = ShipmentData(
                warehouse="KSP",
                sos_sales_order_id=(mapped_sales_order_list[0].id),
                date=self._serialize_datetime(ship_data.ship_details[0].date),
                tracking_no=str([num.tracking_no for num in ship_data.ship_details][0]),
                carrier=carrier,
                number=f"KSP-{ship_data.cust_ref}",
                lines=lines,
            )

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
                raise ValueError(
                    f"Productiv Ship Data Not Found in DB: "
                    f"source_id={_sync.source_id}"
                )

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
                warehouse="CLT",
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
            raise ValueError(f"Sync Source Not Valid: {_sync.source}")

        # =====================================================
        # VALIDATE MAPPING
        # =====================================================
        if _ship_data is None:
            raise ValueError(
                f"Unable to build shipment data for "
                f"source={_sync.source}, "
                f"source_id={_sync.source_id}"
            )

        # =====================================================
        # GET SOS SHIPMENT TEMPLATE
        # =====================================================
        template = await self.get_sos_shipment_template(_ship_data.sos_sales_order_id)

        if not template:
            raise ValueError(
                f"No SOS shipment template for sales_order_id={_ship_data.sos_sales_order_id}"
            )

        # =====================================================
        # HEADER VALUES
        # =====================================================
        template["location"] = self.get_sos_shipment_location(_ship_data.warehouse)
        template["trackingNumber"] = _ship_data.tracking_no
        template["number"] = _ship_data.number
        template["date"] = _ship_data.date
        # Only include carrier if one is available.
        if _ship_data.carrier:
            _carrier_name = _ship_data.carrier.upper()
            carrier_id = self.get_sos_shipment_method_id(carrier_name=_carrier_name)
            template["shippingMethod"] = {"id": carrier_id}
            if _carrier_name.upper() not in settings.SMALL_PARCEL_CARRIERS:
                template["carrier"] = {"name": _carrier_name}

        # =====================================================
        # MAP SHIPMENT LINES
        # =====================================================
        template_lines = template.get("lines", [])

        new_lines: list[dict[str, Any]] = []

        next_line_number = len(template_lines) + 1

        for ship_line in _ship_data.lines:

            matched = False

            for template_line in template_lines:

                linked_transaction = template_line.get("linkedTransaction") or {}

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
            line for line in template_lines if line.get("shipped", 0) > 0
        ]

        if not template["lines"]:
            raise ValueError(
                f"No shipment lines remaining after mapping: "
                f"source={_sync.source}, "
                f"source_id={_sync.source_id}"
            )

        return template

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

            cutoff_date = datetime(2026, 5, 1)

            for source_name, model in sources:

                if source_name == "sutton":
                    continue
                    source_id = model.invoice
                    _date = model.date

                elif source_name == "ksp":
                    source_id = model.cust_ref
                    _date = model.delivered_to_wms_date

                elif source_name == "productiv":
                    continue
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
                    model.cust_po_no.startswith("9"),
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

    def get_sos_shipment_location(self, warehouse_code: str) -> dict[str, Any]:
        normalized = str(warehouse_code or "").strip().upper()
        location = settings.SOS_SHIPMENT_LOCATIONS.get(normalized)
        if isinstance(location, dict) and location.get("id") and location.get("name"):
            return {"id": int(location["id"]), "name": str(location["name"])}
        return {
            "id": int(settings.SOS_DEFAULT_LOCATION_ID),
            "name": str(settings.SOS_DEFAULT_LOCATION_NAME),
        }

    def get_sos_shipment_method_id(self, carrier_name: str | None) -> int:
        carrier = str(carrier_name or "").strip().upper()
        if "UPS" in carrier:
            key = "UPS"
        elif "FEDEX" in carrier or carrier.startswith("FDX"):
            key = "FEDEX"
        elif "DHL" in carrier:
            key = "DHL"
        elif "USPS" in carrier:
            key = "USPS"
        elif "SMALL PARCEL" in carrier:
            key = "Small Parcel"
        else:
            key = "LTL"
        return int(
            settings.SOS_SHIPMENT_METHOD_IDS.get(
                key, settings.SOS_SHIPMENT_METHOD_IDS.get("LTL", 5)
            )
        )
