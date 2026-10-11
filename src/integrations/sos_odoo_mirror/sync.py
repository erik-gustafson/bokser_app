"""Strict GET-only scans using the existing SOS client and private watermarks."""
from datetime import datetime, timedelta, timezone
from .capture import CaptureError, fetch_master_records
from .contract import normalize, timestamp
from .transactions import ENTITIES, normalize_transaction, validate_transaction
from .delivery import deliver


def read_transactions(response, entity, observed_at, approved_fields, *, size, total=None, count=None):
    try:
        response.raise_for_status(); body=response.json()
    except Exception:
        raise CaptureError('source_request_failed') from None
    if not isinstance(body,dict) or body.get('status')!='ok':raise CaptureError('source_status_not_ok')
    records=body.get('data'); actual=body.get('count'); available=body.get('totalCount')
    if not isinstance(records,list) or type(actual) is not int or type(available) is not int or actual!=len(records) or not 0<=actual<=size or actual>available:
        raise CaptureError('page_count_mismatch')
    if total is not None and total!=available:raise CaptureError('source_changed_during_capture')
    if count is not None and count!=actual:raise CaptureError('incomplete_page')
    return available,[normalize_transaction(entity,r,observed_at,approved_fields) for r in records]


async def fetch_transactions(client, entity, observed_at, *, since=None, approved_fields=(), page_size=200, max_records=100000):
    if entity not in ENTITIES or type(page_size) is not int or not 1<=page_size<=200 or type(max_records) is not int or max_records<=0:
        raise CaptureError('invalid_capture_options')
    timestamp(observed_at)
    params={'start':1,'maxresults':page_size,'archived':'yes'}
    if since is not None:
        params['updatedsince']=timestamp(since).astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    def read(response, **kwargs):
        return read_transactions(response,entity,observed_at,approved_fields,size=page_size,**kwargs)
    try:
        total,first=read(await client.get('/'+entity,params=params))
        if total>max_records:raise CaptureError('capture_limit_exceeded')
        if len(first)!=min(total,page_size):raise CaptureError('incomplete_first_page')
        records=list(first)
        for start in range(page_size+1,total+1,page_size):
            _,page=read(await client.get('/'+entity,params=dict(params,start=start)),total=total,count=min(page_size,total-start+1))
            records.extend(page)
        if len({r['source_id'] for r in records})!=total:raise CaptureError('duplicate_or_missing_source_ids')
        _,again=read(await client.get('/'+entity,params=params),total=total,count=len(first))
        key=lambda p:(p['source_id'],p['sync_token'],validate_transaction(p)[1])
        if [key(p) for p in first]!=[key(p) for p in again]:raise CaptureError('source_changed_during_capture')
        return records
    except (CaptureError,ValueError):raise
    except Exception:raise CaptureError('source_request_failed') from None


async def synchronize(journal, source_client, odoo_client, *, account_code, company_id,
                      approved_fields=(), reconcile=False, reconciliation_hours=24,
                      delivery_limit=1000, lake_root=None):
    owner=journal.acquire_run()
    if owner is None:return {'busy':True}
    try:
        # Previously captured deliveries can progress even if today's source
        # scan fails. Source OAuth availability never owns the delivery cursor.
        await deliver(journal,odoo_client,account_code=account_code,company_id=company_id,limit=delivery_limit)
        started=datetime.now(timezone.utc)
        observed=started.isoformat()
        payloads=[];cursors={};full=[]
        for entity in ('vendor','customer'):
            records=await fetch_master_records(source_client,entity,include_archived=True,approved_fields=approved_fields)
            payloads.extend(normalize(entity,r,observed) for r in records)
            cursors[entity]=observed;full.append(entity)
            if journal.acquire_run(owner=owner)!=owner:raise RuntimeError('mirror_run_lease_lost')
        for entity in ENTITIES:
            previous=journal.cursor(entity);last_full=journal.cursor('full:'+entity)
            is_full=reconcile or previous is None or last_full is None or started-timestamp(last_full)>=timedelta(hours=reconciliation_hours)
            since=None if is_full else (timestamp(previous)-timedelta(minutes=5)).isoformat()
            if lake_root is not None and not is_full:continue
            payloads.extend(await fetch_transactions(source_client,entity,observed,since=since,approved_fields=approved_fields))
            cursors[entity]=observed
            if is_full:cursors['full:'+entity]=observed;full.append(entity)
            if journal.acquire_run(owner=owner)!=owner:raise RuntimeError('mirror_run_lease_lost')
        # No watermark advances if any endpoint/page/contract/graph fails.
        journal.stage(payloads,cursors=cursors,full_entities=full)
        if lake_root is not None:
            from .lake import consume_existing_lake
            await consume_existing_lake(journal,lake_root,approved_fields=approved_fields)
        return await deliver(journal,odoo_client,account_code=account_code,company_id=company_id,limit=delivery_limit)
    finally:journal.release_run(owner)
