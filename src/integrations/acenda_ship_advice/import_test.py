"""Explicit-file draft import; no polling, acknowledgment or warehouse writes."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from .contract import ContractError, review_reason
from .normalize import build_payload
from .backfill import read_records

def read_parent(path):
    body=json.loads(path.read_text())
    records=body.get('payload',body) if isinstance(body,dict) else body
    if isinstance(records,dict) and isinstance(records.get('data'),list): records=records['data']
    if isinstance(records,dict): records=[records]
    if not isinstance(records,list) or len(records)!=1: raise ContractError('one_parent_record_required')
    return records[0]

async def send(payload):
    import httpx
    from .odoo_client import AcendaOdooClient
    if os.environ.get('ACENDA_ODOO_TEST_ENABLED')!='true':
        raise ContractError('explicit_test_setting_required')
    async with httpx.AsyncClient() as http:
        client=AcendaOdooClient(base_url=os.environ['ACENDA_ODOO_BASE_URL'],
          database=os.environ['ACENDA_ODOO_DATABASE'],api_key=os.environ['ACENDA_ODOO_API_KEY'],http_client=http)
        result=await client.import_order(os.environ['ACENDA_ODOO_ACCOUNT_CODE'],payload)
    print('Odoo result:',json.dumps({k:result.get(k) for k in ('state','binding_id','sale_order_id')},sort_keys=True))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--parent-file',required=True,type=Path)
    parser.add_argument('--advice-file',required=True,type=Path,action='append')
    parser.add_argument('--organization-slug',required=True)
    parser.add_argument('--currency',default=os.environ.get('ACENDA_ORDER_CURRENCY','USD'))
    parser.add_argument('--send-test',action='store_true')
    args=parser.parse_args()
    advices=[r for p in args.advice_file for r in read_records(p)]
    payload=build_payload(read_parent(args.parent_file),advices,organization_slug=args.organization_slug,currency=args.currency)
    reason=review_reason(payload)
    print('Parent contract: validated')
    print('Parent lines:',len(payload['lines']),'Ship Advices:',len(payload['advices']))
    print('Review:',reason or 'ready_for_mapping')
    if args.send_test: asyncio.run(send(payload))
    else: print('Preview only. No database or external writes.')

if __name__=='__main__':
    try: main()
    except Exception as error:
        print('Acenda test import failed:',error.code if isinstance(error,ContractError) else type(error).__name__)
        raise SystemExit(1)
