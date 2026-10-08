"""Dependency-free HTTPS client. Keys and response bodies never enter errors."""
from dataclasses import dataclass
import json
import math
import time
from urllib import request, error, parse


class GatewayError(RuntimeError):
    def __init__(self, status=None, retry_after=0):
        super().__init__("KSP gateway request failed" + (" (HTTP %s)" % status if status else ""))
        self.status, self.retry_after = status, retry_after


@dataclass
class Response:
    status: int
    data: object
    headers: dict


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def https_transport(method, url, headers, body, timeout):
    encoded = json.dumps(body, allow_nan=False).encode() if body is not None else None
    req = request.Request(url, data=encoded, headers=headers, method=method)
    try:
        response = request.build_opener(NoRedirect()).open(req, timeout=timeout)
    except error.HTTPError as exc:
        return Response(exc.code, None, dict(exc.headers))
    except (error.URLError, TimeoutError, OSError):
        raise GatewayError() from None
    with response:
        raw = response.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024:
            raise GatewayError(response.status)
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError):
            raise GatewayError(response.status) from None
        return Response(response.status, data, dict(response.headers))


class KSPGatewayClient:
    BASE = "https://connect.ksp3plhq.com"

    def __init__(self, api_key, store, *, transport=https_transport, sleep=time.sleep):
        if not isinstance(api_key, str) or not api_key.strip() or any(c in api_key for c in "\r\n"):
            raise ValueError("A KSP API key is required")
        self._key, self.store, self.transport, self.sleep = api_key, store, transport, sleep

    def _request(self, method, path, body=None):
        attempts = 3 if method == "GET" else 1
        for attempt in range(attempts):
            wait = self.store.reserve_request_slot()
            if wait > 0:
                self.sleep(wait)
            response = self.transport(method, self.BASE + path,
                                      {"X-API-Key": self._key, "Content-Type": "application/json",
                                       "Accept": "application/json",
                                       "User-Agent": "Bokser-KSP-Integration-Diagnostic/1.0"}, body, 30)
            if 200 <= response.status < 300:
                return response.data
            header = next((v for k, v in response.headers.items() if k.lower() == "retry-after"), "1")
            try:
                value = float(header)
                wait = min(max(value, 1), 60) if math.isfinite(value) else 1
            except (ValueError, TypeError):
                wait = 1
            if method == "GET" and response.status in (429, 500, 502, 503, 504) and attempt + 1 < attempts:
                self.sleep(wait)
                continue
            raise GatewayError(response.status, wait)

    def submit_order(self, body):
        # Never automatically retry POST: a timeout or 502 can follow acceptance.
        return self._request("POST", "/v1/orders", body)

    def order(self, identifier):
        return self._request("GET", "/v1/orders/" + parse.quote(identifier, safe=""))

    def tracking(self, identifier):
        return self._request("GET", "/v1/orders/" + parse.quote(identifier, safe="") + "/tracking")

    def find_order(self, code):
        raw = self._request("GET", "/v1/orders?" + parse.urlencode({"page": 0, "size": 50, "Code.eq": code}))
        # The guide omits the exact order-list envelope. Recognize only explicit
        # arrays; any other shape must be verified using a real response fixture.
        rows = raw if isinstance(raw, list) else raw.get("data") if isinstance(raw, dict) else None
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise GatewayError()
        matches = [row for row in rows if row.get("code") == code]
        if len(matches) > 1:
            raise GatewayError()
        return matches[0] if matches else None

    def query_inventory(self, skus):
        if not isinstance(skus, list) or not 1 <= len(skus) <= 100 or any(not isinstance(s, str) or not s for s in skus):
            raise ValueError("Query 1 to 100 explicit SKUs")
        return self._request("POST", "/v1/inventory/query", {"skus": skus})

    def availability(self, page=0, size=100):
        if type(page) is not int or page < 0 or type(size) is not int or not 1 <= size <= 100:
            raise ValueError("Invalid inventory page")
        return self._request("GET", "/v1/inventory/availability?" + parse.urlencode({"page": page, "size": size}))


class OdooFulfillmentClient:
    def __init__(self, base_url, database, api_key, *, transport=https_transport):
        parsed = parse.urlsplit(base_url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
            raise ValueError("Odoo requires an HTTPS origin")
        if not database or not api_key or any(c in database + api_key for c in "\r\n"):
            raise ValueError("Odoo database and API key are required")
        self.base, self.database, self._key, self.transport = base_url.rstrip("/"), database, api_key, transport

    def _call(self, method, arguments):
        response = self.transport("POST", self.base + "/json/2/stock.picking/" + method,
                                  {"Authorization": "bearer " + self._key, "X-Odoo-Database": self.database,
                                   "Content-Type": "application/json"}, arguments, 30)
        if response.status != 200:
            raise GatewayError(response.status)
        return response.data

    def acknowledge(self, anchor_id, claim_token, order_id, warehouse_id):
        result = self._call("bokser_acknowledge_submission", {
            "ids": [anchor_id], "claim_token": claim_token,
            "wms_order_ref": order_id, "warehouse_id": warehouse_id,
        })
        if result is not True:
            raise GatewayError()

    def apply_shipment(self, anchor_id, report):
        result = self._call("bokser_apply_shipment_event", {"ids": [anchor_id], "report": report})
        if not isinstance(result, dict) or result.get("event_id") != report["event_id"]:
            raise GatewayError()
        return result
