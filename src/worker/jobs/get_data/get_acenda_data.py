from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from src.core.config import settings
from src.core.configs.acenda import AcendaEndpoint
from src.integrations.acenda_client import AcendaClient
from src.storage.raw.writer import RawPayloadWriter

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EndpointFetchResult:
    endpoint: AcendaEndpoint
    records: list[dict[str, Any]] = field(default_factory=list)
    error: Exception | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class GetAcendaData:
    """
    Service to get data from Acenda API.
    Requests include Orders
    """

    def __init__(self, *, acenda_client: AcendaClient | None = None) -> None:
        self.acenda_client = acenda_client or AcendaClient()
        self._owns_acenda_client = acenda_client is None
        self._open_depth = 0

    async def open(self) -> None:
        self._open_depth += 1

    async def close(self) -> None:
        if self._open_depth <= 0:
            return

        self._open_depth -= 1
        if self._open_depth == 0 and self._owns_acenda_client:
            await self.acenda_client.aclose()

    async def __aenter__(self) -> "GetAcendaData":
        await self.open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def iter_endpoint_data(
        self,
        *,
        max_concurrency: int = 3,
    ) -> AsyncIterator[EndpointFetchResult]:
        """
        Yields each endpoint result as soon as it finishes.

        This allows the job to write each raw payload immediately instead of
        waiting for every endpoint to finish.
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def fetch_with_limit(endpoint: AcendaEndpoint) -> EndpointFetchResult:
            async with semaphore:
                try:
                    records = await self.get_raw_acenda_data(
                        path=endpoint.path, max_concurrency=max_concurrency
                    )
                    return EndpointFetchResult(endpoint=endpoint, records=records)
                except Exception as exc:
                    logger.exception(
                        "Failed to fetch Acenda endpoint=%s", endpoint.name
                    )
                    return EndpointFetchResult(endpoint=endpoint, error=exc)

        tasks = [
            asyncio.create_task(fetch_with_limit(endpoint))
            for endpoint in settings.acenda_enabled_endpoints()
        ]

        for task in asyncio.as_completed(tasks):
            yield await task

    async def _get_raw_acenda_data_with_open_client(
        self,
        *,
        path: str,
        max_results: int,
        max_concurrency: int,
    ) -> list[dict[str, Any]]:
        base_params = {}
        client = self.acenda_client
        first = await client.get(path_or_url=path, params=base_params)
        first.raise_for_status()

        data = first.json()
        records = self._extract_records(data, context=f"path={path}")
        total_count = data.get("num_results", 0)

        if total_count <= max_results:
            return records

        total_pages = (total_count + max_results - 1) // max_results
        semaphore = asyncio.Semaphore(max_concurrency)

        async def fetch_page(page_idx: int) -> list[dict[str, Any]]:
            async with semaphore:
                page_params = {**base_params, "page": page_idx}

                response = await client.get(path_or_url=path, params=page_params)
                response.raise_for_status()
                page_records = self._extract_records(
                    response.json(),
                    context=f"path={path} page={page_idx}",
                )
                return page_records

        tasks = [
            asyncio.create_task(fetch_page(page_idx))
            for page_idx in range(2, total_pages + 1)
        ]

        for task in asyncio.as_completed(tasks):
            try:
                records.extend(await task)
            except Exception:
                logger.exception("Error fetching Acenda page for path=%s", path)

        return records

    async def get_raw_acenda_data(
        self,
        path: str,
        max_results: int = 100,
        max_concurrency: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Paginated GET using Acenda params: maxresults/start and any other filters.
        """
        should_open = self._open_depth == 0

        if should_open:
            await self.open()

        try:
            return await self._get_raw_acenda_data_with_open_client(
                path=path,
                max_results=max_results,
                max_concurrency=max_concurrency,
            )
        finally:
            if should_open:
                await self.close()

    def _extract_records(
        self, payload: dict[str, Any], *, context: str
    ) -> list[dict[str, Any]]:
        records = payload.get("result", [])
        if not isinstance(records, list):
            raise ValueError(f"Expected Acenda response data list ({context})")
        return records


async def sync_acenda_endpoints_job(
    *,
    acenda_data: GetAcendaData,
    raw_writer: RawPayloadWriter,
    max_concurrency: int = 3,
) -> None:
    """
    Fetch all enabled Acenda endpoints and write each endpoint payload as soon
    as that endpoint finishes.

    RawPayloadWriter stays lightweight: it only writes the payload it is given.
    """
    successful_endpoints = 0
    failed_endpoints = 0
    total_records = 0

    async with acenda_data:
        async for result in acenda_data.iter_endpoint_data(
            max_concurrency=max_concurrency
        ):
            endpoint = result.endpoint

            if not result.ok:
                failed_endpoints += 1
                logger.warning(
                    "Skipping raw write for Acenda endpoint=%s due to fetch error: %s",
                    endpoint.name,
                    result.error,
                )
                continue

            records = result.records

            write_result = raw_writer.write_json_payload(
                source_system="acenda",
                entity_name=endpoint.name,
                payload=records,
            )

            successful_endpoints += 1
            total_records += write_result.record_count

            logger.info(
                "Fetched and wrote Acenda endpoint=%s records=%s file=%s",
                endpoint.name,
                write_result.record_count,
                write_result.file_path,
            )

    logger.info(
        "Finished Acenda endpoint sync. successful_endpoints=%s failed_endpoints=%s total_records=%s",
        successful_endpoints,
        failed_endpoints,
        total_records,
    )
