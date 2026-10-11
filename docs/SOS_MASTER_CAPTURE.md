# SOS master capture checkpoint — 2026-10-09

Update 2026-10-10: the 67 historical customer mapping blockers below are resolved.
Both original batches validate with zero blockers under wire schema 2; see
[SOS_PARTNER_MAPPING.md](SOS_PARTNER_MAPPING.md). The counts below remain the original
capture-time assessment; files/checksums are preserved. No live Odoo import occurred.

Verify current repositories, source connection and deployment state before continuing.
This is opt-in capture development. Production Odoo delivery/scheduling remains disabled.

Read-only verification used the existing NAS sos_inventory connection. Last-known
full active captures: 295 customers and 489 vendors. Current contact mapping validates
228 customers and all 489 vendors; 67 customers remain blocked (66 parent dependencies,
one with distinct phone/mobile numbers). These are readiness counts, not delivery
acknowledgments. No live records were sent to Odoo. Archived/deleted records remain pending.

API references: [customers](https://developer.sosinventory.com/apidoc/Customer),
[vendors](https://developer.sosinventory.com/apidoc/Vendor),
[rate limits](https://developer.sosinventory.com/apidoc/overview).
Queries have one-based start pagination, at most 200 records, count/totalCount/status/data.
Never send summary, including summary=no: its presence requests partial records.

The backend capture.py/capture_cli.py reuse SOSClient and RawPayloadWriter. Existing
token selection executes SET TRANSACTION READ ONLY, never refreshes/rotates OAuth,
and fails on missing/near-expiry tokens. Existing token maintenance remains separate.

From the backend worktree, using existing private configuration:

    python -m src.integrations.sos_odoo_mirror.capture_cli --capture --entity both --source-scope ACCOUNT_CODE --output-root PRIVATE_DIRECTORY --env-file EXISTING_PRIVATE_ENV_FILE

Alternatively supply settings through the environment and omit --env-file. Use a
dedicated private folder outside Git/shared ingestion. POSIX scope directories use
0700 and files 0600; Windows access follows inherited ACLs. Configuration is read,
not copied/printed. The source-scope label must match the intended Odoo account code
on apply. It prevents accidental wrong-file use but is not independent tenant proof:
the inspected responses expose no tenant ID. bokser-sos-prod records provenance from
the existing NAS connection. Confirm connection ownership/company mapping before
production Odoo account setup. Never adopt partners by name/email.

Only id, syncToken, name/email/website/phone/mobile, archived, summaryOnly and parent ID
persist. Passwords, payment credentials, arbitrary keys/values, notes and unreviewed
fields are removed before transfer/storage. This is contact capture, not full master
parity. No vendor business table, backend migration or Odoo schema change was added.

Sequential pagination rejects non-ok HTTP-200 responses, incomplete records/pages,
bad IDs/versions, duplicate IDs, changing totals and first-page content/version drift.
GET retries/rate limits use the existing client. A bounded scan (default 10000 records)
publishes only after all pages pass and page one is rechecked. SOS lists have no atomic
snapshot guarantee; changes to later pages may escape this check. Repeated scans and
revision reconciliation are needed before unattended synchronization.

Metadata retains original start/end time, source scope/revision field and blocked IDs/
codes. written_at_utc is scan start, never replay time. _mirror_capture/captures.sqlite3
serializes captures and commits a receipt after publishing the complete file. This is
capture progress, not a delta cursor or delivery acknowledgment. Shared ingestion
cursors, DataLakeFile claims/status, token tables and worker scheduling are untouched.
Failed pages produce no file/success receipt for that entity. Rerun performs a full scan.
A journal failure after publication leaves an orphan file: verify/checksum it or rerun.
With --entity both, a completed customer receipt remains valid if vendor then fails.
Every customer batch is revalidated with the current mapper before import; historical
blocked counts never authorize skipping records or bypass dependency validation.

syncToken is documented as a record version and retained verbatim; monotonic ordering
is not assumed. updatedsince is documented without timezone; lastSync concerns
QuickBooks synchronization rather than a reliable SOS update cursor. No source records
were mutated to test revision semantics. Capture uses full scans without updatedsince/
createdsince. Odoo wire version 1 still uses observation time; source version enforcement
needs a reviewed next contract.

Fourteen capture tests and eleven existing mirror backend tests pass. They cover failed
pages without progress, retry, incomplete/summary records, ID/count/version drift,
wrong source scope, sensitive-field exclusion and blocked-batch refusal. The same page/
projection/auth code ran in memory in the existing NAS container for live GET checks;
it was not installed/copied there. All publication/receipt storage happened locally.
Local CLI help passed; direct local credential configuration remains environment-dependent.
Earlier limited-contact Odoo ORM/HTTPS verification still applies; addon runtime code
did not change in this increment. Production Odoo readiness has not been established.

Private artifacts outside Git:
C:/Users/erik/Downloads/Bokser_Production_Baseline/private-sos-master-captures holds
capture_summary.json, sanitized real contact snapshots and the receipt ledger. Keep
these private. Schema-only evidence is sos_master_probe_20261009.json in the baseline
folder; local convenience harness run_sos_master_capture_readonly.py is also there.
The committed CLI is the supported entry point; do not publish contact-data bundles.

Parent-first and alternate-number mappings now pass local/ORM/HTTPS verification.
Next extend addresses/contacts/terms/currency and source revision bindings before
transactions. Production imports remain disabled. No shared deployment/upgrade/database migration owner is
designated. Those operations have one owner at a time. Use separate feature worktrees,
preserve other sessions and coordinate shared model/config/security/migration changes.
