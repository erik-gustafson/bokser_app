from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from pydantic import ValidationError

from src.database.models.acenda_models import AcendaOrderHeaders, AcendaOrderItems
from src.database.models.sos_models import SosSalesOrderHeader, SosSalesOrderLine
from src.worker.jobs.push_data.sos.sos_payload_mapper import (
    SosOrderReferences,
    SosSalesOrderPayloadMapper,
)


class SosSalesOrderPayloadMapperTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.mapper = SosSalesOrderPayloadMapper()
        self.order_date = datetime(2026, 7, 15, 12, 30, tzinfo=timezone.utc)

    def test_acenda_and_sos_orders_produce_equivalent_payloads(self) -> None:
        acenda_order = self._acenda_order()
        sos_order = self._sos_order()

        acenda_payload = self.mapper.map_acenda_order(
            acenda_order,
            SosOrderReferences(
                customer_id=501,
                location_id=601,
                item_ids={acenda_order.items[0].id: 701},
            ),
        ).to_payload()
        sos_payload = self.mapper.map_sos_order(sos_order).to_payload()

        self.assertEqual(acenda_payload, sos_payload)
        self.assertEqual(acenda_payload["date"], "2026-07-15T12:30:00Z")
        self.assertEqual(acenda_payload["customerPO"], "PO-42")
        self.assertEqual(acenda_payload["lines"][0]["unitprice"], 12.5)
        self.assertEqual(
            acenda_payload["shipping"]["address"]["stateProvince"],
            "NC",
        )

    def test_create_payload_omits_database_and_response_fields(self) -> None:
        payload = self.mapper.map_sos_order(self._sos_order()).to_payload()

        forbidden = {
            "id",
            "syncToken",
            "sales_order_id",
            "linkedTransactions",
            "total",
        }
        self.assertTrue(forbidden.isdisjoint(payload))
        self.assertTrue(forbidden.isdisjoint(payload["lines"][0]))
        self.assertNotIn("billing", payload)

    def test_missing_acenda_item_mapping_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "no valid SOS item mapping"):
            self.mapper.map_acenda_order(
                self._acenda_order(),
                SosOrderReferences(customer_id=501, item_ids={}),
            )

    def test_missing_sos_customer_is_rejected(self) -> None:
        order = self._sos_order()
        order.customer_id = None

        with self.assertRaisesRegex(ValueError, "no valid customer_id"):
            self.mapper.map_sos_order(order)

    def test_empty_order_is_rejected(self) -> None:
        order = self._sos_order()
        order.lines = []

        with self.assertRaises(ValidationError):
            self.mapper.map_sos_order(order)

    def test_invalid_quantity_is_rejected(self) -> None:
        order = self._sos_order()
        order.lines[0].quantity = 0

        with self.assertRaises(ValidationError):
            self.mapper.map_sos_order(order)

    def test_missing_quantity_is_rejected_with_context(self) -> None:
        order = self._sos_order()
        order.lines[0].quantity = None

        with self.assertRaisesRegex(ValueError, "line 998 has no quantity"):
            self.mapper.map_sos_order(order)

    async def test_payload_can_be_passed_unchanged_to_client(self) -> None:
        client = AsyncMock()
        payload = self.mapper.map_sos_order(self._sos_order()).to_payload()

        await client.post("/salesorder/", json_data=payload)

        client.post.assert_awaited_once_with(
            "/salesorder/",
            json_data=payload,
        )

    def _acenda_order(self) -> AcendaOrderHeaders:
        order = AcendaOrderHeaders(
            id=100,
            created_at=self.order_date,
            updated_at=self.order_date,
            ordered_at=self.order_date,
            order_number=42,
            purchase_order="PO-42",
            fields={"comment": "Marketplace order"},
            ship_first_name="Ada",
            ship_last_name="Lovelace",
            ship_company="Example Co",
            ship_address_1="1 Main St",
            ship_city="Charlotte",
            ship_state="NC",
            ship_postal_code="28202",
            ship_country="US",
            ship_email="ada@example.com",
            ship_phone_number="555-0100",
        )
        order.items = [
            AcendaOrderItems(
                id=200,
                order_id=100,
                created_at=self.order_date,
                updated_at=self.order_date,
                product_name="Widget",
                quantity=2,
                unit_price=12.5,
            )
        ]
        return order

    def _sos_order(self) -> SosSalesOrderHeader:
        order = SosSalesOrderHeader(
            id=999,
            sync_token=7,
            number="42",
            date=self.order_date,
            customer_id=501,
            location_id=601,
            customer_po="PO-42",
            comment="Marketplace order",
            shipping_company="Example Co",
            shipping_contact="Ada Lovelace",
            shipping_phone="555-0100",
            shipping_email="ada@example.com",
            shipping_address_line_1="1 Main St",
            shipping_city="Charlotte",
            shipping_state_province="NC",
            shipping_postal_code="28202",
            shipping_country="US",
            total=25.0,
        )
        order.lines = [
            SosSalesOrderLine(
                id=998,
                sales_order_id=999,
                item_id=701,
                description="Widget",
                quantity=2,
                unit_price=12.5,
            )
        ]
        return order


if __name__ == "__main__":
    unittest.main()
