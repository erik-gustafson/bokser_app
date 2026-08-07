from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.worker.jobs.get_data.base_get import (
    EndpointFetchResult,
    sync_endpoints_job,
)


class _TargetSource:
    source_name = "sos_inventory"
    state_file = Path("sos_query_state.json")

    def __init__(self, results: list[EndpointFetchResult]) -> None:
        self.results = results
        self.update_state_file = AsyncMock()

    async def __aenter__(self) -> _TargetSource:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def iter_endpoint_data(self, *, max_concurrency: int):
        for result in self.results:
            yield result


class SyncEndpointsJobTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_success_advances_state_without_writing_file(self) -> None:
        endpoint = SimpleNamespace(name="updated_items")
        target = _TargetSource(
            [EndpointFetchResult(endpoint=endpoint, records=[])]
        )
        raw_writer = MagicMock()

        await sync_endpoints_job(
            target_source_factory=lambda: target,
            raw_writer=raw_writer,
        )

        raw_writer.write_json_payload.assert_not_called()
        target.update_state_file.assert_awaited_once_with(
            state_type="updated_items",
            records=[],
        )

    async def test_failed_fetch_does_not_advance_state(self) -> None:
        endpoint = SimpleNamespace(name="updated_items")
        target = _TargetSource(
            [
                EndpointFetchResult(
                    endpoint=endpoint,
                    error=RuntimeError("SOS request failed"),
                )
            ]
        )
        raw_writer = MagicMock()

        await sync_endpoints_job(
            target_source_factory=lambda: target,
            raw_writer=raw_writer,
        )

        raw_writer.write_json_payload.assert_not_called()
        target.update_state_file.assert_not_awaited()

    async def test_failed_write_does_not_advance_state(self) -> None:
        endpoint = SimpleNamespace(name="updated_items")
        target = _TargetSource(
            [EndpointFetchResult(endpoint=endpoint, records=[{"id": 1}])]
        )
        raw_writer = MagicMock()
        raw_writer.write_json_payload.side_effect = RuntimeError(
            "lake write failed"
        )

        with self.assertRaisesRegex(RuntimeError, "lake write failed"):
            await sync_endpoints_job(
                target_source_factory=lambda: target,
                raw_writer=raw_writer,
            )

        target.update_state_file.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
