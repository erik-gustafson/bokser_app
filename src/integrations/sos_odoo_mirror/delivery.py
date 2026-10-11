"""Durable delivery state in the existing private capture journal; no business DB."""
from contextlib import closing
from datetime import datetime, timezone
import json
import secrets
import sqlite3
import time
from .capture import CaptureJournal
from .contract import order_batch, validate
from .transactions import dependencies, order_transactions, validate_transaction
from .client import MirrorError


def check(payload):
    return validate(payload) if payload['entity'] in ('customer','vendor') else validate_transaction(payload)


class DeliveryJournal(CaptureJournal):
    def __init__(self, root, target):
        from urllib.parse import urlsplit
        from .capture import source_scope
        if not isinstance(target, dict) or set(target) != {'url', 'database', 'account_code', 'company_id'}:
            raise ValueError('invalid_delivery_target')
        url = urlsplit(target['url'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment:
            raise ValueError('invalid_delivery_target')
        source_scope(target['account_code'])
        if type(target['company_id']) is not int or target['company_id'] <= 0 or not isinstance(target['database'], str) or not target['database'].strip() or any(ord(c)<32 for c in target['database']):
            raise ValueError('invalid_delivery_target')
        super().__init__(root)
        with self.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS delivery_target (singleton INTEGER PRIMARY KEY CHECK(singleton=1), target TEXT NOT NULL)')
            canonical=json.dumps(target,sort_keys=True,separators=(',',':'))
            previous=db.execute('SELECT target FROM delivery_target WHERE singleton=1').fetchone()
            if previous and previous[0]!=canonical:raise ValueError('delivery_target_changed_use_new_journal')
            if not previous:db.execute('INSERT INTO delivery_target VALUES(1,?)',(canonical,))
            db.execute("CREATE TABLE IF NOT EXISTS deliveries (id INTEGER PRIMARY KEY, entity TEXT NOT NULL, source_id TEXT NOT NULL, sync_token TEXT NOT NULL, payload_hash TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0, lease_until REAL NOT NULL DEFAULT 0, owner TEXT, error_code TEXT, native_id INTEGER, result TEXT, UNIQUE(entity,source_id,sync_token))")
            db.execute('CREATE TABLE IF NOT EXISTS mirror_scan_cursors(entity TEXT PRIMARY KEY, started_at TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS mirror_run_lease(singleton INTEGER PRIMARY KEY CHECK(singleton=1), owner TEXT NOT NULL, expires_at REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS mirror_missing_candidates(entity TEXT NOT NULL,source_id TEXT NOT NULL,observed_at TEXT NOT NULL,PRIMARY KEY(entity,source_id))')
            db.execute('CREATE TABLE IF NOT EXISTS mirror_lake_receipts(manifest_id INTEGER PRIMARY KEY,sha256 TEXT NOT NULL)')

    def stage(self, payloads, *, scan_entity=None, scan_started_at=None, cursors=None, full_entities=(), manifest=None):
        # Whole graph/contract validation precedes every durable mutation.
        masters=[p for p in payloads if p['entity'] in ('customer','vendor')]
        transactions=[p for p in payloads if p['entity'] not in ('customer','vendor')]
        ordered=[]
        for entity in ('vendor','customer'):
            batch=[p for p in masters if p['entity']==entity]
            if batch:ordered.extend(order_batch(batch))
        ordered.extend(order_transactions(transactions))
        with self.transaction() as db:
            if manifest is not None:
                identifier,checksum=manifest
                if type(identifier) is not int or identifier<=0 or not isinstance(checksum,str) or len(checksum)!=64:
                    raise ValueError('invalid_lake_manifest')
                previous=db.execute('SELECT sha256 FROM mirror_lake_receipts WHERE manifest_id=?',(identifier,)).fetchone()
                if previous and previous[0]!=checksum:raise ValueError('lake_manifest_changed')
            for p in ordered:
                _,business_hash=check(p)
                token=p.get('sync_token')
                if token is None:raise ValueError('versioned_delivery_required')
                row=db.execute('SELECT payload_hash FROM deliveries WHERE entity=? AND source_id=? AND sync_token=?',
                    (p['entity'],p['source_id'],token)).fetchone()
                if row and row[0]!=business_hash:raise ValueError('source_revision_conflict')
                if not row:
                    db.execute('INSERT INTO deliveries(entity,source_id,sync_token,payload_hash,payload) VALUES(?,?,?,?,?)',
                        (p['entity'],p['source_id'],token,business_hash,json.dumps(p,sort_keys=True,allow_nan=False)))
            updates = dict(cursors or {})
            if scan_entity is not None:updates[scan_entity] = scan_started_at
            for entity, started_at in updates.items():
                from .contract import timestamp
                timestamp(started_at)
                db.execute('INSERT INTO mirror_scan_cursors VALUES(?,?) ON CONFLICT(entity) DO UPDATE SET started_at=excluded.started_at',
                    (entity,started_at))
            for entity in full_entities:
                seen={p['source_id'] for p in ordered if p['entity']==entity}
                previous={row[0] for row in db.execute('SELECT DISTINCT source_id FROM deliveries WHERE entity=?',(entity,))}
                db.execute('DELETE FROM mirror_missing_candidates WHERE entity=?',(entity,))
                for identifier in previous-seen:
                    db.execute('INSERT INTO mirror_missing_candidates VALUES(?,?,?)',(entity,identifier,updates[entity]))
            if manifest is not None:
                db.execute('INSERT OR IGNORE INTO mirror_lake_receipts VALUES(?,?)',manifest)
        return len(ordered)

    def lake_cursor(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT COALESCE(MAX(manifest_id),0) FROM mirror_lake_receipts').fetchone()[0]

    def cursor(self, entity):
        with closing(sqlite3.connect(self.path)) as db:
            row=db.execute('SELECT started_at FROM mirror_scan_cursors WHERE entity=?',(entity,)).fetchone()
        return row[0] if row else None

    def acquire_run(self, *, now=None, owner=None):
        now=time.time() if now is None else now
        with self.transaction() as db:
            row=db.execute('SELECT owner,expires_at FROM mirror_run_lease WHERE singleton=1').fetchone()
            if row and row[1]>now and row[0]!=owner:return None
            owner=owner or secrets.token_hex(16)
            db.execute('INSERT INTO mirror_run_lease VALUES(1,?,?) ON CONFLICT(singleton) DO UPDATE SET owner=excluded.owner,expires_at=excluded.expires_at',(owner,now+7200))
            return owner

    def release_run(self, owner):
        with self.transaction() as db:
            db.execute('DELETE FROM mirror_run_lease WHERE singleton=1 AND owner=?',(owner,))

    def claim(self, *, now=None):
        now=time.time() if now is None else now
        with self.transaction() as db:
            # Preserve insertion dependency order. A blocked/leased earlier
            # revision never permits overtaking it with another source revision.
            rows=db.execute("SELECT id,payload FROM deliveries WHERE (state='pending' OR (state='leased' AND lease_until<=?)) AND next_attempt<=? ORDER BY id",(now,now)).fetchall()
            for row_id,encoded in rows:
                p=json.loads(encoded)
                prior=db.execute("SELECT 1 FROM deliveries WHERE entity=? AND source_id=? AND id<? AND state!='done' LIMIT 1",(p['entity'],p['source_id'],row_id)).fetchone()
                if prior:continue
                if p['entity'] in ('customer', 'vendor'):
                    required = []
                    if p.get('parent_source_id'):
                        required.append((p['entity'], p['parent_source_id']))
                else:
                    required = [(p['partner_entity'], p['partner_source_id'])]
                    required.extend((d['entity'], d['source_id']) for d in dependencies(p))
                # Dependencies outside this journal are checked by Odoo. For
                # known queued parents, wait for their durable acknowledgement.
                waiting = any(db.execute("SELECT 1 FROM deliveries WHERE entity=? AND source_id=? AND state!='done' LIMIT 1", key).fetchone() for key in required)
                if waiting:continue
                owner=secrets.token_hex(16)
                db.execute("UPDATE deliveries SET state='leased',owner=?,lease_until=?,attempts=attempts+1 WHERE id=?",(owner,now+120,row_id))
                return row_id,owner,p
        return None

    def finish(self, row_id, owner, result):
        with self.transaction() as db:
            changed=db.execute("UPDATE deliveries SET state='done',lease_until=0,owner=NULL,error_code=NULL,native_id=?,result=? WHERE id=? AND owner=? AND state='leased'",
                (result.get('res_id',result.get('partner_id')),result['status'],row_id,owner)).rowcount
            if changed!=1:raise ValueError('delivery_lease_lost')

    def fail(self, row_id, owner, *, retryable, code, now=None):
        import re
        if not isinstance(code, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,95}', code):
            code = 'mirror_delivery_failed'
        now=time.time() if now is None else now
        with self.transaction() as db:
            row=db.execute("SELECT attempts FROM deliveries WHERE id=? AND owner=? AND state='leased'",(row_id,owner)).fetchone()
            if not row:raise ValueError('delivery_lease_lost')
            retry=retryable and row[0]<10
            delay=min(3600,30*2**min(row[0]-1,7))
            db.execute('UPDATE deliveries SET state=?,lease_until=0,owner=NULL,next_attempt=?,error_code=? WHERE id=?',
                ('pending' if retry else 'blocked',now+delay,code,row_id))

    def retry_blocked(self):
        with self.transaction() as db:
            return db.execute("UPDATE deliveries SET state='pending',attempts=0,next_attempt=0,error_code=NULL WHERE state='blocked'").rowcount

    def replay_reviewed_all(self):
        # Owner-only recovery after an Odoo restore. Keep immutable snapshots,
        # target pin and hashes; native gates still detect edits/conflicts.
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM deliveries WHERE state='leased' AND lease_until>? LIMIT 1",(time.time(),)).fetchone() or db.execute('SELECT 1 FROM mirror_run_lease WHERE expires_at>? LIMIT 1',(time.time(),)).fetchone():
                raise ValueError('mirror_recovery_requires_stopped_delivery')
            return db.execute("UPDATE deliveries SET state='pending',attempts=0,next_attempt=0,lease_until=0,owner=NULL,error_code=NULL,native_id=NULL,result=NULL").rowcount

    def summary(self):
        with closing(sqlite3.connect(self.path)) as db:
            states=dict(db.execute('SELECT state,COUNT(*) FROM deliveries GROUP BY state').fetchall())
            errors=dict(db.execute('SELECT error_code,COUNT(*) FROM deliveries WHERE error_code IS NOT NULL GROUP BY error_code').fetchall())
            missing=dict(db.execute('SELECT entity,COUNT(*) FROM mirror_missing_candidates GROUP BY entity').fetchall())
        return {'states':states,'errors':errors,'missing_candidates':missing}


async def deliver(journal, client, *, account_code, company_id, limit=1000):
    delivered=0
    while delivered<limit:
        claim=journal.claim()
        if claim is None:break
        row_id,owner,payload=claim
        try:
            method=client.import_partner if payload['entity'] in ('customer','vendor') else client.import_transaction
            result=await method(account_code=account_code,company_id=company_id,payload=payload)
        except MirrorError as exc:
            journal.fail(row_id,owner,retryable=exc.retryable,code=str(exc))
        except Exception:
            # Preserve the lease for crash recovery; never acknowledge an
            # unknown outcome or print exception/request/credential contents.
            raise RuntimeError('mirror_delivery_interrupted_replay_safe') from None
        else:journal.finish(row_id,owner,result)
        delivered+=1
    return journal.summary()
