from __future__ import annotations

import asyncio
import logging
import random
import time
import httpx

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from src.integrations._base_client.client_auth import AuthStrategy, BasicAuth

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RetryConfig:
    max_attempts: int = 5
    base_delay_sec: float = 0.5
    max_delay_sec: float = 5.0
    jitter_sec: float = 0.25
    retry_statuses: frozenset[int] = field(
        default_factory=lambda: frozenset({408, 429, 500, 502, 503, 504})
    )
    unauthorized_statuses: frozenset[int] = field(
        default_factory=lambda: frozenset({401})
    )


class AsyncRateLimiter:
    """
    Simple process-local async rate limiter.

    This limits calls within this Python process/container only.
    Use Redis or another shared limiter if you run multiple containers.
    """

    def __init__(self, *, min_interval_sec: float) -> None:
        self.min_interval_sec = min_interval_sec
        self._lock = asyncio.Lock()
        self._last_call_ts = 0.0

    async def wait(self) -> None:
        if self.min_interval_sec <= 0:
            return

        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call_ts
            sleep_for = self.min_interval_sec - elapsed

            if sleep_for > 0:
                await asyncio.sleep(sleep_for)

            self._last_call_ts = time.monotonic()


class AuthenticatedHttpClient:
    """
    Shared async HTTP client.

    Handles:
      - GET / POST / PUT
      - pluggable auth strategy
      - process-local rate limiting
      - retry on configured statuses
      - one auth recovery attempt after unauthorized
    """

    THROTTLE_MESSAGE = "Throttle limit exceeded."

    def __init__(
        self,
        *,
        base_url: str,
        auth: AuthStrategy,
        base_headers: Mapping[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
        retry: RetryConfig | None = None,
        rate_limiter: AsyncRateLimiter | None = None,
    ) -> None:

        self.base_url = base_url.rstrip("/")
        self.auth = auth
        self.base_headers = dict(base_headers or {})
        self.retry = retry or RetryConfig()
        self.rate_limiter = rate_limiter or AsyncRateLimiter(min_interval_sec=0.0)

        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> AuthenticatedHttpClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def get(
        self,
        path_or_url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        return await self._request(
            "GET",
            path_or_url,
            params=params,
            headers=headers,
        )

    async def post(
        self,
        path_or_url: str,
        *,
        json_data: Any | None = None,
        data: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        return await self._request(
            "POST",
            path_or_url,
            json_data=json_data,
            data=data,
            params=params,
            headers=headers,
        )

    async def put(
        self,
        path_or_url: str,
        *,
        json_data: Any | None = None,
        data: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        return await self._request(
            "PUT",
            path_or_url,
            json_data=json_data,
            data=data,
            params=params,
            headers=headers,
        )

    async def _request(
        self,
        method: str,
        path_or_url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_data: Any | None = None,
        data: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        url = self._build_url(path_or_url)
        attempt = 0
        recovered_after_unauthorized = False

        while True:
            attempt += 1
            await self.rate_limiter.wait()

            try:
                response = await self.client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    data=data,
                    headers=await self._headers(headers),
                )
            except (
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.TransportError,
            ) as exc:
                if attempt >= self.retry.max_attempts:
                    logger.error(
                        "%s request failed after %s attempts due to transport error: %s",
                        method,
                        attempt,
                        exc,
                    )
                    raise

                await self._sleep_before_retry(method, attempt, exc=exc)
                continue

            if self._is_unauthorized(response) and not recovered_after_unauthorized:
                recovered_after_unauthorized = True

                if await self.auth.handle_unauthorized():
                    logger.info(
                        "Recovered from unauthorized response; retrying method=%s",
                        method,
                    )
                    continue

                return response

            if self._should_retry(response):
                if attempt >= self.retry.max_attempts:
                    logger.error(
                        "%s request returned retryable status=%s after %s attempts",
                        method,
                        response.status_code,
                        attempt,
                    )
                    return response

                await self._sleep_before_retry(method, attempt, response=response)
                continue

            return response

    async def _headers(
        self, extra_headers: Mapping[str, str] | None = None
    ) -> dict[str, str]:
        headers = dict(self.base_headers)
        headers.update(await self.auth.get_headers())

        if extra_headers:
            headers.update(extra_headers)

        return headers

    def _build_url(self, path_or_url: str) -> str:
        if path_or_url.startswith(("http://", "https://")):
            return path_or_url

        return f"{self.base_url}/{path_or_url.lstrip('/')}"

    def _is_unauthorized(self, response: httpx.Response) -> bool:
        return response.status_code in self.retry.unauthorized_statuses

    def _should_retry(self, response: httpx.Response) -> bool:
        if response.status_code in self.retry.retry_statuses:
            return True

        # Some APIs return HTTP 200 with an application-level throttle message.
        if (
            response.status_code == 200
            and self._json_message(response) == self.THROTTLE_MESSAGE
        ):
            return True

        return False

    async def _sleep_before_retry(
        self,
        method: str,
        attempt: int,
        *,
        response: httpx.Response | None = None,
        exc: Exception | None = None,
    ) -> None:
        delay = self._retry_delay(attempt, response=response)

        logger.warning(
            "%s request retrying attempt=%s/%s delay=%.2fs status=%s error=%r",
            method,
            attempt,
            self.retry.max_attempts,
            delay,
            response.status_code if response else None,
            exc,
        )

        await asyncio.sleep(delay)

    def _retry_delay(
        self,
        attempt: int,
        *,
        response: httpx.Response | None = None,
    ) -> float:
        retry_after = (
            self._retry_after_seconds(response) if response is not None else None
        )

        if retry_after is not None:
            return retry_after

        exponential = self.retry.base_delay_sec * (2 ** (attempt - 1))
        capped = min(self.retry.max_delay_sec, exponential)

        return capped + random.uniform(0, self.retry.jitter_sec)

    def _retry_after_seconds(self, response: httpx.Response) -> float | None:
        value = response.headers.get("Retry-After")

        if not value:
            return None

        try:
            return min(float(value), self.retry.max_delay_sec)
        except ValueError:
            return None

    @staticmethod
    def _json_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return ""

        if not isinstance(payload, dict):
            return ""

        message = payload.get("message", "")
        return message if isinstance(message, str) else ""


class BasicApiClient(AuthenticatedHttpClient):
    def __init__(
        self,
        *,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        base_headers: Mapping[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
        retry: RetryConfig | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url or "",
            auth=BasicAuth(
                username=username or "",
                password=password or "",
            ),
            base_headers=base_headers
            or {
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            client=client,
            timeout=timeout,
            retry=retry,
            rate_limiter=AsyncRateLimiter(min_interval_sec=0.501),
        )
