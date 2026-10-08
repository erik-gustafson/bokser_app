from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo


class PayloadError(ValueError):
    pass


def valid_signature(raw: bytes, signature: str | None, secret: str) -> bool:
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature.encode('utf-8'), expected.encode('ascii'))


def parse_notification(raw: bytes, *, max_bytes: int = 2_000_000) -> dict:
    if len(raw) > max_bytes:
        raise PayloadError('Payload exceeds configured limit')
    try:
        doc = json.loads(raw)
        data = doc['data']
        if data['type'] != 'webhook_notification':
            raise ValueError()
        UUID(data['id'])
        if not isinstance(data['attributes']['event'], str) or not data['attributes']['event']:
            raise ValueError()
        if not isinstance(doc.get('included', []), list):
            raise ValueError()
        for resource in doc.get('included', []):
            if not isinstance(resource, dict) or not isinstance(resource.get('id'), str) or not isinstance(resource.get('type'), str):
                raise ValueError()
        return doc
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise PayloadError('Invalid Terminal49 notification envelope') from exc


def resources(doc: dict) -> dict[tuple[str, str], dict]:
    primary = doc.get('data', [])
    primary = primary if isinstance(primary, list) else [primary]
    return {(r['type'], r['id']): r for r in [*primary, *doc.get('included', [])]
            if isinstance(r, dict) and 'type' in r and 'id' in r}


def relationship(resource: dict, name: str) -> list[dict]:
    data = resource.get('relationships', {}).get(name, {}).get('data')
    return data if isinstance(data, list) else [data] if isinstance(data, dict) else []


def container_ids(doc: dict) -> set[str]:
    """Use resource identity and relationship IDs, never a physical number."""
    result = set()
    for r in resources(doc).values():
        if r['type'] == 'container':
            result.add(r['id'])
        for name in ('container', 'containers', 'reference_object'):
            result.update(x['id'] for x in relationship(r, name) if x.get('type') == 'container')
    return result


def utc_timestamp(value: str | None) -> str | None:
    if value is None:
        return None
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise PayloadError('Source timestamps require a timezone')
    return dt.astimezone(timezone.utc).isoformat()


def local_date(value: str | None, timezone_name: str | None) -> str | None:
    if value is None:
        return None
    if len(value) == 10:
        return datetime.fromisoformat(value).date().isoformat()
    if not timezone_name:
        raise PayloadError('Timestamp Last Free Day requires terminal timezone')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise PayloadError('Last Free Day timestamp requires an offset')
    return dt.astimezone(ZoneInfo(timezone_name)).date().isoformat()


def normalize_snapshot(doc: dict, container_id: str, *, observed_at: str) -> dict:
    """Normalize a freshly fetched API snapshot, not an old webhook snapshot.

    Absent keys stay absent. Explicit nulls stay null for Odoo to clear.
    observed_at is fetch time, not a provider revision or milestone timestamp.
    Caller must serialize fetch + publish per container to prevent regressions.
    """
    index = resources(doc)
    c = index.get(('container', container_id))
    if c is None:
        raise PayloadError('Requested container missing from API response')
    a = c.get('attributes', {})
    out = {'terminal49_container_id': container_id}
    status_map = {'new': 'unknown', 'on_ship': 'in_transit', 'grounded': 'discharged',
                  'available': 'available', 'not_available': 'discharged',
                  'awaiting_inland_transfer': 'discharged', 'on_rail': 'in_transit',
                  'off_dock': 'outgated', 'picked_up': 'outgated',
                  'delivered': 'delivered', 'empty_returned': 'empty_returned'}
    if 'current_status' in a:
        out['source_status'] = a['current_status']
        out['transport_status'] = status_map.get(a['current_status'], 'unknown')
    for source, target in [('number', 'number'), ('pod_arrived_at', 'port_arrived_at'),
                           ('pod_discharged_at', 'port_discharged_at'),
                           ('pod_full_out_at', 'port_outgated_at'),
                           ('empty_terminated_at', 'empty_returned_at')]:
        if source in a:
            out[target] = utc_timestamp(a[source]) if target.endswith('_at') else a[source]
    if 'available_for_pickup' in a:
        available = a['available_for_pickup']
        if available is not None and not isinstance(available, bool):
            raise PayloadError('Invalid pickup availability')
        out['pickup_available'] = 'unknown' if available is None or a.get('availability_known') is False else 'yes' if available else 'no'
    if 'pickup_lfd' in a:
        out['last_free_day'] = local_date(a['pickup_lfd'], a.get('pod_timezone'))
    for key in ('holds_at_pod_terminal', 'fees_at_pod_terminal', 'pickup_appointment_at',
                'pod_rail_loaded_at', 'pod_rail_departed_at', 'pod_rail_arrived_at',
                'pod_rail_unloaded_at', 'final_destination_full_out_at'):
        if key in a:
            out[key] = a[key]
    terminal_link = relationship(c, 'pod_terminal')
    if terminal_link:
        t = index.get((terminal_link[0]['type'], terminal_link[0]['id']))
        if t and 'name' in t.get('attributes', {}):
            out['destination_terminal'] = t['attributes']['name']
    elif 'pod_terminal' in c.get('relationships', {}):
        out['destination_terminal'] = None
    shipment = {}
    links = relationship(c, 'shipment')
    if links:
        shipment['terminal49_shipment_id'] = links[0]['id']
        s = index.get((links[0]['type'], links[0]['id']))
        if s:
            sa = s.get('attributes', {})
            for key in ('bill_of_lading_number', 'pod_eta_at', 'pod_original_eta_at',
                        'destination_eta_at', 'pod_ata_at', 'ref_numbers'):
                if key in sa:
                    shipment[key] = utc_timestamp(sa[key]) if key.endswith('_at') else sa[key]
            if 'pod_eta_at' in sa:
                out['port_eta'] = utc_timestamp(sa['pod_eta_at'])
            for source, target in [('pod_vessel_name', 'vessel_name'), ('pod_voyage_number', 'voyage_number'),
                                   ('shipping_line_name', 'carrier_name'), ('shipping_line_scac', 'carrier_scac')]:
                if source in sa:
                    out[target] = sa[source]
            if 'destination_eta_at' in sa:
                out['inland_eta'] = utc_timestamp(sa['destination_eta_at'])
    # Absence is distinct from explicit null. Store the complete provider snapshot
    # in the lake; these approved fields are the operational projection only.
    return {'schema_version': 1, 'observed_at': utc_timestamp(observed_at),
            'container': out, 'shipment': shipment}


def event_records(doc: dict) -> list[dict]:
    """Keep provider events separate from current state, including corrections."""
    result = []
    for r in resources(doc).values():
        if r['type'] not in ('transport_event', 'estimated_event', 'container_updated_event'):
            continue
        a = r.get('attributes', {})
        result.append({'source_event_id': r['id'], 'resource_type': r['type'],
                       'container_ids': [x['id'] for x in relationship(r, 'container')],
                       'attributes': a, 'relationships': r.get('relationships', {})})
    return result
