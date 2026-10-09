"""One sandbox synchronization pass; schedule only after local acceptance tests."""
import asyncio
from datetime import datetime, timezone
import os
import argparse
import re
import httpx
import psycopg
from .client import AmazonClient
from .inbox import AmazonInbox
from .odoo import OdooAmazonClient
from .orders import timestamp
from .sync import sync_once
from src.core.configs.amazon import AmazonSettings


async def main():
    parser = argparse.ArgumentParser(description='Amazon sandbox import test')
    parser.add_argument('--demo', action='store_true', help='Import built-in synthetic orders without calling Amazon')
    parser.add_argument('--retry-order', help='Replay a held order after correcting its SKU/address setup')
    args = parser.parse_args()
    config = AmazonSettings()
    if config.amazon_environment != 'sandbox':
        raise ValueError('Sandbox only in this release')
    if not config.amazon_enabled or config.amazon_owner != 'bokser' or not config.amazon_seller_id:
        raise ValueError('Enable the sandbox account and configure its seller ID')
    if not args.demo:
        config.require_active()
    initial = datetime.fromisoformat(timestamp(os.environ.get('AMAZON_INITIAL_SYNC_AT', '2026-10-01T00:00:00Z')))
    # Do not print exception chains, credentials, response bodies or payloads.
    with psycopg.connect(os.environ['AMAZON_DATABASE_URL']) as connection:
        async with httpx.AsyncClient() as http:
            odoo = OdooAmazonClient(base_url=os.environ['AMAZON_ODOO_URL'],
                database=os.environ['AMAZON_ODOO_DATABASE'], api_key=os.environ['AMAZON_ODOO_API_KEY'], http_client=http)
            inbox = AmazonInbox(connection, os.environ['AMAZON_ACCOUNT_CODE'])
            if args.retry_order:
                if not re.fullmatch(r'\d{3}-\d{7}-\d{7}', args.retry_order):
                    raise ValueError('Invalid retry order identity')
                inbox.lock()
                inbox.retry_order(args.retry_order)
            if args.demo:
                from .demo import demo_orders
                from .orders import normalize_order
                if not inbox.account.endswith('-demo'):
                    raise ValueError('Demo requires a separate account code ending in -demo')
                inbox.lock()
                inbox.store_page([normalize_order(o, seller_id=config.amazon_seller_id,
                    marketplace_id=config.amazon_marketplace_id, environment='sandbox') for o in demo_orders()])
                count = 0
                for order_id, updated_at, payload in inbox.pending():
                    await odoo.import_order(inbox.account, payload)
                    inbox.acknowledge(order_id, updated_at)
                    count += 1
            else:
                async with AmazonClient(config, http) as client:
                    count = await sync_once(client, inbox, odoo,
                        initial=initial, now=datetime.now(timezone.utc), include_recipient=True)
            print('Sandbox inbox orders processed: %s' % count)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as error:
        print('Amazon sandbox sync failed (%s). Review configuration and service availability; no payload logged.' % type(error).__name__)
        raise SystemExit(1)
