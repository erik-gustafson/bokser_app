from __future__ import annotations

import unittest

from src.worker.jobs.process_data.sos.process_sos_data import (
    SOS_ENTITY_TYPES,
    SosPayloadMapper,
)


class SosPayloadMapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mapper = SosPayloadMapper()

    def test_maps_sales_order_graph_and_linked_transactions(self) -> None:
        order = self.mapper.map_sales_order(
            {
                "id": 10,
                "syncToken": 2,
                "customer": {
                    "id": 20,
                    "name": "Customer",
                    "fullname": "Customer",
                },
                "billing": {
                    "company": "Billing Co",
                    "address": {"line1": "1 Main", "city": "Charlotte"},
                },
                "linkedInvoices": [
                    {
                        "id": 30,
                        "transactionType": "inv",
                        "refNumber": "INV-30",
                        "lineNumber": 1,
                    }
                ],
                "lines": [
                    {
                        "id": 40,
                        "lineNumber": 1,
                        "item": {"id": 50, "name": "Item"},
                        "unitprice": 12.5,
                        "linkedTransaction": {
                            "id": 60,
                            "transactionType": "SO",
                            "refNumber": "SO-60",
                            "lineNumber": 2,
                        },
                    }
                ],
            }
        )

        self.assertEqual(order.customer_id, 20)
        self.assertEqual(order.billing_address_line_1, "1 Main")
        self.assertEqual(order.linked_transactions[0].type, "inv")
        self.assertEqual(order.lines[0].unit_price, 12.5)
        self.assertEqual(order.lines[0].linked_transactions[0].type, "SO")

    def test_maps_item_receipt_other_costs(self) -> None:
        receipt = self.mapper.map_item_receipt(
            {
                "id": 100,
                "syncToken": 1,
                "otherCosts": [
                    {
                        "id": 101,
                        "lineNumber": 3,
                        "item": {"id": 102, "name": "Freight"},
                        "vendor": {"id": 103, "name": "Carrier"},
                        "class": {"id": 104, "name": "B2B"},
                        "amount": 25.5,
                        "bill": True,
                    }
                ],
            }
        )

        other_cost = receipt.other_costs[0]
        self.assertEqual(other_cost.item_receipt_id, 100)
        self.assertEqual(other_cost.item_name, "Freight")
        self.assertEqual(other_cost.vendor_name, "Carrier")
        self.assertEqual(other_cost.amount, 25.5)
        self.assertTrue(other_cost.bill)

    def test_maps_sales_order_channel_and_priority_references(self) -> None:
        order = self.mapper.map_sales_order(
            {
                "id": 10,
                "channel": {"id": 1, "name": "DTC"},
                "department": "Unused department",
                "priority": {"id": 2, "name": "Normal"},
            }
        )

        self.assertEqual(order.channel_id, 1)
        self.assertEqual(order.channel_name, "DTC")
        self.assertEqual(order.department, "Unused department")
        self.assertEqual(order.priority_id, 2)
        self.assertEqual(order.priority_name, "Normal")

    def test_maps_invoice_string_channel_to_name(self) -> None:
        invoice = self.mapper.map_invoice(
            {
                "id": 20,
                "channel": "Wholesale",
            }
        )

        self.assertIsNone(invoice.channel_id)
        self.assertEqual(invoice.channel_name, "Wholesale")

    def test_maps_shipment_channel_and_string_priority(self) -> None:
        shipment = self.mapper.map_shipment(
            {
                "id": 30,
                "channel": {"id": 3, "name": "Marketplace"},
                "priority": "Expedited",
            }
        )

        self.assertEqual(shipment.channel_id, 3)
        self.assertEqual(shipment.channel_name, "Marketplace")
        self.assertIsNone(shipment.priority_id)
        self.assertEqual(shipment.priority_name, "Expedited")

    def test_only_modeled_endpoint_entities_are_claimed(self) -> None:
        self.assertIn("updated_sales_orders", SOS_ENTITY_TYPES)
        self.assertIn("updated_items", SOS_ENTITY_TYPES)
        self.assertNotIn("new_sales_orders", SOS_ENTITY_TYPES)
        self.assertNotIn("all_sales_orders", SOS_ENTITY_TYPES)
        self.assertNotIn("updated_payments", SOS_ENTITY_TYPES)
        self.assertNotIn("updated_purchase_orders", SOS_ENTITY_TYPES)


if __name__ == "__main__":
    unittest.main()
