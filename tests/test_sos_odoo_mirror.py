import asyncio
import json
import tempfile
import unittest
from pathlib import Path
import httpx
from src.integrations.sos_odoo_mirror.contract import normalize, validate, replay_action, timestamp
from src.integrations.sos_odoo_mirror.__main__ import load_batch
from src.integrations.sos_odoo_mirror.client import OdooMirrorClient, MirrorError

T = "2026-10-09T12:00:00Z"


class ContractTests(unittest.TestCase):
    def test_allowlist_excludes_secrets_and_raw_payload(self):
        p = normalize("customer", {"id": 1, "name": "Example", "portalPassword": "excluded",
            "accountToken": "excluded", "values_raw": {"secret": "excluded"}}, T)
        self.assertNotIn("excluded", json.dumps(p))
        self.assertEqual(p["source_id"], "1")

    def test_mobile_only_maps_to_native_phone_and_dual_numbers_block(self):
        payload = normalize("customer", {"id": 1, "name": "X", "mobile": "555-0100"}, T)
        self.assertEqual(payload["values"]["phone"], "555-0100")
        self.assertNotIn("mobile", payload["values"])
        with self.assertRaisesRegex(ValueError, "multiple_phone_numbers_pending"):
            normalize("customer", {"id": 1, "name": "X", "phone": "555-0100", "mobile": "555-0101"}, T)

    def test_id_and_value_validation(self):
        for identifier in (True, "1", 0, -1):
            with self.assertRaises(ValueError):
                normalize("vendor", {"id": identifier, "name": "X"}, T)
        for value in (False, {}, [], 3, "X\nY"):
            with self.assertRaises(ValueError):
                normalize("customer", {"id": 1, "name": "X", "phone": value}, T)

    def test_hierarchy_and_archived_rejected(self):
        for extra in ({"parent": {"id": 2}}, {"archived": True}):
            with self.assertRaises(ValueError):
                normalize("customer", {"id": 1, "name": "X", **extra}, T)

    def test_timezone_and_unknown_fields_rejected(self):
        with self.assertRaises(ValueError):
            normalize("customer", {"id": 1, "name": "X"}, "2026-10-09T12:00:00")
        p = normalize("customer", {"id": 1, "name": "X"}, T)
        p["values"]["password"] = "excluded"
        with self.assertRaises(ValueError):
            validate(p)

    def test_replay_order_and_conflict(self):
        old = timestamp(T)
        new = timestamp("2026-10-09T13:00:00Z")
        self.assertEqual(replay_action(old, "a", old, "a", True), "duplicate")
        self.assertEqual(replay_action(new, "b", old, "a", True), "stale")
        self.assertEqual(replay_action(old, "a", new, "b", True), "update")
        with self.assertRaisesRegex(ValueError, "observation_conflict"):
            replay_action(old, "a", old, "b", True)
        with self.assertRaisesRegex(ValueError, "local_edit_conflict"):
            replay_action(old, "a", new, "b", False)

    def test_batch_rejects_duplicate_ids_and_count_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"snapshot.json"
            records = [{"id": 1, "name": "X"}]*2
            path.write_text(json.dumps(records))
            with self.assertRaisesRegex(ValueError, "duplicate_source_id"):
                load_batch(path, "customer", T)
            path.write_text(json.dumps({"metadata": {"source_system": "sos_inventory",
                "entity_name": "customer", "written_at_utc": T, "record_count": 2},
                "payload": records[:1]}))
            with self.assertRaisesRegex(ValueError, "lake_count_mismatch"):
                load_batch(path, "customer")

    def test_valid_existing_lake_envelope(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"snapshot.json"
            path.write_text(json.dumps({"metadata": {"source_system": "sos_inventory",
                "entity_name": "vendor", "written_at_utc": T, "record_count": 1},
                "payload": [{"id": 3, "name": "X"}]}))
            self.assertEqual(load_batch(path, "vendor")[0]["source_id"], "3")


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_json2_call_and_replay_response(self):
        calls = []
        def transport(request):
            calls.append(request)
            return httpx.Response(200, json={"status": "duplicate", "source_id": "1", "partner_id": 9})
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
            client = OdooMirrorClient(base_url="https://example.invalid", database="test", api_key="test-key", client=http)
            result = await client.import_partner(account_code="sos", company_id=2,
                payload=normalize("customer", {"id": 1, "name": "X"}, T))
        self.assertEqual(result["status"], "duplicate")
        self.assertEqual(len(calls), 1)
        self.assertEqual(str(calls[0].url), "https://example.invalid/json/2/bokser.sos.account/import_partner")
        self.assertEqual(json.loads(calls[0].content)["company_id"], 2)

    async def test_error_sanitization_and_no_redirect_or_retry(self):
        calls = []
        def transport(request):
            calls.append(request)
            return httpx.Response(302, headers={"Location": "https://other.invalid"}, text="secret body")
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
            client = OdooMirrorClient(base_url="https://example.invalid", database="test", api_key="test-key", client=http)
            with self.assertRaisesRegex(MirrorError, "odoo_request_failed") as error:
                await client.import_partner(account_code="sos", company_id=2,
                    payload=normalize("vendor", {"id": 1, "name": "X"}, T))
            self.assertNotIn("secret", str(error.exception))
        self.assertEqual(len(calls), 1)

    async def test_reject_insecure_or_credential_urls(self):
        for url in ("http://example.invalid", "https://user:pass@example.invalid", "https://example.invalid/path", "https://example.invalid?token=x"):
            with self.assertRaises(ValueError):
                OdooMirrorClient(base_url=url, database="test", api_key="key", client=None)


if __name__ == "__main__":
    unittest.main()
