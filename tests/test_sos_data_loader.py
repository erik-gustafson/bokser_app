from __future__ import annotations

import unittest
from typing import get_args

from src.core.config import settings

from src.worker.jobs.process_data.sos.process_sos_data import (
    PAYLOAD_MODELS,
    SOS_ENTITY_TYPES,
    PayloadType,
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

    def test_maps_purchase_order_graph_and_linked_receipts(self) -> None:
        purchase_order = self.mapper.map_purchase_order(
            {
                "id": 100,
                "vendor": {"id": 101, "name": "Vendor"},
                "customer": {
                    "id": 102,
                    "name": "Customer",
                    "fullname": "Customer Full Name",
                },
                "location": {"id": 103, "name": "Warehouse"},
                "terms": {"id": 104, "name": "Net 30"},
                "currency": {"id": 105, "name": "USD"},
                "taxCode": {"id": 106, "name": "Tax"},
                "shippingMethod": {"id": 107, "name": "Ground"},
                "billing": {"address": {"line1": "1 Vendor Way"}},
                "shipping": {"address": {"line1": "2 Warehouse Way"}},
                "linkedTransaction": self._linked_transaction(108),
                "linkedReceipts": [self._linked_transaction(109)],
                "customFields": [self._custom_field(110)],
                "lines": [self._transaction_line(111)],
            }
        )

        self.assertEqual(purchase_order.vendor_id, 101)
        self.assertEqual(purchase_order.customer_fullname, "Customer Full Name")
        self.assertEqual(purchase_order.billing_address_line_1, "1 Vendor Way")
        self.assertEqual(purchase_order.lines[0].purchase_order_id, 100)
        self.assertEqual(purchase_order.custom_fields[0].custom_field_id, 110)
        self.assertEqual(
            {transaction.linked_transaction_id for transaction in purchase_order.linked_transactions},
            {108, 109},
        )
        self.assertEqual(
            purchase_order.lines[0].linked_transactions[0].linked_transaction_id,
            211,
        )

    def test_maps_sales_receipt_graph_and_payment_method(self) -> None:
        receipt = self.mapper.map_sales_receipt(
            {
                "id": 200,
                "customer": {"id": 201, "name": "Customer"},
                "location": {"id": 202, "name": "Store"},
                "paymentMethod": {
                    "id": 203,
                    "name": "Card",
                    "syncToken": 4,
                    "sosPayType": "CreditCard",
                },
                "depositAccount": {"id": 204, "name": "Undeposited"},
                "channel": {"id": 205, "name": "Retail"},
                "priority": {"id": 206, "name": "Normal"},
                "orderStage": {"id": 207, "name": "Closed"},
                "shippingMethod": {"id": 208, "name": "Pickup"},
                "linkedTransaction": self._linked_transaction(209),
                "customFields": [self._custom_field(210)],
                "lines": [self._transaction_line(211)],
            }
        )

        self.assertEqual(receipt.payment_method_id, 203)
        self.assertEqual(receipt.payment_method_sync_token, 4)
        self.assertEqual(receipt.payment_method_sos_pay_type, "CreditCard")
        self.assertEqual(receipt.deposit_account_id, 204)
        self.assertEqual(receipt.lines[0].sales_receipt_id, 200)
        self.assertEqual(receipt.custom_fields[0].sales_receipt_id, 200)
        self.assertEqual(receipt.linked_transactions[0].linked_transaction_id, 209)

    def test_maps_estimate_graph(self) -> None:
        estimate = self.mapper.map_estimate(
            {
                "id": 300,
                "customer": {"id": 301, "name": "Customer"},
                "channel": {"id": 302, "name": "Wholesale"},
                "linkedTransaction": self._linked_transaction(303),
                "customFields": [self._custom_field(304)],
                "lines": [self._transaction_line(305)],
            }
        )

        self.assertEqual(estimate.customer_id, 301)
        self.assertEqual(estimate.channel_id, 302)
        self.assertEqual(estimate.lines[0].estimate_id, 300)
        self.assertEqual(estimate.custom_fields[0].estimate_id, 300)
        self.assertEqual(estimate.linked_transactions[0].estimate_id, 300)

    def test_maps_return_graph(self) -> None:
        returned = self.mapper.map_return(
            {
                "id": 400,
                "customer": {"id": 401, "name": "Customer"},
                "currency": {"id": 402, "name": "USD"},
                "location": {"id": 403, "name": "Returns"},
                "channel": {"id": 404, "name": "Marketplace"},
                "shippingMethod": {"id": 405, "name": "Ground"},
                "linkedTransaction": self._linked_transaction(406),
                "customFields": [self._custom_field(407)],
                "lines": [self._transaction_line(408)],
            }
        )

        self.assertEqual(returned.customer_id, 401)
        self.assertEqual(returned.shipping_method_id, 405)
        self.assertEqual(returned.lines[0].return_id, 400)
        self.assertEqual(returned.custom_fields[0].return_id, 400)
        self.assertEqual(returned.linked_transactions[0].return_id, 400)

    def test_maps_rma_graph(self) -> None:
        rma = self.mapper.map_rma(
            {
                "id": 500,
                "customer": {"id": 501, "name": "Customer"},
                "location": {"id": 502, "name": "Returns"},
                "channel": {"id": 503, "name": "Retail"},
                "shippingMethod": {"id": 504, "name": "Freight"},
                "billing": {"address": {"city": "Charlotte"}},
                "shipping": {"address": {"city": "Raleigh"}},
                "linkedTransaction": self._linked_transaction(505),
                "customFields": [self._custom_field(506)],
                "lines": [self._transaction_line(507)],
            }
        )

        self.assertEqual(rma.customer_id, 501)
        self.assertEqual(rma.billing_city, "Charlotte")
        self.assertEqual(rma.shipping_city, "Raleigh")
        self.assertEqual(rma.lines[0].rma_id, 500)
        self.assertEqual(rma.custom_fields[0].rma_id, 500)
        self.assertEqual(rma.linked_transactions[0].rma_id, 500)

    def test_maps_payment_graph_and_payment_method(self) -> None:
        payment = self.mapper.map_payment(
            {
                "id": 600,
                "customer": {
                    "id": 601,
                    "name": "Customer",
                    "fullname": "Customer Full Name",
                },
                "location": {"id": 602, "name": "Office"},
                "paymentMethod": {
                    "id": 603,
                    "name": "Check",
                    "syncToken": 5,
                    "sosPayType": "Check",
                },
                "currency": {"id": 604, "name": "USD"},
                "channel": {"id": 605, "name": "B2B"},
                "depositAccount": {"id": 606, "name": "Checking"},
                "class": {"id": 607, "name": "Wholesale"},
                "billing": {"address": {"postalCode": "28202"}},
                "linkedTransaction": self._linked_transaction(608),
                "customFields": [self._custom_field(609)],
                "lines": [
                    {
                        "id": 610,
                        "lineNumber": 1,
                        "class": {"id": 611, "name": "Wholesale"},
                        "linkedTransaction": self._linked_transaction(612),
                        "description": "Payment",
                        "amount": 25.0,
                    }
                ],
            }
        )

        self.assertEqual(payment.customer_fullname, "Customer Full Name")
        self.assertEqual(payment.payment_method_id, 603)
        self.assertEqual(payment.payment_method_sync_token, 5)
        self.assertEqual(payment.payment_method_sos_pay_type, "Check")
        self.assertEqual(payment.billing_postal_code, "28202")
        self.assertEqual(payment.lines[0].payment_id, 600)
        self.assertEqual(payment.lines[0].class_id, 611)
        self.assertEqual(payment.custom_fields[0].payment_id, 600)
        self.assertEqual(payment.linked_transactions[0].payment_id, 600)

    def test_maps_adjustment_graph_without_linked_transactions(self) -> None:
        adjustment = self.mapper.map_adjustment(
            {
                "id": 700,
                "account": {"id": 701, "name": "Shrinkage"},
                "location": {"id": 702, "name": "Warehouse"},
                "customFields": [self._custom_field(703)],
                "lines": [
                    {
                        "id": 704,
                        "lineNumber": 1,
                        "item": {"id": 705, "name": "Widget"},
                        "class": {"id": 706, "name": "Inventory"},
                        "uom": {"id": 707, "name": "EA"},
                        "quantityDiff": -1,
                        "newQuantity": 9,
                        "valueDiff": -5.0,
                    }
                ],
            }
        )

        self.assertEqual(adjustment.account_id, 701)
        self.assertEqual(adjustment.location_id, 702)
        self.assertEqual(adjustment.lines[0].adjustment_id, 700)
        self.assertEqual(adjustment.lines[0].item_id, 705)
        self.assertEqual(adjustment.lines[0].quantity_diff, -1)
        self.assertFalse(hasattr(adjustment.lines[0], "linked_transactions"))
        self.assertEqual(adjustment.custom_fields[0].adjustment_id, 700)

    def test_every_payload_type_has_a_model_and_dispatch_branch(self) -> None:
        payload_types = set(get_args(PayloadType))

        self.assertEqual(payload_types, set(PAYLOAD_MODELS))
        for record_id, payload_type in enumerate(payload_types, start=1):
            with self.subTest(payload_type=payload_type):
                record = self.mapper.map_record(payload_type, {"id": record_id})
                self.assertIsInstance(record, PAYLOAD_MODELS[payload_type])

    def test_all_enabled_endpoint_entities_are_claimed(self) -> None:
        endpoint_names = {
            endpoint.name for endpoint in settings.sos_enabled_endpoints()
        }

        self.assertTrue(endpoint_names.issubset(SOS_ENTITY_TYPES))
        self.assertIn("updated_purchase_orders", SOS_ENTITY_TYPES)
        self.assertNotIn("estiamtes", SOS_ENTITY_TYPES)
        self.assertNotIn("new_sales_orders", SOS_ENTITY_TYPES)
        self.assertNotIn("all_sales_orders", SOS_ENTITY_TYPES)
        self.assertNotIn("updated_payments", SOS_ENTITY_TYPES)

    @staticmethod
    def _linked_transaction(transaction_id: int) -> dict[str, object]:
        return {
            "id": transaction_id,
            "transactionType": "Transaction",
            "refNumber": f"REF-{transaction_id}",
            "lineNumber": 1,
        }

    @staticmethod
    def _custom_field(custom_field_id: int) -> dict[str, object]:
        return {
            "id": custom_field_id,
            "name": "Test Field",
            "value": "Test Value",
            "dataType": "String",
        }

    @classmethod
    def _transaction_line(cls, line_id: int) -> dict[str, object]:
        return {
            "id": line_id,
            "lineNumber": 1,
            "item": {"id": line_id + 1, "name": "Widget"},
            "class": {"id": line_id + 2, "name": "Inventory"},
            "uom": {"id": line_id + 3, "name": "EA"},
            "tax": {"taxable": True},
            "linkedTransaction": cls._linked_transaction(line_id + 100),
            "description": "Widget",
            "quantity": 1,
            "unitprice": 10.0,
            "amount": 10.0,
        }


if __name__ == "__main__":
    unittest.main()
