from __future__ import annotations

import csv
import json
import mimetypes
import re
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4


class RawFileType(StrEnum):
    JSON = "json"
    JSONL = "jsonl"
    NDJSON = "ndjson"
    CSV = "csv"
    TSV = "tsv"
    TXT = "txt"
    XML = "xml"
    HTML = "html"
    PDF = "pdf"
    XLS = "xls"
    XLSX = "xlsx"
    ZIP = "zip"
    GZ = "gz"
    PARQUET = "parquet"
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg"
    WEBP = "webp"
    DOC = "doc"
    DOCX = "docx"
    EML = "eml"
    MSG = "msg"


@dataclass(frozen=True)
class RawWriteResult:
    file_path: Path
    file_name: str
    metadata_path: Path | None
    record_count: int
    file_size_bytes: int
    sha256: str
    written_at_utc: datetime
    file_type: str


class RawPayloadWriter:
    def __init__(self, lake_root: str | Path) -> None:
        self._lake_root = Path(lake_root)

    def write_json_payload(
        self,
        *,
        source_system: str,
        entity_name: str,
        payload: dict[str, Any] | list[Any],
        metadata: Mapping[str, Any] | None = None,
    ) -> RawWriteResult:
        now = datetime.now(timezone.utc)
        safe_source_system = self._safe_path_part(source_system)
        safe_entity_name = self._safe_path_part(entity_name)

        out_dir = self._build_output_dir(
            source_system=safe_source_system,
            entity_name=safe_entity_name,
            now=now,
        )

        file_name, ingestion_id = self._build_file_name(
            entity_name=safe_entity_name,
            file_type=RawFileType.JSON,
            now=now,
        )
        file_path = out_dir / file_name

        tmp_path = file_path.with_suffix(".tmp")

        record_count = len(payload) if isinstance(payload, list) else 1

        wrapped_payload = {
            "metadata": {
                "source_system": safe_source_system,
                "entity_name": safe_entity_name,
                "file_type": RawFileType.JSON.value,
                "record_count": record_count,
                "written_at_utc": now.isoformat(),
                "ingestion_id": ingestion_id,
                **dict(metadata or {}),
            },
            "payload": payload,
        }

        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(wrapped_payload, f, indent=2, ensure_ascii=False, default=str)
            f.write("\n")

        tmp_path.replace(file_path)

        file_bytes = file_path.read_bytes()
        checksum = hashlib.sha256(file_bytes).hexdigest()

        return RawWriteResult(
            file_path=file_path,
            file_name=file_name,
            metadata_path=None,
            record_count=record_count,
            file_size_bytes=file_path.stat().st_size,
            written_at_utc=now,
            sha256=checksum,
            file_type=RawFileType.JSON.value,
        )

    def write_json_lines(
        self,
        *,
        source_system: str,
        entity_name: str,
        records: Iterable[Mapping[str, Any]],
        metadata: Mapping[str, Any] | None = None,
        file_type: RawFileType = RawFileType.JSONL,
    ) -> RawWriteResult:
        now = datetime.now(timezone.utc)
        safe_source_system = self._safe_path_part(source_system)
        safe_entity_name = self._safe_path_part(entity_name)
        safe_file_type = self._safe_file_type(file_type)

        if safe_file_type not in {RawFileType.JSONL.value, RawFileType.NDJSON.value}:
            raise ValueError("file_type must be jsonl or ndjson.")

        out_dir = self._build_output_dir(
            source_system=safe_source_system,
            entity_name=safe_entity_name,
            now=now,
        )

        file_name, ingestion_id = self._build_file_name(
            entity_name=safe_entity_name,
            file_type=safe_file_type,
            now=now,
        )

        file_path = out_dir / file_name

        #
        tmp_path = file_path.with_suffix(".tmp")

        record_count = 0
        #
        with tmp_path.open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False, default=str))
                f.write("\n")
                record_count += 1
        #
        tmp_path.replace(file_path)

        metadata_path = self._write_sidecar_metadata(
            file_path=file_path,
            source_system=safe_source_system,
            entity_name=safe_entity_name,
            file_type=safe_file_type,
            record_count=record_count,
            written_at_utc=now,
            ingestion_id=ingestion_id,
            metadata=metadata,
        )

        file_bytes = file_path.read_bytes()
        checksum = hashlib.sha256(file_bytes).hexdigest()

        return RawWriteResult(
            file_path=file_path,
            file_name=file_name,
            metadata_path=metadata_path,
            record_count=record_count,
            file_size_bytes=file_path.stat().st_size,
            written_at_utc=now,
            sha256=checksum,
            file_type=safe_file_type,
        )

    def write_csv_rows(
        self,
        *,
        source_system: str,
        entity_name: str,
        rows: Iterable[Mapping[str, Any]],
        metadata: Mapping[str, Any] | None = None,
        delimiter: str = ",",
        file_type: RawFileType = RawFileType.CSV,
    ) -> RawWriteResult:
        now = datetime.now(timezone.utc)
        safe_source_system = self._safe_path_part(source_system)
        safe_entity_name = self._safe_path_part(entity_name)
        safe_file_type = self._safe_file_type(file_type)

        if safe_file_type not in {RawFileType.CSV.value, RawFileType.TSV.value}:
            raise ValueError("file_type must be csv or tsv.")

        out_dir = self._build_output_dir(
            source_system=safe_source_system,
            entity_name=safe_entity_name,
            now=now,
        )

        file_name, ingestion_id = self._build_file_name(
            entity_name=safe_entity_name,
            file_type=safe_file_type,
            now=now,
        )
        file_path = out_dir / file_name

        tmp_path = file_path.with_suffix(".tmp")

        rows_list = list(rows)
        fieldnames = sorted({key for row in rows_list for key in row.keys()})

        with tmp_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
            writer.writeheader()
            writer.writerows(rows_list)

        tmp_path.replace(file_path)

        metadata_path = self._write_sidecar_metadata(
            file_path=file_path,
            source_system=safe_source_system,
            entity_name=safe_entity_name,
            file_type=safe_file_type,
            record_count=len(rows_list),
            written_at_utc=now,
            ingestion_id=ingestion_id,
            metadata=metadata,
        )

        file_bytes = file_path.read_bytes()
        checksum = hashlib.sha256(file_bytes).hexdigest()

        return RawWriteResult(
            file_path=file_path,
            file_name=file_name,
            metadata_path=metadata_path,
            record_count=len(rows_list) if isinstance(rows_list, list) else 1,
            file_size_bytes=file_path.stat().st_size,
            written_at_utc=now,
            sha256=checksum,
            file_type=safe_file_type,
        )

    def write_file_bytes(
        self,
        *,
        source_system: str,
        entity_name: str,
        file_bytes: bytes,
        file_type: RawFileType | str,
        original_file_name: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> RawWriteResult:
        now = datetime.now(timezone.utc)
        safe_source_system = self._safe_path_part(source_system)
        safe_entity_name = self._safe_path_part(entity_name)
        safe_file_type = self._safe_file_type(file_type)

        out_dir = self._build_output_dir(
            source_system=safe_source_system,
            entity_name=safe_entity_name,
            now=now,
        )

        file_name, ingestion_id = self._build_file_name(
            entity_name=safe_entity_name,
            file_type=safe_file_type,
            now=now,
        )
        file_path = out_dir / file_name

        tmp_path = file_path.with_suffix(".tmp")

        tmp_path.write_bytes(file_bytes)

        tmp_path.replace(file_path)

        metadata_path = self._write_sidecar_metadata(
            file_path=file_path,
            source_system=safe_source_system,
            entity_name=safe_entity_name,
            file_type=safe_file_type,
            record_count=0,
            written_at_utc=now,
            ingestion_id=ingestion_id,
            metadata={
                "original_file_name": original_file_name,
                "content_type": mimetypes.guess_type(original_file_name or file_name)[
                    0
                ],
                **dict(metadata or {}),
            },
        )

        file_bytes = file_path.read_bytes()
        checksum = hashlib.sha256(file_bytes).hexdigest()

        return RawWriteResult(
            file_path=file_path,
            file_name=file_name,
            metadata_path=metadata_path,
            record_count=0,
            file_size_bytes=file_path.stat().st_size,
            written_at_utc=now,
            sha256=checksum,
            file_type=safe_file_type,
        )

    def _build_output_dir(
        self,
        *,
        source_system: str,
        entity_name: str,
        now: datetime,
    ) -> Path:
        out_dir = (
            self._lake_root
            / "raw"
            / source_system
            / entity_name
            / f"year={now:%Y}"
            / f"month={now:%m}"
            / f"day={now:%d}"
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir

    @staticmethod
    def _build_file_name(
        *,
        entity_name: str,
        file_type: RawFileType | str,
        now: datetime,
    ) -> tuple[str, str]:
        safe_file_type = RawPayloadWriter._safe_file_type(file_type)
        ingestion_id = uuid4().hex

        return (
            f"{entity_name}_{now:%Y%m%dT%H%M%S}_" f"{ingestion_id}.{safe_file_type}",
            ingestion_id,
        )

    @staticmethod
    def _safe_path_part(value: str) -> str:
        value = value.strip().lower()
        value = re.sub(r"[^a-z0-9._-]+", "_", value)
        value = value.strip("._-")

        if not value:
            raise ValueError("Path part cannot be empty.")

        return value

    @staticmethod
    def _safe_file_type(file_type: RawFileType | str) -> str:
        value = str(file_type).lower().strip().lstrip(".")

        if "." in value:
            value = value.rsplit(".", 1)[-1]

        value = re.sub(r"[^a-z0-9]+", "", value)

        if not value:
            raise ValueError("File type cannot be empty.")

        return value

    def _write_sidecar_metadata(
        self,
        *,
        file_path: Path,
        source_system: str,
        entity_name: str,
        file_type: str,
        record_count: int | None,
        written_at_utc: datetime,
        ingestion_id: str,
        metadata: Mapping[str, Any] | None,
    ) -> Path:
        metadata_path = file_path.with_suffix(file_path.suffix + ".metadata.json")

        sidecar = {
            "source_system": source_system,
            "entity_name": entity_name,
            "file_type": file_type,
            "record_count": record_count,
            "written_at_utc": written_at_utc.isoformat(),
            "ingestion_id": ingestion_id,
            "file_name": file_path.name,
            "file_path": str(file_path),
            "file_size_bytes": file_path.stat().st_size,
            "metadata": dict(metadata or {}),
        }

        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(sidecar, f, indent=2, ensure_ascii=False, default=str)
            f.write("\n")

        return metadata_path


__all__ = [
    "RawFileType",
    "RawWriteResult",
    "RawPayloadWriter",
]
