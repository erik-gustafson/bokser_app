from datetime import timedelta
from .orders import normalize_order


async def sync_once(client, inbox, odoo, *, initial, now, include_recipient=False):
    # This release is restricted to synthetic sandbox orders. Live PII storage,
    # downstream deletion and warehouse dispatch require a subsequent release.
    if client.config.amazon_environment != 'sandbox':
        raise ValueError('Version 0.2 order sync supports sandbox only')
    inbox.lock()
    lower = inbox.cursor(initial) - timedelta(minutes=5)
    upper = now - timedelta(minutes=3)
    if upper > lower:
        async for page in client.order_pages(updated_after=lower, updated_before=upper, include_customer=include_recipient):
            orders = [normalize_order(o, seller_id=client.config.amazon_seller_id,
                      marketplace_id=client.config.amazon_marketplace_id, environment='sandbox') for o in page['orders']]
            inbox.store_page(orders)
        inbox.advance(upper)
    count = 0
    # An Odoo failure leaves the inbox record undelivered. Atomic Odoo import
    # and its unique order identity make timeout/restart replay safe.
    for order_id, updated_at, payload in inbox.pending():
        await odoo.import_order(inbox.account, payload)
        inbox.acknowledge(order_id, updated_at)
        count += 1
    return count
