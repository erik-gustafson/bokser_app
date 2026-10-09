import copy
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import httpx

from src.integrations.amazon_client.orders import normalize_order
from src.integrations.amazon_client.odoo import OdooAmazonClient, OdooConnectorError
from src.integrations.amazon_client.sync import sync_once
from src.integrations.amazon_client.client import AmazonClient
from src.core.configs.amazon import AmazonSettings

NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)

def raw_order():
    return {'orderId': '123-1234567-1234567', 'createdTime': '2026-10-01T12:00:00Z',
            'lastUpdatedTime': '2026-10-05T10:00:00Z',
            'salesChannel': {'channelName': 'AMAZON', 'marketplaceId': 'ATVPDKIKX0DER'},
            'fulfillment': {'fulfilledBy': 'MERCHANT', 'fulfillmentStatus': 'UNSHIPPED'},
            'buyer': {'email': 'not-collected@example.invalid'},
            'recipient': {'deliveryAddress': {'name': 'Synthetic Recipient', 'addressLine1': '1 Test Street',
                'city': 'Minneapolis', 'stateOrRegion': 'MN', 'postalCode': '55401',
                'countryCode': 'US', 'phone': 'not-collected'}},
            'orderItems': [{'orderItemId': 'item-1', 'quantityOrdered': 2, 'product': {'sellerSku': 'TEST-AMAZON-SKU',
                'price': {'unitPrice': {'amount': '12.50', 'currencyCode': 'USD'}}}}]}

def normalize(raw):
    return normalize_order(raw, seller_id='test-seller', marketplace_id='ATVPDKIKX0DER', environment='sandbox')

class NormalizationTests(unittest.TestCase):
    def test_allowlist_drops_buyer_phone_and_raw_payload(self):
        result = normalize(raw_order())
        self.assertNotIn('buyer', result)
        self.assertNotIn('phone', result['recipient'])
        self.assertEqual(result['lines'][0]['unit_price'], '12.50')

    def test_fba_has_no_recipient(self):
        raw = raw_order(); raw['fulfillment']['fulfilledBy'] = 'AMAZON'
        self.assertIsNone(normalize(raw)['recipient'])

    def test_pending_has_no_recipient(self):
        raw = raw_order(); raw['fulfillment']['fulfillmentStatus'] = 'PENDING'
        self.assertIsNone(normalize(raw)['recipient'])

    def test_cancellation_creates_hold(self):
        raw = raw_order(); raw['orderItems'][0]['cancellation'] = {'cancellationRequest': {'reason': 'test'}}
        self.assertTrue(normalize(raw)['cancellation_requested'])

    def test_wrong_marketplace_rejected(self):
        raw = raw_order(); raw['salesChannel']['marketplaceId'] = 'OTHER'
        with self.assertRaises(ValueError): normalize(raw)

    def test_duplicates_and_booleans_rejected(self):
        raw = raw_order(); raw['orderItems'] *= 2
        with self.assertRaises(ValueError): normalize(raw)
        raw = raw_order(); raw['orderItems'][0]['quantityOrdered'] = True
        with self.assertRaises(ValueError): normalize(raw)

    def test_invalid_price_and_timestamp_rejected(self):
        raw = raw_order(); raw['orderItems'][0]['product']['price']['unitPrice']['amount'] = 'NaN'
        with self.assertRaises(ValueError): normalize(raw)
        raw = raw_order(); raw['lastUpdatedTime'] = '2026-10-05T10:00:00'
        with self.assertRaises(ValueError): normalize(raw)

class MemoryInbox:
    account = 'amazon-test'
    def __init__(self): self.rows = {}; self.watermark = None; self.events = []
    def lock(self): self.events.append('lock')
    def cursor(self, initial): return self.watermark or initial
    def store_page(self, orders):
        self.events.append('page')
        for order in orders:
            key = order['order_id']
            if key not in self.rows or order['updated_at'] > self.rows[key][1]:
                self.rows[key] = (key, order['updated_at'], order)
    def advance(self, upper): self.events.append('advance'); self.watermark = upper
    def pending(self): return list(self.rows.values())
    def acknowledge(self, key, version):
        self.events.append('ack'); self.rows.pop(key)

class FakeAmazon:
    config = SimpleNamespace(amazon_environment='sandbox', amazon_seller_id='test-seller', amazon_marketplace_id='ATVPDKIKX0DER')
    def __init__(self, fail=False): self.fail = fail
    async def order_pages(self, **kwargs):
        yield {'orders': [raw_order()]}
        if self.fail: raise RuntimeError('page two unavailable')

class SyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_sandbox_and_production_hosts_are_explicit(self):
        for mode, host in [('sandbox', 'sandbox.sellingpartnerapi-na.amazon.com'), ('production', 'sellingpartnerapi-na.amazon.com')]:
            requests = []
            def handle(request):
                requests.append(request)
                if request.url.host == 'api.amazon.com':
                    return httpx.Response(200, json={'access_token': 'test', 'expires_in': 3600})
                return httpx.Response(200, json={'orders': []})
            config = AmazonSettings(_env_file=None, amazon_environment=mode, amazon_enabled=True,
                amazon_seller_id='test', amazon_lwa_client_id='test', amazon_lwa_client_secret='test',
                amazon_lwa_refresh_token='test')
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
                async with AmazonClient(config, http) as client:
                    await client._request('searchOrders', 'GET', '/orders/2026-01-01/orders')
            self.assertEqual(requests[-1].url.host, host)

    async def test_failed_page_preserves_cursor_and_durable_first_page(self):
        inbox = MemoryInbox()
        with self.assertRaises(RuntimeError):
            await sync_once(FakeAmazon(True), inbox, None, initial=NOW-timedelta(days=1), now=NOW)
        self.assertIsNone(inbox.watermark)
        self.assertEqual(len(inbox.rows), 1)

    async def test_odoo_timeout_replay_is_not_acknowledged(self):
        inbox = MemoryInbox()
        class Odoo:
            async def import_order(self, *args): raise OdooConnectorError('timeout')
        with self.assertRaises(OdooConnectorError):
            await sync_once(FakeAmazon(), inbox, Odoo(), initial=NOW-timedelta(days=1), now=NOW)
        self.assertIsNotNone(inbox.watermark)
        self.assertEqual(len(inbox.rows), 1)
        self.assertNotIn('ack', inbox.events)

    async def test_success_delivers_committed_page(self):
        inbox = MemoryInbox()
        class Odoo:
            async def import_order(self, account, payload): return {'state': 'imported'}
        self.assertEqual(await sync_once(FakeAmazon(), inbox, Odoo(), initial=NOW-timedelta(days=1), now=NOW), 1)
        self.assertEqual(inbox.events, ['lock', 'page', 'advance', 'ack'])

    async def test_production_sync_blocked_before_any_storage(self):
        client = FakeAmazon(); client.config = copy.copy(client.config); client.config.amazon_environment = 'production'
        inbox = MemoryInbox()
        with self.assertRaises(ValueError):
            await sync_once(client, inbox, None, initial=NOW, now=NOW)
        self.assertEqual(inbox.events, [])

    async def test_https_and_atomic_odoo_contract(self):
        requests = []
        def handle(request):
            requests.append(request)
            return httpx.Response(200, json={'state': 'imported'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            client = OdooAmazonClient(base_url='https://odoo.test', database='bokser_amazon_sandbox', api_key='test', http_client=http)
            await client.import_order('amazon-test', normalize(raw_order()))
            self.assertEqual(requests[0].url.path, '/json/2/bokser.amazon.account/import_order')
            self.assertEqual(requests[0].headers['X-Odoo-Database'], 'bokser_amazon_sandbox')
            with self.assertRaises(ValueError):
                OdooAmazonClient(base_url='http://odoo.test', database='test', api_key='test', http_client=http)

    async def test_http_error_never_contains_response_pii(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(403, text='PRIVATE BUYER SECRET'))) as http:
            client = OdooAmazonClient(base_url='https://odoo.test', database='test', api_key='test', http_client=http)
            with self.assertRaises(OdooConnectorError) as error:
                await client.import_order('test', {})
            self.assertNotIn('PRIVATE', str(error.exception))

if __name__ == '__main__': unittest.main()
