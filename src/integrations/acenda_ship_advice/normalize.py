"""Build one parent-order contract from explicit raw order/advice snapshots."""
from decimal import Decimal, InvalidOperation
from .contract import ContractError, identity, timestamp, validate
from .finance import build_finance, check_advice_finance, FinancialError, PARENT_KEYS

FINANCIAL_KEYS=('item_tax','ship_tax','shipping','total_item_discount','total_shipping_discount',
 'tax_total','total_shipping_price','total_shipping_tax_price','total_handling_price',
 'total_item_tax','total_tax_price','other_fees','total_gift_option_price',
 'total_gift_option_tax_price','gift_message_price','gift_message_tax_price',
 'total_customization_price','total_customization_tax_price','tax_rate')

def raw_id(value):
    if type(value) is int: value=str(value)
    return identity(value)

def financial_review(record):
    if record.get('discounts') or record.get('kit_items'): return True
    for key in FINANCIAL_KEYS:
        value=record.get(key)
        if value is not None:
            try:
                amount=Decimal(str(value))
                if not amount.is_finite() or amount != 0: return True
            except InvalidOperation: return True
    return False

def money(value):
    try:
        amount=Decimal(str(value))
        if not amount.is_finite() or amount<0: raise ValueError()
        return str(amount)
    except (ValueError,InvalidOperation): raise ContractError('price_invalid') from None

def currency_for(record, fallback):
    supplied=record.get('currency') or record.get('currency_code')
    if supplied and supplied != fallback: raise ContractError('currency_mismatch')
    return supplied or fallback

def address(raw):
    return {'name':' '.join(filter(None,[raw.get('first_name'),raw.get('last_name')])),
      'street':raw.get('address_1'),'street2':raw.get('address_2') or '',
      'city':raw.get('city'),'state':raw.get('state'),'postal_code':raw.get('postal_code'),
      'country_code':raw.get('country')}

def build_payload(parent, advices, *, organization_slug, currency='USD'):
    if not isinstance(parent,dict) or not isinstance(advices,list): raise ContractError('source_payload_invalid')
    oid=raw_id(parent.get('id')); items=parent.get('order_item')
    if not isinstance(items,list) or not items or type(parent.get('line_count')) is not int or parent['line_count']!=len(items):
        raise ContractError('complete_parent_lines_required')
    currency_for(parent,currency)
    recipient=address(parent.get('shipping_information') or {})
    payload={'schema_version':1,'environment':'test','organization_slug':organization_slug,
      'order_id':oid,'updated_at':timestamp(parent.get('updated_at')).isoformat()+'Z',
      'status':parent.get('status'),'currency':currency,'recipient':recipient,
      'financial_review':financial_review(parent),'lines':[],'advices':[]}
    for item in items:
        if raw_id(item.get('order_id')) != oid: raise ContractError('order_item_parent_mismatch')
        payload['financial_review'] |= financial_review(item)
        payload['lines'].append({'external_line_id':raw_id(item.get('id')),
          'sku':item.get('sku'),'quantity':item.get('quantity'),
          'fulfilled_quantity':item.get('quantity_fulfilled'),'canceled_quantity':item.get('quantity_canceled'),
          'unit_price':money(item.get('unit_price')),'currency':currency_for(item,currency)})
    # Complete financial snapshots reconcile before lifting the old generic hold.
    finance = None
    if all(key in parent for key in PARENT_KEYS):
        try:
            finance = build_finance(parent, items, currency)
        except FinancialError as error:
            raise ContractError(str(error)) from None
        payload['finance'] = finance
        payload['financial_review'] = False
    parent_lines={i['external_line_id']:i for i in payload['lines']}
    raw_parent_lines = {str(item['id']): item for item in items}
    for raw in advices:
        if raw_id(raw.get('order_id'))!=oid: raise ContractError('advice_parent_mismatch')
        currency_for(raw,currency)
        if address(raw.get('delivery_information') or raw.get('delivery_info') or {}) != recipient:
            raise ContractError('advice_address_review')
        advice={'advice_id':raw_id(raw.get('id')),'order_id':oid,
          'updated_at':timestamp(raw.get('updated_at')).isoformat()+'Z','status':raw.get('status'),
          'warehouse_id':raw_id(raw.get('warehouse_id')),'provider_id':raw_id(raw.get('fulfillment_provider_id')),
          'financial_review':financial_review(raw),'lines':[]}
        raw_lines=raw.get('ship_advice_item',raw.get('items'))
        if not isinstance(raw_lines,list): raise ContractError('advice_lines_missing')
        for item in raw_lines:
            currency_for(item,currency)
            iid=raw_id(item.get('order_item_id'))
            if iid not in parent_lines: raise ContractError('advice_line_parent_mismatch')
            if Decimal(money(item.get('unit_price')))!=Decimal(parent_lines[iid]['unit_price']):
                raise ContractError('advice_price_review')
            advice['financial_review'] |= financial_review(item)
            advice['lines'].append({'advice_item_id':raw_id(item.get('id')),
              'advice_id':raw_id(item.get('ship_advice_id')),'order_item_id':iid,
              'sku':item.get('sku'),'status':item.get('status'),'quantity':item.get('quantity'),
              'fulfilled_quantity':item.get('quantity_fulfilled'),'canceled_quantity':item.get('quantity_canceled'),
              'rerouted_quantity':item.get('quantity_rerouted')})
        if finance is not None:
            try:
                check_advice_finance(raw, raw_parent_lines, finance)
            except FinancialError as error:
                raise ContractError(str(error)) from None
            advice['financial_review'] = False
        advice['lines'].sort(key=lambda x:x['advice_item_id'])
        payload['advices'].append(advice)
    payload['lines'].sort(key=lambda x:x['external_line_id'])
    payload['advices'].sort(key=lambda x:x['advice_id'])
    validate(payload)
    return payload
