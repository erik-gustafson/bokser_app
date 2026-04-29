from __future__ import annotations

from collections.abc import Mapping

import httpx

from src.integrations._client_settings.auth_strategies import BasicAuth
from src.integrations._client_settings.base_client import (
    AsyncRateLimiter,
    AuthenticatedHttpClient,
    RetryConfig,
)


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
