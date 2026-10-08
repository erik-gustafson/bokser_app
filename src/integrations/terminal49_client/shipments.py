"""Shipment-level durable tracking and bounded container discovery."""
import re
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from .core import relationship, resources
from .initiation import clean, choose_request, ReviewRequired, validate_input
from .store import IdentityConflict


def validate_reference(kind, number, scac):
    number, scac = clean(number), clean(scac)
    if kind not in ('bill_of_lading', 'booking') or not re.fullmatch(r'[A-Z0-9]{1,64}', number):
        raise ValueError('Enter a carrier master bill of lading or booking reference.')
    if scac and not re.fullmatch(r'[A-Z]{2,4}', scac):
        raise ValueError('Enter a two to four letter carrier SCAC.')
    return kind, number, scac


def discovery(doc, row):
    shipment = doc['data']
    sid = str(UUID(shipment['id']))
    a = shipment.get('attributes', {})
    if shipment.get('type') != 'shipment' or 'line_tracking_stopped_at' not in a or a['line_tracking_stopped_at']:
        raise ReviewRequired('Shipment is stopped or its active tracking status is unknown.')
    if row['scac'] and clean(a.get('shipping_line_scac')) != row['scac']:
        raise ReviewRequired('Shipment carrier does not match the tracking request.')
    if row['request_type'] == 'bill_of_lading' and clean(a.get('bill_of_lading_number')) != row['request_number']:
        raise ReviewRequired('Shipment master bill of lading does not match the request.')
    linked = relationship(shipment, 'containers')
    if len(linked) > 1000 or doc.get('links', {}).get('next'):
        raise ReviewRequired('Shipment container discovery is truncated or exceeds the import limit.')
    lookup = resources(doc)
    result, numbers, ids = [], set(), set()
    for link in linked:
        cid = str(UUID(link['id']))
        c = lookup.get(('container', cid))
        if link.get('type') != 'container' or not c:
            raise ReviewRequired('Shipment response is missing related container details.')
        number = clean(c.get('attributes', {}).get('number'))
        validate_input(number, 'container', '', '')
        if cid in ids or number in numbers:
            raise ReviewRequired('Shipment lists a duplicate physical container; review before import.')
        if not any(r.get('type') == 'shipment' and str(UUID(r['id'])) == sid for r in relationship(c, 'shipment')):
            raise ReviewRequired('Discovered container belongs to another shipment.')
        ids.add(cid); numbers.add(number)
        result.append({'container_id': cid, 'number': number})
    return {'shipment_id': sid, 'master_bol': a.get('bill_of_lading_number') or '',
            'carrier_scac': clean(a.get('shipping_line_scac')), 'carrier_name': a.get('shipping_line_name') or '',
            'origin_port': a.get('port_of_lading_name') or '', 'destination_port': a.get('port_of_discharge_name') or '',
            'containers': result}


class ShipmentStore:
    def __init__(self, store):
        self.store = store
        self.scope = (store.account, store.config.odoo_company_id)

    async def start(self, odoo_id, kind, number, scac):
        kind, number, scac = validate_reference(kind, number, scac)
        async with self.store.connect() as conn:
            await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                ('terminal49:initiate:' + self.scope[0] + ':' + str(self.scope[1]),))
            rows = await (await conn.execute('''SELECT * FROM terminal49.shipment_initiations
                WHERE account=%s AND company_id=%s AND
                (odoo_shipment_id=%s OR (request_type=%s AND request_number=%s))''',
                (*self.scope, odoo_id, kind, number))).fetchall()
            if rows:
                if len(rows) != 1 or (rows[0]['odoo_shipment_id'], rows[0]['request_type'], rows[0]['request_number'], rows[0]['scac']) != (odoo_id,kind,number,scac):
                    raise IdentityConflict('Shipment reference or tracking operation already belongs to another Odoo shipment. Review before submitting.')
                return self.result(rows[0])
            row = await (await conn.execute('''INSERT INTO terminal49.shipment_initiations
                (operation_id,account,company_id,odoo_shipment_id,request_type,request_number,scac)
                VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
                (str(uuid4()),*self.scope,odoo_id,kind,number,scac))).fetchone()
            return self.result(row)

    @staticmethod
    def result(row):
        keys = ('operation_id','company_id','odoo_shipment_id','request_type','request_number','scac',
                'status','tracking_request_id','shipment_id','last_error','discovered','observed_at')
        return {k: str(row[k]) if k in ('operation_id','tracking_request_id','shipment_id','observed_at') and row[k] else row[k] for k in keys}

    async def status(self, odoo_id):
        async with self.store.connect() as conn:
            row = await (await conn.execute('''SELECT * FROM terminal49.shipment_initiations
                WHERE account=%s AND company_id=%s AND odoo_shipment_id=%s''', (*self.scope,odoo_id))).fetchone()
            return self.result(row) if row else None

    async def next(self):
        async with self.store.connect() as conn:
            return await (await conn.execute('''SELECT * FROM terminal49.shipment_initiations
                WHERE account=%s AND company_id=%s AND status IN ('QUEUED','SUBMITTING','PENDING','LINKED')
                AND next_check_at<=now() ORDER BY next_check_at,created_at LIMIT 1''',self.scope)).fetchone()

    async def update(self, oid, status, *, rid=None, discovered=None, error=None):
        sid = discovered['shipment_id'] if discovered else None
        async with self.store.connect() as conn:
            if sid:
                other = await (await conn.execute('''SELECT operation_id FROM terminal49.shipment_initiations
                    WHERE account=%s AND company_id=%s AND shipment_id=%s AND operation_id<>%s''',
                    (*self.scope,sid,oid))).fetchone()
                if other:
                    raise ReviewRequired('Terminal49 shipment is already linked to another Odoo shipment.')
            await conn.execute('''UPDATE terminal49.shipment_initiations SET status=%s,
                tracking_request_id=COALESCE(%s,tracking_request_id),shipment_id=COALESCE(%s,shipment_id),
                discovered=COALESCE(%s,discovered),observed_at=CASE WHEN %s THEN now() ELSE observed_at END,
                last_error=%s,attempts=0,updated_at=now(),next_check_at=now()+(%s * interval '1 second')
                WHERE account=%s AND company_id=%s AND operation_id=%s''',
                (status,rid,sid,Jsonb(discovered) if discovered is not None else None,
                 discovered is not None,error,300 if status=='LINKED' else 30,*self.scope,oid))

    async def defer(self, oid, reason):
        async with self.store.connect() as conn:
            await conn.execute('''UPDATE terminal49.shipment_initiations SET attempts=attempts+1,
                status=CASE WHEN attempts>=7 THEN 'NEEDS_REVIEW' ELSE status END,last_error=%s,
                updated_at=now(),next_check_at=now()+interval '1 minute'
                WHERE account=%s AND company_id=%s AND operation_id=%s''', (reason,*self.scope,oid))

    async def legacy_request(self, row):
        async with self.store.connect() as conn:
            rows = await (await conn.execute('''SELECT * FROM terminal49.initiations
                WHERE account=%s AND company_id=%s AND request_type=%s AND request_number=%s
                AND status IN ('SUBMITTING','PENDING','LINKED','NEEDS_REVIEW')''',
                (*self.scope,row['request_type'],row['request_number']))).fetchall()
            ids = {str(r['tracking_request_id']) for r in rows if r['tracking_request_id']}
            if len(ids)>1:
                raise ReviewRequired('Several existing container operations use this reference.')
            if ids:
                return next(iter(ids))
            if rows:
                raise ReviewRequired('An earlier container submission has an uncertain outcome. No new request was sent.')
            return None


class ShipmentInitiator:
    def __init__(self, repository, client):
        self.repo, self.client = repository, client

    async def once(self):
        row = await self.repo.next()
        if not row:
            return False
        oid = str(row['operation_id'])
        try:
            if row['shipment_id']:
                await self.link(row, str(row['shipment_id']))
                return True
            rid = row['tracking_request_id'] or await self.repo.legacy_request(row)
            if rid:
                request = (await self.client.get_tracking_request(str(rid)))['data']
                await self.repo.update(oid, 'PENDING', rid=str(rid))
                await self.resolve(row, request)
                return True
            found = choose_request(await self.client.list_requests(row['request_number']), row)
            if found:
                await self.repo.update(oid,'PENDING',rid=str(UUID(found['id'])))
                await self.resolve(row,found)
                return True
            if row['request_type']=='bill_of_lading':
                doc = await self.client.list_shipments(row['request_number'])
                matches=[]
                for s in doc['data']:
                    a=s.get('attributes',{})
                    if s.get('type')=='shipment' and clean(a.get('bill_of_lading_number'))==row['request_number'] and (not row['scac'] or clean(a.get('shipping_line_scac'))==row['scac']):
                        if 'line_tracking_stopped_at' not in a or a['line_tracking_stopped_at']:
                            raise ReviewRequired('Existing shipment is stopped or active tracking is unknown.')
                        matches.append(s)
                if len(matches)>1:
                    raise ReviewRequired('Several shipments match this master BOL. Review the carrier and journey.')
                if matches:
                    await self.link(row,str(UUID(matches[0]['id'])))
                    return True
            if row['status']=='SUBMITTING':
                raise ReviewRequired('Submission outcome is uncertain. No duplicate tracking request was sent.')
            await self.repo.update(oid,'SUBMITTING')
            attrs={'request_type':row['request_type'],'request_number':row['request_number'],
                   'ref_numbers':['bokser-t49:'+oid]}
            attrs.update({'scac':row['scac']} if row['scac'] else {'auto_detect_vocc_scac':True})
            request=(await self.client.create_tracking_request(attrs))['data']
            await self.repo.update(oid,'PENDING',rid=str(UUID(request['id'])))
            await self.resolve(row,request)
        except ReviewRequired as exc:
            await self.repo.update(oid,'NEEDS_REVIEW',error=str(exc))
        except Exception as exc:
            from .worker import error_code
            await self.repo.defer(oid,error_code(exc))
        return True

    async def resolve(self,row,request):
        a=request.get('attributes',{})
        if request.get('type')!='tracking_request' or a.get('request_type')!=row['request_type'] or clean(a.get('request_number'))!=row['request_number']:
            raise ReviewRequired('Tracking request does not match the Odoo shipment reference.')
        if row['scac'] and a.get('scac') and clean(a['scac'])!=row['scac']:
            raise ReviewRequired('Tracking request carrier does not match Odoo.')
        if a.get('status') in ('failed','tracking_stopped'):
            await self.repo.update(str(row['operation_id']),'FAILED',error='Tracking request failed or stopped; review the reference and carrier.')
            return
        links=relationship(request,'tracked_object')
        if not links:
            await self.repo.update(str(row['operation_id']),'PENDING')
            return
        if len(links)!=1 or links[0].get('type')!='shipment':
            raise ReviewRequired('Tracking request did not resolve one shipment.')
        await self.link(row,str(UUID(links[0]['id'])))

    async def link(self,row,sid):
        data=discovery(await self.client.get_shipment(sid),row)
        if data['shipment_id']!=sid:
            raise ReviewRequired('Provider returned another shipment identity.')
        await self.repo.update(str(row['operation_id']),'LINKED',discovered=data)
