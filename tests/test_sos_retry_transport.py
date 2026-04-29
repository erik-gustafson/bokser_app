from __future__ import annotations

import unittest
from typing import Any, Callable

import httpx

from src.integrations.sos_inventory.client import SOSRetryingAsyncTransport, THROTTLE_MESSAGE


class _QueuedTransport(httpx.AsyncBaseTransport):
    def __init__(self, outputs: list[Callable[[httpx.Request], httpx.Response] | Exception]) -> None:
        self._outputs = outputs
        self.calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        idx = min(self.calls, len(self._outputs) - 1)
        self.calls += 1
        output = self._outputs[idx]
        if isinstance(output, Exception):
            raise output
        return output(request)

    async def aclose(self) -> None:
        return None


def _response(status_code: int, *, payload: dict[str, Any] | None = None) -> Callable[[httpx.Request], httpx.Response]:
    def _factory(request: httpx.Request) -> httpx.Response:
        kwargs: dict[str, Any] = {}
        if payload is not None:
            kwargs["json"] = payload
        return httpx.Response(status_code=status_code, request=request, **kwargs)

    return _factory


class SOSRetryTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_on_retryable_status(self) -> None:
        inner = _QueuedTransport(
            [
                _response(500, payload={"message": "server error"}),
                _response(200, payload={"data": []}),
            ]
        )
        transport = SOSRetryingAsyncTransport(
            transport=inner,
            max_retries=3,
            base_delay=0.0,
            max_delay=0.0,
            throttle_delay=0.0,
            min_interval_sec=0.0,
        )
        request = httpx.Request("GET", "https://api.example.com/salesorder")

        response = await transport.handle_async_request(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(inner.calls, 2)
        await transport.aclose()

    async def test_retries_on_throttle_message(self) -> None:
        inner = _QueuedTransport(
            [
                _response(200, payload={"message": THROTTLE_MESSAGE}),
                _response(200, payload={"data": []}),
            ]
        )
        transport = SOSRetryingAsyncTransport(
            transport=inner,
            max_retries=3,
            base_delay=0.0,
            max_delay=0.0,
            throttle_delay=0.0,
            min_interval_sec=0.0,
        )
        request = httpx.Request("GET", "https://api.example.com/salesorder")

        response = await transport.handle_async_request(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(inner.calls, 2)
        await transport.aclose()

    async def test_retries_on_transport_error(self) -> None:
        inner = _QueuedTransport(
            [
                httpx.ReadTimeout("timed out"),
                _response(200, payload={"data": []}),
            ]
        )
        transport = SOSRetryingAsyncTransport(
            transport=inner,
            max_retries=3,
            base_delay=0.0,
            max_delay=0.0,
            throttle_delay=0.0,
            min_interval_sec=0.0,
        )
        request = httpx.Request("GET", "https://api.example.com/salesorder")

        response = await transport.handle_async_request(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(inner.calls, 2)
        await transport.aclose()

    async def test_returns_last_response_after_retries_exhausted(self) -> None:
        inner = _QueuedTransport(
            [
                _response(500, payload={"message": "server error"}),
                _response(500, payload={"message": "server error"}),
                _response(500, payload={"message": "server error"}),
            ]
        )
        transport = SOSRetryingAsyncTransport(
            transport=inner,
            max_retries=3,
            base_delay=0.0,
            max_delay=0.0,
            throttle_delay=0.0,
            min_interval_sec=0.0,
        )
        request = httpx.Request("GET", "https://api.example.com/salesorder")

        response = await transport.handle_async_request(request)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(inner.calls, 3)
        await transport.aclose()
