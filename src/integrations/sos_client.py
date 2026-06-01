from __future__ import annotations

from collections.abc import Mapping

import httpx

from src.core.config import settings
from src.integrations._base_client.client_auth import OAuthBearerAuth
from src.integrations._base_client.base_client import (
    AsyncRateLimiter,
    AuthenticatedHttpClient,
    RetryConfig,
)
from src.integrations._base_client.token_cache import (
    PROVIDER_SOS,
)


class SOSClient(AuthenticatedHttpClient):
    def __init__(
        self,
        *,
        base_url: str | None = None,
        base_headers: Mapping[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
        retry: RetryConfig | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url or settings.sos_api_url,
            auth=OAuthBearerAuth(provider=PROVIDER_SOS),
            base_headers=base_headers
            or {
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            client=client,
            timeout=timeout,
            retry=retry,
            rate_limiter=AsyncRateLimiter(min_interval_sec=settings.sos_rate_limiter),
        )
