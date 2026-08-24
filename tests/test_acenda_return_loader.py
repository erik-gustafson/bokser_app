from __future__ import annotations

import asyncio
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, select, text
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import NO_VALUE

from src.database.models.acenda_models import (
    AcendaOrderHeaders,
    AcendaOrderItems,
    AcendaOrderLineDiscounts,
    AcendaOrderLineKitItems,
    AcendaOrderReturns,
    AcendaShipAdviceHeaders,
    AcendaShipAdviceItems,
)
from src.worker.jobs.process_data.acenda import process_acenda_data
from src.worker.jobs.process_data.acenda.process_acenda_data import (
    AcendaPayloadMapper,
    RETRYABLE_LAKE_FILE_STATUSES,
    _acenda_payload_type_from_entity,
    load_acenda_records,
)


TIMESTAMP = "2026-08-18T20:03:56.104Z"

RETURN_SAMPLE = {
    "id": 901,
    "created_at": TIMESTAMP,
    "created_by": "service-account-channel_integration_system",
    "updated_at": TIMESTAMP,
    "updated_by": "service-account-channel_integration_system",
    "fields": {},
    "order_id": 101,
    "order_item_id": 201,
    "quantity": 1,
    "rma": "RMA-901",
    "license_plate_number": "LP-901",
    "reason": "damaged",
    "status": "pending",
    "restock_inventory": False,
    "return_required": True,
    "advance_refund": False,
    "method": "mail",
    "carrier": "UPS",
    "return_tracking": [{"number": "1Z901"}],
    "extended_order": {"ignored": True},
}

ORDER_SAMPLE = {
    "id": 101,
    "created_at": TIMESTAMP,
    "created_by": "service-account-channel_integration_system",
    "updated_at": TIMESTAMP,
    "updated_by": "service-account-channel_integration_system",
    "fields": {},
    "order_number": 100101,
    "sales_channel_id": 1,
    "order_item": [
        {
            "id": 201,
            "order_id": 101,
            "created_at": TIMESTAMP,
            "created_by": "service-account-channel_integration_system",
            "updated_at": TIMESTAMP,
            "updated_by": "service-account-channel_integration_system",
            "sku": "RETURN-SKU",
        }
    ],
    "returns": [RETURN_SAMPLE],
}


class _NestedTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False


class _FakeAsyncSession:
    def __init__(self, existing_updated_at: datetime | None = None) -> None:
        self.existing_updated_at = existing_updated_at
        self.merged: list[object] = []

    def begin_nested(self) -> _NestedTransaction:
        return _NestedTransaction()

    async def scalar(self, statement) -> datetime | None:
        return self.existing_updated_at

    async def merge(self, value: object) -> object:
        self.merged.append(value)
        return value


class AcendaReturnMapperTests(unittest.TestCase):
    def test_direct_entity_dispatch_and_extended_field_mapping(self) -> None:
        self.assertEqual(_acenda_payload_type_from_entity("acenda_returns"), "return")

        mapped = AcendaPayloadMapper().map_acenda_return(RETURN_SAMPLE)

        self.assertEqual(mapped.id, 901)
        self.assertEqual(mapped.order_id, 101)
        self.assertEqual(mapped.order_item_id, 201)
        self.assertEqual(mapped.status, "pending")
        self.assertEqual(mapped.return_tracking, [{"number": "1Z901"}])
        self.assertNotIn("extended_order", inspect(mapped).mapper.columns)

    def test_return_requires_identifiers_and_updated_timestamp(self) -> None:
        mapper = AcendaPayloadMapper()

        for field_name in ("id", "order_id", "order_item_id", "updated_at"):
            with self.subTest(field_name=field_name):
                invalid = deepcopy(RETURN_SAMPLE)
                invalid[field_name] = None

                with self.assertRaisesRegex(ValueError, field_name):
                    mapper.map_acenda_return(invalid)

    def test_order_mapper_does_not_populate_returns_relationship(self) -> None:
        order = AcendaPayloadMapper().map_acenda_order(ORDER_SAMPLE)

        self.assertIs(inspect(order).attrs.returns.loaded_value, NO_VALUE)


class AcendaReturnPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        with self.engine.begin() as connection:
            connection.execute(text("ATTACH DATABASE ':memory:' AS acenda"))
            connection.execute(text("PRAGMA foreign_keys = ON"))
            for table in (
                AcendaOrderHeaders.__table__,
                AcendaOrderItems.__table__,
                AcendaOrderLineDiscounts.__table__,
                AcendaOrderLineKitItems.__table__,
                AcendaOrderReturns.__table__,
                AcendaShipAdviceHeaders.__table__,
                AcendaShipAdviceItems.__table__,
            ):
                table.create(connection)

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_direct_return_updates_and_later_order_merge_preserves_it(self) -> None:
        mapper = AcendaPayloadMapper()

        with Session(self.engine) as session:
            session.add(mapper.map_acenda_order(ORDER_SAMPLE))
            session.commit()

            self.assertIsNone(session.get(AcendaOrderReturns, 901))

            session.add(mapper.map_acenda_return(RETURN_SAMPLE))
            session.commit()

            updated_return = deepcopy(RETURN_SAMPLE)
            updated_return["updated_at"] = "2026-08-19T20:03:56.104Z"
            updated_return["status"] = "received"
            session.merge(mapper.map_acenda_return(updated_return))
            session.commit()

            later_order = deepcopy(ORDER_SAMPLE)
            later_order["updated_at"] = "2026-08-20T20:03:56.104Z"
            later_order["returns"][0]["status"] = "stale-order-copy"
            session.merge(mapper.map_acenda_order(later_order))
            session.commit()

            persisted_return = session.scalar(
                select(AcendaOrderReturns).where(AcendaOrderReturns.id == 901)
            )
            self.assertIsNotNone(persisted_return)
            self.assertEqual(persisted_return.status, "received")


class AcendaReturnLoaderTests(unittest.TestCase):
    def test_direct_return_load_and_stale_skip(self) -> None:
        new_session = _FakeAsyncSession()
        new_result = asyncio.run(
            load_acenda_records(
                session=new_session,
                records=[RETURN_SAMPLE],
                payload_type="return",
            )
        )

        self.assertEqual(new_result, {"loaded": 1, "skipped": 0, "failed": []})
        self.assertEqual(len(new_session.merged), 1)
        self.assertIsInstance(new_session.merged[0], AcendaOrderReturns)

        newer_existing = datetime(2026, 8, 19, tzinfo=timezone.utc)
        stale_session = _FakeAsyncSession(existing_updated_at=newer_existing)
        stale_result = asyncio.run(
            load_acenda_records(
                session=stale_session,
                records=[RETURN_SAMPLE],
                payload_type="return",
            )
        )

        self.assertEqual(stale_result, {"loaded": 0, "skipped": 1, "failed": []})
        self.assertEqual(stale_session.merged, [])

    def test_invalid_return_fails_individually(self) -> None:
        invalid = deepcopy(RETURN_SAMPLE)
        invalid["order_item_id"] = None
        session = _FakeAsyncSession()

        result = asyncio.run(
            load_acenda_records(
                session=session,
                records=[RETURN_SAMPLE, invalid],
                payload_type="return",
            )
        )

        self.assertEqual(result["loaded"], 1)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(len(result["failed"]), 1)
        self.assertIn("order_item_id", result["failed"][0]["error"])
        self.assertIn("PARTIAL", RETRYABLE_LAKE_FILE_STATUSES)

    def test_scheduled_loader_processes_returns_after_orders(self) -> None:
        result = {"claimed": 0, "loaded": 0, "skipped": 0, "failed_files": []}

        with patch.object(
            process_acenda_data,
            "load_acenda_lake_files",
            new_callable=AsyncMock,
            return_value=result,
        ) as load_files:
            asyncio.run(process_acenda_data.acenda_load_to_db())

        entities = [call.kwargs["entity_name"] for call in load_files.await_args_list]
        order_indexes = [
            entities.index(entity)
            for entity in ("new_orders", "updated_orders", "acenda_orders")
        ]
        self.assertGreater(entities.index("acenda_returns"), max(order_indexes))


if __name__ == "__main__":
    unittest.main()
