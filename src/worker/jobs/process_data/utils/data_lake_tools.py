from __future__ import annotations

from typing import Any
from pathlib import Path

from datetime import datetime, timezone, timedelta

from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from dataclasses import dataclass


from src.database.models.data_lake_models import DataLakeFile

EXECUTABLE_LAKE_FILE_STATUSES = ("LANDED", "FAILED", "PARTIAL")


@dataclass(frozen=True)
class ClaimedLakeFile:
    id: int
    file_path: str
    source_name: str
    entity_name: str


async def claim_lake_files(
    session: AsyncSession,
    *,
    source_name: str | None = None,
    entity_name: str | None = None,
    limit: int = 25,
) -> list[ClaimedLakeFile]:

    stale_processing_before = datetime.now(timezone.utc) - timedelta(minutes=30)

    stmt = (
        select(DataLakeFile)
        .where(
            or_(
                DataLakeFile.status.in_(EXECUTABLE_LAKE_FILE_STATUSES),
                and_(
                    DataLakeFile.status == "PROCESSING",
                    DataLakeFile.claimed_at < stale_processing_before,
                ),
            )
        )
        .order_by(DataLakeFile.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )

    if source_name:
        stmt = stmt.where(DataLakeFile.source_name == source_name)

    if entity_name:
        stmt = stmt.where(DataLakeFile.entity_name == entity_name)

    result = await session.execute(stmt)
    files = list(result.scalars().all())

    claimed_files: list[ClaimedLakeFile] = []

    for file in files:
        file.status = "PROCESSING"
        file.attempt_count += 1
        file.claimed_at = datetime.now(timezone.utc)

        claimed_files.append(
            ClaimedLakeFile(
                id=file.id,
                file_path=file.file_path,
                source_name=file.source_name,
                entity_name=file.entity_name,
            )
        )

    return claimed_files


def extract_json_records(
    payload: Any,
    *,
    path: Path,
    expected_entity_name: str | None = None,
) -> list[dict[str, Any]]:

    if not isinstance(payload, dict):
        raise ValueError(f"Expected wrapped lake JSON object in {path}")

    metadata = payload.get("metadata")
    records = payload.get("payload")

    if not isinstance(metadata, dict):
        raise ValueError(f"Missing or invalid metadata in {path}")

    if expected_entity_name and metadata.get("entity_name") != expected_entity_name:
        raise ValueError(
            f"Entity mismatch in {path}: "
            f"manifest={expected_entity_name}, "
            f"file={metadata.get('entity_name')}"
        )

    record_list = _normalize_json_records(
        records,
        path=path,
    )

    if any(not isinstance(record, dict) for record in record_list):
        raise ValueError(f"Payload contains non-object records in {path}")

    expected_count = metadata.get("record_count")

    if isinstance(expected_count, int) and expected_count != len(record_list):
        raise ValueError(
            f"Record count mismatch in {path}: "
            f"metadata={expected_count}, "
            f"actual={len(record_list)}"
        )

    return record_list


def _normalize_json_records(
    records: Any,
    *,
    path: Path,
) -> list[dict[str, Any]]:

    if isinstance(records, list):
        return records

    if not isinstance(records, dict):
        raise ValueError(f"Expected payload object or list in {path}")

    orders = records.get("orders")

    if orders is not None:
        if not isinstance(orders, list):
            raise ValueError(f"Expected payload.orders list in {path}")

        return orders

    return [records]
