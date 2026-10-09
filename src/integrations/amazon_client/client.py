from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx

from src.core.configs.amazon import AmazonSettings

API_ROOT = "https://sellingpartnerapi-na.amazon.com"
TOKEN_URL = "https://api.amazon.com/auth/o2/token"


class AmazonAPIError(RuntimeError):
    """Safe diagnostic: never includes headers, URLs, bodies, or customer data."""
    def __init__(self, operation: str, status: int | None = None):
        self.operation = operation
        self.status = status
        super().__init__(f"Amazon {operation} failed (HTTP {status or 'unavailable'})")


class AmazonWriteUncertain(AmazonAPIError):
    """Persist as uncertain and reconcile before any resubmission."""


def utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Amazon timestamps must have a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class _Pacer:
    def __init__(self, interval: float):
        self.interval = interval
        self.lock = asyncio.Lock()
        self.next_at = 0.0

    async def wait(self) -> None:
        async with self.lock:
            await asyncio.sleep(max(0.0, self.next_at - time.monotonic()))
            self.next_at = time.monotonic() + self.interval


class AmazonClient:
    """Single-account client. Share one instance within a single worker process.

    No durable retries, order storage, or ERP side effects here. Injected HTTP
    clients are caller-owned. Endpoints and token host are fixed to avoid sending
    credentials to an arbitrary configured host.
    """
    def __init__(self, config: AmazonSettings, http_client: httpx.AsyncClient | None = None):
        self.config = config
        self._owns_http = http_client is None
        self._http = http_client or httpx.AsyncClient()
        self._token_lock = asyncio.Lock()
        self._token: str | None = None
        self._expires_at = 0.0
        self._pacers = {
            "searchOrders": _Pacer(config.amazon_search_min_interval_seconds),
            "confirmShipment": _Pacer(config.amazon_shipment_min_interval_seconds),
            "patchInventory": _Pacer(config.amazon_inventory_min_interval_seconds),
        }

    async def __aenter__(self) -> AmazonClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()
        self._token = None
        self._expires_at = 0

    async def _access_token(self) -> str:
        self.config.require_active()
        async with self._token_lock:
            if self._token and time.monotonic() < self._expires_at:
                return self._token
            try:
                response = await self._http.post(TOKEN_URL, data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.config.amazon_lwa_refresh_token.get_secret_value(),
                    "client_id": self.config.amazon_lwa_client_id,
                    "client_secret": self.config.amazon_lwa_client_secret.get_secret_value(),
                }, timeout=self.config.amazon_http_timeout_seconds, follow_redirects=False)
            except httpx.HTTPError:
                raise AmazonAPIError("authorization") from None
            if response.status_code != 200:
                raise AmazonAPIError("authorization", response.status_code)
            try:
                body = response.json()
                token = body["access_token"]
                lifetime = int(body["expires_in"])
                if not isinstance(token, str) or not token or lifetime <= 0:
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                raise AmazonAPIError("authorization response") from None
            self._token = token
            self._expires_at = time.monotonic() + max(0, lifetime - 60)
            return token

    async def _request(self, operation: str, method: str, path: str, **kwargs: Any) -> httpx.Response:
        write = method != "GET"
        self.config.require_active(write=write)
        await self._pacers[operation].wait()
        token = await self._access_token()
        # Recheck ownership immediately before sending, including after pacing.
        self.config.require_active(write=write)
        try:
            response = await self._http.request(method, ("https://sandbox.sellingpartnerapi-na.amazon.com" if self.config.amazon_environment == "sandbox" else API_ROOT) + path, headers={
                "x-amz-access-token": token,
                "x-amz-date": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                "user-agent": "BokserAmazon/0.1 (Language=Python)",
                "accept": "application/json",
            }, timeout=self.config.amazon_http_timeout_seconds, follow_redirects=False, **kwargs)
        except httpx.HTTPError:
            error = AmazonWriteUncertain if write else AmazonAPIError
            raise error(operation) from None
        if response.status_code in (401, 403):
            self._token = None
            self._expires_at = 0
        if not 200 <= response.status_code < 300:
            error = AmazonWriteUncertain if write and (response.status_code >= 500 or response.status_code == 408) else AmazonAPIError
            raise error(operation, response.status_code)
        return response

    async def order_pages(self, *, updated_after: datetime, updated_before: datetime,
                          include_customer: bool = False) -> AsyncIterator[dict[str, Any]]:
        """Fetch an immutable update window, including FBA and cancellation changes.

        Caller must durably commit each page to an idempotent, encrypted inbox
        before requesting the next page. Commit the watermark only after complete
        exhaustion. On failure restart the same window; never skip to current time.
        Customer datasets are opt-in pending restricted role and retention support.
        """
        lower, upper = utc_timestamp(updated_after), utc_timestamp(updated_before)
        if updated_before < updated_after or updated_before > datetime.now(timezone.utc) - timedelta(minutes=2):
            raise ValueError("Invalid Amazon update window; upper bound must be at least two minutes old")
        included = ["FULFILLMENT", "CANCELLATION", "PACKAGES", "PROCEEDS", "TAX"]
        if include_customer:
            included += ["RECIPIENT"]
        params = {"lastUpdatedAfter": lower, "lastUpdatedBefore": upper,
                  "marketplaceIds": self.config.amazon_marketplace_id,
                  "maxResultsPerPage": "100", "includedData": ",".join(included)}
        seen: set[str] = set()
        while True:
            response = await self._request("searchOrders", "GET", "/orders/2026-01-01/orders", params=params)
            try:
                page = response.json()
                if not isinstance(page, dict) or not isinstance(page["orders"], list):
                    raise ValueError
                if any(not isinstance(order, dict) or not order.get("orderId") for order in page["orders"]):
                    raise ValueError
                pagination = page.get("pagination") or {}
                if not isinstance(pagination, dict):
                    raise ValueError
                token = pagination.get("nextToken")
                if token is not None and (not isinstance(token, str) or not token or token in seen):
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                raise AmazonAPIError("searchOrders response") from None
            yield page
            if token is None:
                return
            seen.add(token)
            params = {**params, "paginationToken": token}

    async def publish_inventory(self, seller_sku: str, quantity: int, *, product_type: str) -> dict[str, Any]:
        if not seller_sku.strip() or not product_type.strip() or type(quantity) is not int or quantity < 0:
            raise ValueError("Inventory requires SKU, mapped product type, and nonnegative integer quantity")
        path = "/listings/2021-08-01/items/" + quote(self.config.amazon_seller_id, safe="") + "/" + quote(seller_sku, safe="")
        response = await self._request("patchInventory", "PATCH", path,
            params={"marketplaceIds": self.config.amazon_marketplace_id}, json={
                "productType": product_type,
                "patches": [{"op": "merge", "path": "/attributes/fulfillment_availability",
                             "value": [{"fulfillment_channel_code": "DEFAULT", "quantity": quantity}]}],
            })
        try:
            result = response.json()
            if not isinstance(result, dict) or result.get("status") not in ("ACCEPTED", "INVALID"):
                raise ValueError
        except (ValueError, TypeError):
            raise AmazonWriteUncertain("patchInventory response") from None
        # ACCEPTED is a submission acknowledgement, not evidence of applied stock.
        return result

    async def confirm_shipment(self, order_id: str, *, package_reference: str,
                               carrier_code: str, tracking_number: str, shipped_at: datetime,
                               items: dict[str, int], evidence_kind: str, evidence_reference: str,
                               fulfilled_by: str, carrier_name: str | None = None,
                               carrier_acceptance_enabled: bool = False) -> None:
        """Caller persists package reference and validates allocation quantities first.

        Stable numeric package reference is required across retries/corrections.
        Evidence must be verified by a trusted warehouse/carrier adapter.
        """
        import re
        if not re.fullmatch(r"\d{3}-\d{7}-\d{7}", order_id):
            raise ValueError("Invalid Amazon order identifier")
        if fulfilled_by != "MERCHANT":
            raise ValueError("FBA orders cannot use merchant shipment confirmation")
        permitted = {"wms_handoff"}
        if carrier_acceptance_enabled:
            permitted.add("carrier_acceptance")
        if evidence_kind not in permitted or not evidence_reference.strip():
            raise ValueError("Verified shipment evidence is required")
        if not package_reference.isascii() or not package_reference.isdigit() or int(package_reference) <= 0:
            raise ValueError("Persist a positive numeric package reference")
        if not carrier_code.strip() or not tracking_number.strip() or (carrier_code == "Other" and not carrier_name):
            raise ValueError("Carrier and tracking are required")
        if not items or any(not key or type(qty) is not int or qty <= 0 for key, qty in items.items()):
            raise ValueError("Shipment items require Amazon line IDs and positive integer quantities")
        ship_date = utc_timestamp(shipped_at)
        if shipped_at > datetime.now(timezone.utc):
            raise ValueError("Shipment date cannot be in the future")
        package = {"packageReferenceId": package_reference, "carrierCode": carrier_code,
                   "trackingNumber": tracking_number, "shipDate": ship_date,
                   "orderItems": [{"orderItemId": key, "quantity": qty} for key, qty in items.items()]}
        if carrier_name:
            package["carrierName"] = carrier_name
        response = await self._request("confirmShipment", "POST",
            f"/orders/v0/orders/{order_id}/shipmentConfirmation",
            json={"marketplaceId": self.config.amazon_marketplace_id, "packageDetail": package})
        if response.status_code != 204:
            raise AmazonWriteUncertain("confirmShipment response", response.status_code)
