"""Explicit Odoo inbound calls; no SOS write transport or background registration."""
from urllib.parse import urlsplit
import httpx


class MirrorError(RuntimeError):
    def __init__(self, code, *, retryable=False):
        super().__init__(code)
        self.retryable = retryable


class OdooMirrorClient:
    def __init__(self, *, base_url, database, api_key, client):
        url = urlsplit(base_url)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
            raise ValueError("invalid_odoo_url")
        if any(not isinstance(v, str) or not v.strip() or any(ord(c) < 32 for c in v) for v in (database, api_key)):
            raise ValueError("invalid_odoo_credentials")
        self.url = base_url.rstrip("/") + "/json/2/bokser.sos.account/import_partner"
        self.headers = {"Authorization": "bearer " + api_key, "X-Odoo-Database": database}
        self.client = client

    async def import_transaction(self, *, account_code, company_id, payload):
        from .transactions import validate_transaction
        validate_transaction(payload)
        url = self.url.rsplit('/', 1)[0] + '/import_transaction'
        try:
            response = await self.client.post(url, headers=self.headers,
                json={'account_code':account_code,'company_id':company_id,'payload':payload},
                follow_redirects=False,timeout=30)
            response.raise_for_status();result=response.json()
        except httpx.HTTPStatusError as exc:
            raise MirrorError('odoo_http_'+str(exc.response.status_code),
                retryable=exc.response.status_code==429 or exc.response.status_code>=500) from None
        except (httpx.HTTPError,ValueError):
            raise MirrorError('odoo_transport_error',retryable=True) from None
        if not isinstance(result,dict) or set(result)!={'status','entity','source_id','res_id'} or result['entity']!=payload['entity'] or result['source_id']!=payload['source_id'] or result['status'] not in {'created','updated','duplicate','stale','before_cutoff'}:
            raise MirrorError('invalid_odoo_response')
        if result['status']=='before_cutoff':
            if result['res_id'] is not None:raise MirrorError('invalid_odoo_response')
        elif type(result['res_id']) is not int or result['res_id']<=0:raise MirrorError('invalid_odoo_response')
        return result

    async def import_partner(self, *, account_code, company_id, payload):
        from .contract import validate
        validate(payload)
        try:
            response = await self.client.post(self.url, headers=self.headers,
                json={"account_code": account_code, "company_id": company_id, "payload": payload},
                follow_redirects=False, timeout=30)
            response.raise_for_status()
            result = response.json()
        except httpx.HTTPStatusError as exc:
            raise MirrorError("odoo_request_failed_replay_safe",retryable=exc.response.status_code==429 or exc.response.status_code>=500) from None
        except (httpx.HTTPError, ValueError):
            raise MirrorError("odoo_request_failed_replay_safe",retryable=True) from None
        if not isinstance(result, dict) or set(result) != {"status", "source_id", "partner_id"} or result.get("status") not in {"created", "updated", "duplicate", "stale"} or result.get("source_id") != payload["source_id"] or type(result.get("partner_id")) is not int or result["partner_id"] <= 0:
            raise MirrorError("invalid_odoo_response")
        return result
