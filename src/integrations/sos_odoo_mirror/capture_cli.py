"""Explicit GET-only capture using an existing token; never refreshes OAuth."""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
from .capture import API_BASE, capture_master


class ExistingDatabaseTokenAuth:
    async def get_headers(self):
        from sqlalchemy import text
        from src.database.database import async_session
        from src.integrations._base_client.client_auth import AuthHeaders
        async with async_session() as db:
            await db.execute(text("SET TRANSACTION READ ONLY"))
            row = (await db.execute(text("SELECT access_token, expires_at FROM auth_tokens WHERE provider = :provider"),
                {"provider": "sos_inventory"})).one_or_none()
            if not row or not row[0] or row[1] <= datetime.now(timezone.utc) + timedelta(seconds=60):
                raise ValueError("existing_token_missing_or_expiring")
            return AuthHeaders(headers={"Authorization": "Bearer " + row[0]})

    async def handle_unauthorized(self, headers):
        return False


async def run(args):
    if args.env_file:
        from dotenv import load_dotenv
        if not Path(args.env_file).is_file():
            raise ValueError("env_file_missing")
        load_dotenv(args.env_file, override=False)
    from src.integrations.sos_client import SOSClient
    async with SOSClient(base_url=API_BASE) as client:
        client.auth = ExistingDatabaseTokenAuth()
        for entity in (("customer", "vendor") if args.entity == "both" else (args.entity,)):
            result = await capture_master(client, entity=entity, scope=args.source_scope,
                output_root=args.output_root, page_size=args.page_size, max_records=args.max_records,
                include_archived=args.include_archived, approved_fields=args.custom_field)
            print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true", required=True)
    parser.add_argument("--entity", choices=("customer", "vendor", "both"), required=True)
    parser.add_argument("--source-scope", required=True, help="Owner-attested source account code matching the Odoo account code")
    parser.add_argument("--output-root", required=True, help="Dedicated private capture directory outside Git and shared ingestion")
    parser.add_argument("--env-file", help="Optional existing private configuration; not copied or printed")
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--max-records", type=int, default=10000)
    parser.add_argument("--include-archived", action="store_true", help="Capture explicit archived source masters; never infer deletion from absence")
    parser.add_argument("--custom-field", action="append", type=int, default=[], help="Owner-approved SOS custom field ID; repeat for each approved field")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(run(args))
    except Exception:
        parser.exit(1, "sos_master_capture_failed; no success receipt for the failed entity; check access/input/source consistency\n")


if __name__ == "__main__":
    main()
