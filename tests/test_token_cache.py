from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.config import settings
from src.integrations._client_settings import token_cache
from src.integrations._client_settings.token_cache import (
    ALL_PROVIDERS,
    PROVIDER_ACENDA,
    PROVIDER_PRODUCTIV,
    PROVIDER_SOS,
    TokenRecord,
    TokenStore,
    refresh_provider_token,
)


class _InMemoryRefreshTokenStore(TokenStore):
    def __init__(self) -> None:
        super().__init__()
        self.refresh_calls = 0

    async def _refresh_with_cross_container_lock(
        self,
        provider_key: str,
        *,
        expected_access_token: str | None,
        allow_missing_current: bool,
        skew_seconds: int,
    ) -> TokenRecord | None:
        _ = expected_access_token
        _ = allow_missing_current
        _ = skew_seconds

        self.refresh_calls += 1
        await asyncio.sleep(0.02)

        return await self.set(
            provider_key,
            access_token=f"fresh-token-{self.refresh_calls}",
            refresh_token="next-refresh",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            persist=False,
        )


class TokenStoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._settings_backup = {
            "token_warmup_strict": settings.token_warmup_strict,
            "token_refresh_skew_seconds": settings.token_refresh_skew_seconds,
            "sos_authorization_code": settings.sos_authorization_code,
            "sos_client_id": settings.sos_client_id,
            "sos_client_secret": settings.sos_client_secret,
            "sos_oauth_redirect_uri": settings.sos_oauth_redirect_uri,
            "productiv_auth_key": settings.productiv_auth_key,
            "productiv_auth_user": settings.productiv_auth_user,
            "acenda_client_id": settings.acenda_client_id,
            "acenda_client_secret": settings.acenda_client_secret,
            "acenda_token_url": settings.acenda_token_url,
            "productiv_token_url": settings.productiv_token_url,
        }

        settings.token_warmup_strict = True
        settings.token_refresh_skew_seconds = 60

    def tearDown(self) -> None:
        for key, value in self._settings_backup.items():
            setattr(settings, key, value)

    async def test_warmup_loads_valid_db_tokens_without_refresh(self) -> None:
        store = TokenStore()
        original_get = token_cache.get_auth_token_from_db

        async def _get(provider: str, *, session: Any | None = None) -> TokenRecord | None:
            _ = session
            return TokenRecord(
                provider=provider,
                access_token=f"db-token-{provider}",
                refresh_token="db-refresh",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            )

        async def _force_refresh(*args: Any, **kwargs: Any) -> Any:
            _ = args
            _ = kwargs
            raise AssertionError("force_refresh should not run when DB token is valid")

        token_cache.get_auth_token_from_db = _get  # type: ignore[assignment]
        original_force_refresh = store.force_refresh
        store.force_refresh = _force_refresh  # type: ignore[assignment]

        try:
            await store.warmup_on_startup(strict=True)
            for provider in ALL_PROVIDERS:
                cached = await store.get(provider, load_from_db=False)
                self.assertIsNotNone(cached)
                self.assertEqual(cached.access_token, f"db-token-{provider}")
        finally:
            token_cache.get_auth_token_from_db = original_get  # type: ignore[assignment]
            store.force_refresh = original_force_refresh  # type: ignore[assignment]

    async def test_warmup_refreshes_only_expired_provider(self) -> None:
        store = TokenStore()
        now = datetime.now(timezone.utc)
        original_get = token_cache.get_auth_token_from_db

        async def _get(provider: str, *, session: Any | None = None) -> TokenRecord | None:
            _ = session
            if provider == PROVIDER_SOS:
                return TokenRecord(
                    provider=provider,
                    access_token="expired-sos",
                    refresh_token="refresh-sos",
                    expires_at=now - timedelta(minutes=1),
                )

            return TokenRecord(
                provider=provider,
                access_token=f"valid-{provider}",
                refresh_token="refresh",
                expires_at=now + timedelta(minutes=20),
            )

        calls: list[str] = []

        async def _force_refresh(
            provider: str,
            *,
            expected_access_token: str | None = None,
            allow_missing_current: bool = False,
            skew_seconds: int | None = None,
        ) -> TokenRecord | None:
            _ = expected_access_token
            _ = allow_missing_current
            _ = skew_seconds
            calls.append(provider)
            return await store.set(
                provider,
                access_token="fresh-sos",
                refresh_token="next-refresh",
                expires_at=now + timedelta(minutes=30),
                persist=False,
            )

        token_cache.get_auth_token_from_db = _get  # type: ignore[assignment]
        original_force_refresh = store.force_refresh
        store.force_refresh = _force_refresh  # type: ignore[assignment]

        try:
            await store.warmup_on_startup(strict=True)
        finally:
            token_cache.get_auth_token_from_db = original_get  # type: ignore[assignment]
            store.force_refresh = original_force_refresh  # type: ignore[assignment]

        self.assertEqual(calls, [PROVIDER_SOS])

    async def test_concurrent_get_valid_access_token_refreshes_once(self) -> None:
        store = _InMemoryRefreshTokenStore()
        await store.set(
            PROVIDER_SOS,
            access_token="expired-token",
            refresh_token="refresh-token",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            persist=False,
        )

        results = await asyncio.gather(
            *[store.get_valid_access_token(PROVIDER_SOS) for _ in range(20)]
        )

        self.assertEqual(store.refresh_calls, 1)
        self.assertTrue(all(result == "fresh-token-1" for result in results))

    async def test_concurrent_force_refresh_after_401_refreshes_once(self) -> None:
        store = _InMemoryRefreshTokenStore()
        await store.set(
            PROVIDER_SOS,
            access_token="token-that-got-401",
            refresh_token="refresh-token",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            persist=False,
        )

        records = await asyncio.gather(
            *[
                store.force_refresh(
                    PROVIDER_SOS,
                    expected_access_token="token-that-got-401",
                    allow_missing_current=True,
                )
                for _ in range(20)
            ]
        )

        self.assertEqual(store.refresh_calls, 1)
        self.assertTrue(all(record is not None for record in records))
        self.assertTrue(
            all(record.access_token == "fresh-token-1" for record in records if record)
        )

    async def test_sos_refresh_falls_back_to_authorization_code(self) -> None:
        settings.sos_authorization_code = "auth-code"
        settings.sos_client_id = "client-id"
        settings.sos_client_secret = "client-secret"
        settings.sos_oauth_redirect_uri = "https://example.com/callback"

        original_post = token_cache._post_for_token
        grant_types: list[str] = []

        async def _post_for_token(
            *,
            provider: str,
            token_url: str,
            headers: dict[str, str],
            data: dict[str, Any] | None,
            json_data: dict[str, Any] | None,
        ) -> dict[str, Any] | None:
            _ = provider
            _ = token_url
            _ = headers
            _ = json_data
            grant_types.append(str(data.get("grant_type")) if data else "")

            if data and data.get("grant_type") == "refresh_token":
                return None

            return {
                "access_token": "fallback-access-token",
                "refresh_token": "fallback-refresh-token",
                "expires_in": 1800,
            }

        token_cache._post_for_token = _post_for_token  # type: ignore[assignment]
        try:
            refreshed = await refresh_provider_token(
                provider=PROVIDER_SOS,
                current=TokenRecord(
                    provider=PROVIDER_SOS,
                    access_token="old",
                    refresh_token="broken-refresh",
                    expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                ),
            )
        finally:
            token_cache._post_for_token = original_post  # type: ignore[assignment]

        self.assertIsNotNone(refreshed)
        self.assertEqual(grant_types, ["refresh_token", "authorization_code"])
        self.assertEqual(refreshed.access_token, "fallback-access-token")

    async def test_productiv_refresh_contract_shape(self) -> None:
        settings.productiv_auth_key = "Basic test-key"
        settings.productiv_auth_user = "cw+bhapi@getproductiv.com"
        settings.productiv_token_url = "https://secure-wms.com/AuthServer/api/Token"

        original_post = token_cache._post_for_token
        observed: dict[str, Any] = {}

        async def _post_for_token(**kwargs: Any) -> dict[str, Any] | None:
            observed.update(kwargs)
            return {
                "access_token": "productiv-token",
                "expires_in": 3600,
            }

        token_cache._post_for_token = _post_for_token  # type: ignore[assignment]
        try:
            refreshed = await refresh_provider_token(
                provider=PROVIDER_PRODUCTIV,
                current=None,
            )
        finally:
            token_cache._post_for_token = original_post  # type: ignore[assignment]

        self.assertIsNotNone(refreshed)
        self.assertEqual(observed["token_url"], settings.productiv_token_url)
        self.assertEqual(observed["json_data"]["grant_type"], "client_credentials")
        self.assertEqual(
            observed["json_data"]["user_login"],
            settings.productiv_auth_user,
        )
        self.assertEqual(observed["headers"]["Authorization"], settings.productiv_auth_key)
        self.assertIsNone(observed["data"])

    async def test_acenda_refresh_contract_shape(self) -> None:
        settings.acenda_client_id = "acenda-client-id"
        settings.acenda_client_secret = "acenda-client-secret"
        settings.acenda_token_url = "https://acenda.example/token"

        original_post = token_cache._post_for_token
        observed: dict[str, Any] = {}

        async def _post_for_token(**kwargs: Any) -> dict[str, Any] | None:
            observed.update(kwargs)
            return {
                "access_token": "acenda-token",
                "expires_in": 300,
            }

        token_cache._post_for_token = _post_for_token  # type: ignore[assignment]
        try:
            refreshed = await refresh_provider_token(
                provider=PROVIDER_ACENDA,
                current=None,
            )
        finally:
            token_cache._post_for_token = original_post  # type: ignore[assignment]

        self.assertIsNotNone(refreshed)
        self.assertEqual(observed["token_url"], settings.acenda_token_url)
        self.assertEqual(observed["data"]["grant_type"], "client_credentials")
        self.assertEqual(observed["data"]["client_id"], settings.acenda_client_id)
        self.assertEqual(
            observed["data"]["client_secret"],
            settings.acenda_client_secret,
        )
        self.assertIsNone(observed["json_data"])


if __name__ == "__main__":
    unittest.main()
