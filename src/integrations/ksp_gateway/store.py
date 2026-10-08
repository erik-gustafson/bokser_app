"""Durable connector journal; no databases or shared vendor paths are modified."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time

from .mapping import canonical, digest, ReconciliationRequired


class GatewayStore:
    def __init__(self, path, *, clock=time.time, requests_per_minute=60):
        if not 1 <= requests_per_minute <= 60:
            raise ValueError("This candidate permits at most the guide's default 60 requests/minute")
        self.path = str(Path(path).resolve())
        self.clock, self.interval = clock, 60 / requests_per_minute + 0.05
        Path(self.path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        Path(self.path).chmod(0o600)
        with self._tx() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS binding (
                    code TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
                    body TEXT NOT NULL, mapping TEXT NOT NULL, claim_token TEXT NOT NULL,
                    state TEXT NOT NULL, order_id TEXT, logiwa_id TEXT, note TEXT
                );
                CREATE TABLE IF NOT EXISTS package_event (
                    event_id TEXT PRIMARY KEY, code TEXT NOT NULL,
                    report TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    applied INTEGER NOT NULL DEFAULT 0, result TEXT
                );
                CREATE TABLE IF NOT EXISTS rate_slot (
                    id INTEGER PRIMARY KEY CHECK(id=1), next_at REAL NOT NULL
                );
            ''')
        Path(self.path).chmod(0o600)

    @contextmanager
    def _tx(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def reserve_request_slot(self):
        with self._tx() as db:
            row = db.execute("SELECT next_at FROM rate_slot WHERE id=1").fetchone()
            now = self.clock()
            reserved = max(now, row[0] if row else now)
            db.execute("INSERT INTO rate_slot VALUES(1,?) ON CONFLICT(id) DO UPDATE SET next_at=excluded.next_at", (reserved + self.interval,))
        return max(reserved - now, 0)

    def stage(self, body, mapping, claim_token):
        code = mapping["code"]
        fingerprint = digest({"body": body, "mapping": mapping, "claim_token": claim_token})
        with self._tx() as db:
            old = db.execute("SELECT request_hash FROM binding WHERE code=?", (code,)).fetchone()
            if old and old[0] != fingerprint:
                raise ReconciliationRequired("Same KSP order code has different frozen content")
            db.execute("INSERT OR IGNORE INTO binding(code,request_hash,body,mapping,claim_token,state) VALUES(?,?,?,?,?,'ready')",
                       (code, fingerprint, canonical(body), canonical(mapping), claim_token))
        return self.get(code)

    def get(self, code):
        with self._tx() as db:
            row = db.execute("SELECT * FROM binding WHERE code=?", (code,)).fetchone()
        if not row:
            raise KeyError(code)
        result = dict(row)
        result["body"], result["mapping"] = json.loads(result["body"]), json.loads(result["mapping"])
        return result

    def start_post(self, code):
        with self._tx() as db:
            return db.execute("UPDATE binding SET state='posting' WHERE code=? AND state='ready'", (code,)).rowcount == 1

    def state(self, code, state, *, order_id=None, logiwa_id=None, note=None):
        with self._tx() as db:
            db.execute("UPDATE binding SET state=?,order_id=COALESCE(?,order_id),logiwa_id=COALESCE(?,logiwa_id),note=? WHERE code=?",
                       (state, order_id, logiwa_id, note, code))

    def stage_packages(self, code, reports):
        """Validate the entire snapshot before staging any newly discovered event."""
        with self._tx() as db:
            existing = {row["event_id"]: row for row in db.execute(
                "SELECT * FROM package_event WHERE code=?", (code,))}
            if set(existing) - {report["event_id"] for report in reports}:
                raise ReconciliationRequired("Previously observed packages disappeared or changed tracking identity")
            for report in reports:
                old = db.execute("SELECT * FROM package_event WHERE event_id=?", (report["event_id"],)).fetchone()
                if old and old["code"] != code:
                    raise ReconciliationRequired("Package identity belongs to another allocation")
                if old and old["fingerprint"] != digest(report):
                    raise ReconciliationRequired("A previously observed package changed shipped content")
            for report in reports:
                db.execute("INSERT OR IGNORE INTO package_event(event_id,code,report,fingerprint) VALUES(?,?,?,?)",
                           (report["event_id"], code, canonical(report), digest(report)))

    def pending_packages(self, code):
        with self._tx() as db:
            rows = db.execute("SELECT report FROM package_event WHERE code=? AND applied=0 ORDER BY event_id", (code,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def applied(self, event_id, result):
        with self._tx() as db:
            db.execute("UPDATE package_event SET applied=1,result=? WHERE event_id=?", (canonical(result), event_id))

    def poll_codes(self):
        with self._tx() as db:
            return [row[0] for row in db.execute(
                "SELECT code FROM binding WHERE state IN ('accepted','acknowledged','pending','posting','uncertain') ORDER BY code")]
