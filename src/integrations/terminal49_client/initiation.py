"""Durable start/link workflow. Only the worker makes provider mutations."""
import re
from uuid import UUID

from .core import relationship, resources


class ReviewRequired(ValueError):
    pass


def clean(value):
    return ''.join((value or '').split()).upper()


def validate_input(number, request_type, request_number, scac):
    number, request_number, scac = clean(number), clean(request_number), clean(scac)
    if not re.fullmatch(r'[A-Z]{3}[UJZ][0-9]{7}', number):
        raise ValueError('Enter an ISO container number with four letters and seven digits.')
    # ISO 6346 letter values omit multiples of eleven.
    letters = dict(zip('ABCDEFGHIJKLMNOPQRSTUVWXYZ', [10,12,13,14,15,16,17,18,19,20,21,23,24,25,26,27,28,29,30,31,32,34,35,36,37,38]))
    total = sum((int(c) if c.isdigit() else letters[c]) * (2 ** i) for i,c in enumerate(number[:10]))
    if total % 11 % 10 != int(number[-1]):
        raise ValueError('Container number check digit is invalid.')
    if request_type not in ('container', 'bill_of_lading', 'booking'):
        raise ValueError('Unsupported tracking number type.')
    request_number = number if request_type == 'container' else request_number
    if not re.fullmatch(r'[A-Z0-9]{1,64}', request_number):
        raise ValueError('Enter a carrier master bill of lading or booking number.')
    if scac and not re.fullmatch(r'[A-Z]{2,4}', scac):
        raise ValueError('Enter a two to four letter carrier SCAC.')
    return number, request_type, request_number, scac


def choose_container(doc, number, request_type, request_number, scac):
    matches, historical = [], []
    for resource in doc.get('data', []):
        if resource.get('type') != 'container' or clean(resource.get('attributes', {}).get('number')) != number:
            continue
        links = relationship(resource, 'shipment')
        if len(links) != 1:
            raise ReviewRequired('Container shipment identity is unavailable; review the journey.')
        shipment = resources(doc).get(('shipment', links[0]['id']))
        if not shipment:
            raise ReviewRequired('Container shipment details are unavailable; review the journey.')
        attrs = shipment.get('attributes', {})
        if scac and clean(attrs.get('shipping_line_scac')) != scac:
            continue
        if request_type != 'container':
            key = 'bill_of_lading_number' if request_type == 'bill_of_lading' else 'booking_number'
            if key not in attrs:
                raise ReviewRequired('The existing journey lacks the requested shipment reference. Link the verified UUID manually.')
            if clean(attrs.get(key)) != request_number:
                continue
        # Require an explicitly active shipment, never assume missing means active.
        if 'line_tracking_stopped_at' not in attrs or attrs['line_tracking_stopped_at'] or resource.get('attributes', {}).get('current_status') == 'empty_returned':
            historical.append(resource)
        else:
            matches.append(resource)
    if len(matches) > 1:
        raise ReviewRequired('Several active journeys match. Enter the master bill or booking, or link the correct UUID manually.')
    if len(matches) == 1:
        return str(UUID(matches[0]['id']))
    if historical:
        raise ReviewRequired('Only historical or stopped tracking matches. Review the journey before creating new tracking.')
    return None


def choose_request(doc, row):
    matches = []
    marker = 'bokser-t49:' + str(row['operation_id'])
    for r in doc.get('data', []):
        a = r.get('attributes', {})
        if r.get('type') != 'tracking_request' or clean(a.get('request_number')) != row['request_number'] or a.get('request_type') != row['request_type']:
            continue
        if row['scac'] and a.get('scac') and clean(a['scac']) != row['scac']:
            continue
        matches.append(r)
    own = [r for r in matches if marker in r.get('attributes', {}).get('ref_numbers', [])]
    if len(own) == 1:
        return own[0]
    if len(own) > 1 or len(matches) > 1:
        raise ReviewRequired('Several tracking requests match; review before linking or creating tracking.')
    if matches:
        return matches[0]
    return None


class Initiator:
    def __init__(self, store, client):
        self.store, self.client = store, client

    async def once(self):
        row = await self.store.next_initiation()
        if not row:
            return False
        oid = str(row['operation_id'])
        try:
            if row['tracking_request_id']:
                request = (await self.client.get_tracking_request(str(row['tracking_request_id'])))['data']
                await self.resolve_request(row, request)
                return True
            # Complete paginated lookup, with exact local number/journey validation.
            doc = await self.client.list_containers(row['number'])
            cid = choose_container(doc, row['number'], row['request_type'], row['request_number'], row['scac'])
            if cid:
                await self.link(row, cid)
                return True
            found = choose_request(await self.client.list_requests(row['request_number']), row)
            if found:
                await self.store.update_initiation(oid, 'PENDING', tracking_request_id=str(UUID(found['id'])))
                await self.resolve_request(row, found)
                return True
            if row['status'] == 'SUBMITTING':
                # A prior POST may have reached the provider. Never repeat it.
                raise ReviewRequired('Submission outcome is uncertain. No duplicate request was sent. Review Terminal49 tracking requests and link its UUID manually if created.')
            # Commit BEFORE the external side effect. Crash/timeout recovery can
            # only look up requests, never send this operation a second time.
            await self.store.update_initiation(oid, 'SUBMITTING')
            attrs = {'request_type': row['request_type'], 'request_number': row['request_number'],
                     'ref_numbers': ['bokser-t49:' + oid]}
            if row['scac']:
                attrs['scac'] = row['scac']
            else:
                attrs['auto_detect_vocc_scac'] = True
            request = (await self.client.create_tracking_request(attrs))['data']
            rid = str(UUID(request['id']))
            await self.store.update_initiation(oid, 'PENDING', tracking_request_id=rid)
            await self.resolve_request(row, request)
        except ReviewRequired as exc:
            await self.store.update_initiation(oid, 'NEEDS_REVIEW', error=str(exc))
        except Exception as exc:
            # Only safe reads retry. SUBMITTING remains durable for reconciliation.
            import httpx
            reason = 'Terminal49 HTTP %s' % exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else type(exc).__name__
            await self.store.defer_initiation(oid, reason)
        return True

    async def resolve_request(self, row, request):
        a = request.get('attributes', {})
        if clean(a.get('request_number')) != row['request_number'] or a.get('request_type') != row['request_type']:
            raise ReviewRequired('Tracking request identity does not match Odoo.')
        if row['scac'] and a.get('scac') and clean(a['scac']) != row['scac']:
            raise ReviewRequired('Tracking request carrier does not match Odoo.')
        if a.get('status') in ('failed', 'tracking_stopped'):
            await self.store.update_initiation(str(row['operation_id']), 'FAILED', error='Terminal49 tracking request failed or stopped. Review the carrier and tracking reference.')
            return
        shipments = [r for r in relationship(request, 'tracked_object') if r.get('type') == 'shipment']
        if not shipments:
            await self.store.update_initiation(str(row['operation_id']), 'PENDING')
            return
        if len(shipments) != 1:
            raise ReviewRequired('Tracking request resolved several shipments.')
        doc = await self.client.get_shipment(shipments[0]['id'])
        attrs = doc['data'].get('attributes', {})
        if attrs.get('line_tracking_stopped_at'):
            raise ReviewRequired('Shipment tracking is stopped; review before linking.')
        candidates = [r for r in resources(doc).values() if r['type'] == 'container' and clean(r.get('attributes', {}).get('number')) == row['number']]
        if len(candidates) > 1:
            raise ReviewRequired('Several containers match the requested shipment.')
        if not candidates:
            await self.store.update_initiation(str(row['operation_id']), 'PENDING', error='Waiting for the requested container to appear on this shipment.')
            return
        candidate = candidates[0]
        if not any(link['id'] == shipments[0]['id'] for link in relationship(candidate, 'shipment')):
            raise ReviewRequired('Container shipment identity does not match the tracking request.')
        await self.link(row, str(UUID(candidate['id'])))

    async def link(self, row, cid):
        from .store import IdentityConflict
        try:
            await self.store.mapping(cid, row['odoo_container_id'], row['number'], True, refresh=True)
        except IdentityConflict:
            raise ReviewRequired('This Terminal49 journey is already linked to another Odoo record.') from None
        await self.store.update_initiation(str(row['operation_id']), 'LINKED', container_id=cid)
