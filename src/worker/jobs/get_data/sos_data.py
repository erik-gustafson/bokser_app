from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator

from src.core.config import settings
from src.core.configs.sos import SOSEndpoint
from src.integrations.sos_inventory.client import SOSClient
from src.storage.raw.writer import RawPayloadWriter

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EndpointFetchResult:
    endpoint: SOSEndpoint
    records: list[dict[str, Any]] | None = None
    error: Exception | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class GetSosData:
    """
    Service to get data from SOS Inventory API.
    Requests include Sales Orders, Items, Invoices, Shipments, Payments,
    Purchase Orders, and Item Receipts.
    """

    def __init__(self, *, sos_client: SOSClient | None = None) -> None:
        self.sos_client = sos_client or SOSClient()
        self._owns_sos_client = sos_client is None
        self._open_depth = 0

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

    async def get_sales_orders(self) -> list[dict[str, Any]]:
        return await self.get_raw_sos_data("/salesorder")

    async def get_invoices(self) -> list[dict[str, Any]]:
        return await self.get_raw_sos_data("/invoice")

    async def get_shipments(self) -> list[dict[str, Any]]:
        return await self.get_raw_sos_data("/shipment")

    async def get_payments(self) -> list[dict[str, Any]]:
        return await self.get_raw_sos_data("/payment")

    async def get_purchase_orders(self) -> list[dict[str, Any]]:
        return await self.get_raw_sos_data("/purchaseorder")

    async def get_item_receipts(self) -> list[dict[str, Any]]:
        return await self.get_raw_sos_data("/itemreceipt")

    async def get_items(self) -> list[dict[str, Any]]:
        return await self.get_raw_sos_data("/item")

    async def get_raw_sos_data(
        self,
        path: str,
        max_results: int = 200,
        archived: str = "no",
        max_concurrency: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Paginated GET using SOS params: maxresults/start and any other filters.
        """
        if self._open_depth > 0:
            return await self._get_raw_sos_data_with_open_client(
                path=path,
                max_results=max_results,
                archived=archived,
                max_concurrency=max_concurrency,
            )

        async with self:
            return await self._get_raw_sos_data_with_open_client(
                path=path,
                max_results=max_results,
                archived=archived,
                max_concurrency=max_concurrency,
            )

    async def _get_raw_sos_data_with_open_client(
        self,
        *,
        path: str,
        max_results: int,
        archived: str,
        max_concurrency: int,
    ) -> list[dict[str, Any]]:
        base_params = {
            "maxresults": max_results,
            "archived": archived,
        }
        client = self.sos_client
        first = await client.get(path_or_url=path, params=base_params)
        first.raise_for_status()

        data = first.json()
        records = data.get("data", [])
        total_count = data.get("totalCount", 0)

        if not isinstance(records, list):
            raise ValueError(
                f"Expected SOS response data to be a list for path={path}"
            )

        if total_count <= len(records):
            return records

        total_pages = (total_count + max_results - 1) // max_results
        semaphore = asyncio.Semaphore(max_concurrency)

        async def fetch_page(page_idx: int) -> list[dict[str, Any]]:
            async with semaphore:
                start_cursor = (max_results * page_idx) + 1
                page_params = {**base_params, "start": start_cursor}

                response = await client.get(
                    path_or_url=path,
                    params=page_params,
                )
                response.raise_for_status()

                page_data = response.json().get("data", [])

                if not isinstance(page_data, list):
                    raise ValueError(
                        f"Expected SOS page data to be a list for path={path} page={page_idx}"
                    )

                return page_data

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

    async def get_endpoint_data(
        self,
        endpoint: SOSEndpoint,
    ) -> tuple[SOSEndpoint, list[dict[str, Any]]]:
        records = await self.get_raw_sos_data(endpoint.path)
        return endpoint, records

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

        async def fetch_with_limit(endpoint: SOSEndpoint) -> EndpointFetchResult:
            async with semaphore:
                try:
                    _, records = await self.get_endpoint_data(endpoint)
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

    async def get_all_endpoint_data(
        self,
        *,
        max_concurrency: int = 3,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Returns all endpoint data after all endpoint fetches complete.

        Keep this only if something else needs the full in-memory dict.
        For raw-file writing, prefer iter_endpoint_data(...).
        """
        results: dict[str, list[dict[str, Any]]] = {}
        errors: dict[str, str] = {}

        async for result in self.iter_endpoint_data(max_concurrency=max_concurrency):
            if not result.ok:
                errors[result.endpoint.name] = str(result.error)
                continue

            results[result.endpoint.name] = result.records or []

        if errors:
            logger.warning("Some SOS endpoints failed: %s", errors)

        return results


async def sync_sos_endpoints_job(
    *,
    sos_data: GetSosData,
    raw_writer: RawPayloadWriter,
    max_concurrency: int = 3,
) -> None:
    """
    Fetch all enabled SOS endpoints and write each endpoint payload as soon
    as that endpoint finishes.

    RawPayloadWriter stays lightweight: it only writes the payload it is given.
    """
    successful_endpoints = 0
    failed_endpoints = 0
    total_records = 0

    async with sos_data:
        async for result in sos_data.iter_endpoint_data(max_concurrency=max_concurrency):
            endpoint = result.endpoint

            if not result.ok:
                failed_endpoints += 1
                logger.warning(
                    "Skipping raw write for SOS endpoint=%s due to fetch error: %s",
                    endpoint.name,
                    result.error,
                )
                continue

            records = result.records or []

            write_result = raw_writer.write_json_payload(
                source_system="sos_inventory",
                entity_name=endpoint.name,
                payload=records,
            )

            successful_endpoints += 1
            total_records += write_result.record_count

            logger.info(
                "Fetched and wrote SOS endpoint=%s records=%s file=%s",
                endpoint.name,
                write_result.record_count,
                write_result.file_path,
            )

    logger.info(
        "Finished SOS endpoint sync. successful_endpoints=%s failed_endpoints=%s total_records=%s",
        successful_endpoints,
        failed_endpoints,
        total_records,
    )
