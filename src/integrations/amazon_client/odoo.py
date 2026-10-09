import httpx
from urllib.parse import urlsplit


class OdooConnectorError(RuntimeError):
    pass


class OdooAmazonClient:
    def __init__(self, *, base_url, database, api_key, http_client):
        url = urlsplit(base_url)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
            raise ValueError('Odoo requires an HTTPS base URL without credentials or a path')
        self.base_url, self.database, self.api_key, self.http = base_url.rstrip('/'), database, api_key, http_client

    async def import_order(self, account_code, payload):
        try:
            response = await self.http.post(self.base_url + '/json/2/bokser.amazon.account/import_order',
                headers={'Authorization': 'bearer ' + self.api_key, 'X-Odoo-Database': self.database},
                json={'account_code': account_code, 'payload': payload}, timeout=30, follow_redirects=False)
        except httpx.HTTPError:
            raise OdooConnectorError('Odoo import transport failed; replay using the same order identity') from None
        if response.status_code != 200:
            raise OdooConnectorError('Odoo import failed (HTTP %s)' % response.status_code)
        try:
            result = response.json()
            if not isinstance(result, dict) or result.get('state') not in {'imported', 'held', 'reporting', 'exception', 'stale'}:
                raise ValueError()
            return result
        except ValueError:
            raise OdooConnectorError('Odoo import returned an invalid result') from None
