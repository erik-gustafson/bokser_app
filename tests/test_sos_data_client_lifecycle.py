from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any

import httpx

from src.core.config import settings
from src.core.configs.sos import SOSEndpoint
from src.worker.jobs.get_data import sos_data as sos_data_module
from src.worker.jobs.get_data.sos_data import GetSosData, sync_sos_endpoints_job


class _FakeSOSClient:
    def __init__(self) -> None:
        self.closed = False
        self.aclose_calls = 0
        self.get_calls = 0

    async def get(
        self,
        *,
        path_or_url: str,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        if self.closed:
            raise RuntimeError("Cannot send a request, as the client has been closed.")

        self.get_calls += 1
        request = httpx.Request("GET", f"https://example.test{path_or_url}")
        payload = {"data": [{"path": path_or_url, "params": params or {}}], "totalCount": 1}
        return httpx.Response(status_code=200, request=request, json=payload)

    async def aclose(self) -> None:
        self.closed = True
        self.aclose_calls += 1


class _FakeWriter:
    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.calls = 0
        self.fail_on_call = fail_on_call
        self.entities: list[str] = []

    def write_json_payload(
        self,
        *,
        source_system: str,
        entity_name: str,
        payload: list[dict[str, Any]],
    ) -> SimpleNamespace:
        _ = source_system
        _ = payload
        self.calls += 1
        self.entities.append(entity_name)

        if self.fail_on_call is not None and self.calls == self.fail_on_call:
            raise RuntimeError("writer failed")

        return SimpleNamespace(record_count=1, file_path=f"/tmp/{entity_name}.json")


class SOSDataClientLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._settings_cls = type(settings)
        self._original_enabled_endpoints = self._settings_cls.sos_enabled_endpoints
        self._original_sos_client_cls = sos_data_module.SOSClient
        self.endpoints = (
            SOSEndpoint(name="sales_orders", path="/salesorder", entity_name="sales_order"),
            SOSEndpoint(name="invoices", path="/invoice", entity_name="invoice"),
            SOSEndpoint(name="shipments", path="/shipment", entity_name="shipment"),
        )
        self._settings_cls.sos_enabled_endpoints = classmethod(  # type: ignore[assignment]
            lambda cls: self.endpoints
        )

    def tearDown(self) -> None:
        self._settings_cls.sos_enabled_endpoints = self._original_enabled_endpoints  # type: ignore[assignment]
        sos_data_module.SOSClient = self._original_sos_client_cls  # type: ignore[assignment]

    async def test_sync_uses_single_owned_client_lifecycle(self) -> None:
        created: list[_FakeSOSClient] = []

        def _fake_client_factory() -> _FakeSOSClient:
            client = _FakeSOSClient()
            created.append(client)
            return client

        sos_data_module.SOSClient = _fake_client_factory  # type: ignore[assignment]
        sos_data = GetSosData()
        writer = _FakeWriter()

        await sync_sos_endpoints_job(
            sos_data=sos_data,
            raw_writer=writer,  # type: ignore[arg-type]
            max_concurrency=3,
        )

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].aclose_calls, 1)
        self.assertEqual(writer.calls, len(self.endpoints))

    async def test_sync_closes_owned_client_on_exception(self) -> None:
        created: list[_FakeSOSClient] = []

        def _fake_client_factory() -> _FakeSOSClient:
            client = _FakeSOSClient()
            created.append(client)
            return client

        sos_data_module.SOSClient = _fake_client_factory  # type: ignore[assignment]
        sos_data = GetSosData()
        writer = _FakeWriter(fail_on_call=1)

        with self.assertRaises(RuntimeError):
            await sync_sos_endpoints_job(
                sos_data=sos_data,
                raw_writer=writer,  # type: ignore[arg-type]
                max_concurrency=3,
            )

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].aclose_calls, 1)

    async def test_sync_does_not_close_injected_external_client(self) -> None:
        external_client = _FakeSOSClient()
        sos_data = GetSosData(sos_client=external_client)  # type: ignore[arg-type]
        writer = _FakeWriter()

        await sync_sos_endpoints_job(
            sos_data=sos_data,
            raw_writer=writer,  # type: ignore[arg-type]
            max_concurrency=3,
        )

        self.assertEqual(external_client.aclose_calls, 0)
        self.assertFalse(external_client.closed)
        self.assertEqual(writer.calls, len(self.endpoints))
