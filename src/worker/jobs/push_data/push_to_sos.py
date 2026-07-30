from __future__ import annotations

import asyncio
import logging
import json
import hashlib
from datetime import datetime, timezone
from typing import Optional, Any, Sequence
from sqlalchemy import select, func, cast, Text, BigInteger
from sqlalchemy.orm import contains_eager
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from src.integrations.sos_client import SOSClient

from src.database.database import async_session
from src.database.models import (
    AcendaOrderHeaders,
    AcendaOrderItems,
    SosSalesOrderHeader,
    SosItem,
    SosSalesOrderSync,
    ErrorLog,
)

from .sos_payload_mapper import (
    SosSalesOrderPayloadMapper,
    SosSalesOrderCreate,
    SosSalesOrderLineCreate,
)

from .sos_payload_mapper import SosItemsForLoad

from src.core.config import settings

logger = logging.getLogger(__name__)


class SosPostError(Exception):
    pass


class AcendaOrderPush:
    SOURCE = "acenda"
    LOOKBACK_DAYS = 1
    MKT_START_DATE = datetime(
        2026,
        6,
        1,
        tzinfo=timezone.utc,
    )

    def __init__(self) -> None:
        self.sos_items = SosItemsForLoad()
        self.sos_mapper = SosSalesOrderPayloadMapper(self.sos_items)
        self.sos_so_sync = SosSalesOrderSyncService()

    async def send_to_sos(self) -> None:
        """
        Load unsynced Acenda order lines, map them to SOS payloads,
        and create pending SOS sync records.

        Mapping errors are logged per order without stopping the
        remaining orders.
        """

        open_orders = await self.load_open_acenda_db_orders()

        if not open_orders:
            logger.info("No unsynced Acenda order lines found")
            return

        skus = self._get_order_skus(open_orders)

        if skus:
            await self.sos_items.load_sos_items_by_sku(skus=skus)

        mapped_orders, error_logs = self._map_orders(open_orders)

        if error_logs:
            async with async_session() as session:
                async with session.begin():
                    if error_logs:
                        session.add_all(error_logs)

        if not mapped_orders:
            logger.warning(
                "No Acenda orders were successfully mapped",
                extra={"open_order_count": len(open_orders)},
            )
            return

        sync_rows = [
            self.sos_so_sync._build_sync_row(
                source=self.SOURCE,
                header_key=str(order.number),
                line_key=str(line.id),
                payload_hash=self.sos_so_sync._hash_payload(line.to_payload()),
                status="pending",
            )
            for order in mapped_orders
            for line in order.lines
        ]

        if not sync_rows:
            logger.warning("Mapped Acenda orders did not contain any lines")
            return

        # This transaction must finish before posting to SOS.
        async with async_session() as session:
            async with session.begin():
                await self.sos_so_sync._upsert_sync_rows(
                    session=session,
                    rows=sync_rows,
                )

                tasks = [
                    self._post_to_sos_and_log(mapped_order=order)
                    for order in mapped_orders
                ]

                results = await asyncio.gather(*tasks)
                for result, error in results:
                    if result:
                        print("YAY")
                    if error:
                        print("Boo")

    async def _post_to_sos_and_log(self, mapped_order: SosSalesOrderCreate):

        async with async_session() as session:
            async with session.begin():
                try:
                    result = await self.sos_so_sync.post_and_record(
                        session=session,
                        mapped_order=mapped_order,
                        sos_prefix=settings.sos_default_mkt_prefix,
                        source="acenda",
                    )
                    return result, None

                except Exception as exc:
                    logger.exception(
                        "Failed to POST Acenda order to SOS",
                        extra={
                            "order_number": mapped_order.number,
                            "customer_po": mapped_order.customer_po,
                        },
                    )

                    error = ErrorLog(
                        error_type="SOS POST Failure",
                        message=str(exc.args[0]),
                        context=exc.args[1].to_payload(),
                    )

                    return None, error

    async def load_open_acenda_db_orders(
        self,
    ) -> list[AcendaOrderHeaders]:
        """
        Return Acenda order headers containing at least one unsynced line.

        Each header's ``items`` relationship contains only the lines that
        do not already have a matching SOS sync record.
        """
        async with async_session() as session:
            sos_order_sync_exists = (
                select(SosSalesOrderSync.id)
                .where(
                    SosSalesOrderSync.source == self.SOURCE,
                    cast(
                        SosSalesOrderSync.source_line_key,
                        Text,
                    )
                    == cast(AcendaOrderItems.id, Text),
                )
                .correlate(AcendaOrderItems)
                .exists()
            )

            stmt = (
                select(AcendaOrderHeaders)
                .join(AcendaOrderHeaders.items)
                .options(
                    contains_eager(AcendaOrderHeaders.items),
                )
                .where(
                    AcendaOrderHeaders.created_at >= self.MKT_START_DATE,
                    AcendaOrderHeaders.sales_channel_id == 1,
                    ~sos_order_sync_exists,
                )
                .order_by(
                    AcendaOrderHeaders.id.asc(),
                    AcendaOrderItems.id.asc(),
                )
            )

            result = await session.execute(stmt)

            return list(result.unique().scalars().all())

    def _get_order_skus(
        self,
        orders: list[AcendaOrderHeaders],
    ) -> tuple[str, ...]:
        """
        Return the unique, non-null SKUs needed to map the orders.
        """
        return tuple(
            {
                item.sku
                for order in orders
                for item in order.items
                if item.sku is not None
            }
        )

    def _map_orders(
        self,
        orders: list[AcendaOrderHeaders],
    ) -> tuple[list[SosSalesOrderCreate], list[ErrorLog]]:
        """
        Map all orders while isolating failures to individual orders.
        """
        mapped_orders: list[SosSalesOrderCreate] = []
        error_logs: list[ErrorLog] = []

        for order in orders:
            mapped_order, error_log = self._map_order(order)

            if mapped_order is not None:
                mapped_orders.append(mapped_order)

            if error_log is not None:
                error_logs.append(error_log)

        return mapped_orders, error_logs

    def _map_order(
        self,
        order: AcendaOrderHeaders,
    ) -> tuple[SosSalesOrderCreate | None, ErrorLog | None]:
        try:
            payload = self.sos_mapper.map_acenda_order(order)
            return payload, None

        except Exception as exc:
            logger.exception(
                "Failed to map Acenda order",
                extra={"order_id": order.id},
            )

            error = ErrorLog(
                error_type="SOS Item Missing",
                message=str(exc.args[0]),
                context=exc.args[1].to_json(),
            )

            return None, error


class SosSalesOrderSyncService:
    """SosSalesOrderSyncTasks takes database records for Rithum and Guest Supply and creates SOS Sales Orders"""

    def __init__(self):
        self.sos_client = SOSClient()

    async def post_and_record(
        self,
        session: AsyncSession,
        mapped_order: SosSalesOrderCreate,
        sos_prefix: str,
        source: str,
    ):

        duplicate_msg = "Duplicate sales order number. Please choose another number."

        def _is_duplicate_order_number(resp) -> bool:
            if resp.status_code != 400:
                return False
            try:
                msg = (resp.json() or {}).get("message") or ""
            except Exception:
                msg = resp.text or ""
            return msg.strip() == duplicate_msg

        payload = mapped_order.to_payload()

        current_number = str(payload["number"])

        attempts = 0
        resp = None
        success = False

        while attempts < 20:
            payload["number"] = f"{sos_prefix}-{current_number}"
            resp = await self.sos_client.post(
                path_or_url="/salesorder", json_data=payload
            )

            if resp.status_code == 200:
                data = (resp.json() or {}).get("data") or {}
                posted_rows = [line for line in mapped_order.lines]
                await self._record_success(
                    session,
                    source,
                    mapped_order.number,
                    posted_rows,
                    data,
                )
                success = True
                current_number = await self._next_order_number(
                    session,
                    prefix=sos_prefix,
                    bump=True,
                    current_number=current_number,
                )
                break

            if _is_duplicate_order_number(resp):
                attempts += 1
                current_number = await self._next_order_number(
                    session,
                    prefix=sos_prefix,
                    bump=True,
                    current_number=current_number,
                )
                continue

            break  # non-duplicate failure

        if (
            not success
            and attempts >= 20
            and resp is not None
            and _is_duplicate_order_number(resp)
        ):
            fallback_number = await self._next_order_number(
                session,
                prefix=sos_prefix,
                use_timestamp=True,
            )
            payload["number"] = f"{sos_prefix}-{fallback_number}"

            resp = await self.sos_client.post(
                path_or_url="/salesorder", json_data=payload
            )

            if resp.status_code == 200:
                data = (resp.json() or {}).get("data") or {}
                posted_rows = [line for line in mapped_order.lines]
                await self._record_success(
                    session,
                    source,
                    mapped_order.number,
                    posted_rows,
                    data,
                )
                success = True
                current_number = await self._next_order_number(
                    session,
                    prefix=sos_prefix,
                    bump=True,
                    current_number=fallback_number,
                )

        if not success:
            try:
                err_body = resp.json() if resp is not None else {}
            except Exception:
                err_body = {
                    "status_code": resp.status_code if resp is not None else None,
                    "text": resp.text if resp is not None else "",
                }

            await self._record_failure(
                session,
                source,
                mapped_order.number,
                [line for line in mapped_order.lines],
                err_body,
            )

            raise SosPostError("Sos Sales Order Post Failure", mapped_order)

        return success

    async def _record_success(
        self,
        session: AsyncSession,
        source: str,
        sync_header_key: str,
        rows: list[SosSalesOrderLineCreate],
        sos_data: dict[str, Any],
    ) -> None:
        sos_order_id = sos_data.get("id")
        line_map = {
            str(line.get("lineNumber")): line
            for line in (sos_data.get("lines") or [])
            if line.get("lineNumber") is not None
        }
        now = datetime.now(timezone.utc)

        for row in rows:
            line_key = row.id
            sos_line = (
                line_map.get(str(row.line_number))
                if row.line_number is not None
                else None
            )

            sync_row = await self._get_or_create_sync(
                session,
                source=source,
                header_key=sync_header_key,
                line_key=line_key,
                default_status="pending",
            )

            sync_row.status = "sent"
            sync_row.attempts = (sync_row.attempts or 0) + 1
            sync_row.last_error = None
            sync_row.sos_order_id = sos_order_id
            sync_row.sos_line_id = sos_line.get("id") if sos_line else None
            sync_row.last_sent_at = now

    async def _record_failure(
        self,
        session: AsyncSession,
        source: str,
        sync_header_key: str,
        rows: list[SosSalesOrderLineCreate],
        error: dict[str, Any],
    ) -> None:

        for row in rows:
            line_key = row.id
            sync_row = await self._get_or_create_sync(
                session,
                source=source,
                header_key=sync_header_key,
                line_key=line_key,
                default_status="pending",
            )
            sync_row.status = "failed"
            sync_row.attempts = (sync_row.attempts or 0) + 1
            sync_row.last_error = json.dumps(error)

    async def _upsert_sync_rows(
        self, session: AsyncSession, rows: list[SosSalesOrderSync]
    ) -> None:
        for row in rows:
            existing = await self._find_sync_row(
                session,
                source=row.source,
                line_key=row.source_line_key,
            )
            if existing:
                existing.status = row.status
                existing.last_error = row.last_error
                if row.payload_hash:
                    existing.payload_hash = row.payload_hash
            else:
                session.add(row)

    async def _find_sync_row(
        self,
        session: AsyncSession,
        *,
        source: str,
        line_key: str,
    ) -> SosSalesOrderSync | None:
        return (
            (
                await session.execute(
                    select(SosSalesOrderSync)
                    .where(
                        SosSalesOrderSync.source == source,
                        SosSalesOrderSync.source_line_key == line_key,
                    )
                    .order_by(SosSalesOrderSync.id.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )

    async def _next_order_number(
        self,
        session: AsyncSession,
        prefix: str,
        bump: bool = False,
        current_number: Optional[str] = None,
        use_timestamp: bool = False,
    ) -> str:
        """
        Get the next API order number.
        - If current_number is provided, increment it when bump=True (used for retries and subsequent orders).
        - Otherwise pull the max from SOS headers; if none exists or use_timestamp=True, start from a timestamp base.
        """

        if current_number is not None:
            if prefix == settings.sos_default_mkt_prefix:
                return current_number + (".1" if bump else "")
            return str(int(current_number) + (1 if bump else 0))

        last_num = None
        if not use_timestamp:
            last_num = (
                await session.execute(
                    select(
                        func.max(
                            func.cast(
                                func.replace(
                                    SosSalesOrderHeader.number, f"{prefix}-", ""
                                ),
                                BigInteger,
                            )
                        )
                    ).where(
                        SosSalesOrderHeader.number.like(f"{prefix}-%"),
                    )
                )
            ).scalar_one_or_none()

        base_num = (
            int(last_num)
            if last_num is not None
            else int(datetime.utcnow().strftime("%y%m%d%H%M"))
        )

        next_num = base_num + 1
        if bump:
            next_num += 1
        return str(next_num)

    def _hash_payload(self, payload: dict[str, Any]) -> str:
        as_text = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(as_text.encode("utf-8")).hexdigest()

    async def _get_or_create_sync(
        self,
        session: AsyncSession,
        *,
        source: str,
        header_key: str,
        line_key: str,
        default_status: str,
    ) -> SosSalesOrderSync:
        existing = await self._find_sync_row(
            session,
            source=source,
            line_key=line_key,
        )
        if existing:
            return existing

        sync_row = self._build_sync_row(
            source=source,
            header_key=header_key,
            line_key=line_key,
            status=default_status,
        )
        session.add(sync_row)
        return sync_row

    def _build_sync_row(
        self,
        source: str,
        header_key: str,
        line_key: str,
        status: str,
        payload_hash: str | None = None,
        error: Optional[str] = None,
    ) -> SosSalesOrderSync:
        return SosSalesOrderSync(
            source=source,
            source_header_key=header_key,
            source_line_key=line_key,
            payload_hash=payload_hash,
            status=status,
            last_error=error,
        )
