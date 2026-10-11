import asyncio
import copy
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from src.integrations.sos_odoo_mirror.sync import fetch_transactions, synchronize
from src.integrations.sos_odoo_mirror.delivery import DeliveryJournal
from src.integrations.sos_odoo_mirror.transactions import normalize_transaction
from test_sos_mirror_transactions import raw,T
from test_sos_mirror_delivery import TARGET


class Source:
    def __init__(self, pages):self.pages=iter(pages);self.params=[]
    async def get(self,path,*,params):
        self.params.append(dict(params))
        body=next(self.pages)
        if isinstance(body,Exception):raise body
        return httpx.Response(200,json=body,request=httpx.Request('GET','https://source.example.test'+path))


def page(records,total):return {'status':'ok','count':len(records),'totalCount':total,'data':records}


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.TemporaryDirectory();self.addCleanup(self.root.cleanup)
        self.journal=DeliveryJournal(self.root.name,TARGET)

    def test_strict_pagination_and_overlap_query_is_explicit(self):
        source=Source([page([raw(identifier=1)],2),page([raw(identifier=2)],2),page([raw(identifier=1)],2)])
        result=asyncio.run(fetch_transactions(source,'salesorder',T,page_size=1,since=T))
        self.assertEqual([p['source_id'] for p in result],['1','2'])
        self.assertEqual([p['start'] for p in source.params],[1,2,1])
        self.assertEqual(source.params[0]['updatedsince'],T)
        self.assertEqual(source.params[0]['archived'],'yes');self.assertNotIn('summary',source.params[0])

    def test_partial_duplicate_changed_or_failed_pages_never_return_success(self):
        first=page([raw(identifier=1)],2)
        changed=copy.deepcopy(first);changed['data'][0]['syncToken']=2
        for pages in ([first,page([],2)], [first,page([raw(identifier=1)],2)],
                      [first,page([raw(identifier=2)],2),changed],
                      [first,RuntimeError('source failure')]):
            with self.subTest(pages=len(pages)),self.assertRaises(ValueError):
                asyncio.run(fetch_transactions(Source(pages),'salesorder',T,page_size=1))
        self.assertEqual(self.journal.summary()['states'],{})

    def test_full_scan_missing_is_review_candidate_and_never_auto_archives(self):
        p=normalize_transaction('salesorder',raw(),T)
        self.journal.stage([p],cursors={'salesorder':T},full_entities=['salesorder'])
        self.journal.stage([],cursors={'salesorder':'2026-10-11T12:00:00Z'},full_entities=['salesorder'])
        self.assertEqual(self.journal.summary()['missing_candidates'],{'salesorder':1})
        self.assertEqual(self.journal.summary()['states'],{'pending':1})
        self.journal.stage([p],cursors={'salesorder':'2026-10-12T12:00:00Z'},full_entities=['salesorder'])
        self.assertEqual(self.journal.summary()['missing_candidates'],{})

    def test_scan_failure_leaves_all_cursors_and_queue_unchanged(self):
        with patch('src.integrations.sos_odoo_mirror.sync.fetch_master_records',new=AsyncMock(return_value=[])),\
             patch('src.integrations.sos_odoo_mirror.sync.fetch_transactions',new=AsyncMock(side_effect=ValueError('incomplete_page'))):
            with self.assertRaisesRegex(ValueError,'incomplete'):
                asyncio.run(synchronize(self.journal,object(),object(),account_code='synthetic',company_id=1))
        self.assertIsNone(self.journal.cursor('customer'));self.assertEqual(self.journal.summary()['states'],{})
        self.assertIsNotNone(self.journal.acquire_run())

    def test_previous_delivery_progresses_even_when_next_source_scan_fails(self):
        self.journal.stage([normalize_transaction('salesorder',raw(),T)])
        client=type('Client',(),{'import_transaction':AsyncMock(return_value={'status':'created','res_id':123})})()
        with patch('src.integrations.sos_odoo_mirror.sync.fetch_master_records',new=AsyncMock(side_effect=ValueError('incomplete_page'))):
            with self.assertRaisesRegex(ValueError,'incomplete_page'):
                asyncio.run(synchronize(self.journal,object(),client,account_code='synthetic',company_id=1))
        self.assertEqual(self.journal.summary()['states'],{'done':1});self.assertIsNone(self.journal.cursor('customer'))

    def test_run_lease_is_exclusive_and_crash_recoverable(self):
        first=self.journal.acquire_run(now=100)
        self.assertIsNone(self.journal.acquire_run(now=101))
        self.assertEqual(self.journal.acquire_run(now=102,owner=first),first)
        second=self.journal.acquire_run(now=8000)
        self.assertNotEqual(first,second)
        self.journal.release_run(first)
        self.assertIsNone(self.journal.acquire_run(now=8001))

    def test_reconciliation_is_periodic_and_cursor_commits_before_delivery(self):
        with patch('src.integrations.sos_odoo_mirror.sync.fetch_master_records',new=AsyncMock(return_value=[])),\
             patch('src.integrations.sos_odoo_mirror.sync.fetch_transactions',new=AsyncMock(return_value=[])) as fetch,\
             patch('src.integrations.sos_odoo_mirror.sync.deliver',new=AsyncMock(return_value={'states':{}})):
            asyncio.run(synchronize(self.journal,object(),object(),account_code='synthetic',company_id=1))
            self.assertTrue(all(call.kwargs['since'] is None for call in fetch.call_args_list))
            fetch.reset_mock()
            asyncio.run(synchronize(self.journal,object(),object(),account_code='synthetic',company_id=1))
            self.assertTrue(all(call.kwargs['since'] is not None for call in fetch.call_args_list))
            self.assertIsNotNone(self.journal.cursor('full:salesorder'))

    def test_complete_pipeline_restarts_without_duplicate_native_records(self):
        from src.integrations.sos_odoo_mirror.capture import project_record
        from src.integrations.sos_odoo_mirror.client import MirrorError
        from test_sos_mirror_master import master_record
        async def masters(client,entity,**kwargs):
            record=master_record();record['id']=18 if entity=='vendor' else 17
            return [project_record(record,entity)]
        async def transactions(client,entity,observed,**kwargs):
            return [normalize_transaction(entity,raw(entity),observed)]
        class Client:
            def __init__(self):self.native={};self.failed=False
            async def send(client,**kwargs):
                p=kwargs['payload'];key=(p['entity'],p['source_id']);previous=key in client.native
                client.native.setdefault(key,len(client.native)+1)
                if p['entity']=='shipment' and not client.failed:
                    client.failed=True;raise MirrorError('odoo_transport_error',retryable=True)
                key_name='partner_id' if p['entity'] in ('customer','vendor') else 'res_id'
                return {'status':'duplicate' if previous else 'created',key_name:client.native[key]}
            import_partner=send
            import_transaction=send
        client=Client()
        with patch('src.integrations.sos_odoo_mirror.sync.fetch_master_records',new=masters),\
             patch('src.integrations.sos_odoo_mirror.sync.fetch_transactions',new=transactions):
            first=asyncio.run(synchronize(self.journal,object(),client,account_code='synthetic',company_id=1))
            self.assertEqual(first['states'],{'done':11,'pending':1})
            with self.journal.transaction() as db:db.execute('UPDATE deliveries SET next_attempt=0')
            restarted=DeliveryJournal(self.root.name,TARGET)
            result=asyncio.run(synchronize(restarted,object(),client,account_code='synthetic',company_id=1))
        self.assertEqual(result['states'],{'done':12});self.assertEqual(len(client.native),12)

    def test_lake_mode_skips_api_deltas_and_preserves_full_reconciliation(self):
        with patch('src.integrations.sos_odoo_mirror.sync.fetch_master_records',new=AsyncMock(return_value=[])),\
             patch('src.integrations.sos_odoo_mirror.sync.fetch_transactions',new=AsyncMock(return_value=[])) as fetch,\
             patch('src.integrations.sos_odoo_mirror.lake.consume_existing_lake',new=AsyncMock(return_value=0)) as lake:
            asyncio.run(synchronize(self.journal,object(),object(),account_code='synthetic',company_id=1,lake_root=self.root.name))
            self.assertEqual(fetch.await_count,10);fetch.reset_mock()
            asyncio.run(synchronize(self.journal,object(),object(),account_code='synthetic',company_id=1,lake_root=self.root.name))
            self.assertEqual(fetch.await_count,0)
            asyncio.run(synchronize(self.journal,object(),object(),account_code='synthetic',company_id=1,lake_root=self.root.name,reconcile=True))
            self.assertEqual(fetch.await_count,10);self.assertEqual(lake.await_count,3)
