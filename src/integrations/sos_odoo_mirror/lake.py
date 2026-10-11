"""Read existing SOS lake files without taking loader claims or moving its cursor."""
import hashlib
import json
from pathlib import Path
from .transactions import normalize_transaction
from .contract import timestamp

ENTITIES={'updated_sales_orders':'salesorder','sales_receipts':'salesreceipt','estimates':'estimate',
    'updated_invoices':'invoice','updated_shipments':'shipment','updated_item_receipts':'itemreceipt',
    'payments':'payment','purchase_orders':'purchaseorder','returns':'return','rmas':'rma'}


def stage_file(journal, lake_root, manifest, *, approved_fields=()):
    if manifest.get('source_name')!='sos_inventory' or manifest.get('entity_name') not in ENTITIES:
        raise ValueError('unsupported_lake_source')
    root=Path(lake_root).resolve();path=Path(manifest['file_path'])
    path=(path if path.is_absolute() else root/path).resolve()
    if not path.is_relative_to(root):raise ValueError('lake_path_outside_root')
    try:content=path.read_bytes()
    except OSError:raise ValueError('lake_file_unavailable') from None
    checksum=hashlib.sha256(content).hexdigest()
    if checksum!=manifest['sha256']:raise ValueError('lake_checksum_mismatch')
    try:body=json.loads(content)
    except ValueError:raise ValueError('invalid_lake_json') from None
    if not isinstance(body,dict) or set(body)!= {'metadata','payload'} or not isinstance(body['metadata'],dict) or not isinstance(body['payload'],list):
        raise ValueError('invalid_lake_envelope')
    metadata=body['metadata'];records=body['payload']
    if metadata.get('source_system')!='sos_inventory' or metadata.get('entity_name')!=manifest['entity_name'] or type(metadata.get('record_count')) is not int or metadata['record_count']!=len(records) or manifest['record_count']!=len(records):
        raise ValueError('lake_manifest_mismatch')
    observed=metadata.get('written_at_utc');timestamp(observed)
    payloads=[normalize_transaction(ENTITIES[manifest['entity_name']],r,observed,approved_fields) for r in records]
    # This receipt proves only file integrity/staging, not upstream API scan
    # completeness. Only a separate strict source reconciliation advances that.
    return journal.stage(payloads,manifest=(manifest['id'],checksum))


async def consume_existing_lake(journal, lake_root, *, approved_fields=(), limit=100):
    from sqlalchemy import text
    from src.database.database import async_session
    async with async_session() as db:
        await db.execute(text('SET TRANSACTION READ ONLY'))
        rows=(await db.execute(text("SELECT id,source_name,entity_name,file_path,record_count,sha256 FROM data_lake_files WHERE source_name='sos_inventory' AND id>:cursor AND entity_name IN ('updated_sales_orders','sales_receipts','estimates','updated_invoices','updated_shipments','updated_item_receipts','payments','purchase_orders','returns','rmas') ORDER BY id LIMIT :limit"),{'cursor':journal.lake_cursor(),'limit':limit})).mappings().all()
    for row in rows:stage_file(journal,lake_root,dict(row),approved_fields=approved_fields)
    return len(rows)
