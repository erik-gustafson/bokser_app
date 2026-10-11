"""Synthetic transaction HTTPS checks; requires an explicitly disposable database.
Uses the same private environment as check_sos_mirror_runtime.py. The fixture
must map item 100, UOM 1, currency 42, location 1, payment method 88 and deposit
account 33, and bind customer 17/vendor 18. Never run against real accounts.
"""
import argparse
import asyncio
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import secrets
import ssl
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from src.integrations.sos_odoo_mirror.client import OdooMirrorClient
from src.integrations.sos_odoo_mirror.transactions import ENTITIES,normalize_transaction

MODELS={'purchaseorder':'purchase.order','estimate':'sale.order','salesorder':'sale.order',
    'invoice':'account.move','salesreceipt':'account.move','payment':'account.payment',
    'itemreceipt':'stock.picking','return':'stock.picking','rma':'stock.picking','shipment':'stock.picking'}


async def verify():
    database=os.environ['SOS_MIRROR_ODOO_DATABASE']
    if not database.startswith('bokser_sos_mirror_local'):raise ValueError('disposable_database_required')
    account=os.environ['SOS_MIRROR_ODOO_ACCOUNT'];company=int(os.environ['SOS_MIRROR_ODOO_COMPANY'])
    observed=datetime.now(timezone.utc).isoformat();identifier=secrets.randbelow(900000000)+100000000
    checks=[];native={}
    async with httpx.AsyncClient(verify=ssl.create_default_context(cafile=os.environ.get('SOS_MIRROR_TLS_CA')),trust_env=False) as http:
        client=OdooMirrorClient(base_url=os.environ['SOS_MIRROR_ODOO_URL'],database=database,api_key=os.environ['SOS_MIRROR_ODOO_API_KEY'],client=http)
        root=client.url.split('/json/2/')[0]
        def payload(entity,token=1,total=20,source_id=identifier):
            line={'id':101,'lineNumber':1,'item':{'id':100},'uom':{'id':1},'description':'Synthetic transaction',
                'quantity':2,'unitprice':total/2,'amount':total,'tax':{'taxable':False}}
            if entity=='payment':line={'id':101,'lineNumber':1,'amount':total}
            return normalize_transaction(entity,{'id':source_id,'syncToken':token,'summaryOnly':False,'archived':False,
                'date':'2026-10-10','number':'Synthetic HTTPS transaction','total':total,'customer':{'id':17},'vendor':{'id':18},
                'currency':{'id':42},'location':{'id':1},'paymentMethod':{'id':88},'depositAccount':{'id':33},'lines':[line]},observed)
        async def send(p):return await client.import_transaction(account_code=account,company_id=company,payload=p)
        async def rpc(model,method,body):
            response=await http.post(root+'/json/2/'+model+'/'+method,headers=client.headers,json=body)
            assert response.status_code==200,'native_rpc_failed'
            return response.json()
        for entity in ENTITIES:
            p=payload(entity);first=await send(p);second=await send(p)
            assert first['status']=='created' and second['status']=='duplicate' and first['res_id']==second['res_id'],'create_replay_failed'
            native[entity]=first['res_id']
            rows=await rpc(MODELS[entity],'read',{'ids':[first['res_id']],'fields':['state','company_id','bokser_sos_entity']})
            assert rows[0]['state']=='draft' and rows[0]['company_id'][0]==company and rows[0]['bokser_sos_entity']==entity,'native_draft_check_failed'
            checks.extend([entity+'_create_replay',entity+'_native_draft'])
            if MODELS[entity]=='stock.picking':
                moves=await rpc('stock.move','search_read',{'domain':[['picking_id','=',first['res_id']]],'fields':['quantity','state']})
                assert moves and all(m['quantity']==0 and m['state']=='draft' for m in moves),'stock_side_effect'
                checks.append(entity+'_no_stock_movement')
        p=payload('salesorder',token=2,total=30)
        assert (await send(p))['status']=='updated','update_failed'
        assert (await send(payload('salesorder')))['status']=='stale','stale_failed'
        checks.extend(['transaction_update','transaction_stale'])
        concurrent=await asyncio.gather(send(payload('salesorder',source_id=identifier+1)),send(payload('salesorder',source_id=identifier+1)))
        assert sorted(r['status'] for r in concurrent)==['created','duplicate'] and concurrent[0]['res_id']==concurrent[1]['res_id'],'concurrent_replay_failed'
        checks.append('transaction_concurrent_replay')
        await rpc('sale.order','write',{'ids':[native['salesorder']],'vals':{'client_order_ref':'Synthetic local edit'}})
        response=await http.post(client.url.rsplit('/',1)[0]+'/import_transaction',headers=client.headers,
            json={'account_code':account,'company_id':company,'payload':p})
        assert response.status_code>=400 and 'local_edit_conflict' in response.text,'local_edit_gate_failed'
        checks.append('transaction_local_edit_conflict')
    return {'passed':len(checks),'checks':checks,'database':database}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable',action='store_true',required=True)
    parser.parse_args()
    try:print(json.dumps(asyncio.run(verify())))
    except Exception:parser.exit(1,'synthetic_transaction_runtime_check_failed; inspect disposable runtime without exposing credentials\n')


if __name__=='__main__':main()
