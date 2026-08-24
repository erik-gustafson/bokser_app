from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session, configure_mappers, selectinload

from src.database.models.acenda_models import (
    AcendaFulfillmentItems,
    AcendaFulfillments,
    AcendaFulfillmentTracking,
    AcendaShipAdviceHeaders,
)
from src.worker.jobs.process_data.acenda.process_acenda_data import (
    AcendaPayloadMapper,
    _acenda_payload_type_from_entity,
)


FULFILLMENT_SAMPLE = [
    {
        "id": 57488,
        "created_at": "2026-08-18T20:03:56.104Z",
        "created_by": "service-account-channel_integration_system",
        "updated_at": "2026-08-18T20:03:56.104Z",
        "updated_by": "service-account-channel_integration_system",
        "fields": {},
        "ship_advice_id": 56983,
        "tracking_info": [{"number": "1Z7F0F280332188401", "url": ""}],
        "carrier": "UPS",
        "date_shipped": "2026-08-18T20:03:56.04Z",
        "other_carrier": "",
        "shipping_method": "SHIPSTORE",
        "status": "shipped",
        "type": "shipment",
        "cost": 0,
        "is_ltl": False,
        "fulfillment_items": [
            {"quantity": 1, "ship_advice_item_id": 65531, "external_id": None},
            {"quantity": 2, "ship_advice_item_id": 65532, "external_id": None},
        ],
        "external_id": None,
        "ship_from": None,
    },
    {
        "id": 57487,
        "created_at": "2026-08-18T20:03:55.975Z",
        "created_by": "service-account-channel_integration_system",
        "updated_at": "2026-08-18T20:03:55.975Z",
        "updated_by": "service-account-channel_integration_system",
        "fields": {},
        "ship_advice_id": 56980,
        "tracking_info": [{"number": "1Z7F0F280337171197", "url": ""}],
        "carrier": "UPS",
        "date_shipped": "2026-08-18T20:03:55.906Z",
        "other_carrier": "",
        "shipping_method": "SHIPSTORE",
        "status": "shipped",
        "type": "shipment",
        "cost": 0,
        "is_ltl": False,
        "fulfillment_items": [
            {"quantity": 1, "ship_advice_item_id": 65580, "external_id": None}
        ],
        "external_id": None,
        "ship_from": None,
    },
]


class AcendaFulfillmentMapperTests(unittest.TestCase):
    def test_mappers_configure_and_entity_dispatches(self) -> None:
        configure_mappers()
        self.assertEqual(
            _acenda_payload_type_from_entity("acenda_fulfillments"),
            "fulfillment",
        )

    def test_maps_sample_parent_tracking_and_items(self) -> None:
        mapper = AcendaPayloadMapper()

        first, second = [
            mapper.map_acenda_fulfillment(record) for record in FULFILLMENT_SAMPLE
        ]

        self.assertEqual(first.id, 57488)
        self.assertEqual(first.ship_advice_id, 56983)
        self.assertEqual(first.fulfillment_type, "shipment")
        self.assertEqual(first.date_shipped.microsecond, 40000)
        self.assertEqual(
            [tracking.tracking_number for tracking in first.tracking],
            ["1Z7F0F280332188401"],
        )
        self.assertEqual(
            [(item.ship_advice_item_id, item.quantity) for item in first.items],
            [(65531, 1), (65532, 2)],
        )
        self.assertEqual(second.id, 57487)
        self.assertEqual(len(second.items), 1)

    def test_intentionally_excluded_fields_are_not_columns(self) -> None:
        fulfillment_columns = set(inspect(AcendaFulfillments).columns.keys())
        tracking_columns = set(inspect(AcendaFulfillmentTracking).columns.keys())
        item_columns = set(inspect(AcendaFulfillmentItems).columns.keys())

        self.assertTrue(
            {
                "created_by",
                "updated_by",
                "other_carrier",
                "external_id",
                "ship_from",
            }.isdisjoint(fulfillment_columns)
        )
        self.assertNotIn("url", tracking_columns)
        self.assertNotIn("external_id", item_columns)


class AcendaFulfillmentRelationshipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        with self.engine.begin() as connection:
            connection.execute(text("ATTACH DATABASE ':memory:' AS acenda"))
            for table in (
                AcendaShipAdviceHeaders.__table__,
                AcendaFulfillments.__table__,
                AcendaFulfillmentTracking.__table__,
                AcendaFulfillmentItems.__table__,
            ):
                table.create(connection)

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_tracking_is_available_directly_from_ship_advice(self) -> None:
        timestamp = datetime(2026, 8, 18, tzinfo=timezone.utc)
        payload = deepcopy(FULFILLMENT_SAMPLE[0])
        payload["tracking_info"].append({"number": "SECOND", "url": "ignored"})

        with Session(self.engine) as session:
            session.add(
                AcendaShipAdviceHeaders(
                    id=56983,
                    order_id=1,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
            session.add(AcendaPayloadMapper().map_acenda_fulfillment(payload))
            session.commit()

            ship_advice = session.scalar(
                select(AcendaShipAdviceHeaders).options(
                    selectinload(AcendaShipAdviceHeaders.fulfillment_tracking)
                )
            )

            self.assertIsNotNone(ship_advice)
            self.assertEqual(
                sorted(
                    tracking.tracking_number
                    for tracking in ship_advice.fulfillment_tracking
                ),
                ["1Z7F0F280332188401", "SECOND"],
            )

    def test_cross_entity_ids_do_not_require_ship_advice_rows(self) -> None:
        payload = deepcopy(FULFILLMENT_SAMPLE[1])
        payload["ship_advice_id"] = 999999

        with Session(self.engine) as session:
            fulfillment = AcendaPayloadMapper().map_acenda_fulfillment(payload)
            session.add(fulfillment)
            session.commit()

            self.assertIsNotNone(session.get(AcendaFulfillments, fulfillment.id))

    def test_merge_removes_missing_owned_children(self) -> None:
        mapper = AcendaPayloadMapper()
        original = deepcopy(FULFILLMENT_SAMPLE[0])

        with Session(self.engine) as session:
            session.add(mapper.map_acenda_fulfillment(original))
            session.commit()
            session.expunge_all()

            updated = deepcopy(original)
            updated["updated_at"] = "2026-08-19T20:03:56.104Z"
            updated["fulfillment_items"] = updated["fulfillment_items"][:1]
            updated["tracking_info"] = []
            session.merge(mapper.map_acenda_fulfillment(updated))
            session.commit()

            item_count = len(
                session.scalars(
                    select(AcendaFulfillmentItems).where(
                        AcendaFulfillmentItems.fulfillment_id == 57488
                    )
                ).all()
            )
            tracking_count = len(
                session.scalars(
                    select(AcendaFulfillmentTracking).where(
                        AcendaFulfillmentTracking.fulfillment_id == 57488
                    )
                ).all()
            )

            self.assertEqual(item_count, 1)
            self.assertEqual(tracking_count, 0)


if __name__ == "__main__":
    unittest.main()
