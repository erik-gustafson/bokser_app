from __future__ import annotations

import logging

from pathlib import Path
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Self, Protocol, Generic, TypeVar
from src.storage.raw.writer import RawPayloadWriter

logger = logging.getLogger(__name__)

EndpointT = TypeVar("EndpointT")


@dataclass(frozen=True, slots=True)
class EndpointFetchResult(Generic[EndpointT]):
    endpoint: EndpointT
    records: list[dict[str, Any]] = field(default_factory=list)
    error: Exception | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class TargetData(Protocol):

    @property
    def source_name(self) -> str: ...

    @property
    def state_file(self) -> Path: ...

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, *args: object) -> None: ...

    async def update_state_file(
        self, state_type: str, records: list[dict[str, Any]]
    ): ...

    def iter_endpoint_data(
        self,
        *,
        max_concurrency: int,
    ) -> AsyncIterator[EndpointFetchResult]: ...


async def sync_endpoints_job(
    *,
    target_data_factory: Callable[[], TargetData],
    raw_writer: RawPayloadWriter,
    max_concurrency: int = 3,
) -> None:
    successful_endpoints = 0
    failed_endpoints = 0
    total_records = 0

    target_data = target_data_factory()

    source_name = target_data.source_name

    async with target_data:
        async for result in target_data.iter_endpoint_data(
            max_concurrency=max_concurrency,
        ):
            endpoint = result.endpoint

            if not result.ok:
                failed_endpoints += 1
                logger.warning(
                    f"Skipping raw write for {source_name} endpoint=%s due to fetch error: %s",
                    endpoint.name,
                    result.error,
                )
                continue

            endpoint_name = endpoint.name
            records = result.records

            write_result = raw_writer.write_json_payload(
                source_system=source_name,
                entity_name=endpoint_name,
                payload=records,
            )

            successful_endpoints += 1
            total_records += write_result.record_count

            logger.info(
                f"Fetched and wrote {source_name} endpoint=%s records=%s file=%s",
                endpoint.name,
                write_result.record_count,
                write_result.file_path,
            )

            if records:
                await target_data.update_state_file(
                    state_type=endpoint_name, records=records
                )

    logger.info(
        f"Finished {source_name} endpoint sync. successful_endpoints=%s failed_endpoints=%s total_records=%s",
        successful_endpoints,
        failed_endpoints,
        total_records,
    )
