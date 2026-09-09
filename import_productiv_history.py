"""Land a local JSON array of Productiv or KSP shipment payloads.

Run from the repo root:
    python import_productiv_history.py productiv_history.json
    python import_productiv_history.py ksp_history.json --warehouse ksp

Uses the configured database and lake_root. Registers a LANDED file, which
the normal shipment worker can pick up; this script does not run that worker.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path, PurePosixPath


async def import_shipment_history(
    path: Path, warehouse: str = "productiv", *,
    lake_root: Path | None = None, worker_lake_root: str | None = None,
) -> int:
    entities = {"productiv": "orderconfirm", "ksp": "order_update"}
    if warehouse not in entities:
        raise ValueError(f"Unsupported warehouse: {warehouse}")

    with path.open("r", encoding="utf-8-sig") as file:
        records = json.load(file)

    if not isinstance(records, list):
        raise ValueError("Expected a JSON array of original shipment payloads.")

    valid_records = []
    skipped = 0
    for index, record in enumerate(records):
        if warehouse == "ksp":
            if not isinstance(record, dict) or any(
                record.get(field) is None for field in ("cust_ref", "cust_po_no")
            ):
                raise ValueError(
                    f"Record at index {index} is missing cust_ref or cust_po_no."
                )
            if record.get("shipments") is not None and not isinstance(
                record["shipments"], list
            ):
                raise ValueError(
                    f"Record at index {index}: shipments must be an array."
                )
            valid_records.append(record)
            continue

        resource = record.get("resource") if isinstance(record, dict) else None
        body = resource.get("body") if isinstance(resource, dict) else None
        read_only = body.get("readOnly") if isinstance(body, dict) else None
        if not isinstance(read_only, dict) or read_only.get("orderId") is None:
            contexts = [value for value in (record, resource, body)
                        if isinstance(value, dict)]
            external_id = next(
                (value[key] for value in contexts for key in ("external_id", "externalId")
                 if value.get(key) is not None), None,
            )
            event_id = next(
                (value["wmsEventId"] for value in contexts
                 if value.get("wmsEventId") is not None), None,
            )
            logging.warning(
                "Skipping Productiv record at index %s: missing "
                "resource.body.readOnly.orderId; external_id=%s wmsEventId=%s",
                index, external_id, event_id,
            )
            skipped += 1
            continue
        valid_records.append(record)

    records = valid_records
    logging.info("Validated %s payloads; skipped %s from %s.", len(records), skipped, path)

    if not records:
        logging.info("No payloads in %s; nothing written.", path)
        return 0

    from src.core.config import settings
    from src.database.database import async_session
    from src.database.models import DataLakeFile
    from src.storage.raw.writer import RawPayloadWriter

    local_root = lake_root or settings.lake_root
    if not local_root.is_absolute():
        raise ValueError(
            "Lake root must be an absolute local/shared path. On Windows, use "
            "--lake-root X:/path/to/shared/lake --worker-lake-root /app/data_lake."
        )
    if worker_lake_root is not None and (
        not PurePosixPath(worker_lake_root).is_absolute() or "\\" in worker_lake_root
    ):
        raise ValueError("--worker-lake-root must be an absolute Linux path.")
    if not local_root.is_dir():
        raise FileNotFoundError(f"Lake root does not exist: {local_root}")

    result = RawPayloadWriter(local_root).write_json_payload(
        source_system=warehouse, entity_name=entities[warehouse], payload=records,
    )
    registered_path = str(result.file_path)
    if worker_lake_root is not None:
        registered_path = str(PurePosixPath(worker_lake_root).joinpath(
            *result.file_path.relative_to(local_root).parts
        ))

    async with async_session() as session:
        session.add(DataLakeFile(
            source_name=warehouse,
            entity_name=entities[warehouse],
            file_path=registered_path,
            file_name=result.file_name,
            record_count=result.record_count,
            file_size_bytes=result.file_size_bytes,
            sha256=result.sha256,
            landed_at=result.written_at_utc,
            status="LANDED",
        ))
        await session.commit()
    logging.info("Wrote %s; registered worker path %s", result.file_path, registered_path)

    logging.info("Landed %s %s payloads from %s.", len(records), warehouse, path)
    return len(records)


async def import_productiv_history(path: Path) -> int:
    return await import_shipment_history(path, warehouse="productiv")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", type=Path, help="Local JSON array of payloads")
    parser.add_argument(
        "--warehouse",
        choices=("productiv", "ksp"),
        default="productiv",
        help="Payload source (default: productiv)",
    )
    parser.add_argument("--lake-root", type=Path, help="Local path to the worker's shared lake")
    parser.add_argument("--worker-lake-root", help="Linux mount path, e.g. /app/data_lake")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    asyncio.run(import_shipment_history(
        args.json_file, args.warehouse,
        lake_root=args.lake_root, worker_lake_root=args.worker_lake_root,
    ))


"""
.venv\Scripts\python.exe import_productiv_history.py productiv_history.json --warehouse productiv
.venv\Scripts\python.exe import_productiv_history.py ksp_history.json --warehouse ksp

"""
