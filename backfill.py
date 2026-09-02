from __future__ import annotations

import json
import hashlib
import logging
import asyncio
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select, or_, and_

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult

from src.core.config import settings

from src.storage.raw.writer import RawPayloadWriter

from src.database.database import async_session
from src.database.models.data_lake_models import DataLakeFile
from src.database.models import BokserAPIWebhookEvent

logger = logging.getLogger(__name__)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _read_lake_metadata(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as f:
        file_data = json.load(f)

    if not isinstance(file_data, dict):
        raise ValueError(f"Expected wrapped lake JSON object in {path}")

    metadata = file_data.get("metadata")
    payload = file_data.get("payload")

    if not isinstance(metadata, dict):
        raise ValueError(f"Missing or invalid metadata in {path}")

    if not isinstance(payload, list):
        raise ValueError(f"Missing or invalid payload list in {path}")

    return metadata, payload


def _map_host_path_to_worker_path(
    file_path: Path,
    *,
    host_root: str | Path,
    worker_root: str | Path,
) -> str:
    """
    Converts a local/host path into the path the worker container can read.

    Example:
        host_root = r"C:\\Users\\Erik\\data_lake"
        worker_root = "/app/data_lake"

        C:\\Users\\Erik\\data_lake\\raw\\acenda\\...
        becomes
        /app/data_lake/raw/acenda/...
    """

    host_root_path = Path(host_root)
    worker_root_path = (
        PureWindowsPath(worker_root) if "\\" in str(worker_root) else Path(worker_root)
    )

    relative_path = file_path.relative_to(host_root_path)

    return str(Path(worker_root) / relative_path).replace("\\", "/")


async def queue_lake_files_from_path(
    top_level_path: str | Path,
    *,
    worker_root_path: str | Path | None = None,
    source_name: str | None = None,
    entity_name: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """
    Recursively scans a lake folder and inserts matching JSON files into data_lake_files
    as LANDED. Existing file_path rows are skipped.

    top_level_path:
        The path visible to the process running this function.

    worker_root_path:
        Optional path to store in data_lake_files.file_path instead of the local path.
        Use this when queueing from Windows but the worker reads files inside Docker.

    source_name/entity_name:
        Optional filters based on metadata values.
    """

    root = Path(top_level_path)

    if not root.exists():
        raise FileNotFoundError(f"Path does not exist: {root}")

    if not root.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {root}")

    queued = 0
    skipped_existing = 0
    failed: list[dict[str, Any]] = []

    json_files = sorted(root.rglob("*.json"))

    if limit is not None:
        json_files = json_files[:limit]

    async with async_session() as session:
        async with session.begin():
            for path in json_files:
                try:
                    metadata, payload = _read_lake_metadata(path)

                    file_source_name = metadata.get("source_system")
                    file_entity_name = metadata.get("entity_name")

                    if source_name and file_source_name != source_name:
                        continue

                    if entity_name and file_entity_name != entity_name:
                        continue

                    if not file_source_name:
                        raise ValueError(f"Missing metadata.source_system in {path}")

                    if not file_entity_name:
                        raise ValueError(f"Missing metadata.entity_name in {path}")

                    file_bytes = path.read_bytes()
                    checksum = hashlib.sha256(file_bytes).hexdigest()

                    if worker_root_path is not None:
                        db_file_path = _map_host_path_to_worker_path(
                            path,
                            host_root=root,
                            worker_root=worker_root_path,
                        )
                    else:
                        db_file_path = str(path)

                    landed_at = parse_dt(
                        metadata.get("written_at_utc")
                    ) or datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

                    stmt = (
                        pg_insert(DataLakeFile)
                        .values(
                            source_name=file_source_name,
                            entity_name=file_entity_name,
                            file_path=db_file_path,
                            file_name=path.name,
                            record_count=len(payload),
                            file_size_bytes=len(file_bytes),
                            sha256=checksum,
                            landed_at=landed_at,
                            status="LANDED",
                            attempt_count=0,
                            loaded_count=0,
                            skipped_count=0,
                            failed_count=0,
                        )
                        .on_conflict_do_nothing(index_elements=[DataLakeFile.file_path])
                    )

                    result = await session.execute(stmt)

                    if not isinstance(result, CursorResult):
                        raise TypeError(
                            "Expected a CursorResult from the DML statement"
                        )

                    if result.rowcount == 1:
                        queued += 1
                    else:
                        skipped_existing += 1

                except Exception as exc:
                    logger.exception("Failed to queue lake file path=%s", path)

                    failed.append(
                        {
                            "file_path": str(path),
                            "error": str(exc),
                        }
                    )

    return {
        "scanned": len(json_files),
        "queued": queued,
        "skipped_existing": skipped_existing,
        "failed": failed,
    }


async def sort_webhook_files():

    raw_writer = RawPayloadWriter(Path(r"X:\data_lake\prod"))
    order_updates = []
    new_orders = []

    async with async_session() as session:

        stmt = (
            select(BokserAPIWebhookEvent)
            .where(BokserAPIWebhookEvent.source == "ksp")
            .order_by(BokserAPIWebhookEvent.id)
        )

        events = (await session.execute(stmt)).scalars().all()

    for event in events:
        if event.event_type == "order_update":
            order_updates.append(event.payload)
        if event.event_type == "order_new":
            new_orders.append(event.payload)

    await write_payload_to_data_lake(
        raw_writer=raw_writer,
        records=order_updates,
        source_name="ksp",
        endpoint_name="order_update",
    )

    await write_payload_to_data_lake(
        raw_writer=raw_writer,
        records=new_orders,
        source_name="ksp",
        endpoint_name="order_new",
    )


async def write_payload_to_data_lake(
    raw_writer: RawPayloadWriter,
    records: list[Any],
    source_name: str,
    endpoint_name: str,
):

    async with async_session() as session:

        if records:
            write_result = raw_writer.write_json_payload(
                source_system=source_name,
                entity_name=endpoint_name,
                payload=records,
            )

            file_path = str(write_result.file_path).replace(
                "X:\\data_lake", "\\app\\data_lake"
            )

            file_path = file_path.replace("\\", "/")

            session.add(
                DataLakeFile(
                    source_name=source_name,
                    entity_name=endpoint_name,
                    file_path=file_path,
                    file_name=write_result.file_name,
                    record_count=write_result.record_count,
                    file_size_bytes=write_result.file_size_bytes,
                    sha256=write_result.sha256,
                    landed_at=write_result.written_at_utc,
                    status="LANDED",
                )
            )

            await session.commit()

        logger.info(
            f"Fetched and wrote {source_name} endpoint=%s records=%s file=%s",
            endpoint_name,
            write_result.record_count,
            write_result.file_path,
        )


if __name__ == "__main__":

    asyncio.run(sort_webhook_files())

    result = asyncio.run(
        queue_lake_files_from_path(
            r"C:\Users\erik\Code\data_lake\dev\raw\acenda",
            worker_root_path="/app/data_lake/raw/acenda",
            source_name="acenda",
        )
    )

    print(result)
