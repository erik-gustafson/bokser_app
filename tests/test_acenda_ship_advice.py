import ast
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('advice_preview', ROOT / 'src/integrations/acenda_ship_advice/preview.py')
preview = importlib.util.module_from_spec(spec); spec.loader.exec_module(preview)


def advice():
    return {'id': 1, 'order_id': 2, 'warehouse_id': 3, 'status': 'pending',
            'ship_advice_item': [{'id': 4, 'ship_advice_id': 1, 'order_item_id': 5,
                'status': 'pending', 'sku': 'TEST', 'quantity': 2,
                'quantity_fulfilled': 0, 'quantity_canceled': 0, 'quantity_rerouted': 0,
                'unit_price': '12.50'}]}


class PreviewTests(unittest.TestCase):
    def test_pending_is_only_a_candidate(self):
        self.assertEqual(preview.assess(advice()), 'candidate_pending_mapping')

    def test_history_not_released(self):
        a=advice(); a['status']='shipped'
        self.assertEqual(preview.assess(a), 'historical')

    def test_missing_quantities_not_assumed_zero(self):
        a=advice(); del a['ship_advice_item'][0]['quantity_fulfilled']
        self.assertEqual(preview.assess(a), 'quantity_review')

    def test_partial_cancel_and_reroute_are_reviews(self):
        for field in ('quantity_fulfilled','quantity_canceled','quantity_rerouted'):
            a=advice(); a['ship_advice_item'][0][field]=1
            self.assertEqual(preview.assess(a), 'partial_cancel_or_reroute_review')

    def test_bad_price_and_currency(self):
        a=advice(); a['ship_advice_item'][0]['unit_price']='NaN'
        self.assertEqual(preview.assess(a), 'price_review')
        a=advice(); a['currency']='EUR'
        self.assertEqual(preview.assess(a), 'currency_mismatch')
        with self.assertRaises(ValueError): preview.assess(advice(), currency='usd')

    def test_line_and_warehouse_identity(self):
        a=advice(); a['warehouse_id']=None
        self.assertEqual(preview.assess(a), 'identity_or_warehouse_review')
        a=advice(); a['ship_advice_item'][0]['ship_advice_id']=99
        self.assertEqual(preview.assess(a), 'line_identity_review')

    def test_financial_and_kit_review(self):
        a=advice(); a['ship_advice_item'][0]['total_tax_price']='0.20'
        self.assertEqual(preview.assess(a), 'financial_mapping_review')
        a=advice(); a['ship_advice_item'][0]['kit_items']=[{'sku':'KIT-PART'}]
        self.assertEqual(preview.assess(a), 'kit_mapping_review')


class MapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=ROOT/'src/worker/jobs/process_data/acenda/process_acenda_data.py'
        tree=ast.parse(path.read_text())
        klass=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='AcendaPayloadMapper')
        # Execute the actual two mapper methods, isolating database/application imports.
        methods=[n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name in ('map_ship_advice_header','map_ship_advice_item')]
        isolated=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),ast.ClassDef(name=klass.name,bases=[],keywords=[],body=methods,decorator_list=[])],type_ignores=[])
        ast.fix_missing_locations(isolated)
        ns=dict(AcendaShipAdviceHeaders=lambda **kw:SimpleNamespace(**kw),
                AcendaShipAdviceItems=lambda **kw:SimpleNamespace(**kw),
                as_int=lambda v:0 if v is None else int(v),
                as_str=lambda v:'' if v is None else str(v),
                as_decimal=lambda v:None if v is None else Decimal(str(v)),
                parse_dt=lambda v:None if not v else datetime.fromisoformat(v.replace('Z','+00:00')))
        exec(compile(isolated,str(path),'exec'),ns)
        cls.mapper=ns['AcendaPayloadMapper']()

    def test_line_values_and_precision_preserved(self):
        item=advice()['ship_advice_item'][0]
        item.update(unit_price='12.345678', total_item_discount='1.25', line_id='source-line')
        obj=self.mapper.map_ship_advice_item(item)
        self.assertEqual(obj.quantity,2)
        self.assertEqual(obj.quantity_fulfilled,0)
        self.assertEqual(obj.quantity_canceled,0)
        self.assertEqual(obj.sku,'TEST')
        self.assertEqual(obj.status,'pending')
        self.assertEqual(obj.unit_price,Decimal('12.345678'))
        self.assertEqual(obj.total_item_discount,Decimal('1.25'))
        self.assertEqual(obj.line_id,'source-line')

    def test_missing_source_values_stay_unknown(self):
        obj=self.mapper.map_ship_advice_item(dict(id=4,order_item_id=5,ship_advice_id=1))
        for key in ('quantity','quantity_fulfilled','quantity_canceled','sku','status','unit_price'):
            self.assertIsNone(getattr(obj,key))

    def test_header_status_and_routing_preserved(self):
        a=advice();a.update(external_order_id='SOURCE-REF', sales_channel_id=7, shipping_method='Ground', currency_code='EUR')
        obj=self.mapper.map_ship_advice_header(a)
        self.assertEqual(obj.status,'pending')
        self.assertEqual(obj.currency,'EUR')
        self.assertEqual(obj.external_order_id,'SOURCE-REF')
        self.assertEqual(obj.sales_channel_id,7)
        self.assertEqual(obj.warehouse_id,3)
        self.assertEqual(obj.ship_advice_items[0].quantity,2)

if __name__=='__main__': unittest.main()
