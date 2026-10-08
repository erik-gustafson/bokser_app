from __future__ import annotations

import asyncio
import time
from uuid import UUID


class Terminal49Client:
    """Accepts an application-owned httpx.AsyncClient or compatible transport.

    Each response (including errors) is sent to an async raw-response sink before
    parsing. Retries are bounded; exhausted requests must retry via the inbox.
    Share one instance per process to enforce the local request pacing.
    """
    def __init__(self, http_client, api_key: str, response_sink, *, interval: float = 1.0):
        if not api_key:
            raise ValueError('Terminal49 API key is required')
        self.http = http_client
        self.api_key = api_key
        self.sink = response_sink
        self.interval = max(0.0, interval)
        self.lock = asyncio.Lock()
        self.next_at = 0.0

    async def get_container(self, container_id: str) -> dict:
        cid = str(UUID(container_id))  # Never follow untrusted webhook links.
        return await self._get(f'containers/{cid}', {'include': 'shipment,pod_terminal'})

    async def get_shipment(self, shipment_id: str) -> dict:
        sid = str(UUID(shipment_id))
        return await self._get(f'shipments/{sid}', {'include': 'containers'})

    async def get_tracking_request(self, request_id: str) -> dict:
        return await self._get(f'tracking_requests/{UUID(request_id)}', {'include': 'tracked_object'})

    async def get_events(self, container_id: str) -> dict:
        cid = str(UUID(container_id))
        # Endpoint has no documented pagination parameters. Included container
        # history is obtained in one response; refuse truncation rather than miss it.
        doc = await self._get(f'containers/{cid}/transport_events', {})
        if doc.get('links', {}).get('next'):
            raise ValueError('Unexpected paginated events; operator review required')
        return doc

    async def _get(self, path: str, params: dict) -> dict:
        for attempt in range(4):
            async with self.lock:
                await asyncio.sleep(max(0.0, self.next_at - time.monotonic()))
                self.next_at = time.monotonic() + self.interval
                response = await self.http.get('https://api.terminal49.com/v2/' + path,
                    params=params, headers={'Authorization': 'Token ' + self.api_key,
                                            'Accept': 'application/vnd.api+json'},
                    timeout=30.0, follow_redirects=False)
                await self.sink(response.content, {'path': path, 'status_code': response.status_code})
            if response.status_code != 429 and response.status_code < 500:
                response.raise_for_status()
                return response.json()
            if attempt == 3:
                response.raise_for_status()
            retry_after = response.headers.get('Retry-After', '')
            delay = min(float(retry_after), 60.0) if retry_after.isdigit() else 2 ** attempt
            await asyncio.sleep(delay)
        raise RuntimeError('Unreachable')

    async def _list(self, path, params):
        data, included = [], []
        # Reconstruct fixed-origin requests; never follow provider pagination URLs.
        for page in range(1, 101):
            doc = await self._get(path, dict(params, **{'page[number]': page, 'page[size]': 50}))
            if not isinstance(doc.get('data'), list):
                raise ValueError('Invalid provider list response')
            data.extend(doc['data'])
            included.extend(doc.get('included', []))
            if not doc.get('links', {}).get('next'):
                return {'data': data, 'included': included}
        raise ValueError('Lookup exceeds pagination limit; operator review required')

    async def list_containers(self, number):
        return await self._list('containers', {'filter[number]': number, 'include': 'shipment'})

    async def list_requests(self, number):
        return await self._list('tracking_requests', {'filter[request_number]': number})

    async def list_shipments(self, number):
        return await self._list('shipments', {'filter[number]': number})

    async def create_tracking_request(self, attributes):
        # Deliberately ONE attempt. POST is not proven provider-idempotent.
        async with self.lock:
            await asyncio.sleep(max(0.0, self.next_at - time.monotonic()))
            self.next_at = time.monotonic() + self.interval
            body = {'data': {'type': 'tracking_request', 'attributes': attributes}}
            from json import dumps
            await self.sink(dumps(body).encode(), {'path': 'tracking_requests', 'method': 'POST', 'kind': 'request'})
            response = await self.http.post('https://api.terminal49.com/v2/tracking_requests',
                json=body, headers={'Authorization': 'Token ' + self.api_key,
                                   'Accept': 'application/vnd.api+json'},
                timeout=30.0, follow_redirects=False)
            await self.sink(response.content, {'path': 'tracking_requests', 'method': 'POST', 'status_code': response.status_code})
            response.raise_for_status()
            return response.json()
