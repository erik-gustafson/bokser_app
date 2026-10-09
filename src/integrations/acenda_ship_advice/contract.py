"""Acenda contract validation; pure functions, no database or API side effects."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from collections import defaultdict
import hashlib
import json

class ContractError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)

def fail(code):
    raise ContractError(code)

def identity(value):
    if not isinstance(value, str) or not value.isdigit() or int(value) <= 0:
        fail('identity_invalid')
    return value

def timestamp(value):
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            fail('timestamp_invalid')
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except (AttributeError, TypeError, ValueError):
        fail('timestamp_invalid')

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def parent_snapshot(payload):
    result = {k: payload.get(k) for k in ('order_id','updated_at','status','currency','recipient','lines','financial_review')}
    if 'finance' in payload: result['finance'] = payload['finance']
    return result

def quotation_snapshot(payload):
    result = {k: payload.get(k) for k in ('status','currency','recipient','lines','financial_review')}
    if 'finance' in payload: result['finance'] = payload['finance']
    return result

def validate(payload):
    if not isinstance(payload, dict) or payload.get('schema_version') != 1 or payload.get('environment') != 'test':
        fail('contract_invalid')
    identity(payload.get('order_id'))
    timestamp(payload.get('updated_at'))
    lines=payload.get('lines')
    advices=payload.get('advices')
    if not isinstance(lines,list) or not lines or not isinstance(advices,list) or not advices:
        fail('parent_or_advice_missing')
    currency=payload.get('currency')
    if not isinstance(currency,str) or len(currency)!=3 or not currency.isalpha() or currency != currency.upper():
        fail('currency_invalid')
    seen={}
    for line in lines:
        if not isinstance(line,dict): fail('line_invalid')
        oid=identity(line.get('external_line_id'))
        if oid in seen: fail('line_identity_invalid')
        seen[oid]=line
        if line.get('currency') != currency: fail('currency_mismatch')
        if not isinstance(line.get('sku'),str) or not line['sku'].strip(): fail('sku_missing')
        if type(line.get('quantity')) is not int or line['quantity'] <= 0: fail('quantity_invalid')
        for key in ('fulfilled_quantity','canceled_quantity'):
            if type(line.get(key)) is not int or line[key]<0: fail('quantity_unknown')
        try:
            price=Decimal(str(line['unit_price']))
            if not price.is_finite() or price < 0: fail('price_invalid')
        except (KeyError,InvalidOperation,ValueError): fail('price_invalid')
    advice_ids=set(); item_ids=set()
    for advice in advices:
        if not isinstance(advice,dict): fail('advice_invalid')
        aid=identity(advice.get('advice_id'))
        if aid in advice_ids or advice.get('order_id') != payload['order_id']: fail('advice_parent_mismatch')
        advice_ids.add(aid)
        identity(advice.get('warehouse_id')); identity(advice.get('provider_id'))
        timestamp(advice.get('updated_at'))
        if not isinstance(advice.get('lines'),list) or not advice['lines']: fail('advice_lines_missing')
        for line in advice['lines']:
            iid=identity(line.get('advice_item_id'))
            if iid in item_ids: fail('advice_item_duplicate')
            item_ids.add(iid)
            if line.get('advice_id')!=aid or line.get('order_item_id') not in seen: fail('advice_line_parent_mismatch')
            parent=seen[line['order_item_id']]
            if line.get('sku') != parent['sku']: fail('advice_sku_mismatch')
            for key in ('quantity','fulfilled_quantity','canceled_quantity','rerouted_quantity'):
                if type(line.get(key)) is not int or line[key]<0: fail('advice_quantity_unknown')
            if line['quantity']<=0: fail('quantity_invalid')
    if 'finance' in payload:
        from .finance import validate_finance, FinancialError
        try:
            validate_finance(payload['finance'], lines, currency)
        except FinancialError as error:
            fail(str(error))
    return lines, advices

def review_reason(payload):
    lines, advices=validate(payload)
    if payload.get('status') in ('canceled','cancelled'): return 'cancellation_review'
    if payload.get('status') not in ('pending', 'routed'): return 'parent_status_review'
    if payload.get('financial_review'): return 'financial_mapping_review'
    if any(x['fulfilled_quantity'] or x['canceled_quantity'] for x in lines): return 'parent_partial_or_cancel_review'
    quantities=defaultdict(int)
    for advice in advices:
        if advice.get('status') != 'pending': return 'advice_history_or_status_review'
        if advice.get('financial_review'): return 'financial_mapping_review'
        for line in advice['lines']:
            if line.get('status') != 'pending': return 'advice_line_status_review'
            if line['fulfilled_quantity'] or line['canceled_quantity'] or line['rerouted_quantity']:
                return 'advice_partial_cancel_or_reroute_review'
            quantities[line['order_item_id']]+=line['quantity']
    if any(quantities[x['external_line_id']]!=x['quantity'] for x in lines):
        return 'advice_coverage_review'
    return None
