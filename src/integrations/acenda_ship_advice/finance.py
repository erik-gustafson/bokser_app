"""Reconcile Acenda USD merchandise, fixed discounts and shipping; no side effects."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal('0.01')
PARENT_KEYS = ('subtotal', 'shipping', 'total_item_discount', 'total_shipping_discount', 'total')
LINE_KEYS = ('total_item_discount', 'total_shipping_price', 'total_shipping_discount', 'total_item_price', 'total_price')
EXTRA_KEYS = ('tax_rate', 'other_fees', 'total_handling_price', 'gift_message_price',
              'gift_message_tax_price', 'giftwrap_price', 'giftwrap_tax_price',
              'total_gift_option_price', 'total_gift_option_tax_price',
              'total_customization_price', 'total_customization_tax_price')

class FinancialError(ValueError):
    pass

def number(value):
    if isinstance(value, bool) or value is None:
        raise FinancialError('financial_amount_missing')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise FinancialError('financial_amount_invalid') from None
    if not result.is_finite() or result < 0:
        raise FinancialError('financial_amount_invalid')
    return result

def amount(value):
    result = number(value)
    if result != result.quantize(CENT):
        raise FinancialError('financial_precision_review')
    return result

def rounded(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)

def text(value):
    return format(value, '.2f')

def zero_extras(record, *, required_taxes=()):
    for key in required_taxes:
        if number(record.get(key)) != 0:
            raise FinancialError('tax_mapping_review')
    for key in EXTRA_KEYS + ('item_tax', 'ship_tax', 'tax_total', 'total_item_tax',
                              'total_shipping_tax_price', 'total_tax_price'):
        if record.get(key) is not None and number(record[key]) != 0:
            raise FinancialError('additional_financial_mapping_review')
    if record.get('kit_items'):
        raise FinancialError('kit_financial_review')

def source_discounts(record, item_discount, shipping_discount):
    entries = record.get('discounts')
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        raise FinancialError('discount_structure_review')
    sums = {'items': Decimal(0), 'shipping': Decimal(0)}
    result = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or entry.get('affects') not in sums or entry.get('fields'):
            raise FinancialError('discount_type_review')
        identity = str(entry.get('id', ''))
        if not identity.isdigit() or int(identity) <= 0 or identity in seen:
            raise FinancialError('discount_identity_review')
        seen.add(identity)
        price = amount(entry.get('price'))
        sums[entry['affects']] += price
        result.append({'source_discount_id': identity, 'affects': entry['affects'], 'amount': text(price)})
    if sums['items'] != item_discount or sums['shipping'] != shipping_discount:
        raise FinancialError('discount_totals_review')
    return sorted(result, key=lambda value: value['source_discount_id'])

def build_finance(parent, items, currency):
    if currency != 'USD':
        raise FinancialError('financial_currency_review')
    zero_extras(parent, required_taxes=('item_tax', 'ship_tax', 'tax_total'))
    if parent.get('discounts'):
        raise FinancialError('parent_discount_allocation_review')
    totals = {key: amount(parent.get(key)) for key in PARENT_KEYS}
    result = {'currency': currency, 'gross_items': text(totals['subtotal']),
              'item_discount': text(totals['total_item_discount']),
              'shipping': text(totals['shipping']),
              'shipping_discount': text(totals['total_shipping_discount']),
              'tax': '0.00', 'total': text(totals['total']), 'lines': []}
    for item in items:
        zero_extras(item, required_taxes=('total_item_tax', 'total_shipping_tax_price', 'total_tax_price'))
        quantity = item.get('quantity')
        if type(quantity) is not int or quantity <= 0:
            raise FinancialError('financial_quantity_review')
        values = {key: amount(item.get(key)) for key in LINE_KEYS}
        gross = rounded(number(item.get('unit_price')) * quantity)
        result['lines'].append({'order_item_id': str(item.get('id')),
          'gross_items': text(gross), 'item_discount': text(values['total_item_discount']),
          'shipping': text(values['total_shipping_price']),
          'shipping_discount': text(values['total_shipping_discount']),
          'net_items': text(values['total_item_price']), 'total': text(values['total_price']),
          'discounts': source_discounts(item, values['total_item_discount'], values['total_shipping_discount'])})
    result['lines'].sort(key=lambda value: value['order_item_id'])
    commercial = [{'external_line_id': str(item.get('id')), 'quantity': item.get('quantity'),
                   'unit_price': str(item.get('unit_price'))} for item in items]
    validate_finance(result, commercial, currency)
    return result

def validate_finance(finance, commercial, currency):
    if not isinstance(finance, dict) or currency != 'USD' or finance.get('currency') != currency:
        raise FinancialError('financial_currency_review')
    if amount(finance.get('tax')) != 0:
        raise FinancialError('tax_mapping_review')
    rows = finance.get('lines')
    if not isinstance(rows, list) or len(rows) != len(commercial):
        raise FinancialError('financial_line_identity_review')
    parent = {str(line['external_line_id']): line for line in commercial}
    seen = set()
    sums = {key: Decimal(0) for key in ('gross_items', 'item_discount', 'shipping', 'shipping_discount', 'total')}
    for row in rows:
        if not isinstance(row, dict):
            raise FinancialError('financial_line_identity_review')
        identity = row.get('order_item_id')
        if identity not in parent or identity in seen:
            raise FinancialError('financial_line_identity_review')
        seen.add(identity)
        line = parent[identity]
        vals = {key: amount(row.get(key)) for key in (*sums, 'net_items')}
        if vals['gross_items'] != rounded(number(line['unit_price']) * line['quantity']):
            raise FinancialError('gross_price_totals_review')
        if vals['item_discount'] > vals['gross_items'] or vals['shipping_discount'] > vals['shipping']:
            raise FinancialError('discount_exceeds_charge_review')
        if vals['net_items'] != vals['gross_items'] - vals['item_discount']:
            raise FinancialError('item_net_totals_review')
        if vals['total'] != vals['net_items'] + vals['shipping'] - vals['shipping_discount']:
            raise FinancialError('line_total_review')
        discounts = row.get('discounts')
        if not isinstance(discounts, list):
            raise FinancialError('discount_structure_review')
        raw = [{'id': value.get('source_discount_id'), 'affects': value.get('affects'),
                'price': value.get('amount')} for value in discounts if isinstance(value, dict)]
        if len(raw) != len(discounts):
            raise FinancialError('discount_structure_review')
        source_discounts({'discounts': raw}, vals['item_discount'], vals['shipping_discount'])
        for key in sums:
            sums[key] += vals[key]
    for key, value in sums.items():
        if amount(finance.get(key)) != value:
            raise FinancialError('parent_financial_totals_review')
    if sums['total'] != sums['gross_items'] - sums['item_discount'] + sums['shipping'] - sums['shipping_discount']:
        raise FinancialError('parent_financial_totals_review')
    return finance

def check_advice_finance(advice, parent_items, finance):
    """Advice amounts verify a snapshot; never add them to commercial totals."""
    zero_extras(advice)
    # Advice header money has no supported allocation contract yet.
    if advice.get('discounts') or any(advice.get(key) is not None and number(advice[key]) != 0
        for key in ('shipping', 'total_item_discount', 'total_shipping_discount', 'total_shipping_price')):
        raise FinancialError('advice_header_financial_review')
    for item in advice.get('ship_advice_item', advice.get('items')) or []:
        zero_extras(item)
        parent = parent_items.get(str(item.get('order_item_id')))
        if parent is None:
            raise FinancialError('financial_line_identity_review')
        keys = ('total_item_discount', 'total_shipping_price', 'total_shipping_discount')
        keys += tuple(key for key in ('total_item_price', 'total_price') if item.get(key) is not None)
        values = {key: amount(item.get(key)) for key in keys}
        source_discounts(item, values['total_item_discount'], values['total_shipping_discount'])
        if item.get('quantity') != parent.get('quantity'):
            # Split/replacement financial allocations need a separate verified policy.
            raise FinancialError('split_financial_allocation_review')
        for key in keys:
            if values[key] != amount(parent.get(key)):
                raise FinancialError('advice_financial_mismatch_review')
