from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json


@dataclass(frozen=True)
class RawWriteResult:
    file_path: Path
    file_name: str
    record_count: int
    file_size_bytes: int
    written_at_utc: datetime


class RawPayloadWriter:
    def __init__(self, lake_root: str | Path) -> None:
        self._lake_root = Path(lake_root)

    def write_json_payload(
        self,
        *,
        source_system: str,
        entity_name: str,
        payload: dict | list,
    ) -> RawWriteResult:
        now = datetime.now(timezone.utc)

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

        file_name = f"{entity_name}_{now:%Y%m%dT%H%M%SZ}_{uuid4().hex[:8]}.json"
        file_path = out_dir / file_name

        with file_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        record_count = len(payload) if isinstance(payload, list) else 1

        return RawWriteResult(
            file_path=file_path,
            file_name=file_name,
            record_count=record_count,
            file_size_bytes=file_path.stat().st_size,
            written_at_utc=now,
        )
