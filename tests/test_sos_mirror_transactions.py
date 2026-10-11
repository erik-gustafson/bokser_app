import copy
import unittest
from src.integrations.sos_odoo_mirror.transactions import ENTITIES, normalize_transaction, validate_transaction, order_transactions

T='2026-10-10T12:00:00Z'


def raw(entity='salesorder', identifier=17, **extra):
    line={'id':101,'lineNumber':1,'item':{'id':100},'uom':{'id':1},'description':'Synthetic',
        'quantity':2,'unitprice':10,'amount':20,'tax':{'taxable':False},'linkedTransaction':None}
    if entity=='payment':line={'id':101,'lineNumber':1,'amount':20,'linkedTransaction':None}
    result={'id':identifier,'syncToken':1,'summaryOnly':False,'archived':False,
        'date':'2026-10-10T00:00:00','number':'Synthetic document','total':20,
        'customer':{'id':17},'vendor':{'id':18},'location':{'id':1},'currency':{'id':42},
        'paymentMethod':{'id':88},'depositAccount':{'id':33},'lines':[line]}
    result.update(extra)
    return result


class TransactionTests(unittest.TestCase):
    def test_all_ten_entities_and_excluded_secrets(self):
        for entity in ENTITIES:
            r=raw(entity);r.update(accountToken='excluded',sosPay={'token':'excluded'},customerNotes='excluded')
            p=normalize_transaction(entity,r,T)
            self.assertNotIn('excluded',str(p));validate_transaction(p)

    def test_decimal_nan_boolean_and_incomplete_records_rejected(self):
        for total in (float('nan'),float('inf'),True,None,{},'1e100'):
            with self.assertRaises(ValueError):normalize_transaction('salesorder',raw(total=total),T)
        for extra in ({'summaryOnly':True},{'archived':None},{'lines':[]},{'customer':None}):
            with self.assertRaises(ValueError):normalize_transaction('salesorder',raw(**extra),T)

    def test_revision_and_observation_are_not_business_hash(self):
        p=normalize_transaction('invoice',raw('invoice'),T);q=copy.deepcopy(p)
        q.update(sync_token='2',observed_at='2026-10-11T12:00:00Z')
        self.assertEqual(validate_transaction(p)[1],validate_transaction(q)[1])
        q['facts']['voided']=True
        self.assertNotEqual(validate_transaction(p)[1],validate_transaction(q)[1])

    def test_dependency_order_cycles_and_missing_external_are_explicit(self):
        parent=normalize_transaction('salesorder',raw(),T)
        r=raw('shipment');r['lines'][0]['linkedTransaction']={'id':17,'transactionType':'Sales Order','lineNumber':1}
        child=normalize_transaction('shipment',r,T)
        self.assertEqual([p['entity'] for p in order_transactions([child,parent])],['salesorder','shipment'])
        # External parents are resolved by the Odoo account, never fabricated.
        self.assertEqual(order_transactions([child]),[child])
        parent['dependencies']=[{'entity':'shipment','source_id':'17','line_number':None}]
        with self.assertRaisesRegex(ValueError,'cycle'):order_transactions([parent,child])

    def test_duplicate_lines_and_unsupported_dependency_fail(self):
        r=raw();r['lines'].append(dict(r['lines'][0]))
        with self.assertRaisesRegex(ValueError,'duplicate'):normalize_transaction('salesorder',r,T)
        r=raw();r['linkedTransaction']={'id':1,'transactionType':'Unknown'}
        with self.assertRaisesRegex(ValueError,'unsupported'):normalize_transaction('salesorder',r,T)

    def test_custom_fields_selected_before_wire_and_unknown_fields_rejected(self):
        r=raw();r['customFields']=[{'id':1,'value':'Synthetic'},{'id':2,'value':'excluded'}]
        p=normalize_transaction('salesorder',r,T,approved_fields=[1])
        self.assertEqual(p['custom_fields'],{'1':'Synthetic'});self.assertNotIn('excluded',str(p))
        p['password']='excluded'
        with self.assertRaises(ValueError):validate_transaction(p)

    def test_document_addresses_keep_only_reviewed_shape_and_reject_truncation(self):
        from src.integrations.sos_odoo_mirror.contract import ADDRESS_FIELDS,ALTERNATE_FIELDS
        address=dict.fromkeys(ALTERNATE_FIELDS,'')
        address.update(company='Synthetic destination',address=dict.fromkeys(ADDRESS_FIELDS,''),password='excluded')
        address['address']['line1']='Synthetic address'
        p=normalize_transaction('salesorder',raw(shipping=address),T)
        self.assertNotIn('excluded',str(p));self.assertEqual(p['addresses']['shipping']['address']['line1'],'Synthetic address')
        del address['address']['line5']
        with self.assertRaisesRegex(ValueError,'incomplete_master_fields'):
            normalize_transaction('salesorder',raw(shipping=address),T)
