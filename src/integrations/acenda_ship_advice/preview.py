"""Conservative candidate assessment, not permission to release fulfillment."""
from collections import Counter
from decimal import Decimal, InvalidOperation
import re


def assess(advice, *, currency='USD'):
    if not re.fullmatch(r'[A-Z]{3}', currency):
        raise ValueError('Invalid configured Acenda currency')
    supplied = advice.get('currency') or advice.get('currency_code')
    if supplied and supplied != currency:
        return 'currency_mismatch'
    if advice.get('status') in {'shipped', 'fulfilled', 'complete', 'completed'}:
        return 'historical'
    if advice.get('status') in {'canceled', 'cancelled'}:
        return 'cancellation_review'
    if advice.get('status') != 'pending':
        return 'status_review'
    if any(type(advice.get(k)) is not int or advice[k] <= 0 for k in ('id', 'order_id', 'warehouse_id')):
        return 'identity_or_warehouse_review'
    items = advice.get('ship_advice_item') or advice.get('items') or []
    if not isinstance(items, list) or not items:
        return 'lines_missing'
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            return 'line_identity_review'
        iid = item.get('id')
        if type(iid) is not int or iid <= 0 or iid in seen or item.get('ship_advice_id') != advice['id']:
            return 'line_identity_review'
        seen.add(iid)
        if type(item.get('order_item_id')) is not int or item['order_item_id'] <= 0:
            return 'line_identity_review'
        if item.get('status') != 'pending':
            return 'line_status_review'
        qty = item.get('quantity')
        counters = [item.get(k) for k in ('quantity_fulfilled', 'quantity_canceled', 'quantity_rerouted')]
        if type(qty) is not int or qty <= 0 or any(type(v) is not int or v < 0 for v in counters):
            return 'quantity_review'
        if any(counters):
            return 'partial_cancel_or_reroute_review'
        if not isinstance(item.get('sku'), str) or not item['sku'].strip():
            return 'sku_missing'
        explicit = item.get('currency') or item.get('currency_code')
        if explicit and explicit != currency:
            return 'currency_mismatch'
        try:
            price = Decimal(str(item['unit_price']))
            if not price.is_finite() or price < 0:
                return 'price_review'
        except (KeyError, InvalidOperation, ValueError):
            return 'price_review'
        if item.get('kit_items'):
            return 'kit_mapping_review'
        if item.get('discounts'):
            return 'financial_mapping_review'
        for key in ('total_item_discount', 'total_shipping_price', 'total_shipping_discount',
                    'total_tax_price', 'total_handling_price', 'other_fees'):
            try:
                value = Decimal(str(item.get(key, 0)))
                if not value.is_finite() or value != 0:
                    return 'financial_mapping_review'
            except InvalidOperation:
                return 'financial_mapping_review'
    return 'candidate_pending_mapping'


def summarize(records, *, currency='USD'):
    return dict(Counter(assess(record, currency=currency) for record in records))
