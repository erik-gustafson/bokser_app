from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any

import httpx

from src.bokser_app.core.config import settings
from src.bokser_app.integrations.sos_inventory.auth import (
    PROVIDER_SOS,
    get_valid_token_async,
)

logger = logging.getLogger(__name__)


class SOSInventoryClient:
    """
    Async SOS Inventory client with:
      - centralized auth header creation
      - centralized retry + backoff
      - process-wide rate limiting
      - thin HTTP helpers
      - SOS-specific workflow methods
    """

    RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
    THROTTLE_MESSAGE = "Throttle limit exceeded."
    DEFAULT_MIN_INTERVAL_SEC = 0.501

    # Shared across all instances in this process.
    _api_lock = asyncio.Lock()
    _last_call_ts = 0.0

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_url: str | None = None,
        base_headers: dict[str, str] | None = None,
        auth_header_name: str | None = None,
        auth_header_prefix: str | None = None,
        max_retries: int = 5,
        base_delay: float = 0.5,
        max_delay: float = 5.0,
        throttle_delay: float = 0.5,
        min_interval_sec: float = DEFAULT_MIN_INTERVAL_SEC,
    ) -> None:
        self._client = client
        self._api_url = (api_url or settings.sos_api_url).rstrip("/")
        self._base_headers = base_headers or settings.sos_base_headers

        self._auth_header_name = auth_header_name or settings.sos_auth_header_name
        self._auth_header_prefix = (
            auth_header_prefix
            if auth_header_prefix is not None
            else settings.sos_auth_header_prefix
        )

        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._throttle_delay = throttle_delay
        self._min_interval_sec = min_interval_sec

    async def _auth_headers(self) -> dict[str, str]:
        token = await get_valid_token_async(PROVIDER_SOS)
        headers = dict(self._base_headers)

        if self._auth_header_prefix:
            headers[self._auth_header_name] = f"{self._auth_header_prefix} {token}"
        else:
            headers[self._auth_header_name] = token

        return headers

    def _build_url(self, path_or_url: str) -> str:
        if path_or_url.startswith(("http://", "https://")):
            return path_or_url
        return f"{self._api_url}/{path_or_url.lstrip('/')}"

    @staticmethod
    def _json_body(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    @classmethod
    def _extract_data(cls, response: httpx.Response) -> Any:
        return cls._json_body(response).get("data")

    @classmethod
    def _extract_message(cls, response: httpx.Response) -> str:
        message = cls._json_body(response).get("message", "")
        return message if isinstance(message, str) else ""

    @classmethod
    async def _rate_limit(cls, min_interval_sec: float) -> None:
        async with cls._api_lock:
            now = time.monotonic()
            elapsed = now - cls._last_call_ts

            if elapsed < min_interval_sec:
                await asyncio.sleep(min_interval_sec - elapsed)

            cls._last_call_ts = time.monotonic()

    def _should_retry_response(self, response: httpx.Response) -> bool:
        if response.status_code in self.RETRYABLE_STATUSES:
            return True

        if (
            response.status_code == 200
            and self._extract_message(response) == self.THROTTLE_MESSAGE
        ):
            return True

        return False

    def _backoff_delay(self, attempt_number: int) -> float:
        return min(
            self._max_delay,
            self._base_delay * (2 ** (attempt_number - 1)),
        ) + random.uniform(0, 0.25)

    async def _request(
        self,
        method: str,
        path_or_url: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: Any = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = self._build_url(path_or_url)
        last_response: httpx.Response | None = None
        last_exception: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            await asyncio.sleep(self._throttle_delay)
            await self._rate_limit(self._min_interval_sec)

            try:
                request_headers = headers or await self._auth_headers()
                response = await self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    headers=request_headers,
                )
                last_response = response

                if not self._should_retry_response(response):
                    if response.is_error:
                        logger.error(
                            "%s %s failed: %s %s",
                            method,
                            url,
                            response.status_code,
                            response.text,
                        )
                    return response

                logger.warning(
                    "%s %s retryable response on attempt %s: %s %s",
                    method,
                    url,
                    attempt,
                    response.status_code,
                    response.text,
                )

            except (
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.TransportError,
            ) as exc:
                last_exception = exc
                logger.warning(
                    "%s %s exception on attempt %s: %s",
                    method,
                    url,
                    attempt,
                    exc,
                )

            if attempt < self._max_retries:
                delay = self._backoff_delay(attempt)
                logger.info("Retrying %s %s in %.2fs", method, url, delay)
                await asyncio.sleep(delay)

        logger.error("%s %s failed after %s attempts", method, url, self._max_retries)

        if last_response is not None:
            return last_response

        raise last_exception or RuntimeError(f"{method} {url} failed with no response")

    async def get(
        self,
        path_or_url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        return await self._request("GET", path_or_url, params=params, headers=headers)

    async def post(
        self,
        path_or_url: str,
        *,
        json_data: Any,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        return await self._request(
            "POST", path_or_url, json_data=json_data, headers=headers
        )

    async def put(
        self,
        path_or_url: str,
        *,
        json_data: Any,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        return await self._request(
            "PUT", path_or_url, json_data=json_data, headers=headers
        )

    # ---------------------------------------------------------------------
    # Compatibility helpers / SOS-specific methods
    # ---------------------------------------------------------------------

    async def rate_limited_get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        return await self.get(url, params=params, headers=headers)

    async def rate_limited_post(
        self,
        url: str,
        data: Any,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        return await self.post(url, json_data=data, headers=headers)

    async def rate_limited_put(
        self,
        url: str,
        data: Any,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        return await self.put(url, json_data=data, headers=headers)

    async def sos_get_request(
        self,
        base_query_string: str = "",
        max_results: int = 100,
    ) -> httpx.Response:
        _ = max_results
        return await self.rate_limited_get(base_query_string)

    async def create_shipment(self, payload: dict[str, Any]) -> httpx.Response:
        return await self.rate_limited_post("/shipment", payload)

    async def make_update_request(
        self,
        url_segment: str,
        record_id: Any,
        record: dict[str, Any],
    ) -> httpx.Response:
        return await self.rate_limited_put(f"{url_segment}/{record_id}", record)

    async def fetch_sales_orders(
        self,
        *,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        response = await self.get("/salesorder", params=params)
        response.raise_for_status()

        data = self._extract_data(response)

        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            return [data]
        return []
