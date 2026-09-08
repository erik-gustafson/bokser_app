from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, TypeAlias, TypeVar, cast

from sqlalchemy import DateTime, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


from src.database.database import async_session
from src.database.models.data_lake_models import DataLakeFile

from src.worker.jobs.process_data.sos.sos_payload_mappers import *

from src.database.models.sos_models import *

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClaimedLakeFile:
    id: int
    file_path: str
    source_name: str
    entity_name: str


async def sos_load_to_db() -> None:
    entity_names = tuple(SOS_ENTITY_TYPES)
    results = await asyncio.gather(
        *(
            load_sos_lake_files(entity_name=entity_name, limit=50)
            for entity_name in entity_names
        )
    )
    total_results = list(zip(entity_names, results, strict=True))

    logger.info("SOS lake load results: %s", total_results)


async def load_sos_lake_files(
    *,
    entity_name: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    if entity_name is not None and entity_name not in SOS_ENTITY_TYPES:
        raise ValueError(f"Unsupported SOS entity_name: {entity_name}")

    total_loaded = 0
    total_skipped = 0
    failed_files: list[dict[str, Any]] = []

    async with async_session() as session:
        async with session.begin():
            claimed_files = await claim_lake_files(
                session,
                entity_name=entity_name,
                limit=limit,
            )

    for lake_file in claimed_files:
        try:
            path = Path(lake_file.file_path)
            with path.open("r", encoding="utf-8") as file:
                file_data = json.load(file)

            records = extract_json_records(
                file_data,
                path=path,
                expected_entity_name=lake_file.entity_name,
            )
            payload_type = SOS_ENTITY_TYPES[lake_file.entity_name]

            async with async_session() as session:
                async with session.begin():
                    result = await load_sos_records(
                        session=session,
                        records=records,
                        payload_type=payload_type,
                    )
                    db_file = await session.get(
                        DataLakeFile,
                        lake_file.id,
                        with_for_update=True,
                    )
                    if db_file is None:
                        raise RuntimeError(
                            f"DataLakeFile id={lake_file.id} disappeared"
                        )

                    failed_count = len(result["failed"])
                    loaded_count = result["loaded"]
                    skipped_count = result["skipped"]
                    record_count = len(records)

                    db_file.processed_at = datetime.now(timezone.utc)
                    db_file.loaded_count = loaded_count
                    db_file.skipped_count = skipped_count
                    db_file.failed_count = failed_count

                    total_loaded += loaded_count
                    total_skipped += skipped_count

                    if record_count == 0:
                        db_file.status = "EMPTY"
                        db_file.last_error = None
                    elif failed_count == record_count:
                        db_file.status = "FAILED"
                        db_file.last_error = json.dumps(result["failed"])[:5000]
                    elif skipped_count == record_count:
                        db_file.status = "SKIPPED"
                        db_file.last_error = None
                    elif failed_count + skipped_count > 0:
                        db_file.status = "PARTIAL"
                        db_file.last_error = (
                            json.dumps(result["failed"])[:5000]
                            if failed_count
                            else None
                        )
                    else:
                        db_file.status = "LOADED"
                        db_file.last_error = None

        except Exception as exc:
            logger.exception(
                "Failed to load SOS lake file id=%s path=%s",
                lake_file.id,
                lake_file.file_path,
            )
            failed_files.append(
                {
                    "file_id": lake_file.id,
                    "file_path": lake_file.file_path,
                    "error": str(exc),
                }
            )

            async with async_session() as session:
                async with session.begin():
                    db_file = await session.get(
                        DataLakeFile,
                        lake_file.id,
                        with_for_update=True,
                    )
                    if db_file is not None:
                        db_file.status = "FAILED"
                        db_file.last_error = str(exc)

    return {
        "claimed": len(claimed_files),
        "loaded": total_loaded,
        "skipped": total_skipped,
        "failed_files": failed_files,
    }


async def claim_lake_files(
    session: AsyncSession,
    *,
    entity_name: str | None = None,
    limit: int = 25,
) -> list[ClaimedLakeFile]:
    stale_processing_before = datetime.now(timezone.utc) - timedelta(minutes=30)

    stmt = (
        select(DataLakeFile)
        .where(
            DataLakeFile.source_name == "sos_inventory",
            DataLakeFile.entity_name.in_(SOS_ENTITY_TYPES),
            or_(
                DataLakeFile.status.in_(["LANDED", "FAILED"]),
                and_(
                    DataLakeFile.status == "PROCESSING",
                    DataLakeFile.claimed_at < stale_processing_before,
                ),
            ),
        )
        .order_by(DataLakeFile.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )

    if entity_name:
        stmt = stmt.where(DataLakeFile.entity_name == entity_name)

    result = await session.execute(stmt)
    files = list(result.scalars().all())
    claimed_files: list[ClaimedLakeFile] = []

    for lake_file in files:
        lake_file.status = "PROCESSING"
        lake_file.attempt_count += 1
        lake_file.claimed_at = datetime.now(timezone.utc)
        claimed_files.append(
            ClaimedLakeFile(
                id=lake_file.id,
                file_path=lake_file.file_path,
                source_name=lake_file.source_name,
                entity_name=lake_file.entity_name,
            )
        )

    return claimed_files


async def load_sos_records(
    session: AsyncSession,
    records: list[dict[str, Any]],
    payload_type: PayloadType,
) -> dict[str, Any]:
    mapper = SosPayloadMapper()
    model = PAYLOAD_MODELS[payload_type]
    loaded = 0
    skipped = 0
    failed: list[dict[str, Any]] = []

    for raw_record in records:
        record_id = raw_record.get("id")
        try:
            data = mapper.map_record(payload_type, raw_record)

            async with session.begin_nested():
                existing_sync_token = await session.scalar(
                    select(model.sync_token).where(model.id == data.id)
                )
                incoming_sync_token = data.sync_token or 0

                if (
                    existing_sync_token is not None
                    and incoming_sync_token <= existing_sync_token
                ):
                    skipped += 1
                    continue

                await session.merge(data)

            loaded += 1

        except Exception as exc:
            logger.exception("Failed to load SOS %s id=%s", payload_type, record_id)
            failed.append({"id": record_id, "error": str(exc)})

    return {"loaded": loaded, "skipped": skipped, "failed": failed}


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
            f"Entity mismatch in {path}: manifest={expected_entity_name}, "
            f"file={metadata.get('entity_name')}"
        )

    if not isinstance(records, list):
        raise ValueError(f"Expected payload list in {path}")
    if any(not isinstance(record, dict) for record in records):
        raise ValueError(f"Payload contains non-object records in {path}")
    return records
