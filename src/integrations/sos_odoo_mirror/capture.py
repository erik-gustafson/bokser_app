"""Opt-in full master capture. No SOS writes, ingestion claims or Odoo delivery."""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from .contract import digest, normalize
from src.storage.raw.writer import RawPayloadWriter

SAFE_FIELDS = ("id", "syncToken", "name", "email", "website", "phone", "mobile", "archived", "summaryOnly")
API_BASE = "https://api.sosinventory.com/api/v2"


class CaptureError(ValueError):
    pass


def source_scope(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value):
        raise CaptureError("invalid_source_scope")
    return value


def project_record(record):
    if not isinstance(record, dict) or not set(SAFE_FIELDS) <= set(record):
        raise CaptureError("incomplete_master_record")
    if record["summaryOnly"] is not False or record["archived"] is not False:
        raise CaptureError("summary_or_archived_record")
    if type(record["id"]) is not int or record["id"] <= 0 or type(record["syncToken"]) is not int or record["syncToken"] < 0:
        raise CaptureError("invalid_source_identity_or_version")
    if any(record[k] is not None and not isinstance(record[k], str) for k in ("name", "email", "website", "phone", "mobile")):
        raise CaptureError("invalid_source_contact_type")
    safe = {key: record[key] for key in SAFE_FIELDS}
    parent = record.get("parent")
    if parent is not None:
        if not isinstance(parent, dict) or type(parent.get("id")) is not int or parent["id"] <= 0:
            raise CaptureError("invalid_parent_reference")
        safe["parent"] = {"id": parent["id"]}
    return safe


def read_page(response, *, page_size, expected_count=None, expected_total=None):
    try:
        response.raise_for_status()
        body = response.json()
    except Exception:
        raise CaptureError("source_request_failed") from None
    if not isinstance(body, dict) or body.get("status") != "ok":
        raise CaptureError("source_status_not_ok")
    count, total, records = body.get("count"), body.get("totalCount"), body.get("data")
    if type(count) is not int or type(total) is not int or count < 0 or total < 0 or not isinstance(records, list):
        raise CaptureError("invalid_page_envelope")
    if count != len(records) or count > page_size or count > total:
        raise CaptureError("page_count_mismatch")
    if expected_total is not None and total != expected_total:
        raise CaptureError("source_changed_during_capture")
    if expected_count is not None and count != expected_count:
        raise CaptureError("incomplete_page")
    return total, [project_record(record) for record in records]


async def fetch_master_records(client, entity, *, page_size=200, max_records=10000):
    if entity not in ("customer", "vendor") or type(page_size) is not int or not 1 <= page_size <= 200 or type(max_records) is not int or max_records <= 0:
        raise CaptureError("invalid_capture_options")
    # Even summary=no requests summary records: never include that parameter.
    params = {"maxresults": page_size, "start": 1, "archived": "no"}
    try:
        response = await client.get("/" + entity, params=params)
        total, first = read_page(response, page_size=page_size)
        if total > max_records:
            raise CaptureError("capture_limit_exceeded")
        if len(first) != min(total, page_size):
            raise CaptureError("incomplete_first_page")
        records = list(first)
        for start in range(page_size + 1, total + 1, page_size):
            response = await client.get("/" + entity, params=dict(params, start=start))
            _, page = read_page(response, page_size=page_size, expected_total=total,
                expected_count=min(page_size, total - start + 1))
            records.extend(page)
        if len(records) != total or len({r["id"] for r in records}) != total:
            raise CaptureError("duplicate_or_missing_source_ids")
        # SOS exposes no atomic list snapshot. Detect count/first-page drift;
        # this cannot prove every page was immutable during the scan.
        response = await client.get("/" + entity, params=params)
        _, check = read_page(response, page_size=page_size, expected_total=total,
            expected_count=len(first))
        if digest(check) != digest(first):
            raise CaptureError("source_changed_during_capture")
        return records
    except CaptureError:
        raise
    except Exception:
        raise CaptureError("source_request_failed") from None


class CaptureJournal:
    """Private capture receipts, not ingestion cursors or delivery acknowledgments."""
    def __init__(self, root):
        self.path = Path(root)/"_mirror_capture"/"captures.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS captures (source_scope TEXT, entity TEXT, started_at TEXT, finished_at TEXT, file_path TEXT UNIQUE, sha256 TEXT, record_count INTEGER, ready_count INTEGER, blocked_count INTEGER)")
        self.path.chmod(0o600)

    @contextmanager
    def transaction(self):
        # Serialize manual capture processes. Crashes release the lock;
        # unsuccessful runs never commit a success receipt.
        with closing(sqlite3.connect(self.path, timeout=1)) as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                yield db


def publish_capture(writer, db, *, entity, scope, records, started_at, finished_at):
    source_scope(scope)
    blocked = []
    for record in records:
        try:
            normalize(entity, record, started_at)
        except ValueError as exc:
            blocked.append({"source_id": str(record["id"]), "code": str(exc)})
    metadata = {"mirror_capture_version": 1, "source_scope": scope,
        "source_api_base": API_BASE, "source_version_field": "syncToken",
        "capture_started_at": started_at, "capture_finished_at": finished_at,
        "written_at_utc": started_at, "pagination_checked": True,
        "ready_count": len(records)-len(blocked), "blocked_count": len(blocked),
        "blocked_records": blocked}
    result = writer.write_json_payload(source_system="sos_inventory", entity_name=entity,
        payload=records, metadata=metadata)
    result.file_path.chmod(0o600)
    # A journal failure leaves a valid orphan capture, never a delivered batch.
    db.execute("INSERT INTO captures VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (scope, entity, started_at, finished_at, str(result.file_path), result.sha256,
         len(records), metadata["ready_count"], len(blocked)))
    return {"entity": entity, "record_count": len(records), "ready_count": metadata["ready_count"],
        "blocked_count": len(blocked), "file_path": str(result.file_path), "sha256": result.sha256}


async def capture_master(client, *, entity, scope, output_root, page_size=200, max_records=10000):
    source_scope(scope)
    root = Path(output_root)/scope
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    journal = CaptureJournal(root)
    with journal.transaction() as db:
        started = datetime.now(timezone.utc).isoformat()
        records = await fetch_master_records(client, entity, page_size=page_size, max_records=max_records)
        finished = datetime.now(timezone.utc).isoformat()
        return publish_capture(RawPayloadWriter(root), db, entity=entity, scope=scope,
            records=records, started_at=started, finished_at=finished)
