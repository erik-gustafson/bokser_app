from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal

from src.core.config import settings
from src.core.configs.acenda import AcendaEndpoint
from src.integrations.acenda_client import AcendaClient
from src.storage.states.state_store import acenda_state
from src.worker.jobs.get_data.base_get import EndpointFetchResult

logger = logging.getLogger(__name__)


AcendaStateType = Literal[
    "new_orders",
    "updated_orders",
]


ACENDA_STATE_PATHS: dict[str, list[str]] = {
    "new_orders": ["all_orders", "last_created_at"],
    "updated_orders": ["all_orders", "last_updated_at"],
}


class GetAcendaData:
    """
    Service to fetch data from the Acenda API.
    """

    def __init__(self, *, acenda_client: AcendaClient | None = None) -> None:
        self.source_name: str = "acenda"
        self.acenda_client = acenda_client or AcendaClient()
        self._owns_acenda_client = acenda_client is None
        self._open_depth = 0

        self.state_file: Path = (
            settings.lake_root / "raw" / "acenda" / "_state" / "acenda_query_state.json"
        )

    async def open(self) -> None:
        self._open_depth += 1

    async def close(self) -> None:
        if self._open_depth <= 0:
            return

        self._open_depth -= 1

        if self._open_depth == 0 and self._owns_acenda_client:
            await self.acenda_client.aclose()

    async def __aenter__(self) -> GetAcendaData:
        await self.open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def iter_endpoint_data(
        self,
        *,
        max_concurrency: int = 3,
    ) -> AsyncIterator[EndpointFetchResult[AcendaEndpoint]]:
        """
        Yield each endpoint result as soon as it finishes.
        """

        semaphore = asyncio.Semaphore(max_concurrency)

        async def fetch_with_limit(
            endpoint: AcendaEndpoint,
        ) -> EndpointFetchResult[AcendaEndpoint]:
            async with semaphore:
                try:
                    records = await self.get_raw_acenda_data(
                        endpoint=endpoint,
                        max_concurrency=max_concurrency,
                    )

                    return EndpointFetchResult(
                        endpoint=endpoint,
                        records=records,
                    )

                except Exception as exc:
                    logger.exception(
                        "Failed to fetch Acenda endpoint=%s",
                        endpoint.name,
                    )

                    return EndpointFetchResult(
                        endpoint=endpoint,
                        error=exc,
                    )

        tasks = [
            asyncio.create_task(fetch_with_limit(endpoint))
            for endpoint in settings.acenda_enabled_endpoints()
        ]

        for task in asyncio.as_completed(tasks):
            yield await task

    async def get_raw_acenda_data(
        self,
        *,
        endpoint: AcendaEndpoint,
        max_results: int = 100,
        max_concurrency: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Paginated GET using Acenda endpoint params.
        """

        should_open = self._open_depth == 0

        if should_open:
            await self.open()

        try:
            return await self._get_raw_acenda_data_with_open_client(
                endpoint=endpoint,
                max_results=max_results,
                max_concurrency=max_concurrency,
            )
        finally:
            if should_open:
                await self.close()

    async def _get_raw_acenda_data_with_open_client(
        self,
        *,
        endpoint: AcendaEndpoint,
        max_results: int,
        max_concurrency: int,
    ) -> list[dict[str, Any]]:
        path = endpoint.path
        client = self.acenda_client

        endpoint_params = settings.get_acenda_endpoint_params(
            self.state_file,
            endpoint=endpoint,
        )

        first_response = await client.get(
            path_or_url=path,
            params=endpoint_params,
        )
        first_response.raise_for_status()

        first_payload = first_response.json()

        records = self._extract_records(
            first_payload,
            context=f"path={path} page=1",
        )

        total_count = int(first_payload.get("num_results") or len(records))

        if total_count <= max_results:
            return records

        total_pages = (total_count + max_results - 1) // max_results
        semaphore = asyncio.Semaphore(max_concurrency)

        async def fetch_page(page_idx: int) -> list[dict[str, Any]]:
            async with semaphore:
                page_params = {
                    **endpoint_params,
                    "page": page_idx,
                }

                response = await client.get(
                    path_or_url=path,
                    params=page_params,
                )
                response.raise_for_status()

                return self._extract_records(
                    response.json(),
                    context=f"path={path} page={page_idx}",
                )

        tasks = [
            asyncio.create_task(fetch_page(page_idx))
            for page_idx in range(2, total_pages + 1)
        ]

        for task in asyncio.as_completed(tasks):
            try:
                records.extend(await task)
            except Exception:
                logger.exception(
                    "Error fetching Acenda page for path=%s",
                    path,
                )

        return records

    def _extract_records(
        self,
        payload: dict[str, Any],
        *,
        context: str,
    ) -> list[dict[str, Any]]:
        records = payload.get("result", [])

        if not isinstance(records, list):
            raise ValueError(f"Expected Acenda result list ({context})")

        return records

    def get_max_date_value(
        self,
        records: list[dict[str, Any]],
        type: str,
    ) -> str | None:

        date_values = [str(record[type]) for record in records if record.get(type)]

        if not date_values:
            return None

        return max(date_values)

    async def update_state_file(self, state_type: str, records: list[dict[str, Any]]):

        if state_type is None:
            raise ValueError(f"Unsupported Acenda state_type={state_type!r}")
        if state_type in ["new_orders", "new_ship_advices"]:
            dt_value = self.get_max_date_value(records=records, type="created_at")
            if dt_value is not None:
                await acenda_state.update({state_type: {"last_created_at": dt_value}})
        if state_type in ["updated_orders", "updated_ship_advices"]:
            dt_value = self.get_max_date_value(records=records, type="updated_at")
            if dt_value is not None:
                await acenda_state.update({state_type: {"last_updated_at": dt_value}})
