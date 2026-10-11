import json
from pathlib import Path
import tempfile
import unittest
from src.integrations.sos_odoo_mirror.contract import normalize, order_batch, validate
from src.integrations.sos_odoo_mirror.__main__ import load_batch

T = "2026-10-10T12:00:00Z"


class DependenciesTests(unittest.TestCase):
    def test_child_before_parent_orders_root_first_with_multiple_levels(self):
        raw = [{"id": 3, "name": "Leaf", "parent": {"id": 2}},
               {"id": 2, "name": "Child", "parent": {"id": 1}}, {"id": 1, "name": "Root"}]
        self.assertEqual([p["source_id"] for p in order_batch([normalize("customer", r, T) for r in raw])], ["1", "2", "3"])

    def test_cycle_and_missing_parent_rejected(self):
        for raw, code in (([{"id": 1, "name": "A", "parent": {"id": 2}}], "missing_parent"),
            ([{"id": 1, "name": "A", "parent": {"id": 2}}, {"id": 2, "name": "B", "parent": {"id": 1}}], "parent_cycle")):
            with self.assertRaisesRegex(ValueError, code):
                order_batch([normalize("customer", r, T) for r in raw])

    def test_parent_identity_is_part_of_payload_hash(self):
        root = normalize("customer", {"id": 2, "name": "A"}, T)
        child = normalize("customer", {"id": 2, "name": "A", "parent": {"id": 1}}, T)
        self.assertNotEqual(validate(root)[1], validate(child)[1])

    def test_legacy_wire_still_valid(self):
        payload = {"schema_version": 1, "entity": "customer", "source_id": "1", "observed_at": T,
            "values": {"name": "Legacy", "email": "", "phone": "", "website": ""}}
        validate(payload)

    def test_invalid_parent_and_vendor_hierarchy_rejected(self):
        for parent in ({"id": True}, {"id": 0}, {"id": 1}, {}):
            with self.assertRaises(ValueError):
                normalize("customer", {"id": 1, "name": "X", "parent": parent}, T)
        with self.assertRaises(ValueError):
            normalize("vendor", {"id": 2, "name": "X", "parent": {"id": 1}}, T)

    def test_historical_blocked_count_recomputed_without_changing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/"capture.json"
            raw = {"metadata": {"source_system": "sos_inventory", "entity_name": "customer",
                "written_at_utc": T, "record_count": 2, "mirror_capture_version": 1,
                "pagination_checked": True, "source_scope": "test", "blocked_count": 1},
                "payload": [{"id": 2, "name": "Child", "parent": {"id": 1}}, {"id": 1, "name": "Parent"}]}
            p.write_text(json.dumps(raw))
            before = p.read_bytes()
            batch = load_batch(p, "customer", expected_source_scope="test")
            self.assertEqual([r["source_id"] for r in batch], ["1", "2"])
            self.assertEqual(p.read_bytes(), before)
