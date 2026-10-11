import tempfile
import unittest
from pathlib import Path
from pydantic import SecretStr
from src.core.configs.sos_mirror import SosMirrorSettings
from src.worker.jobs.push_data.sos_odoo_mirror import build_sos_mirror_job


class MirrorSettingsTests(unittest.TestCase):
    def settings(self,**extra):
        return SosMirrorSettings(_env_file=None,**extra)

    def test_scheduler_is_disabled_by_default_and_no_key_is_required(self):
        s=self.settings()
        self.assertFalse(s.sos_mirror_job_enabled)
        self.assertFalse(s.sos_mirror_source_owner_confirmed)
        self.assertIsNone(s.sos_mirror_odoo_api_key)

    def test_owner_confirmation_is_required_before_building_enabled_job(self):
        with self.assertRaisesRegex(ValueError,'owner_confirmation'):
            build_sos_mirror_job(self.settings())

    def test_reviewed_configuration_pins_target_and_invalid_custom_ids_fail(self):
        with tempfile.TemporaryDirectory() as root:
            values=dict(sos_mirror_source_owner_confirmed=True,sos_mirror_account_code='synthetic',
                sos_mirror_company_id=1,sos_mirror_odoo_database='synthetic',sos_mirror_odoo_url='https://odoo.example.test',
                sos_mirror_odoo_api_key=SecretStr('synthetic-test-key'),sos_mirror_journal_root=Path(root))
            job=build_sos_mirror_job(self.settings(**values))
            self.assertEqual(job.journal.summary()['states'],{})
            values['sos_mirror_custom_field_ids']=[1,1]
            with self.assertRaisesRegex(ValueError,'custom_field_approval'):
                build_sos_mirror_job(self.settings(**values))
