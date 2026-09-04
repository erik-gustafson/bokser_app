from __future__ import annotations

import logging
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession
from src.storage.raw.writer import RawPayloadWriter
from src.database.models import DataLakeFile

logger = logging.getLogger(__name__)


async def write_payload_to_data_lake(
    session: AsyncSession,
    raw_writer: RawPayloadWriter,
    records: dict[str, Any] | list[Any],
    source_name: str,
    endpoint_name: str,
):

    if records:
        write_result = raw_writer.write_json_payload(
            source_system=source_name,
            entity_name=endpoint_name,
            payload=records,
        )

        session.add(
            DataLakeFile(
                source_name=source_name,
                entity_name=endpoint_name,
                file_path=str(write_result.file_path),
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


async def write_file_to_data_lake(
    session: AsyncSession,
    raw_writer: RawPayloadWriter,
    source_name: str,
    entity_name: str,
    file_bytes: bytes,
    file_type: str,
    original_file_name: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    commit: bool = True,
):

    if file_bytes:
        write_result = raw_writer.write_file_bytes(
            source_system=source_name,
            entity_name=entity_name,
            file_bytes=file_bytes,
            file_type=file_type,
            original_file_name=original_file_name,
            metadata=metadata,
        )

        session.add(
            DataLakeFile(
                source_name=source_name,
                entity_name=entity_name,
                file_path=str(write_result.file_path),
                file_name=write_result.file_name,
                record_count=write_result.record_count,
                file_size_bytes=write_result.file_size_bytes,
                sha256=write_result.sha256,
                landed_at=write_result.written_at_utc,
                status="LANDED",
            )
        )

        if commit:
            await session.commit()
        else:
            await session.flush()

        logger.info(
            f"Fetched and wrote {source_name} endpoint=%s records=%s file=%s",
            entity_name,
            write_result.record_count,
            write_result.file_path,
        )
