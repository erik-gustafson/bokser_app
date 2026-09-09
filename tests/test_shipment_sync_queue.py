import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateTable

from src.database.models import SosShipmentSync
from src.database.utils.shipment_sync_queue import shipment_sync_upsert
from src.worker.jobs.push_data.sos import sos_shipment_sync as sync_module
from src.worker.jobs.process_data.sutton.process_sutton_reporting import (
    SuttonReportProcessor,
)
from src.worker.jobs.process_data.warehouses.process_shipment_data import (
    add_to_shipment_sync,
)


class ShipmentSyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS sos")
            await connection.execute(CreateTable(SosShipmentSync.__table__))
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.session_patch = patch.object(sync_module, "async_session", self.sessions)
        self.session_patch.start()
        self.addCleanup(self.session_patch.stop)
        self.task = sync_module.SosShipmentSyncTasks.__new__(
            sync_module.SosShipmentSyncTasks
        )
        self.task.sos_client = SimpleNamespace(
            post=AsyncMock(return_value=httpx.Response(200, json={"data": {"id": 123}}))
        )
        self.task._build_shipment_template = AsyncMock(
            return_value={"lines": [{"shipped": 1}]}
        )

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def enqueue(
        self,
        source="productiv",
        source_id="1",
        status="pending",
        payload_hash="original",
    ):
        async with self.sessions() as session:
            row = SosShipmentSync(
                source=source,
                source_id=source_id,
                status=status,
                payload_hash=payload_hash,
                created_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            session.add(row)
            await session.commit()
            return row.id

    async def row(self, row_id):
        async with self.sessions() as session:
            return await session.get(SosShipmentSync, row_id)

    async def test_success_is_committed_and_not_reposted(self):
        row_id = await self.enqueue()
        await self.task.process_shipment_sync()
        row = await self.row(row_id)
        self.assertEqual(
            (row.status, row.attempts, row.sos_shipment_id), ("sent", 1, 123)
        )
        self.assertIsNotNone(row.last_sent_at)
        self.assertIsNone(row.last_error)
        await self.task.process_shipment_sync()
        self.task.sos_client.post.assert_awaited_once()

    async def test_success_survives_later_mapping_failure(self):
        first = await self.enqueue(source_id="1")
        second = await self.enqueue(source_id="2")
        self.task._build_shipment_template.side_effect = [
            {"lines": []},
            ValueError("Source missing"),
        ]
        with self.assertLogs(sync_module.logger, level="ERROR"):
            await self.task.process_shipment_sync()
        self.assertEqual((await self.row(first)).status, "sent")
        failed = await self.row(second)
        self.assertEqual((failed.status, failed.attempts), ("failed", 1))
        self.assertIn("Source missing", failed.last_error)
        await self.task.process_shipment_sync()
        self.task.sos_client.post.assert_awaited_once()

    async def test_rejection_is_failed_and_timeout_is_held(self):
        first = await self.enqueue(source_id="1")
        second = await self.enqueue(source_id="2")
        self.task.sos_client.post.side_effect = [
            httpx.Response(400, text="invalid shipment"),
            httpx.ReadTimeout("lost response"),
        ]
        with self.assertLogs(sync_module.logger, level="ERROR"):
            await self.task.process_shipment_sync()
        self.assertEqual((await self.row(first)).status, "failed")
        held = await self.row(second)
        self.assertEqual((held.status, held.attempts), ("reconcile", 1))
        self.assertIn("reconciliation", held.last_error)
        self.assertEqual(await self.task.get_shipments_to_sync(), [])

    async def test_completion_commit_failure_records_uncertainty_in_fresh_session(self):
        row_id = await self.enqueue()
        actual_commit = sync_module.async_session.class_.commit

        async def fail_sent_commit(session):
            if any(
                isinstance(row, SosShipmentSync) and row.status == "sent"
                for row in session.dirty
            ):
                raise RuntimeError("completion commit unavailable")
            await actual_commit(session)

        with patch.object(self.sessions.class_, "commit", fail_sent_commit):
            with self.assertLogs(sync_module.logger, level="ERROR"):
                await self.task.process_shipment_sync()
        row = await self.row(row_id)
        self.assertEqual(
            (row.status, row.sos_shipment_id, row.attempts), ("reconcile", 123, 1)
        )
        self.assertIn("completion commit unavailable", row.last_error)

    async def test_stale_candidate_cannot_be_claimed_twice(self):
        row_id = await self.enqueue()
        candidate = await self.row(row_id)
        self.task.get_shipments_to_sync = AsyncMock(return_value=[candidate, candidate])
        await self.task.process_shipment_sync()
        self.task.sos_client.post.assert_awaited_once()
        self.assertEqual((await self.row(row_id)).attempts, 1)

    async def test_disabled_ksp_and_inflight_records_are_not_selected(self):
        ksp = await self.enqueue(source="ksp")
        await self.enqueue(source_id="2", status="processing")
        await self.task.process_shipment_sync()
        self.task.sos_client.post.assert_not_awaited()
        self.assertEqual((await self.row(ksp)).attempts, 0)

    async def test_changed_source_during_post_is_not_marked_sent(self):
        row_id = await self.enqueue()

        async def post(**kwargs):
            async with self.sessions() as session:
                await session.execute(shipment_sync_upsert("productiv", "1", "changed"))
                await session.commit()
            return httpx.Response(200, json={"id": 123})

        self.task.sos_client.post.side_effect = post
        with self.assertLogs(sync_module.logger, level="ERROR"):
            await self.task.process_shipment_sync()
        row = await self.row(row_id)
        self.assertEqual(
            (row.status, row.sos_shipment_id, row.payload_hash),
            ("reconcile", 123, "changed"),
        )

    async def test_missing_response_id_is_held(self):
        row_id = await self.enqueue()
        self.task.sos_client.post.return_value = httpx.Response(200, json={"data": {}})
        with self.assertLogs(sync_module.logger, level="ERROR"):
            await self.task.process_shipment_sync()
        self.assertEqual((await self.row(row_id)).status, "reconcile")

    async def test_interrupted_attempt_is_not_reposted(self):
        row_id = await self.enqueue()
        self.task.sos_client.post.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.task.process_shipment_sync()
        self.assertEqual((await self.row(row_id)).status, "processing")
        await self.task.process_shipment_sync()
        self.task.sos_client.post.assert_awaited_once()

    async def test_sutton_and_warehouse_enqueue_use_shared_policy(self):
        frame = pd.DataFrame(
            [
                {
                    "invoice": 12,
                    "style": "SKU",
                    "purchase_order": "PO",
                    "warehouse_batch_number": "BATCH",
                    "qty_shipped": 2,
                }
            ]
        )
        processor = SuttonReportProcessor()
        async with self.sessions() as session:
            await session.run_sync(
                lambda db: processor.post_sales_report_to_sos_ship_sync(db, frame)
            )
            await add_to_shipment_sync(session, "ksp", "REF", {"quantity": 2})
            await session.commit()
            rows = list((await session.scalars(select(SosShipmentSync))).all())
            self.assertEqual({row.source_id for row in rows}, {"12", "REF"})
            for row in rows:
                row.status = "sent"
                row.sos_shipment_id = 123
            await session.commit()
            await session.run_sync(
                lambda db: processor.post_sales_report_to_sos_ship_sync(db, frame)
            )
            await add_to_shipment_sync(session, "ksp", "REF", {"quantity": 2})
            await session.commit()
        for row in rows:
            self.assertEqual((await self.row(row.id)).status, "sent")

    async def test_ingestion_preserves_completion_and_requires_review_for_changes(self):
        for source in ("sutton", "ksp", "productiv"):
            row_id = await self.enqueue(source=source, status="sent")
            async with self.sessions() as session:
                row = await session.get(SosShipmentSync, row_id)
                row.sos_shipment_id = 123
                row.attempts = 2
                await session.commit()
                await session.execute(shipment_sync_upsert(source, "1", "original"))
                await session.commit()
            unchanged = await self.row(row_id)
            self.assertEqual(
                (unchanged.status, unchanged.attempts, unchanged.sos_shipment_id),
                ("sent", 2, 123),
            )
            async with self.sessions() as session:
                await session.execute(shipment_sync_upsert(source, "1", "changed"))
                await session.commit()
            changed = await self.row(row_id)
            self.assertEqual(
                (changed.status, changed.attempts, changed.sos_shipment_id),
                ("reconcile", 2, 123),
            )

    async def test_ingestion_does_not_retry_failed_rows(self):
        row_id = await self.enqueue(status="failed")
        async with self.sessions() as session:
            await session.execute(shipment_sync_upsert("productiv", "1", "changed"))
            await session.commit()
        self.assertEqual((await self.row(row_id)).status, "failed")

    async def test_ksp_mapping_date_and_empty_details(self):
        detail = SimpleNamespace(
            date=datetime(2026, 9, 8, tzinfo=timezone.utc),
            tracking_no="TRACK",
            carrier="CARRIER",
            items=[SimpleNamespace(item="SKU", quantity=2)],
        )
        shipment = SimpleNamespace(
            cust_ref="REF", cust_po_no="PO", ship_details=[detail]
        )
        session = SimpleNamespace(scalar=AsyncMock(return_value=shipment))
        self.task.get_sos_so_id_by_po = AsyncMock(return_value=[SimpleNamespace(id=1)])
        self.task.get_sos_shipment_template = AsyncMock(return_value={"lines": []})
        candidate = SimpleNamespace(source="ksp", source_id="REF")
        build = sync_module.SosShipmentSyncTasks._build_shipment_template
        result = await build(self.task, session, candidate)
        self.assertEqual(result["date"], "2026-09-08T00:00:00+00:00")
        self.assertEqual(result["lines"][0]["shipped"], 2)
        for details in ([], [SimpleNamespace(items=[])]):
            shipment.ship_details = details
            with self.assertRaisesRegex(ValueError, "No KSP shipment items"):
                await build(self.task, session, candidate)


if __name__ == "__main__":
    unittest.main()
