from __future__ import annotations

import unittest

import httpx

from src.integrations.sos_inventory import client as client_module
from src.integrations.sos_inventory.client import SOSAsyncAuth


class SOSAuthFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_401_triggers_forced_refresh_once(self) -> None:
        calls = {"token": 0, "forced_refresh": 0, "invalidations": 0}

        async def _token_provider(provider: str, force_refresh: bool = False) -> str:
            _ = provider
            calls["token"] += 1
            if force_refresh:
                calls["forced_refresh"] += 1
                return "fresh-token"
            return "cached-token"

        def _invalidate(provider: str, drop_refresh_token: bool = False) -> None:
            _ = provider
            _ = drop_refresh_token
            calls["invalidations"] += 1

        auth = SOSAsyncAuth(
            provider="sos_inventory",
            auth_header_name="Authorization",
            auth_header_prefix="Bearer",
            token_url="https://api.sosinventory.com/oauth2/token",
        )

        request = httpx.Request("GET", "https://api.example.com/salesorder")
        old_get = client_module.get_valid_token_async
        old_invalidate = client_module.invalidate_cached_token
        client_module.get_valid_token_async = _token_provider  # type: ignore[assignment]
        client_module.invalidate_cached_token = _invalidate  # type: ignore[assignment]
        try:
            flow = auth.async_auth_flow(request)
            first_request = await flow.__anext__()
            self.assertEqual(first_request.headers["Authorization"], "Bearer cached-token")

            retry_request = await flow.asend(
                httpx.Response(status_code=401, request=first_request, json={"message": "unauthorized"})
            )
            self.assertEqual(retry_request.headers["Authorization"], "Bearer fresh-token")

            with self.assertRaises(StopAsyncIteration):
                await flow.asend(httpx.Response(status_code=200, request=retry_request, json={"data": []}))
        finally:
            client_module.get_valid_token_async = old_get  # type: ignore[assignment]
            client_module.invalidate_cached_token = old_invalidate  # type: ignore[assignment]

        self.assertEqual(calls["invalidations"], 1)
        self.assertEqual(calls["forced_refresh"], 1)

    async def test_repeated_401_does_not_loop_forever(self) -> None:
        calls = {"forced_refresh": 0}

        async def _token_provider(provider: str, force_refresh: bool = False) -> str:
            _ = provider
            if force_refresh:
                calls["forced_refresh"] += 1
                return "fresh-token"
            return "cached-token"

        auth = SOSAsyncAuth(
            provider="sos_inventory",
            token_url="https://api.sosinventory.com/oauth2/token",
        )

        old_get = client_module.get_valid_token_async
        old_invalidate = client_module.invalidate_cached_token
        client_module.get_valid_token_async = _token_provider  # type: ignore[assignment]
        client_module.invalidate_cached_token = lambda *args, **kwargs: None  # type: ignore[assignment]
        try:
            request = httpx.Request("GET", "https://api.example.com/salesorder")
            flow = auth.async_auth_flow(request)
            first_request = await flow.__anext__()
            retry_request = await flow.asend(
                httpx.Response(status_code=401, request=first_request, json={"message": "unauthorized"})
            )
            with self.assertRaises(StopAsyncIteration):
                await flow.asend(
                    httpx.Response(status_code=401, request=retry_request, json={"message": "still unauthorized"})
                )
        finally:
            client_module.get_valid_token_async = old_get  # type: ignore[assignment]
            client_module.invalidate_cached_token = old_invalidate  # type: ignore[assignment]

        self.assertEqual(calls["forced_refresh"], 1)
