from __future__ import annotations

import unittest
from typing import Any

import httpx

from src.core.configs.sos import SOSEndpoint
from src.worker.jobs.get_data.get_sos_data import GetSosData


class _RecordingSOSClient:
    def __init__(self, *, total_count: int = 1) -> None:
        self.total_count = total_count
        self.calls: list[dict[str, Any]] = []

    async def get(
        self,
        *,
        path_or_url: str,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        request_params = dict(params or {})
        self.calls.append(request_params)
        request = httpx.Request("GET", f"https://example.test{path_or_url}")
        payload = {
            "data": [{"path": path_or_url, "params": request_params}],
            "totalCount": self.total_count,
        }
        return httpx.Response(status_code=200, request=request, json=payload)

    async def aclose(self) -> None:
        pass


class SOSQueryTimestampTests(unittest.IsolatedAsyncioTestCase):
    endpoint = SOSEndpoint(
        name="updated_items",
        path="/item",
    )

    async def test_naive_watermark_is_sent_as_explicit_utc(self) -> None:
        client = _RecordingSOSClient()
        getter = GetSosData(sos_client=client)  # type: ignore[arg-type]
        endpoint_params = {
            "updatedsince": "2026-08-11T17:00:00",
            "status": "open",
        }

        records = await getter._get_raw_sos_data_with_open_client(
            endpoint=self.endpoint,
            endpoint_params=endpoint_params,
            max_results=200,
            archived="no",
            max_concurrency=1,
        )

        self.assertEqual(client.calls[0]["updatedsince"], "2026-08-11T17:00:00Z")
        self.assertEqual(client.calls[0]["status"], "open")
        self.assertEqual(records[0]["params"], client.calls[0])
        self.assertEqual(endpoint_params["updatedsince"], "2026-08-11T17:00:00")

    async def test_aware_watermark_is_converted_to_utc(self) -> None:
        client = _RecordingSOSClient()
        getter = GetSosData(sos_client=client)  # type: ignore[arg-type]

        await getter._get_raw_sos_data_with_open_client(
            endpoint=self.endpoint,
            endpoint_params={"createdsince": "2026-08-11T12:00:00-05:00"},
            max_results=200,
            archived="no",
            max_concurrency=1,
        )

        self.assertEqual(client.calls[0]["createdsince"], "2026-08-11T17:00:00Z")

    async def test_normalized_timestamp_is_reused_for_paginated_requests(self) -> None:
        client = _RecordingSOSClient(total_count=3)
        getter = GetSosData(sos_client=client)  # type: ignore[arg-type]

        await getter._get_raw_sos_data_with_open_client(
            endpoint=self.endpoint,
            endpoint_params={"from": "2026-08-11T17:00:00", "status": "open"},
            max_results=2,
            archived="no",
            max_concurrency=1,
        )

        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[0]["from"], "2026-08-11T17:00:00Z")
        self.assertEqual(client.calls[1]["from"], "2026-08-11T17:00:00Z")
        self.assertEqual(client.calls[1]["status"], "open")
        self.assertEqual(client.calls[1]["start"], 3)


if __name__ == "__main__":
    unittest.main()
