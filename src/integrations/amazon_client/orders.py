from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone is required')
    return result.astimezone(timezone.utc).isoformat()


def normalize_order(order, *, seller_id, marketplace_id, environment):
    """Allowlist the Orders 2026 contract; never persist the original response."""
    if environment not in {'sandbox', 'production'}:
        raise ValueError('Invalid environment')
    oid = order.get('orderId', '')
    if not re.fullmatch(r'\d{3}-\d{7}-\d{7}', oid):
        raise ValueError('Invalid order identity')
    channel = order.get('salesChannel') or {}
    if channel.get('marketplaceId') != marketplace_id or channel.get('channelName') != 'AMAZON':
        raise ValueError('Unexpected marketplace/channel')
    fulfillment = order.get('fulfillment') or {}
    owner = fulfillment.get('fulfilledBy')
    status = fulfillment.get('fulfillmentStatus')
    if owner not in {'MERCHANT', 'AMAZON'} or status not in {
        'PENDING', 'PENDING_AVAILABILITY', 'UNSHIPPED', 'PARTIALLY_SHIPPED',
        'SHIPPED', 'CANCELLED', 'UNFULFILLABLE'}:
        raise ValueError('Missing/unknown fulfillment classification')
    lines, ids = [], set()
    for item in order.get('orderItems', []):
        iid, quantity = item.get('orderItemId'), item.get('quantityOrdered')
        if not isinstance(iid, str) or not iid or iid in ids or type(quantity) is not int or quantity <= 0:
            raise ValueError('Invalid or duplicate order line')
        ids.add(iid)
        product = item.get('product') or {}
        price = (product.get('price') or {}).get('unitPrice') or {}
        amount = None
        if price:
            try:
                amount = Decimal(price['amount'])
                if not amount.is_finite() or amount < 0:
                    raise ValueError('Invalid price')
            except (KeyError, InvalidOperation):
                raise ValueError('Invalid price') from None
        shipped = (item.get('fulfillment') or {}).get('quantityFulfilled', 0)
        if type(shipped) is not int or not 0 <= shipped <= quantity:
            raise ValueError('Invalid fulfilled quantity')
        cancel = item.get('cancellation') or {}
        lines.append({'item_id': iid, 'seller_sku': product.get('sellerSku') or '',
                      'quantity': quantity, 'shipped': shipped,
                      'unit_price': str(amount) if amount is not None else None,
                      'currency': price.get('currencyCode'),
                      'cancellation_requested': bool(cancel.get('cancellationRequest') or cancel.get('cancellationExecution'))})
    if not lines:
        raise ValueError('Order requires lines')
    address = (order.get('recipient') or {}).get('deliveryAddress') or {}
    recipient = None
    # FBA reporting has no reason to retain recipient data.
    if owner == 'MERCHANT' and status in {'UNSHIPPED', 'PARTIALLY_SHIPPED'}:
        recipient = {k: address.get(k) or '' for k in (
            'name', 'addressLine1', 'addressLine2', 'addressLine3',
            'city', 'stateOrRegion', 'postalCode', 'countryCode')}
    return {'schema_version': 1, 'seller_id': seller_id, 'marketplace_id': marketplace_id,
            'environment': environment, 'order_id': oid,
            'created_at': timestamp(order['createdTime']),
            'updated_at': timestamp(order['lastUpdatedTime']), 'fulfilled_by': owner,
            'status': status, 'cancellation_requested': any(l['cancellation_requested'] for l in lines),
            'recipient': recipient, 'lines': lines}
