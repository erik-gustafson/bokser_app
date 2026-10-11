import asyncio
import copy
import tempfile
import unittest
from src.integrations.sos_odoo_mirror.delivery import DeliveryJournal, deliver
from src.integrations.sos_odoo_mirror.client import MirrorError
from src.integrations.sos_odoo_mirror.transactions import normalize_transaction
from test_sos_mirror_transactions import raw, T

TARGET = {'url':'https://odoo.example.test', 'database':'synthetic', 'account_code':'synthetic', 'company_id':1}


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.journal = DeliveryJournal(self.root.name, TARGET)
        self.payload = normalize_transaction('salesorder', raw(), T)

    def test_target_is_pinned_and_cannot_store_credentials(self):
        with self.assertRaisesRegex(ValueError, 'target_changed'):
            DeliveryJournal(self.root.name, dict(TARGET, company_id=2))
        with self.assertRaisesRegex(ValueError, 'invalid_delivery_target'):
            DeliveryJournal(self.root.name, dict(TARGET, api_key='excluded'))

    def test_revision_conflict_rolls_back_stage_and_cursor(self):
        self.journal.stage([self.payload], scan_entity='salesorder', scan_started_at=T)
        changed=copy.deepcopy(self.payload);changed['number']='Conflicting revision'
        other=normalize_transaction('invoice', raw('invoice'), T)
        with self.assertRaisesRegex(ValueError, 'source_revision_conflict'):
            self.journal.stage([other, changed], scan_entity='salesorder', scan_started_at='2026-10-11T12:00:00Z')
        self.assertEqual(self.journal.summary()['states'], {'pending':1})
        self.assertEqual(self.journal.cursor('salesorder'), T)

    def test_lease_crash_replays_and_stale_owner_cannot_acknowledge(self):
        self.journal.stage([self.payload])
        first=self.journal.claim(now=100)
        self.assertIsNone(self.journal.claim(now=101))
        second=self.journal.claim(now=221)
        self.assertEqual(first[0],second[0]);self.assertNotEqual(first[1],second[1])
        result={'status':'duplicate','res_id':123}
        with self.assertRaisesRegex(ValueError,'lease_lost'):
            self.journal.finish(first[0],first[1],result)
        self.journal.finish(second[0],second[1],result)
        self.assertEqual(self.journal.summary()['states'],{'done':1})

    def test_transient_retry_blocks_overtaking_and_waits_for_dependencies(self):
        shipment=raw('shipment');shipment['lines'][0]['linkedTransaction']={'id':17,'transactionType':'Sales Order','lineNumber':1}
        child=normalize_transaction('shipment',shipment,T)
        self.journal.stage([child,self.payload])
        parent=self.journal.claim(now=100)
        self.assertEqual(parent[2]['entity'],'salesorder')
        self.journal.fail(parent[0],parent[1],retryable=True,code='odoo_http_503',now=100)
        self.assertIsNone(self.journal.claim(now=101))
        parent=self.journal.claim(now=131)
        self.journal.finish(parent[0],parent[1],{'status':'created','res_id':123})
        child_claim=self.journal.claim(now=131)
        self.assertEqual(child_claim[2]['entity'],'shipment')

    def test_nontransient_error_requires_explicit_retry_and_codes_are_sanitized(self):
        self.journal.stage([self.payload]);claim=self.journal.claim(now=100)
        self.journal.fail(claim[0],claim[1],retryable=False,code='private unexpected text',now=100)
        self.assertIsNone(self.journal.claim(now=10000))
        self.assertEqual(self.journal.summary()['errors'],{'mirror_delivery_failed':1})
        self.assertEqual(self.journal.retry_blocked(),1)
        self.assertIsNotNone(self.journal.claim(now=10000))

    def test_delivery_replay_after_commit_without_acknowledgement(self):
        self.journal.stage([self.payload])
        class FakeClient:
            def __init__(self):self.native={};self.calls=0
            async def import_transaction(client,**kwargs):
                client.calls+=1
                key=kwargs['payload']['source_id']
                previous=key in client.native
                client.native[key]=123
                if client.calls==1:raise MirrorError('odoo_transport_error',retryable=True)
                return {'status':'duplicate' if previous else 'created','res_id':123}
        client=FakeClient()
        asyncio.run(deliver(self.journal,client,account_code='synthetic',company_id=1))
        with self.journal.transaction() as db:
            db.execute('UPDATE deliveries SET next_attempt=0')
        result=asyncio.run(deliver(self.journal,client,account_code='synthetic',company_id=1))
        self.assertEqual(result['states'],{'done':1});self.assertEqual(client.native,{'17':123})

    def test_revisions_cannot_overtake_an_unacknowledged_version(self):
        self.journal.stage([self.payload])
        newer=copy.deepcopy(self.payload);newer['sync_token']='2'
        self.journal.stage([newer])
        first=self.journal.claim(now=100)
        self.assertIsNone(self.journal.claim(now=101))
        self.journal.finish(first[0],first[1],{'status':'created','res_id':123})
        self.assertEqual(self.journal.claim(now=101)[2]['sync_token'],'2')

    def test_restore_replay_requires_stopped_delivery_and_preserves_snapshots(self):
        self.journal.stage([self.payload]);claim=self.journal.claim()
        with self.assertRaisesRegex(ValueError,'requires_stopped'):
            self.journal.replay_reviewed_all()
        self.journal.finish(claim[0],claim[1],{'status':'created','res_id':123})
        self.assertEqual(self.journal.replay_reviewed_all(),1)
        self.assertEqual(self.journal.claim()[2],self.payload)

    def test_backfill_requeues_only_latest_exclusions_in_selected_date_scope(self):
        p=copy.deepcopy(self.payload);p['transaction_date']='2025-06-01'
        q=copy.deepcopy(p);q['sync_token']='2'
        older=copy.deepcopy(p);older['source_id']='19';older['transaction_date']='2024-01-01'
        for item in (p,q,older):
            self.journal.stage([item]);claim=self.journal.claim()
            self.journal.finish(claim[0],claim[1],{'status':'before_cutoff','res_id':None})
        current=copy.deepcopy(self.payload);current['source_id']='20'
        self.journal.stage([current]);claim=self.journal.claim()
        self.journal.finish(claim[0],claim[1],{'status':'created','res_id':123})
        self.assertEqual(self.journal.requeue_cutoff_exclusions('2025-01-01'),1)
        claim=self.journal.claim()
        self.assertEqual(claim[2]['sync_token'],'2');self.assertEqual(claim[2]['transaction_date'],'2025-06-01')

    def test_backfill_requires_stopped_runs_and_canonical_date(self):
        owner=self.journal.acquire_run()
        with self.assertRaisesRegex(ValueError,'requires_stopped'):
            self.journal.requeue_cutoff_exclusions('2025-01-01')
        self.journal.release_run(owner)
        for value in ('20250101','bad','2025-02-30'):
            with self.assertRaises(ValueError):self.journal.requeue_cutoff_exclusions(value)

    def test_transport_accepts_stale_exclusion_without_native_record(self):
        import httpx
        from src.integrations.sos_odoo_mirror.client import OdooMirrorClient
        async def run():
            transport=httpx.MockTransport(lambda request:httpx.Response(200,json={
                'status':'stale','entity':'salesorder','source_id':'17','res_id':None}))
            async with httpx.AsyncClient(transport=transport) as http:
                client=OdooMirrorClient(base_url=TARGET['url'],database='synthetic',api_key='synthetic-test-key',client=http)
                return await client.import_transaction(account_code='synthetic',company_id=1,payload=self.payload)
        self.assertEqual(asyncio.run(run())['status'],'stale')
