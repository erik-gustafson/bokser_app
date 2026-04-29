from __future__ import annotations

import asyncio
import unittest
from datetime import timedelta
from typing import Any

from src.core.config import settings
from src.integrations.sos_inventory import auth


class _TokenRow:
    def __init__(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        expires_at,
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at


class SOSAuthTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._original_settings = {
            "sos_refresh_token": settings.sos_refresh_token,
            "sos_authorization_code": settings.sos_authorization_code,
            "sos_client_id": settings.sos_client_id,
            "sos_client_secret": settings.sos_client_secret,
            "sos_oauth_redirect_uri": settings.sos_oauth_redirect_uri,
            "sos_token_refresh_skew_seconds": settings.sos_token_refresh_skew_seconds,
        }
        self._original_load_auth_token = auth.load_auth_token
        self._original_upsert_auth_token = auth.upsert_auth_token
        self._original_db_retry_delay = auth._db_retry_delay

        settings.sos_refresh_token = ""
        settings.sos_authorization_code = ""
        settings.sos_client_id = "client-id"
        settings.sos_client_secret = "client-secret"
        settings.sos_oauth_redirect_uri = "https://localhost/callback"
        settings.sos_token_refresh_skew_seconds = 60

        async def _load_none(provider: str) -> Any:
            _ = provider
            return None

        async def _upsert_noop(**kwargs: Any) -> None:
            _ = kwargs
            return None

        auth.load_auth_token = _load_none  # type: ignore[assignment]
        auth.upsert_auth_token = _upsert_noop  # type: ignore[assignment]
        auth._db_retry_delay = lambda attempt: 0.0  # type: ignore[assignment]
        auth.invalidate_cached_token(drop_refresh_token=True)

    def tearDown(self) -> None:
        auth.invalidate_cached_token(drop_refresh_token=True)
        auth.load_auth_token = self._original_load_auth_token  # type: ignore[assignment]
        auth.upsert_auth_token = self._original_upsert_auth_token  # type: ignore[assignment]
        auth._db_retry_delay = self._original_db_retry_delay  # type: ignore[assignment]
        for key, value in self._original_settings.items():
            setattr(settings, key, value)

    async def test_cached_token_is_reused(self) -> None:
        auth._cached_access_token = "cached-token"  # type: ignore[attr-defined]
        auth._cached_expires_at = auth._now() + timedelta(minutes=10)  # type: ignore[attr-defined]

        async def _should_not_run(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("fetch/exchange should not run when token is cached")

        old_fetch = auth.fetch_sos_token
        old_exchange = auth.exchange_sos_token
        auth.fetch_sos_token = _should_not_run  # type: ignore[assignment]
        auth.exchange_sos_token = _should_not_run  # type: ignore[assignment]
        try:
            token = await auth.get_valid_token_async(auth.PROVIDER_SOS)
        finally:
            auth.fetch_sos_token = old_fetch  # type: ignore[assignment]
            auth.exchange_sos_token = old_exchange  # type: ignore[assignment]

        self.assertEqual(token, "cached-token")

    async def test_db_first_refresh_token_is_used_before_env(self) -> None:
        settings.sos_refresh_token = "env-refresh"
        calls = {"count": 0}

        async def _load_db_token(provider: str) -> Any:
            self.assertEqual(provider, auth.PROVIDER_SOS)
            return _TokenRow(
                access_token="expired-db-access",
                refresh_token="db-refresh",
                expires_at=auth._now() - timedelta(minutes=1),
            )

        async def _fetch(refresh_token: str | None) -> tuple[str, Any, dict[str, Any], str | None]:
            calls["count"] += 1
            self.assertEqual(refresh_token, "db-refresh")
            return "fresh-token", auth._now() + timedelta(minutes=30), {}, "next-refresh"

        old_load = auth.load_auth_token
        old_fetch = auth.fetch_sos_token
        auth.load_auth_token = _load_db_token  # type: ignore[assignment]
        auth.fetch_sos_token = _fetch  # type: ignore[assignment]
        try:
            token = await auth.get_valid_token_async(auth.PROVIDER_SOS)
        finally:
            auth.load_auth_token = old_load  # type: ignore[assignment]
            auth.fetch_sos_token = old_fetch  # type: ignore[assignment]

        self.assertEqual(token, "fresh-token")
        self.assertEqual(calls["count"], 1)

    async def test_refresh_path_used_when_refresh_token_available(self) -> None:
        settings.sos_refresh_token = "seed-refresh"
        calls = {"count": 0}

        async def _fetch(refresh_token: str | None) -> tuple[str, Any, dict[str, Any], str | None]:
            calls["count"] += 1
            self.assertEqual(refresh_token, "seed-refresh")
            return "fresh-token", auth._now() + timedelta(minutes=30), {}, "next-refresh"

        old_fetch = auth.fetch_sos_token
        auth.fetch_sos_token = _fetch  # type: ignore[assignment]
        try:
            token = await auth.get_valid_token_async(auth.PROVIDER_SOS)
        finally:
            auth.fetch_sos_token = old_fetch  # type: ignore[assignment]

        self.assertEqual(token, "fresh-token")
        self.assertEqual(calls["count"], 1)

    async def test_env_refresh_token_used_when_db_refresh_missing(self) -> None:
        settings.sos_refresh_token = "env-refresh"

        async def _load_db_token(provider: str) -> Any:
            self.assertEqual(provider, auth.PROVIDER_SOS)
            return _TokenRow(
                access_token="expired-db-access",
                refresh_token=None,
                expires_at=auth._now() - timedelta(minutes=1),
            )

        async def _fetch(refresh_token: str | None) -> tuple[str, Any, dict[str, Any], str | None]:
            self.assertEqual(refresh_token, "env-refresh")
            return "fresh-token", auth._now() + timedelta(minutes=30), {}, "next-refresh"

        old_load = auth.load_auth_token
        old_fetch = auth.fetch_sos_token
        auth.load_auth_token = _load_db_token  # type: ignore[assignment]
        auth.fetch_sos_token = _fetch  # type: ignore[assignment]
        try:
            token = await auth.get_valid_token_async(auth.PROVIDER_SOS)
        finally:
            auth.load_auth_token = old_load  # type: ignore[assignment]
            auth.fetch_sos_token = old_fetch  # type: ignore[assignment]

        self.assertEqual(token, "fresh-token")

    async def test_exchange_used_when_no_refresh_token(self) -> None:
        settings.sos_refresh_token = ""
        settings.sos_authorization_code = "auth-code"
        calls = {"exchange": 0}

        async def _exchange(code: str) -> tuple[str, Any, dict[str, Any], str | None]:
            calls["exchange"] += 1
            self.assertEqual(code, "auth-code")
            return (
                "exchange-token",
                auth._now() + timedelta(minutes=30),
                {},
                "refresh-from-exchange",
            )

        old_exchange = auth.exchange_sos_token
        auth.exchange_sos_token = _exchange  # type: ignore[assignment]
        try:
            token = await auth.get_valid_token_async(auth.PROVIDER_SOS)
        finally:
            auth.exchange_sos_token = old_exchange  # type: ignore[assignment]

        self.assertEqual(token, "exchange-token")
        self.assertEqual(calls["exchange"], 1)

    async def test_db_read_failure_falls_back_without_breaking_auth(self) -> None:
        settings.sos_refresh_token = "env-refresh"
        calls = {"fetch": 0}

        async def _load_raises(provider: str) -> Any:
            _ = provider
            raise RuntimeError("db unavailable")

        async def _fetch(refresh_token: str | None) -> tuple[str, Any, dict[str, Any], str | None]:
            calls["fetch"] += 1
            self.assertEqual(refresh_token, "env-refresh")
            return "fallback-token", auth._now() + timedelta(minutes=30), {}, "new-refresh"

        old_load = auth.load_auth_token
        old_fetch = auth.fetch_sos_token
        auth.load_auth_token = _load_raises  # type: ignore[assignment]
        auth.fetch_sos_token = _fetch  # type: ignore[assignment]
        try:
            token = await auth.get_valid_token_async(auth.PROVIDER_SOS)
        finally:
            auth.load_auth_token = old_load  # type: ignore[assignment]
            auth.fetch_sos_token = old_fetch  # type: ignore[assignment]

        self.assertEqual(token, "fallback-token")
        self.assertEqual(calls["fetch"], 1)

    async def test_upsert_on_refresh_success(self) -> None:
        settings.sos_refresh_token = "seed-refresh"
        writes: list[dict[str, Any]] = []

        async def _fetch(refresh_token: str | None) -> tuple[str, Any, dict[str, Any], str | None]:
            self.assertEqual(refresh_token, "seed-refresh")
            return (
                "persisted-access",
                auth._now() + timedelta(minutes=30),
                {"provider": auth.PROVIDER_SOS},
                "persisted-refresh",
            )

        async def _upsert(**kwargs: Any) -> None:
            writes.append(kwargs)

        old_fetch = auth.fetch_sos_token
        old_upsert = auth.upsert_auth_token
        auth.fetch_sos_token = _fetch  # type: ignore[assignment]
        auth.upsert_auth_token = _upsert  # type: ignore[assignment]
        try:
            token = await auth.get_valid_token_async(auth.PROVIDER_SOS)
        finally:
            auth.fetch_sos_token = old_fetch  # type: ignore[assignment]
            auth.upsert_auth_token = old_upsert  # type: ignore[assignment]

        self.assertEqual(token, "persisted-access")
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]["provider"], auth.PROVIDER_SOS)
        self.assertEqual(writes[0]["access_token"], "persisted-access")
        self.assertEqual(writes[0]["refresh_token"], "persisted-refresh")

    async def test_db_write_retries_then_continues_in_memory(self) -> None:
        settings.sos_refresh_token = "seed-refresh"
        attempts = {"count": 0}

        async def _fetch(refresh_token: str | None) -> tuple[str, Any, dict[str, Any], str | None]:
            self.assertEqual(refresh_token, "seed-refresh")
            return "fresh-token", auth._now() + timedelta(minutes=30), {}, "next-refresh"

        async def _upsert(**kwargs: Any) -> None:
            _ = kwargs
            attempts["count"] += 1
            raise RuntimeError("write failed")

        old_fetch = auth.fetch_sos_token
        old_upsert = auth.upsert_auth_token
        auth.fetch_sos_token = _fetch  # type: ignore[assignment]
        auth.upsert_auth_token = _upsert  # type: ignore[assignment]
        try:
            token = await auth.get_valid_token_async(auth.PROVIDER_SOS)
        finally:
            auth.fetch_sos_token = old_fetch  # type: ignore[assignment]
            auth.upsert_auth_token = old_upsert  # type: ignore[assignment]

        self.assertEqual(token, "fresh-token")
        self.assertEqual(attempts["count"], 3)

    async def test_exchange_fallback_when_refresh_fails(self) -> None:
        settings.sos_refresh_token = "seed-refresh"
        settings.sos_authorization_code = "auth-code"

        async def _fetch(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("refresh failed")

        async def _exchange(code: str) -> tuple[str, Any, dict[str, Any], str | None]:
            self.assertEqual(code, "auth-code")
            return "fallback-token", auth._now() + timedelta(minutes=30), {}, "new-refresh"

        old_fetch = auth.fetch_sos_token
        old_exchange = auth.exchange_sos_token
        auth.fetch_sos_token = _fetch  # type: ignore[assignment]
        auth.exchange_sos_token = _exchange  # type: ignore[assignment]
        try:
            token = await auth.get_valid_token_async(auth.PROVIDER_SOS)
        finally:
            auth.fetch_sos_token = old_fetch  # type: ignore[assignment]
            auth.exchange_sos_token = old_exchange  # type: ignore[assignment]

        self.assertEqual(token, "fallback-token")

    async def test_concurrent_calls_refresh_once(self) -> None:
        settings.sos_refresh_token = "seed-refresh"
        calls = {"count": 0}

        async def _fetch(refresh_token: str | None) -> tuple[str, Any, dict[str, Any], str | None]:
            calls["count"] += 1
            await asyncio.sleep(0.05)
            return "shared-token", auth._now() + timedelta(minutes=30), {}, refresh_token

        old_fetch = auth.fetch_sos_token
        auth.fetch_sos_token = _fetch  # type: ignore[assignment]
        try:
            results = await asyncio.gather(
                auth.get_valid_token_async(auth.PROVIDER_SOS),
                auth.get_valid_token_async(auth.PROVIDER_SOS),
                auth.get_valid_token_async(auth.PROVIDER_SOS),
            )
        finally:
            auth.fetch_sos_token = old_fetch  # type: ignore[assignment]

        self.assertEqual(results, ["shared-token", "shared-token", "shared-token"])
        self.assertEqual(calls["count"], 1)

    async def test_missing_refresh_and_auth_code_fails(self) -> None:
        settings.sos_refresh_token = ""
        settings.sos_authorization_code = ""
        with self.assertRaises(RuntimeError):
            await auth.get_valid_token_async(auth.PROVIDER_SOS)
