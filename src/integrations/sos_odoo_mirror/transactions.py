"""Allowlisted SOS transaction snapshots; shared verbatim with the Odoo addon."""
from datetime import date
from decimal import Decimal, InvalidOperation
from .contract import ADDRESS_FIELDS, ALTERNATE_FIELDS, digest, reference_id, text_object, timestamp, valid_identifier, selected_custom_field_ids

ENTITIES = ('purchaseorder', 'itemreceipt', 'estimate', 'salesorder', 'invoice',
            'salesreceipt', 'payment', 'return', 'rma', 'shipment')
FINANCIAL = ('purchaseorder', 'estimate', 'salesorder', 'invoice', 'salesreceipt')
STOCK = ('itemreceipt', 'return', 'rma', 'shipment')
ALIASES = {e: e for e in ENTITIES}
ALIASES.update({'purchase order':'purchaseorder', 'item receipt':'itemreceipt',
    'sales order':'salesorder', 'sales receipt':'salesreceipt', 'receipt':'itemreceipt'})
NUMBER_FACTS = ('subTotal', 'discountPercent', 'discountAmount', 'taxPercent', 'taxAmount',
    'shippingAmount', 'depositPercent', 'depositAmount', 'balance', 'exchangeRate')
FLAG_FACTS = ('closed', 'confirmed', 'pendingApproval', 'voided', 'dropShip', 'blanketPO',
    'contractManufacturing', 'createCreditMemo', 'creditHold')
TEXT_FACTS = ('customerPO', 'trackingNumber', 'status', 'number')
LINE_FACTS = ('received', 'picked', 'shipped', 'invoiced', 'returned', 'backOrdered',
    'produced', 'cost', 'margin', 'listPrice')
LINE_KEYS = {'source_id', 'line_number', 'item_id', 'uom_id', 'description', 'quantity',
    'unit_price', 'amount', 'discount', 'tax_id', 'taxable', 'facts', 'dependencies'}


def decimal_text(value, *, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('invalid_decimal')
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('invalid_decimal') from None
    if not number.is_finite() or abs(number) > Decimal('1e18') or number.as_tuple().exponent < -12:
        raise ValueError('invalid_decimal')
    return format(number, 'f')


def text_value(value):
    if value is None:
        return ''
    if not isinstance(value, str) or len(value) > 8192 or any(ord(c) < 32 and c not in '\t\r\n' for c in value):
        raise ValueError('invalid_transaction_text')
    return value


def calendar_date(value):
    if not isinstance(value, str):
        raise ValueError('transaction_date_required')
    try:
        result = date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        raise ValueError('invalid_transaction_date') from None
    if len(value) != 10:
        # SOS exposes calendar-local timestamps without offsets. The business
        # date is their literal date, never the replay machine's timezone.
        from datetime import datetime
        try: datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError: raise ValueError('invalid_transaction_date') from None
    return result


def links(raw):
    if raw is None:
        return []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError('invalid_transaction_dependencies')
    result = []
    for link in raw:
        if not isinstance(link, dict):
            raise ValueError('invalid_transaction_dependencies')
        entity = ALIASES.get(str(link.get('transactionType', '')).lower())
        if entity is None:
            raise ValueError('unsupported_transaction_dependency')
        source_id = reference_id(link)
        line = link.get('lineNumber')
        if line is not None and (type(line) is not int or line < 0):
            raise ValueError('invalid_dependency_line')
        result.append({'entity':entity, 'source_id':source_id, 'line_number':line})
    return result


def transaction_addresses(record):
    result={}
    for role in ('billing','shipping'):
        raw=record.get(role)
        if raw is None:continue
        wrapper=text_object(raw,ALTERNATE_FIELDS)
        wrapper['address']=text_object(raw.get('address'),ADDRESS_FIELDS)
        for value in list(wrapper.values())[:-1]:text_value(value)
        for value in wrapper['address'].values():text_value(value)
        result[role]=wrapper
    return result


def normalize_transaction(entity, record, observed_at, approved_fields=()):
    if entity not in ENTITIES or not isinstance(record, dict) or record.get('summaryOnly') is not False:
        raise ValueError('complete_transaction_required')
    if type(record.get('id')) is not int or record['id'] <= 0 or type(record.get('syncToken')) is not int or record['syncToken'] < 0:
        raise ValueError('invalid_source_identity_or_version')
    if type(record.get('archived')) is not bool or not isinstance(record.get('lines'), list):
        raise ValueError('complete_transaction_required')
    partner_entity = 'vendor' if entity in ('purchaseorder', 'itemreceipt') else 'customer'
    partner = reference_id(record.get(partner_entity))
    if partner is None:
        raise ValueError('transaction_partner_required')
    facts = {k:decimal_text(record[k], nullable=True) for k in NUMBER_FACTS if k in record}
    for k in FLAG_FACTS:
        if k in record:
            if type(record[k]) is not bool: raise ValueError('invalid_transaction_flag')
            facts[k] = record[k]
    facts.update({k:text_value(record[k]) for k in TEXT_FACTS if k in record})
    custom, approved = {}, selected_custom_field_ids(entity, approved_fields)
    for field in record.get('customFields') or []:
        if not isinstance(field, dict) or type(field.get('id')) is not int or field['id'] <= 0:
            raise ValueError('invalid_custom_fields')
        key = str(field['id'])
        if key in approved:
            if key in custom: raise ValueError('duplicate_custom_field')
            value = field.get('value')
            if value is not None: value = text_value(value) if isinstance(value, str) else value
            if value is not None and not isinstance(value, (str, bool, int, float)):
                raise ValueError('invalid_custom_field_value')
            custom[key] = value
    lines = []
    for raw in record['lines']:
        if not isinstance(raw, dict) or type(raw.get('id')) is not int or raw['id'] <= 0 or type(raw.get('lineNumber')) is not int or raw['lineNumber'] < 0:
            raise ValueError('invalid_transaction_line_identity')
        tax = raw.get('tax') or {}
        if not isinstance(tax, dict) or type(tax.get('taxable', False)) is not bool:
            raise ValueError('invalid_line_tax')
        line = {'source_id':str(raw['id']), 'line_number':raw['lineNumber'],
            'item_id':reference_id(raw.get('item')), 'uom_id':reference_id(raw.get('uom')),
            'description':text_value(raw.get('description')), 'quantity':decimal_text(raw.get('quantity'), nullable=entity == 'payment'),
            'unit_price':decimal_text(raw.get('unitprice'), nullable=entity not in FINANCIAL),
            'amount':decimal_text(raw.get('amount'), nullable=entity in STOCK),
            'discount':decimal_text(raw.get('percentdiscount') or 0),
            'tax_id':reference_id(tax.get('taxCode') or record.get('taxCode')),
            'taxable':tax.get('taxable', False), 'dependencies':links(raw.get('linkedTransaction')),
            'facts':{k:decimal_text(raw[k], nullable=True) for k in LINE_FACTS if k in raw}}
        lines.append(line)
    payload = {'schema_version':1, 'entity':entity, 'source_id':str(record['id']),
        'sync_token':str(record['syncToken']), 'observed_at':observed_at,
        'transaction_date':calendar_date(record.get('date')), 'partner_entity':partner_entity,
        'partner_source_id':partner, 'currency_source_id':reference_id(record.get('currency')),
        'location_source_id':reference_id(record.get('location')), 'terms_source_id':reference_id(record.get('terms')),
        'payment_method_source_id':reference_id(record.get('paymentMethod')),
        'deposit_account_source_id':reference_id(record.get('depositAccount')),
        'number':text_value(record.get('number')), 'total':decimal_text(record.get('total')),
        'archived':record['archived'], 'facts':facts, 'custom_fields':custom,
        'dependencies':links(record.get('linkedTransaction')), 'lines':lines,
        'addresses':transaction_addresses(record)}
    validate_transaction(payload)
    return payload


def validate_transaction(payload):
    expected = {'schema_version','entity','source_id','sync_token','observed_at','transaction_date',
        'partner_entity','partner_source_id','currency_source_id','location_source_id','terms_source_id',
        'payment_method_source_id','deposit_account_source_id','number','total','archived','facts',
        'custom_fields','dependencies','lines','addresses'}
    if not isinstance(payload, dict) or set(payload) != expected or type(payload['schema_version']) is not int or payload['schema_version'] != 1 or payload['entity'] not in ENTITIES:
        raise ValueError('invalid_transaction_envelope')
    entity = payload['entity']
    if payload['partner_entity'] != ('vendor' if entity in ('purchaseorder','itemreceipt') else 'customer'):
        raise ValueError('invalid_transaction_partner_role')
    for key in ('source_id','partner_source_id'):
        if not valid_identifier(payload[key]): raise ValueError('invalid_transaction_source_id')
    for key in ('currency_source_id','location_source_id','terms_source_id','payment_method_source_id','deposit_account_source_id'):
        if payload[key] is not None and not valid_identifier(payload[key]): raise ValueError('invalid_transaction_reference')
    token = payload['sync_token']
    if not isinstance(token,str) or not token.isascii() or not token.isdecimal() or len(token)>64 or str(int(token)) != token:
        raise ValueError('invalid_sync_token')
    observed = timestamp(payload['observed_at'])
    if calendar_date(payload['transaction_date']) != payload['transaction_date'] or type(payload['archived']) is not bool:
        raise ValueError('invalid_transaction_date_or_archived')
    text_value(payload['number']); decimal_text(payload['total'])
    addresses=payload['addresses']
    if not isinstance(addresses,dict) or not set(addresses)<= {'billing','shipping'} or transaction_addresses(addresses)!=addresses:
        raise ValueError('invalid_transaction_addresses')
    if not isinstance(payload['facts'],dict) or not set(payload['facts']) <= set(NUMBER_FACTS+FLAG_FACTS+TEXT_FACTS):
        raise ValueError('invalid_transaction_facts')
    for k,v in payload['facts'].items():
        if k in NUMBER_FACTS: decimal_text(v,nullable=True)
        elif k in FLAG_FACTS:
            if type(v) is not bool: raise ValueError('invalid_transaction_flag')
        else: text_value(v)
    custom=payload['custom_fields']
    if not isinstance(custom,dict) or any(not valid_identifier(k) for k in custom):raise ValueError('invalid_custom_fields')
    for v in custom.values():
        if isinstance(v,str):text_value(v)
        elif v is not None and not isinstance(v,(int,float,bool)):raise ValueError('invalid_custom_field_value')
    lines = payload['lines']
    if not isinstance(lines,list) or len(lines)>10000 or (entity != 'payment' and not lines):
        raise ValueError('transaction_lines_required')
    ids,numbers=set(),set()
    for line in lines:
        if not isinstance(line,dict) or set(line)!=LINE_KEYS or not valid_identifier(line['source_id']):raise ValueError('invalid_transaction_line')
        if type(line['line_number']) is not int or line['line_number']<0 or line['source_id'] in ids or line['line_number'] in numbers:raise ValueError('duplicate_or_invalid_transaction_line')
        ids.add(line['source_id']);numbers.add(line['line_number'])
        for key in ('item_id','uom_id','tax_id'):
            if line[key] is not None and not valid_identifier(line[key]):raise ValueError('invalid_transaction_reference')
        if entity != 'payment' and line['item_id'] is None:raise ValueError('line_item_required')
        quantity=decimal_text(line['quantity'],nullable=entity=='payment')
        if quantity is not None and Decimal(quantity)<0:raise ValueError('negative_line_quantity')
        decimal_text(line['unit_price'],nullable=entity not in FINANCIAL)
        decimal_text(line['amount'],nullable=entity in STOCK)
        if not 0<=Decimal(decimal_text(line['discount']))<=100:raise ValueError('invalid_line_discount')
        if type(line['taxable']) is not bool:raise ValueError('invalid_line_tax')
        text_value(line['description'])
        if not isinstance(line['facts'],dict) or not set(line['facts'])<=set(LINE_FACTS):raise ValueError('invalid_line_facts')
        for v in line['facts'].values():decimal_text(v,nullable=True)
    for dependency in dependencies(payload):
        if not isinstance(dependency,dict) or set(dependency)!={'entity','source_id','line_number'} or dependency['entity'] not in ENTITIES or not valid_identifier(dependency['source_id']):raise ValueError('invalid_transaction_dependency')
        line=dependency['line_number']
        if line is not None and (type(line) is not int or line<0):raise ValueError('invalid_dependency_line')
        if (dependency['entity'],dependency['source_id'])==(entity,payload['source_id']):raise ValueError('self_transaction_dependency')
    return observed, digest({k:v for k,v in payload.items() if k not in ('sync_token','observed_at')})


def dependencies(payload):
    if not isinstance(payload.get('dependencies'),list) or any(not isinstance(line.get('dependencies'),list) for line in payload.get('lines',[])):
        raise ValueError('invalid_transaction_dependencies')
    return payload['dependencies'] + [d for line in payload['lines'] for d in line['dependencies']]


def order_transactions(payloads):
    from collections import deque
    indexed={}
    for p in payloads:
        validate_transaction(p);key=(p['entity'],p['source_id'])
        if key in indexed:raise ValueError('duplicate_transaction_in_batch')
        indexed[key]=p
    incoming={key:set() for key in indexed};children={key:set() for key in indexed}
    for key,p in indexed.items():
        for d in dependencies(p):
            parent=(d['entity'],d['source_id'])
            if parent in indexed:incoming[key].add(parent);children[parent].add(key)
    ready=deque(key for key in indexed if not incoming[key]);ordered=[]
    while ready:
        key=ready.popleft();ordered.append(indexed[key])
        for child in sorted(children[key]):
            incoming[child].discard(key)
            if not incoming[child]:ready.append(child)
    if len(ordered)!=len(indexed):raise ValueError('transaction_dependency_cycle')
    return ordered
