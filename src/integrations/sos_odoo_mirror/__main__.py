"""Manually validate/replay a partner snapshot. Dry run is the default."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import httpx
from .contract import normalize, timestamp
from .client import OdooMirrorClient, MirrorError


def load_batch(path, entity, observed_at=None, expected_source_scope=None):
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if isinstance(raw, dict) and set(raw) == {"metadata", "payload"}:
        metadata = raw["metadata"]
        if not isinstance(metadata, dict) or metadata.get("source_system") != "sos_inventory" or metadata.get("entity_name") != entity:
            raise ValueError("invalid_lake_metadata")
        if metadata.get("mirror_capture_version") is not None:
            if metadata.get("mirror_capture_version") != 1 or metadata.get("pagination_checked") is not True:
                raise ValueError("invalid_mirror_capture")
            if expected_source_scope is not None and metadata.get("source_scope") != expected_source_scope:
                raise ValueError("source_scope_mismatch")
            if type(metadata.get("blocked_count")) is not int or metadata["blocked_count"] != 0:
                raise ValueError("blocked_capture_requires_mapping_review")
        observed_at = metadata.get("written_at_utc")
        records = raw["payload"]
        if not isinstance(records, list) or type(metadata.get("record_count")) is not int or metadata["record_count"] != len(records):
            raise ValueError("lake_count_mismatch")
    else:
        records = raw
    timestamp(observed_at)
    if not isinstance(records, list):
        raise ValueError("snapshot_list_required")
    batch = [normalize(entity, record, observed_at) for record in records]
    if len({p["source_id"] for p in batch}) != len(batch):
        raise ValueError("duplicate_source_id_in_batch")
    return batch


async def run(args):
    # Validate every record before any network call; stop on the first server error.
    batch = load_batch(args.file, args.entity, args.observed_at, expected_source_scope=args.account if args.apply else None)
    if not args.apply:
        print(json.dumps({"mode": "dry_run", "entity": args.entity, "validated_records": len(batch)}))
        return
    if not args.account or not args.company or args.company <= 0:
        raise ValueError("account_and_company_required")
    async with httpx.AsyncClient() as http:
        client = OdooMirrorClient(base_url=os.environ.get("SOS_MIRROR_ODOO_URL", ""),
            database=os.environ.get("SOS_MIRROR_ODOO_DATABASE", ""),
            api_key=os.environ.get("SOS_MIRROR_ODOO_API_KEY", ""), client=http)
        counts = {}
        for payload in batch:
            result = await client.import_partner(account_code=args.account, company_id=args.company, payload=payload)
            counts[result["status"]] = counts.get(result["status"], 0) + 1
        print(json.dumps({"mode": "apply", "results": counts}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True)
    parser.add_argument("--entity", choices=("customer", "vendor"), required=True)
    parser.add_argument("--observed-at", help="Timezone-qualified capture time for a plain JSON list")
    parser.add_argument("--account")
    parser.add_argument("--company", type=int)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except (ValueError, MirrorError, OSError):
        parser.exit(1, "mirror_batch_failed; fix input/configuration or inspect Odoo; replay the same captured file\n")


if __name__ == "__main__":
    main()
