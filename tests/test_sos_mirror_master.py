import copy
import unittest
from src.integrations.sos_odoo_mirror.contract import normalize, validate, revision_action, payload_digest
from src.integrations.sos_odoo_mirror.capture import project_record

T = "2026-10-10T12:00:00Z"


def master_record(**extra):
    return dict(id=1, syncToken=0, name="Synthetic master", email=None, phone=None,
        mobile=None, website=None, archived=False, summaryOnly=False, companyName=None,
        altPhone=None, fax=None, contact=None, billing=None, shipping=None,
        address=None, accountNumber=None, terms=None, currency=None, **extra)


class MasterTests(unittest.TestCase):
    def test_revision_and_master_shape(self):
        p = normalize("customer", master_record(), T)
        self.assertEqual((p["schema_version"], p["sync_token"]), (3, "0"))
        self.assertEqual(validate(p)[1], payload_digest(p))

    def test_business_hash_excludes_revision_and_capture_time(self):
        p = normalize("customer", master_record(), T)
        q = copy.deepcopy(p)
        q.update(sync_token="100", observed_at="2026-10-11T12:00:00Z")
        self.assertEqual(validate(p)[1], validate(q)[1])
        q["master"]["contact"]["firstName"] = "Changed"
        self.assertNotEqual(validate(p)[1], validate(q)[1])

    def test_revision_prevents_later_capture_from_overwriting_newer_source(self):
        self.assertEqual(revision_action("10", "9", "a", "b", True), "stale")
        self.assertEqual(revision_action("9", "10", "a", "b", True), "update")
        self.assertEqual(revision_action("9", "10", "a", "a", True), "duplicate")
        with self.assertRaisesRegex(ValueError, "source_revision_conflict"):
            revision_action("10", "10", "a", "b", True)
        with self.assertRaisesRegex(ValueError, "local_edit_conflict"):
            revision_action("10", "9", "a", "b", False)

    def test_old_capture_with_version_requires_recapture(self):
        with self.assertRaisesRegex(ValueError, "recapture_required"):
            normalize("customer", {"id": 1, "name": "Old", "syncToken": 0}, T)

    def test_summary_cannot_clear_complete_master_even_with_all_keys_present(self):
        r = master_record(); r["summaryOnly"] = True
        with self.assertRaisesRegex(ValueError, "summary_master_record_forbidden"):
            normalize("customer", r, T)

    def test_strict_token_and_values(self):
        for token in (True, -1, "1"):
            r = master_record(); r["syncToken"] = token
            with self.assertRaises(ValueError): normalize("customer", r, T)
        for token in ("-1", "01", "", "1.0", "1" * 65, "\u0661", None, True):
            p = normalize("customer", master_record(), T); p["sync_token"] = token
            with self.assertRaises(ValueError): validate(p)
        for key in ("companyName", "altPhone", "fax", "accountNumber"):
            r = master_record(); r[key] = False
            with self.assertRaises(ValueError): normalize("vendor", r, T)

    def test_projection_nested_allowlist_and_ambiguous_addresses(self):
        r = master_record(); r["contact"] = dict(title="", firstName="Synthetic", middleName="",
            lastName="Person", suffix="", password="excluded")
        r["currency"] = {"id": 42, "name": "excluded"}
        r["customFields"] = [{"id": 1, "value": "excluded"}]
        safe = project_record(r, "customer")
        self.assertNotIn("excluded", str(safe))
        self.assertEqual(normalize("customer", safe, T)["master"]["currency_id"], "42")
        r["altAddresses"] = [{"portalPassword": "excluded"}]
        with self.assertRaisesRegex(ValueError, "incomplete_master_fields"):
            project_record(r, "customer")

    def test_master_source_whitespace_preserved_and_other_controls_rejected(self):
        r = master_record(); r["contact"] = dict(title="", firstName="Synthetic\tPerson",
            middleName="", lastName="", suffix="")
        self.assertEqual(normalize("customer", r, T)["master"]["contact"]["firstName"], "Synthetic\tPerson")
        r["contact"]["firstName"] = "Synthetic\x00Person"
        with self.assertRaisesRegex(ValueError, "invalid_master_value"):
            normalize("customer", r, T)
