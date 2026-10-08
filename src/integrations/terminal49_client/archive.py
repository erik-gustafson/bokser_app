from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _durable_new_file(path: Path, content: bytes) -> None:
    with path.open('xb') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def archive_delivery(lake_root: Path, raw: bytes, *, signature_valid: bool,
                     notification_id: str | None = None,
                     event: str | None = None, entity: str = 'webhook_deliveries') -> dict:
    """Archive exact bytes; caller commits manifest + inbox before returning 202.

    Linux/NAS filesystem. Unique filenames preserve every duplicate delivery.
    Does not store signatures, API credentials or arbitrary request headers.
    """
    if entity not in ('webhook_deliveries', 'api_responses'):
        raise ValueError('Unsupported archive entity')
    now = datetime.now(timezone.utc)
    folder = Path(lake_root) / 'raw' / 'terminal49' / entity / f'year={now:%Y}' / f'month={now:%m}' / f'day={now:%d}'
    folder.mkdir(parents=True, exist_ok=True)
    delivery_id = uuid4().hex
    path = folder / f'{entity}_{now:%Y%m%dT%H%M%S}_{delivery_id}.json'
    metadata = {'source_name': 'terminal49', 'entity_name': entity,
                'delivery_id': delivery_id, 'notification_id': notification_id,
                'event': event, 'signature_valid': signature_valid,
                'file_path': str(path), 'file_name': path.name,
                'file_size_bytes': len(raw), 'record_count': 1,
                'sha256': hashlib.sha256(raw).hexdigest(), 'landed_at': now.isoformat()}
    _durable_new_file(path, raw)
    _durable_new_file(path.with_suffix('.json.metadata.json'), json.dumps(metadata).encode())
    # Persist newly created partition directory entries up to the existing lake root.
    for directory_path in [folder.parent, folder.parent.parent, folder.parent.parent.parent,
                           folder.parent.parent.parent.parent, Path(lake_root) / 'raw', Path(lake_root)]:
        descriptor = os.open(directory_path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return metadata
