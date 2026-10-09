"""Explicit-file backfill of stored Ship Advices; dry-run by default."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from .preview import summarize


def read_records(path):
    if path.suffix == '.jsonl':
        with path.open() as stream:
            records = [json.loads(line) for line in stream if line.strip()]
    else:
        body = json.loads(path.read_text())
        records = body.get('payload', body) if isinstance(body, dict) else body
        if isinstance(records, dict) and isinstance(records.get('data'), list):
            records = records['data']
        if isinstance(records, dict):
            records = [records]
    if not isinstance(records, list) or not records:
        raise ValueError('A nonempty Ship Advice file is required')
    for record in records:
        if not isinstance(record, dict) or not {'id','order_id','updated_at'} <= record.keys() or not (
            'ship_advice_item' in record or 'items' in record
        ):
            raise ValueError('File contains an unsupported Ship Advice record')
    return records


async def apply_files(paths):
    # Import production settings/DB only when explicitly applying.
    from src.database.database import async_session
    from src.worker.jobs.process_data.acenda.process_acenda_data import load_acenda_records
    total = dict(loaded=0, skipped=0, failed=0)
    for path in paths:
        records = read_records(path)
        async with async_session() as session:
            async with session.begin():
                result = await load_acenda_records(session, records, 'acenda_ship_advices')
                if result['failed']:
                    raise RuntimeError('Backfill file contains failed records; file transaction rolled back')
        total['loaded'] += result['loaded']
        total['skipped'] += result['skipped']
    print('Backfill result:', json.dumps(total, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', type=Path, action='append', required=True)
    parser.add_argument('--currency')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    currency = args.currency or os.environ.get('ACENDA_ORDER_CURRENCY', 'USD')
    for path in args.file:
        records = read_records(path)
        print('Records:', len(records))
        print('Preview:', json.dumps(summarize(records, currency=currency), sort_keys=True))
    if args.apply:
        asyncio.run(apply_files(args.file))
    else:
        print('Dry-run only. No database, Odoo, Acenda or warehouse writes.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Backfill failed:', type(error).__name__, '(no payload printed)')
        raise SystemExit(1)
