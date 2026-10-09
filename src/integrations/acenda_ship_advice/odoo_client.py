from urllib.parse import urlsplit
import httpx

class AcendaOdooError(RuntimeError):
    pass

class AcendaOdooClient:
    def __init__(self, *, base_url, database, api_key, http_client):
        url=urlsplit(base_url)
        if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('','/'):
            raise ValueError('Odoo requires an HTTPS base URL without credentials or a path')
        if not database or not api_key: raise ValueError('Odoo database and API key are required')
        self.url=base_url.rstrip('/');self.database=database;self.key=api_key;self.http=http_client

    async def import_order(self,account_code,payload):
        try:
            response=await self.http.post(self.url+'/json/2/bokser.acenda.account/import_order',
              headers={'Authorization':'bearer '+self.key,'X-Odoo-Database':self.database},
              json={'account_code':account_code,'payload':payload},timeout=30,follow_redirects=False)
        except httpx.HTTPError:
            raise AcendaOdooError('Odoo transport failed; replay the same parent/advice identities') from None
        if response.status_code!=200:
            raise AcendaOdooError('Odoo import failed (HTTP %s)' % response.status_code)
        try:
            result=response.json()
            if not isinstance(result,dict) or result.get('state') not in {'held','exception','imported','stale'}: raise ValueError()
            return result
        except ValueError: raise AcendaOdooError('Odoo returned an invalid import result') from None
