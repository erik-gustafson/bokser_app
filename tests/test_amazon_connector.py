import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone

import httpx

from src.core.configs.amazon import AmazonSettings
from src.integrations.amazon_client import AmazonClient, AmazonAPIError, AmazonWriteUncertain
from src.integrations.amazon_client.policies import (
    Commitment, StockSnapshot, dispatch_allowed, publishable_inventory, reservation_release_allowed,
)

NOW = datetime.now(timezone.utc)


def config(**changes):
    return AmazonSettings(_env_file=None, amazon_enabled=True, amazon_writes_enabled=True,
        amazon_seller_id="test-seller", amazon_lwa_client_id="test-client",
        amazon_lwa_client_secret="test-secret", amazon_lwa_refresh_token="test-refresh",
        amazon_search_min_interval_seconds=.001, amazon_shipment_min_interval_seconds=.001,
        amazon_inventory_min_interval_seconds=.001, **changes)


class ClientTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self, handler, settings=None):
        requests = []
        def transport(request):
            requests.append(request)
            if str(request.url) == "https://api.amazon.com/auth/o2/token":
                return httpx.Response(200, json={"access_token": "test-access", "expires_in": 3600})
            return handler(request)
        http = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        client = AmazonClient(settings or config(), http)
        self.addAsyncCleanup(http.aclose)
        return client, requests, http

    async def pages(self, client):
        return [page async for page in client.order_pages(updated_after=NOW-timedelta(days=1),
                                                          updated_before=NOW-timedelta(minutes=5))]

    async def shipment(self, client, **changes):
        values = dict(package_reference="101", carrier_code="UPS", tracking_number="test-track",
                      shipped_at=NOW-timedelta(hours=1), items={"test-line": 2},
                      evidence_kind="wms_handoff", evidence_reference="warehouse-event-1",
                      fulfilled_by="MERCHANT")
        values.update(changes)
        await client.confirm_shipment("123-1234567-1234567", **values)

    async def test_pagination_nested_cursor_and_same_window(self):
        def handle(request):
            second = "paginationToken" in request.url.params
            return httpx.Response(200, json={"orders": [{"orderId": "second" if second else "first"}],
                                            **({} if second else {"pagination": {"nextToken": "cursor"}})})
        client, requests, _ = self.make_client(handle)
        pages = await self.pages(client)
        self.assertEqual([p["orders"][0]["orderId"] for p in pages], ["first", "second"])
        first, second = requests[1:]
        self.assertEqual(second.url.params["paginationToken"], "cursor")
        self.assertEqual(first.url.params["lastUpdatedBefore"], second.url.params["lastUpdatedBefore"])
        self.assertNotIn("fulfilledBy", first.url.params)  # Both MFN and FBA imported.
        self.assertNotIn("RECIPIENT", first.url.params["includedData"])

    async def test_repeated_cursor_fails(self):
        client, _, _ = self.make_client(lambda _: httpx.Response(200, json={"orders": [], "pagination": {"nextToken": "same"}}))
        with self.assertRaises(AmazonAPIError):
            await self.pages(client)

    async def test_missing_orders_is_not_success(self):
        client, _, _ = self.make_client(lambda _: httpx.Response(200, json={}))
        with self.assertRaises(AmazonAPIError):
            await self.pages(client)

    async def test_future_window_rejected_without_network(self):
        client, requests, _ = self.make_client(lambda _: httpx.Response(200))
        with self.assertRaises(ValueError):
            _ = [p async for p in client.order_pages(updated_after=NOW-timedelta(days=1), updated_before=NOW)]
        self.assertEqual(requests, [])

    async def test_concurrent_calls_refresh_token_once(self):
        client, requests, _ = self.make_client(lambda _: httpx.Response(200, json={"orders": []}))
        await asyncio.gather(self.pages(client), self.pages(client))
        self.assertEqual(sum(r.url.host == "api.amazon.com" for r in requests), 1)

    async def test_disabled_and_transferred_owner_make_no_requests(self):
        for values in ({"amazon_enabled": False}, {"amazon_owner": "channelengine"}):
            cfg = config()
            for key, value in values.items(): setattr(cfg, key, value)
            client, requests, _ = self.make_client(lambda _: httpx.Response(200), cfg)
            with self.assertRaises(ValueError): await self.pages(client)
            self.assertEqual(requests, [])

    async def test_write_switch_does_not_block_reads(self):
        cfg = config(); cfg.amazon_writes_enabled = False
        client, requests, _ = self.make_client(lambda _: httpx.Response(200, json={"orders": []}), cfg)
        await self.pages(client)
        before = len(requests)
        with self.assertRaises(ValueError): await self.shipment(client)
        self.assertEqual(len(requests), before)

    async def test_inventory_only_quantity_merge_and_encoded_sku(self):
        client, requests, _ = self.make_client(lambda _: httpx.Response(200, json={"status": "ACCEPTED", "submissionId": "test"}))
        result = await client.publish_inventory("sku / #", 9, product_type="HOME")
        self.assertEqual(result["status"], "ACCEPTED")
        request = requests[-1]
        self.assertIn("sku%20%2F%20%23", str(request.url))
        self.assertEqual(json.loads(request.content), {"productType": "HOME", "patches": [
            {"op": "merge", "path": "/attributes/fulfillment_availability",
             "value": [{"fulfillment_channel_code": "DEFAULT", "quantity": 9}]}]})

    async def test_negative_or_boolean_inventory_rejected(self):
        client, requests, _ = self.make_client(lambda _: httpx.Response(200))
        for qty in [-1, True, 1.5]:
            with self.assertRaises(ValueError): await client.publish_inventory("sku", qty, product_type="HOME")
        self.assertEqual(requests, [])

    async def test_shipment_valid_body(self):
        client, requests, _ = self.make_client(lambda _: httpx.Response(204))
        await self.shipment(client)
        body = json.loads(requests[-1].content)
        self.assertEqual(body["packageDetail"]["orderItems"], [{"orderItemId": "test-line", "quantity": 2}])
        self.assertEqual(body["packageDetail"]["packageReferenceId"], "101")

    async def test_label_and_fba_are_blocked(self):
        client, requests, _ = self.make_client(lambda _: httpx.Response(204))
        for changes in ({"evidence_kind": "label_created"}, {"fulfilled_by": "AMAZON"},
                        {"package_reference": "box-1"}, {"items": {"test-line": 0}},
                        {"evidence_kind": "carrier_acceptance"}):
            with self.assertRaises(ValueError): await self.shipment(client, **changes)
        self.assertEqual(requests, [])

    async def test_carrier_acceptance_requires_explicit_setting(self):
        client, _, _ = self.make_client(lambda _: httpx.Response(204))
        await self.shipment(client, evidence_kind="carrier_acceptance", carrier_acceptance_enabled=True)

    async def test_uncertain_write_not_retried(self):
        for mode in ["timeout", "server"]:
            def handle(request):
                if mode == "timeout": raise httpx.ReadTimeout("secret response", request=request)
                return httpx.Response(503, text="private buyer data")
            client, requests, _ = self.make_client(handle)
            with self.assertRaises(AmazonWriteUncertain) as caught: await self.shipment(client)
            self.assertNotIn("secret", str(caught.exception))
            self.assertNotIn("private", str(caught.exception))
            self.assertEqual(len(requests), 2)  # One token call, one shipment call.

    async def test_429_exposed_for_durable_retry(self):
        client, requests, _ = self.make_client(lambda _: httpx.Response(429))
        with self.assertRaises(AmazonAPIError) as caught: await self.pages(client)
        self.assertEqual(caught.exception.status, 429)
        self.assertEqual(len(requests), 2)

    async def test_injected_http_is_not_closed(self):
        client, _, http = self.make_client(lambda _: httpx.Response(200))
        await client.aclose()
        self.assertFalse(http.is_closed)

    async def test_owned_http_closed(self):
        client = AmazonClient(config())
        await client.aclose()
        self.assertTrue(client._http.is_closed)


class PolicyTests(unittest.TestCase):
    def inventory(self, stocks, commitments=(), **changes):
        return publishable_inventory(stocks, commitments, now=NOW, max_age=changes.pop("max_age", timedelta(minutes=30)), **changes)

    def test_reflected_reservations_not_subtracted_twice(self):
        stocks = [StockSnapshot("a", 80, NOW)]
        c = Commitment("order-line", "a", 20, 20)
        self.assertEqual(self.inventory(stocks, [c, c]).quantity, 80)

    def test_partially_reflected_commitment(self):
        self.assertEqual(self.inventory([StockSnapshot("a", 80, NOW)], [Commitment("line", "a", 20, 5)]).quantity, 65)

    def test_stale_warehouse_zero_healthy_still_counted(self):
        result = self.inventory([StockSnapshot("a", 100, NOW-timedelta(hours=1)), StockSnapshot("b", 20, NOW)])
        self.assertEqual(result.quantity, 20)
        self.assertEqual(result.excluded_warehouses, ("a",))

    def test_unknown_age_blocks_publication(self):
        with self.assertRaises(ValueError): self.inventory([], max_age=None)

    def test_conflicting_duplicates_block_publication(self):
        with self.assertRaises(ValueError):
            self.inventory([StockSnapshot("a", 10, NOW)], [Commitment("same", "a", 3), Commitment("same", "a", 4)])

    def test_unallocated_all_channel_demand_buffer_cap_and_zero(self):
        stocks = [StockSnapshot("a", 20, NOW), StockSnapshot("b", 30, NOW)]
        self.assertEqual(self.inventory(stocks, [Commitment("pending", None, 12)], buffer=3).quantity, 35)
        self.assertEqual(self.inventory(stocks, cap=10).quantity, 10)
        self.assertEqual(self.inventory(stocks, [Commitment("demand", None, 100)]).quantity, 0)

    def test_invalid_correlation_and_missing_warehouse(self):
        for commitment in [Commitment("line", "a", 2, 3), Commitment("line", "missing", 2)]:
            with self.assertRaises(ValueError): self.inventory([StockSnapshot("a", 10, NOW)], [commitment])

    def test_duplicate_snapshots_block(self):
        with self.assertRaises(ValueError): self.inventory([StockSnapshot("a", 10, NOW)] * 2)

    def test_future_snapshot_excluded(self):
        self.assertEqual(self.inventory([StockSnapshot("a", 10, NOW+timedelta(seconds=1))]).quantity, 0)

    def test_dispatch_eligibility(self):
        base = dict(fulfilled_by="MERCHANT", status="UNSHIPPED", mapping_valid=True,
                    address_valid=True, allocation_ready=True, cancellation_requested=False, reservation_override=False)
        self.assertTrue(dispatch_allowed(**base))
        for key, value in [("fulfilled_by", "AMAZON"), ("status", "PENDING"), ("status", "CANCELLED"),
                           ("mapping_valid", False), ("address_valid", False), ("allocation_ready", False),
                           ("cancellation_requested", True), ("reservation_override", True)]:
            self.assertFalse(dispatch_allowed(**{**base, key: value}))

    def test_release_requires_verified_stop_for_accepted_units(self):
        self.assertFalse(reservation_release_allowed(accepted_by_wms=True, stop_verified=False, shipped_quantity=0))
        self.assertTrue(reservation_release_allowed(accepted_by_wms=True, stop_verified=True, shipped_quantity=0))
        self.assertFalse(reservation_release_allowed(accepted_by_wms=True, stop_verified=True, shipped_quantity=1))


if __name__ == "__main__": unittest.main()
