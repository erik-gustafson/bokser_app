import copy
import unittest
from src.integrations.sos_odoo_mirror.capture import project_record
from src.integrations.sos_odoo_mirror.contract import ADDRESS_FIELDS, ALTERNATE_FIELDS, normalize, validate, payload_digest
from test_sos_mirror_master import master_record, T


def alternate(name="Secondary", kind="Shipping"):
    result = dict.fromkeys(ALTERNATE_FIELDS, "")
    result.update(addressName=name, addressType=kind, address=dict.fromkeys(ADDRESS_FIELDS, ""))
    result["address"].update(line1="Synthetic address")
    return result


class LifecycleTests(unittest.TestCase):
    def test_owner_skips_and_entity_scope_filter_values_before_capture(self):
        from src.integrations.sos_odoo_mirror.contract import selected_custom_field_ids
        requested=[1,5,7,8,9,10,11,12,13,14,16,17,18,19,20,24]
        r=master_record();r['customFields']=[{'id':i,'value':'00123' if i==1 else 'excluded'} for i in requested]
        safe=project_record(r,'customer',approved_fields=requested)
        self.assertEqual(safe['approvedCustomFields'],{'1':'00123'})
        self.assertNotIn('excluded',str(safe))
        self.assertEqual(selected_custom_field_ids('shipment',requested),{'7'})
        for entity in ('vendor','salesorder','return','rma'):
            self.assertEqual(selected_custom_field_ids(entity,requested),set())
    def test_alternates_are_order_independent_and_scoped_source_keys(self):
        r = master_record(); r["altAddresses"] = [alternate(), alternate("Invoice", "Billing")]
        p = normalize("customer", project_record(r, "customer"), T)
        r["altAddresses"].reverse()
        q = normalize("customer", project_record(r, "customer"), T)
        self.assertEqual(validate(p)[1], validate(q)[1])
        self.assertEqual(len({a["key"] for a in p["master"]["alternates"]}), 2)
        q["master"]["alternates"][0]["key"] = "forged"
        with self.assertRaises(ValueError): validate(q)

    def test_duplicate_label_type_rejected_without_adopting_by_content(self):
        r = master_record(); r["altAddresses"] = [alternate(), alternate()]
        with self.assertRaisesRegex(ValueError, "duplicate_alternate"):
            project_record(r, "customer")

    def test_archival_is_explicit_and_hashed(self):
        r = master_record(); p = normalize("customer", project_record(r, "customer"), T)
        r["archived"] = True; q = normalize("customer", project_record(r, "customer"), T)
        self.assertTrue(q["archived"])
        self.assertNotEqual(validate(p)[1], validate(q)[1])

    def test_custom_approval_allowlist_excludes_unselected_values(self):
        r = master_record(); r["customFields"] = [{"id": 1, "value": "Synthetic"}, {"id": 2, "value": "excluded"}]
        safe = project_record(r, "customer", approved_fields=[1])
        self.assertNotIn("excluded", str(safe))
        p = normalize("customer", safe, T)
        self.assertEqual(p["master"]["custom_fields"], {"1": "Synthetic"})
        self.assertEqual(p["schema_version"], 4)

    def test_upgrade_hash_preserves_previous_schema_projection(self):
        r = master_record(); old = normalize("customer", r, T)
        new = normalize("customer", project_record(r, "customer"), T)
        self.assertEqual(payload_digest(old), payload_digest(new, 3))
