"""Read-only definition inventory. Never reads or exports record field values."""
from .capture import CaptureError


async def inventory(client):
    definitions, total, start = [], None, 1
    while total is None or len(definitions) < total:
        response = await client.get('/customfield', params={'start': start, 'maxresults': 200})
        response.raise_for_status()
        body = response.json()
        data = body.get('data')
        if body.get('status') != 'ok' or type(body.get('totalCount')) is not int or not isinstance(data, list) or body.get('count') != len(data):
            raise CaptureError('invalid_custom_field_inventory')
        if total is not None and total != body['totalCount']:
            raise CaptureError('custom_field_inventory_changed')
        total = body['totalCount']
        if total < 0 or total > 10000 or len(data) != min(200, total-len(definitions)):
            raise CaptureError('incomplete_custom_field_inventory')
        for raw in data:
            if not isinstance(raw, dict) or type(raw.get('id')) is not int or raw['id'] <= 0:
                raise CaptureError('invalid_custom_field_definition')
            safe = {k: raw.get(k) for k in ('id', 'name', 'dataType', 'showOn', 'displayOn')}
            if not isinstance(safe['name'], str) or not isinstance(safe['dataType'], str):
                raise CaptureError('invalid_custom_field_definition')
            definitions.append(safe)
        start += 200
    if len({r['id'] for r in definitions}) != total:
        raise CaptureError('duplicate_custom_field_definition')
    return sorted(definitions, key=lambda r: r['id'])
