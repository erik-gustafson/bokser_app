from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from src.database.models.acenda_models import AcendaOrderHeaders, AcendaOrderItems


class AcendaModelSerializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.timestamp = datetime(2026, 7, 28, 12, 30, tzinfo=timezone.utc)

    def test_order_header_to_dict_is_json_safe(self) -> None:
        order = AcendaOrderHeaders(
            id=100,
            created_at=self.timestamp,
            updated_at=self.timestamp,
            ordered_at=self.timestamp,
            order_number=42,
            sales_channel_id=7,
            fields={"nested": {"values": [1, "two", None]}},
        )
        order.items = []

        result = order.to_dict()

        self.assertEqual(result["created_at"], self.timestamp.isoformat())
        self.assertEqual(result["ordered_at"], self.timestamp.isoformat())
        self.assertNotIn("items", result)
        self.assertNotIn("ship_advice_headers", result)
        json.dumps(result)

    def test_order_item_to_dict_is_json_safe(self) -> None:
        item = AcendaOrderItems(
            id=200,
            order_id=100,
            created_at=self.timestamp,
            updated_at=self.timestamp,
            expected_shipping_date=self.timestamp,
            sku="SKU-200",
        )

        result = item.to_dict()

        self.assertEqual(result["updated_at"], self.timestamp.isoformat())
        self.assertEqual(
            result["expected_shipping_date"],
            self.timestamp.isoformat(),
        )
        self.assertNotIn("ship_advice_items", result)
        json.dumps(result)


if __name__ == "__main__":
    unittest.main()
