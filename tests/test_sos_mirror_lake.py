import copy
import tempfile
import unittest
from pathlib import Path
from src.storage.raw.writer import RawPayloadWriter
from src.integrations.sos_odoo_mirror.delivery import DeliveryJournal
from src.integrations.sos_odoo_mirror.lake import stage_file
from test_sos_mirror_delivery import TARGET
from test_sos_mirror_transactions import raw


class LakeTests(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.TemporaryDirectory();self.addCleanup(self.root.cleanup)
        self.journal=DeliveryJournal(Path(self.root.name)/'private',TARGET)
        self.lake=Path(self.root.name)/'lake'
        result=RawPayloadWriter(self.lake).write_json_payload(source_system='sos_inventory',entity_name='updated_sales_orders',payload=[raw()])
        self.manifest={'id':1,'source_name':'sos_inventory','entity_name':'updated_sales_orders',
            'file_path':str(result.file_path),'record_count':1,'sha256':result.sha256}

    def test_valid_lake_file_stages_idempotently_without_source_watermarks(self):
        stage_file(self.journal,self.lake,self.manifest)
        stage_file(self.journal,self.lake,self.manifest)
        self.assertEqual(self.journal.lake_cursor(),1)
        self.assertEqual(self.journal.summary()['states'],{'pending':1})
        self.assertIsNone(self.journal.cursor('salesorder'))

    def test_corrupt_mismatched_and_outside_files_never_advance_receipt(self):
        for overrides in ({'sha256':'0'*64},{'record_count':2},{'entity_name':'updated_invoices'},
                          {'file_path':str(Path(self.root.name)/'elsewhere.json')},{'source_name':'other'}):
            with self.subTest(overrides=list(overrides)),self.assertRaises(ValueError):
                stage_file(self.journal,self.lake,dict(self.manifest,**overrides))
        self.assertEqual(self.journal.lake_cursor(),0);self.assertEqual(self.journal.summary()['states'],{})

    def test_changed_manifest_is_rejected_atomically(self):
        stage_file(self.journal,self.lake,self.manifest)
        with self.assertRaisesRegex(ValueError,'manifest_changed'):
            self.journal.stage([],manifest=(1,'0'*64))
        self.assertEqual(self.journal.lake_cursor(),1)

    def test_incomplete_source_record_never_becomes_delivery(self):
        record=raw();del record['syncToken']
        result=RawPayloadWriter(self.lake).write_json_payload(source_system='sos_inventory',entity_name='updated_sales_orders',payload=[record])
        bad=dict(self.manifest,file_path=str(result.file_path),sha256=result.sha256)
        with self.assertRaises(ValueError):stage_file(self.journal,self.lake,bad)
        self.assertEqual(self.journal.lake_cursor(),0)

    def test_source_conflict_rolls_back_lake_receipt(self):
        stage_file(self.journal,self.lake,self.manifest)
        record=raw(number='Different same revision')
        result=RawPayloadWriter(self.lake).write_json_payload(source_system='sos_inventory',entity_name='updated_sales_orders',payload=[record])
        bad=dict(self.manifest,id=2,file_path=str(result.file_path),sha256=result.sha256)
        with self.assertRaisesRegex(ValueError,'source_revision_conflict'):stage_file(self.journal,self.lake,bad)
        self.assertEqual(self.journal.lake_cursor(),1)
