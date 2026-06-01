from __future__ import annotations

import base64
from typing import Protocol

from src.integrations._base_client.token_cache import TokenStore, token_store


class AuthStrategy(Protocol):
    async def get_headers(self) -> dict[str, str]: ...

    async def handle_unauthorized(self) -> bool: ...


class OAuthBearerAuth:
    """
    Bearer-token auth backed by TokenStore.

    Handles:
      - Authorization: Bearer <access_token>
      - refresh on 401 through token_store.force_refresh(...)
    """

    def __init__(
        self,
        *,
        provider: str,
        tokens: TokenStore = token_store,
    ) -> None:
        self.provider = provider
        self.tokens = tokens
        self._last_access_token: str | None = None

    async def get_headers(self) -> dict[str, str]:
        access_token = await self.tokens.get_valid_access_token(self.provider)
        self._last_access_token = access_token

        return {
            "Authorization": f"Bearer {access_token}",
        }

    async def handle_unauthorized(self) -> bool:
        refreshed = await self.tokens.force_refresh(
            self.provider,
            expected_access_token=self._last_access_token,
            allow_missing_current=True,
        )
        return refreshed is not None


class BasicAuth:
    """
    Basic auth strategy.

    Handles:
      - Authorization: Basic base64(username:password)

    Basic auth generally cannot auto-recover from 401, so
    handle_unauthorized returns False.
    """

    def __init__(
        self,
        *,
        username: str,
        password: str,
    ) -> None:
        self.username = username
        self.password = password

    async def get_headers(self) -> dict[str, str]:
        raw = f"{self.username}:{self.password}".encode("utf-8")
        encoded = base64.b64encode(raw).decode("ascii")

        return {
            "Authorization": f"Basic {encoded}",
        }

    async def handle_unauthorized(self) -> bool:
        return False


class NoAuth:
    """
    Optional no-auth strategy for endpoints that do not require auth.
    """

    async def get_headers(self) -> dict[str, str]:
        return {}

    async def handle_unauthorized(self) -> bool:
        return False
