import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
import httpx
from src.integrations.sos_odoo_mirror.capture import CaptureError, capture_master, fetch_master_records
from src.integrations.sos_odoo_mirror.__main__ import load_batch


def record(identifier, **extra):
    return {"id": identifier, "syncToken": 0, "name": "Synthetic", "email": None,
        "website": None, "phone": None, "mobile": None, "archived": False,
        "summaryOnly": False, **extra}


def page(records, total=None, **extra):
    body = {"status": "ok", "count": len(records), "totalCount": len(records) if total is None else total,
        "data": records, **extra}
    return httpx.Response(200, json=body, request=httpx.Request("GET", "https://example.invalid"))


class FakeClient:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    async def get(self, path, *, params):
        self.calls.append((path, params))
        response = self.pages.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class CaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_pages_and_sensitive_allowlist(self):
        first = page([record(1, portalPassword="excluded", keys={"secret": "excluded"}), record(2)], 3)
        client = FakeClient([first, page([record(3)], 3), first])
        captured = await fetch_master_records(client, "customer", page_size=2)
        self.assertEqual([r["id"] for r in captured], [1, 2, 3])
        self.assertNotIn("excluded", json.dumps(captured))
        self.assertEqual([c[1]["start"] for c in client.calls], [1, 3, 1])
        self.assertTrue(all("summary" not in c[1] and "updatedsince" not in c[1] for c in client.calls))

    async def test_failed_later_page_has_no_file_or_success_receipt(self):
        client = FakeClient([page([record(1), record(2)], 3), RuntimeError("private source body")])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(CaptureError, "source_request_failed") as exc:
                await capture_master(client, entity="customer", scope="test", output_root=directory, page_size=2)
            self.assertNotIn("private", str(exc.exception))
            self.assertEqual(list(Path(directory).rglob("*.json")), [])
            with closing(sqlite3.connect(Path(directory)/"test/_mirror_capture/captures.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM captures").fetchone()[0], 0)

    async def test_duplicate_ids_rejected(self):
        client = FakeClient([page([record(1), record(2)], 3), page([record(1)], 3)])
        with self.assertRaisesRegex(CaptureError, "duplicate_or_missing"):
            await fetch_master_records(client, "vendor", page_size=2)

    async def test_retry_after_failure_performs_full_scan_and_records_only_success(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(CaptureError):
                await capture_master(FakeClient([RuntimeError("timeout")]), entity="vendor",
                    scope="test", output_root=directory)
            response = page([record(1)])
            client = FakeClient([response, response])
            result = await capture_master(client, entity="vendor", scope="test", output_root=directory)
            self.assertEqual(result["record_count"], 1)
            self.assertEqual(client.calls[0][1]["start"], 1)
            with closing(sqlite3.connect(Path(directory)/"test/_mirror_capture/captures.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM captures").fetchone()[0], 1)

    async def test_short_page_rejected(self):
        client = FakeClient([page([record(1), record(2)], 4), page([record(3)], 4)])
        with self.assertRaisesRegex(CaptureError, "incomplete_page"):
            await fetch_master_records(client, "vendor", page_size=2)

    async def test_total_count_drift_rejected(self):
        client = FakeClient([page([record(1), record(2)], 3), page([record(3)], 4)])
        with self.assertRaisesRegex(CaptureError, "source_changed"):
            await fetch_master_records(client, "vendor", page_size=2)

    async def test_first_page_revision_drift_rejected(self):
        client = FakeClient([page([record(1)]), page([record(1, syncToken=1)])])
        with self.assertRaisesRegex(CaptureError, "source_changed"):
            await fetch_master_records(client, "customer")

    async def test_application_error_even_http_200_rejected(self):
        client = FakeClient([page([], status="error", message="Throttle limit exceeded.")])
        with self.assertRaisesRegex(CaptureError, "source_status_not_ok"):
            await fetch_master_records(client, "customer")

    async def test_count_mismatch_and_summary_and_missing_fields_rejected(self):
        missing = record(1)
        del missing["phone"]
        for response in (page([record(1)], count=2), page([record(1, summaryOnly=True)]), page([missing])):
            with self.assertRaises(CaptureError):
                await fetch_master_records(FakeClient([response]), "vendor")

    async def test_identity_version_validation(self):
        for bad in (record(True), record(0), record(1, syncToken=True), record(1, syncToken=-1)):
            with self.assertRaisesRegex(CaptureError, "identity_or_version"):
                await fetch_master_records(FakeClient([page([bad])]), "customer")

    async def test_empty_full_capture_valid(self):
        self.assertEqual(await fetch_master_records(FakeClient([page([]), page([])]), "vendor"), [])

    async def test_limits_and_scope_fail_before_network(self):
        client = FakeClient([])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(CaptureError, "invalid_source_scope"):
                await capture_master(client, entity="vendor", scope="../unsafe", output_root=directory)
            self.assertEqual(client.calls, [])
        with self.assertRaisesRegex(CaptureError, "limit_exceeded"):
            await fetch_master_records(FakeClient([page([record(1)], 100)]), "vendor", page_size=1, max_records=10)

    async def test_capture_receipt_separate_from_delivery_and_wrong_scope_rejected(self):
        response = page([record(1)])
        with tempfile.TemporaryDirectory() as directory:
            result = await capture_master(FakeClient([response, response]), entity="customer", scope="test", output_root=directory)
            batch = load_batch(result["file_path"], "customer", expected_source_scope="test")
            self.assertEqual(batch[0]["source_id"], "1")
            with self.assertRaisesRegex(ValueError, "source_scope_mismatch"):
                load_batch(result["file_path"], "customer", expected_source_scope="other")
            body = json.loads(Path(result["file_path"]).read_text())
            self.assertEqual(body["metadata"]["written_at_utc"], body["metadata"]["capture_started_at"])
            self.assertEqual(body["payload"][0]["syncToken"], 0)
            with closing(sqlite3.connect(Path(directory)/"test/_mirror_capture/captures.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT record_count FROM captures").fetchone()[0], 1)

    async def test_hierarchy_and_dual_phone_capture_revalidate_successfully(self):
        response = page([record(1), record(2, parent={"id": 1}), record(3, phone="a", mobile="b")])
        with tempfile.TemporaryDirectory() as directory:
            result = await capture_master(FakeClient([response, response]), entity="customer", scope="test", output_root=directory)
            self.assertEqual((result["ready_count"], result["blocked_count"]), (3, 0))
            self.assertEqual(len(load_batch(result["file_path"], "customer", expected_source_scope="test")), 3)


if __name__ == "__main__":
    unittest.main()
