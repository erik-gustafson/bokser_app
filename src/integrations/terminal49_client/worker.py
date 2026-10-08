from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from contextlib import suppress
from datetime import datetime, timezone

import httpx
from psycopg.types.json import Jsonb

from .client import Terminal49Client
from .config import Terminal49Settings
from .core import container_ids, event_records, normalize_snapshot, relationship, resources
from .store import Store

log = logging.getLogger('terminal49.worker')


class UnresolvedResource(ValueError):
    pass


class Worker:
    def __init__(self, config, store, client):
        self.config, self.store, self.client = config, store, client

    async def resolve(self, doc):
        ids = container_ids(doc)
        event = doc['data']['attributes']['event']
        if event == 'shipment.estimated.arrival' or not ids:
            shipment_ids, request_ids = set(), set()
            for resource in resources(doc).values():
                if resource['type'] == 'shipment':
                    shipment_ids.add(resource['id'])
                if resource['type'] == 'tracking_request':
                    request_ids.add(resource['id'])
                for name in ('shipment', 'reference_object'):
                    for link in relationship(resource, name):
                        if link.get('type') == 'shipment':
                            shipment_ids.add(link['id'])
                        if link.get('type') == 'tracking_request':
                            request_ids.add(link['id'])
            for rid in sorted(request_ids):
                request = await self.client.get_tracking_request(rid)
                ids.update(container_ids(request))
                for resource in resources(request).values():
                    shipment_ids.update(link['id'] for link in relationship(resource, 'shipment'))
            for sid in sorted(shipment_ids):
                ids.update(container_ids(await self.client.get_shipment(sid)))
        if not ids and event.startswith(('container.', 'shipment.')):
            # Never acknowledge as processed when routing cannot be determined.
            # Reconciliation independently repairs mapped current state.
            raise UnresolvedResource('Resource relationships did not resolve a container')
        return ids

    async def refresh(self, conn, cid, webhook=None):
        doc = await self.client.get_container(cid)
        c = resources(doc).get(('container', cid))
        if c is None:
            raise UnresolvedResource('Requested container missing')
        links = relationship(c, 'shipment')
        if links and ('shipment', links[0]['id']) not in resources(doc):
            shipment = await self.client.get_shipment(links[0]['id'])
            doc.setdefault('included', []).extend(r for r in resources(shipment).values() if r['type'] != 'container')
        history = await self.client.get_events(cid)
        events = {}
        for source in (webhook or {}, history):
            for e in event_records(source):
                # A webhook with several containers must not assign each event
                # to every container. Unscoped events only bind from /containers/id.
                if cid in e['container_ids'] or (source is history and not e['container_ids']):
                    events[(e['resource_type'], e['source_event_id'])] = e
        observed = datetime.now(timezone.utc).isoformat()
        message = normalize_snapshot(doc, cid, observed_at=observed)
        await self.store.publish(conn, cid, message, list(events.values()))

    async def once(self, conn):
        async with conn.transaction():
            row = await (await conn.execute('''SELECT * FROM terminal49.notifications
                WHERE account=%s AND status IN ('PENDING','RETRY') AND retry_at<=now()
                ORDER BY received_at LIMIT 1 FOR UPDATE SKIP LOCKED''', (self.store.account,))).fetchone()
            if row:
                try:
                    # Savepoint rolls back partial feed/snapshot writes on failure.
                    async with conn.transaction():
                        ids = await self.resolve(row['payload'])
                        for cid in sorted(ids):
                            await self.refresh(conn, cid, row['payload'])
                        await conn.execute('''UPDATE terminal49.notifications SET status='PROCESSED',
                            attempts=attempts+1,processed_at=now(),last_error=NULL
                            WHERE account=%s AND notification_id=%s''',
                            (self.store.account, row['notification_id']))
                except Exception as exc:
                    attempts = row['attempts'] + 1
                    reason = error_code(exc)
                    await conn.execute('''UPDATE terminal49.notifications SET status=%s,
                        attempts=%s,retry_at=now()+(%s * interval '1 second'),last_error=%s
                        WHERE account=%s AND notification_id=%s''',
                        ('FAILED' if attempts >= self.config.max_attempts else 'RETRY', attempts,
                         min(3600, 30 * 2 ** min(attempts, 7)), reason,
                         self.store.account, row['notification_id']))
                    log.warning('Notification deferred: %s', reason)
        # Run one reconciliation as well; a constant webhook stream cannot starve it.
        async with conn.transaction():
            mapping = await (await conn.execute('''SELECT * FROM terminal49.mappings
                WHERE account=%s AND active AND next_refresh_at<=now()
                ORDER BY next_refresh_at LIMIT 1 FOR UPDATE SKIP LOCKED''', (self.store.account,))).fetchone()
            if mapping:
                try:
                    async with conn.transaction():
                        await self.refresh(conn, str(mapping['container_id']))
                except Exception as exc:
                    await conn.execute('''UPDATE terminal49.mappings SET last_error=%s,
                        next_refresh_at=now()+interval '5 minutes'
                        WHERE account=%s AND company_id=%s AND container_id=%s''',
                        (error_code(exc), self.store.account, mapping['company_id'], mapping['container_id']))
                    log.warning('Reconciliation deferred: %s', error_code(exc))
        return bool(row or mapping)


def error_code(exc):
    if isinstance(exc, httpx.HTTPStatusError):
        return 'Terminal49 HTTP %s' % exc.response.status_code
    return type(exc).__name__  # Do not log URLs, credentials or payloads.


async def run(args):
    config = Terminal49Settings()
    store = Store(config)
    if args.bootstrap:
        await store.bootstrap()
        print('Terminal49 schema version 1 ready; shared lake manifest verified.')
        return
    config.require_enabled(worker=True)
    if args.retry_notification:
        from uuid import UUID
        nid = str(UUID(args.retry_notification))
        async with store.connect() as conn:
            await conn.execute('''UPDATE terminal49.notifications SET status='PENDING',
                attempts=0,retry_at=now(),last_error=NULL WHERE account=%s AND notification_id=%s''',
                (store.account, nid))
        print('Notification queued for retry.')
        return
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with suppress(NotImplementedError):
            asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    async with store.connect(autocommit=True) as conn:
        locked = await (await conn.execute('SELECT pg_try_advisory_lock(hashtextextended(%s, 0))',
            ('terminal49:worker:' + store.account,))).fetchone()
        if not next(iter(locked.values())):
            raise ValueError('Another Terminal49 worker owns this account')
        # Session lock lives for the connection lifetime. A single provider
        # worker serializes fetch and publish so late requests cannot regress state.
        async with httpx.AsyncClient() as http:
            client = Terminal49Client(http, config.api_key.get_secret_value(), store.archive_response,
                                      interval=config.request_interval_seconds)
            worker = Worker(config, store, client)
            while not stop.is_set():
                busy = await worker.once(conn)
                if args.once:
                    break
                try:
                    await asyncio.wait_for(stop.wait(), timeout=1 if busy else 10)
                except asyncio.TimeoutError:
                    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bootstrap', action='store_true')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--retry-notification')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(run(args))
    except Exception as exc:
        print('Terminal49 command failed (%s); inspect configuration and service status.' % type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
