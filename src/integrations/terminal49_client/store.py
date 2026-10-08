from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .archive import archive_delivery


class IdentityConflict(ValueError):
    pass


class Store:
    def __init__(self, config):
        self.config = config
        self.account = config.account_code

    @asynccontextmanager
    async def connect(self, *, autocommit=False):
        conn = await psycopg.AsyncConnection.connect(
            self.config.database_url.get_secret_value(), row_factory=dict_row,
            autocommit=autocommit, connect_timeout=10)
        async with conn:
            yield conn

    async def bootstrap(self):
        async with self.connect() as conn:
            await conn.execute(Path(__file__).with_name('schema.sql').read_text())
            row = await (await conn.execute('SELECT version FROM terminal49.schema_version')).fetchone()
            if row['version'] != 3:
                raise ValueError('Unsupported Terminal49 schema version')
            # Existing bokser_app migration must supply the shared lake manifest.
            await conn.execute('SELECT id FROM public.data_lake_files LIMIT 0')

    async def manifest(self, conn, meta, status):
        await conn.execute('''INSERT INTO public.data_lake_files
            (source_name, entity_name, file_path, file_name, record_count,
             file_size_bytes, sha256, landed_at, status, attempt_count,
             loaded_count, skipped_count, failed_count)
            VALUES('terminal49', %s, %s, %s, 1, %s, %s, %s, %s, 0, 0, 0, 0)''',
            (meta['entity_name'], meta['file_path'], meta['file_name'], meta['file_size_bytes'],
             meta['sha256'], meta['landed_at'], status))

    async def accept(self, raw, valid, doc, reason=None):
        nid = doc['data']['id'] if doc else None
        event = doc['data']['attributes']['event'] if doc else None
        meta = await asyncio.to_thread(archive_delivery, self.config.lake_root, raw,
                    signature_valid=valid, notification_id=nid, event=event)
        duplicate = False
        conflict = False
        async with self.connect() as conn:
            if valid and doc:
                row = await (await conn.execute('''INSERT INTO terminal49.notifications
                    (account, notification_id, event, payload, sha256)
                    VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING notification_id''',
                    (self.account, nid, event, Jsonb(doc), meta['sha256']))).fetchone()
                duplicate = row is None
                if duplicate:
                    old = await (await conn.execute('''SELECT sha256 FROM terminal49.notifications
                        WHERE account=%s AND notification_id=%s''', (self.account, nid))).fetchone()
                    conflict = old['sha256'] != meta['sha256']
                    if conflict:
                        reason = 'Conflicting body for existing notification ID'
            accepted = bool(valid and doc and not conflict)
            await self.manifest(conn, meta, 'ARCHIVED' if accepted else 'SKIPPED')
            await conn.execute('''INSERT INTO terminal49.deliveries
                (delivery_id, account, notification_id, signature_valid, accepted,
                 duplicate, reason, file_path, sha256)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (meta['delivery_id'], self.account, nid, valid, accepted, duplicate,
                 reason, meta['file_path'], meta['sha256']))
        if conflict:
            raise IdentityConflict(reason)
        return {'accepted': accepted, 'duplicate': duplicate, 'notification_id': nid}

    async def archive_response(self, raw, metadata):
        meta = await asyncio.to_thread(archive_delivery, self.config.lake_root, raw,
                    signature_valid=True, entity='api_responses')
        # Keep only approved path and status metadata, never request credentials.
        # Sidecar is immutable; request details are a separate archived JSON record.
        details = {'response_file': meta['file_path'], **metadata}
        from json import dumps
        detail_meta = await asyncio.to_thread(archive_delivery, self.config.lake_root,
                    dumps(details).encode(), signature_valid=True, entity='api_responses')
        async with self.connect() as conn:
            await self.manifest(conn, meta, 'ARCHIVED')
            await self.manifest(conn, detail_meta, 'ARCHIVED')

    async def mapping(self, cid, odoo_id, number, active, *, refresh=False):
        cid = str(UUID(cid))
        company = self.config.odoo_company_id
        async with self.connect() as conn:
            # Serialize changes to a company's mappings, including first insert.
            await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))',
                               ('terminal49:mapping:' + self.account + ':' + str(company),))
            rows = await (await conn.execute('''SELECT * FROM terminal49.mappings
                WHERE account=%s AND company_id=%s AND (container_id=%s OR odoo_container_id=%s)''',
                (self.account, company, cid, odoo_id))).fetchall()
            if any(str(r['container_id']) != cid or r['odoo_container_id'] != odoo_id for r in rows):
                raise IdentityConflict('Mapping already bound to another container journey')
            if rows:
                await conn.execute('''UPDATE terminal49.mappings SET
                    next_refresh_at=CASE WHEN active<>%s OR expected_number<>%s OR %s
                        THEN now() ELSE next_refresh_at END,
                    expected_number=%s, active=%s WHERE account=%s AND company_id=%s AND container_id=%s''',
                    (active, number, refresh, number, active, self.account, company, cid))
            else:
                await conn.execute('''INSERT INTO terminal49.mappings
                    (account,company_id,container_id,odoo_container_id,expected_number,active)
                    VALUES(%s,%s,%s,%s,%s,%s)''', (self.account, company, cid, odoo_id, number, active))

    async def feed(self, after, limit):
        async with self.connect() as conn:
            rows = await (await conn.execute('''SELECT version,payload FROM terminal49.feed
                WHERE account=%s AND company_id=%s AND version>%s ORDER BY version LIMIT %s''',
                (self.account, self.config.odoo_company_id, after, limit))).fetchall()
        return {'schema_version': 1, 'items': [dict(version=r['version'], **r['payload']) for r in rows],
                'next_cursor': rows[-1]['version'] if rows else after}

    async def publish(self, conn, cid, message, events):
        c = message['container']
        if not c.get('number'):
            raise ValueError('Provider container number is missing')
        for event in events:
            await conn.execute('''INSERT INTO terminal49.events
                (account,resource_type,event_id,container_id,payload)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT(account,resource_type,event_id,container_id)
                DO UPDATE SET payload=excluded.payload,observed_at=now()''',
                (self.account, event['resource_type'], event['source_event_id'], cid, Jsonb(event)))
        await conn.execute('''INSERT INTO terminal49.snapshots
            (account,container_id,shipment_id,number,observed_at,payload)
            VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(account,container_id) DO UPDATE SET
            shipment_id=excluded.shipment_id,number=excluded.number,
            observed_at=excluded.observed_at,payload=excluded.payload''',
            (self.account, cid, message['shipment'].get('terminal49_shipment_id'),
             c['number'], message['observed_at'], Jsonb(message)))
        mappings = await (await conn.execute('''SELECT * FROM terminal49.mappings
            WHERE account=%s AND container_id=%s AND active FOR UPDATE''', (self.account, cid))).fetchall()
        for mapping in mappings:
            await conn.execute('''UPDATE terminal49.mappings SET
                next_refresh_at=now()+(%s * interval '1 minute')
                WHERE account=%s AND company_id=%s AND container_id=%s''',
                (self.config.reconcile_minutes, self.account, mapping['company_id'], cid))
            if ''.join(c['number'].split()).upper() != mapping['expected_number']:
                await conn.execute('''UPDATE terminal49.mappings SET last_error=%s
                    WHERE account=%s AND company_id=%s AND container_id=%s''',
                    ('Container number does not match Odoo mapping', self.account, mapping['company_id'], cid))
                continue
            await conn.execute('''INSERT INTO terminal49.feed_counter(account) VALUES(%s)
                ON CONFLICT DO NOTHING''', (self.account,))
            version = await (await conn.execute('''UPDATE terminal49.feed_counter
                SET version=version+1 WHERE account=%s RETURNING version''', (self.account,))).fetchone()
            payload = dict(message, company_id=mapping['company_id'],
                           odoo_container_id=mapping['odoo_container_id'], events=events)
            await conn.execute('''INSERT INTO terminal49.feed
                (account,version,company_id,container_id,odoo_container_id,payload)
                VALUES(%s,%s,%s,%s,%s,%s)''', (self.account, version['version'], mapping['company_id'],
                    cid, mapping['odoo_container_id'], Jsonb(payload)))
            await conn.execute('''UPDATE terminal49.mappings SET last_error=NULL,
                next_refresh_at=now()+(%s * interval '1 minute')
                WHERE account=%s AND company_id=%s AND container_id=%s''',
                (self.config.reconcile_minutes, self.account, mapping['company_id'], cid))

    async def health(self):
        async with self.connect() as conn:
            version = await (await conn.execute('SELECT version FROM terminal49.schema_version')).fetchone()
            if version['version'] != 3:
                raise ValueError('Terminal49 schema upgrade is required')
            return {'ok': True}

    async def status(self):
        async with self.connect() as conn:
            notifications = await (await conn.execute('''SELECT status,count(*) AS count
                FROM terminal49.notifications WHERE account=%s GROUP BY status''', (self.account,))).fetchall()
            errors = await (await conn.execute('''SELECT container_id::text,odoo_container_id,last_error
                FROM terminal49.mappings WHERE account=%s AND company_id=%s AND last_error IS NOT NULL''',
                (self.account, self.config.odoo_company_id))).fetchall()
        return {'notifications': notifications, 'mapping_errors': errors}

    async def initiate(self, odoo_id, number, request_type, request_number, scac):
        from uuid import uuid4
        from .initiation import validate_input
        number, request_type, request_number, scac = validate_input(number, request_type, request_number, scac)
        company = self.config.odoo_company_id
        async with self.connect() as conn:
            await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))',
                ('terminal49:initiate:' + self.account + ':' + str(company),))
            existing = await (await conn.execute('''SELECT * FROM terminal49.initiations
                WHERE account=%s AND company_id=%s AND odoo_container_id=%s''', (self.account, company, odoo_id))).fetchone()
            if existing:
                if (existing['number'], existing['request_type'], existing['request_number'], existing['scac']) != (number, request_type, request_number, scac):
                    raise IdentityConflict('An existing tracking operation has different identifiers. Review it before changing the journey.')
                return self.initiation_result(existing)
            other = await (await conn.execute('''SELECT operation_id FROM terminal49.initiations
                WHERE account=%s AND company_id=%s AND number=%s AND status IN ('QUEUED','SUBMITTING','PENDING')''', (self.account, company, number))).fetchone()
            if other:
                raise IdentityConflict('Another Odoo record has a pending operation for this container.')
            row = await (await conn.execute('''INSERT INTO terminal49.initiations
                (operation_id,account,company_id,odoo_container_id,number,request_type,request_number,scac)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
                (str(uuid4()), self.account, company, odoo_id, number, request_type, request_number, scac))).fetchone()
            return self.initiation_result(row)

    @staticmethod
    def initiation_result(row):
        return {k: str(row[k]) if k in ('operation_id', 'tracking_request_id', 'container_id') and row[k] else row[k]
                for k in ('operation_id','company_id','odoo_container_id','number','request_type','request_number','scac','status','tracking_request_id','container_id','last_error')}

    async def initiation_status(self, odoo_id):
        async with self.connect() as conn:
            row = await (await conn.execute('''SELECT * FROM terminal49.initiations
                WHERE account=%s AND company_id=%s AND odoo_container_id=%s''',
                (self.account,self.config.odoo_company_id,odoo_id))).fetchone()
            return self.initiation_result(row) if row else None

    async def next_initiation(self):
        async with self.connect() as conn:
            return await (await conn.execute('''SELECT * FROM terminal49.initiations
                WHERE account=%s AND company_id=%s AND status IN ('QUEUED','SUBMITTING','PENDING')
                AND next_check_at<=now() ORDER BY next_check_at LIMIT 1''',
                (self.account,self.config.odoo_company_id))).fetchone()

    async def update_initiation(self, oid, status, *, tracking_request_id=None, container_id=None, error=None):
        async with self.connect() as conn:
            await conn.execute('''UPDATE terminal49.initiations SET status=%s,
                tracking_request_id=COALESCE(%s,tracking_request_id),container_id=COALESCE(%s,container_id),
                last_error=%s,updated_at=now(),attempts=0,next_check_at=now()+interval '30 seconds'
                WHERE operation_id=%s AND account=%s AND company_id=%s''',
                (status,tracking_request_id,container_id,error,oid,self.account,self.config.odoo_company_id))

    async def defer_initiation(self, oid, reason):
        async with self.connect() as conn:
            await conn.execute('''UPDATE terminal49.initiations SET attempts=attempts+1,
                status=CASE WHEN attempts>=7 THEN 'NEEDS_REVIEW' ELSE status END,
                last_error=%s,updated_at=now(),next_check_at=now()+interval '1 minute'
                WHERE operation_id=%s AND account=%s AND company_id=%s''',
                (reason,oid,self.account,self.config.odoo_company_id))

    async def shipment_submission(self, row):
        async with self.connect() as conn:
            return await (await conn.execute('''SELECT tracking_request_id, status FROM terminal49.shipment_initiations
                WHERE account=%s AND company_id=%s AND request_type=%s AND request_number=%s
                AND status IN ('SUBMITTING','PENDING','NEEDS_REVIEW','LINKED')''',
                (self.account,self.config.odoo_company_id,row['request_type'],row['request_number']))).fetchone()
