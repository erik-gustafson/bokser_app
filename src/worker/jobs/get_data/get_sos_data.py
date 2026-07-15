from __future__ import annotations

import asyncio
import logging

from typing import Any
from pathlib import Path
from datetime import date, datetime, timezone
from collections.abc import AsyncIterator

from src.core.config import settings
from src.core.configs.sos import SOSEndpoint
from src.integrations.sos_client import SOSClient
from src.storage.states.state_store import sos_state
from src.worker.jobs.get_data.base_get import EndpointFetchResult

logger = logging.getLogger(__name__)


class GetSosData:
    """
    Service to get data from SOS Inventory API.
    Requests include Sales Orders, Items, Invoices, Shipments, Payments,
    Purchase Orders, and Item Receipts.
    """

    def __init__(self, *, sos_client: SOSClient | None = None) -> None:
        self.source_name: str = "sos_inventory"
        self.sos_client = sos_client or SOSClient()
        self._owns_sos_client = sos_client is None
        self._open_depth = 0
        self.run_started_at = settings.sos_timestamp_format(None)
        self.state_file: Path = (
            settings.lake_root
            / "raw"
            / "sos_inventory"
            / "_state"
            / "sos_query_state.json"
        )

    async def open(self) -> None:
        self._open_depth += 1

    async def close(self) -> None:
        if self._open_depth <= 0:
            return

        self._open_depth -= 1
        if self._open_depth == 0 and self._owns_sos_client:
            await self.sos_client.aclose()

    async def __aenter__(self) -> "GetSosData":
        await self.open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def get_raw_sos_data(
        self,
        *,
        endpoint: SOSEndpoint,
        max_results: int = 200,
        archived: str = "no",
        max_concurrency: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Paginated GET using SOS params: maxresults/start and any other filters.
        """
        should_open = self._open_depth == 0

        if should_open:
            await self.open()

        try:
            endpoint_params = settings.get_sos_endpoint_params(
                file_path=self.state_file, endpoint=endpoint
            )
            return await self._get_raw_sos_data_with_open_client(
                endpoint=endpoint,
                endpoint_params=endpoint_params,
                max_results=max_results,
                archived=archived,
                max_concurrency=max_concurrency,
            )
        finally:
            if should_open:
                await self.close()

    async def _get_raw_sos_data_with_open_client(
        self,
        *,
        endpoint: SOSEndpoint,
        endpoint_params: dict,
        max_results: int,
        archived: str,
        max_concurrency: int,
    ) -> list[dict[str, Any]]:
        path = endpoint.path

        base_params = {
            **endpoint_params,
            "maxresults": max_results,
            "archived": archived,
        }

        client = self.sos_client

        first_response = await client.get(
            path_or_url=path,
            params=base_params,
        )

        first_response.raise_for_status()

        first_payload = first_response.json()

        records = self._extract_records(
            first_payload,
            context=f"path={path} page=1",
        )

        total_count = int(first_payload.get("totalCount")) or 0

        if total_count <= len(records):
            return records

        total_pages = (total_count + max_results - 1) // max_results
        semaphore = asyncio.Semaphore(max_concurrency)

        async def fetch_page(page_idx: int) -> list[dict[str, Any]]:
            async with semaphore:
                start_cursor = (max_results * page_idx) + 1
                page_params = {**base_params, "start": start_cursor}

                response = await client.get(path_or_url=path, params=page_params)
                response.raise_for_status()
                page_records = self._extract_records(
                    response.json(),
                    context=f"path={path} page={page_idx}",
                )
                return page_records

        tasks = [
            asyncio.create_task(fetch_page(page_idx))
            for page_idx in range(1, total_pages)
        ]

        for task in asyncio.as_completed(tasks):
            try:
                records.extend(await task)
            except Exception:
                logger.exception("Error fetching SOS page for path=%s", path)

        return records

    async def iter_endpoint_data(
        self, *, max_concurrency: int = 3, interval_ms: int = 501
    ) -> AsyncIterator[EndpointFetchResult[SOSEndpoint]]:
        """
        Yields each endpoint result as soon as it finishes.

        This allows the job to write each raw payload immediately instead of
        waiting for every endpoint to finish.
        """

        semaphore = asyncio.Semaphore(max_concurrency)

        async def fetch_with_limit(
            endpoint: SOSEndpoint,
        ) -> EndpointFetchResult[SOSEndpoint]:
            async with semaphore:
                try:
                    records = await self.get_raw_sos_data(
                        endpoint=endpoint, max_concurrency=max_concurrency
                    )
                    return EndpointFetchResult(endpoint=endpoint, records=records)
                except Exception as exc:
                    logger.exception("Failed to fetch SOS endpoint=%s", endpoint.name)
                    return EndpointFetchResult(endpoint=endpoint, error=exc)

        tasks = [
            asyncio.create_task(fetch_with_limit(endpoint))
            for endpoint in settings.sos_enabled_endpoints()
        ]

        for task in asyncio.as_completed(tasks):
            yield await task

    def _extract_records(
        self,
        payload: dict[str, Any],
        *,
        context: str,
    ) -> list[dict[str, Any]]:
        records = payload.get("data", [])

        if not isinstance(records, list):
            raise ValueError(f"Expected SOS response data list ({context})")

        return records

    def _serialize_datetime(self, value: date | datetime | None) -> str:
        if value is None:
            return datetime.now(timezone.utc).isoformat()
        if isinstance(value, datetime):
            dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        dt = datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
        return dt.isoformat()

    async def update_state_file(self, state_type: str, records: list[dict[str, Any]]):

        await sos_state.update({state_type: {"last_run_at": self.run_started_at}})
