Current checkpoint: [Transactions, lifecycle and automation](SOS_TRANSACTIONS_AND_AUTOMATION.md), addon 19.0.0.5.1. Erik owns shared operations; database bokser_test and cutoff 2026-01-01 are confirmed; company 2 is proposed; only custom IDs 1 and 7 are approved. The older checkpoints below are historical.

Current checkpoint: see [Master fields and source revisions](SOS_MASTER_FIELDS_AND_REVISIONS.md) for wire schema 3, addon 19.0.0.3.0, current source blockers and validation. Earlier counts and limitations below are historical.

# SOS to Odoo mirror

Last verified locally: 2026-10-10. This is development source, not a deployed mirror.
Re-read live Git refs, other worktrees and NAS deployment state before merging or operating.

## Scope and decisions

The full agreed scope is vendors, purchase orders, receipts, customers, estimates,
sales orders, invoices, sales receipts, payments, returns, RMAs and shipments.
Reuse the SOS lake, existing SOS client and native Odoo records. Mirror business
records without triggering extra business functionality. Before cutover only
SOS to Odoo is allowed, except separately authorized SOS push tests.
Historical transaction cutoff and direction are system parameters.

This increment implements complete, non-archived customer/vendor contact snapshots,
including customer parent dependencies and separate mobile numbers,
into native `res.partner` only. Its binding is unique by
(account, entity, SOS ID); account identity/company cannot be changed after creation.
Name/email matching is deliberately not an identity rule. A customer and vendor
with the same numeric ID have separate bindings and separate partners.
Adoption/deduplication of existing Odoo partners needs a reviewed mapping before use
on a real dataset. It currently creates new partners; it does not adopt existing ones.
Name, email, phone, website, mobile and parent source identity transfer. Odoo 19
has no native mobile field; SOS Mobile is an additive native partner field.
A mobile-only number also falls back to phone. Customer/vendor rank and
company are set by the server. Addresses, terms, currencies, archival,
custom fields and complete master parity remain pending. Raw JSON, notes, portal
passwords and payment credentials are excluded by an explicit field allowlist.

## Existing ingestion and gaps

Backend transaction endpoint registration exists for sales orders, sales receipts,
estimates, invoices, shipments, item receipts, payments, purchase orders,
adjustments, returns, RMAs and items. Customers/vendors are not registered there.
A customer SQL model exists but has no registered customer payload mapper; a
vendor SQL model was not found. No additional business tables or backend DB
migration were introduced. Existing ingestion cursors, loaders, shared settings,
worker schedule, transaction processing and lake manifests are unchanged.

The manual Odoo import consumer accepts either a plain JSON list of complete source
snapshots with explicit capture time, or the existing RawPayloadWriter envelope
(metadata source_system=sos_inventory, entity_name=customer/vendor,
written_at_utc with timezone, record_count, payload list). It does not discover
files automatically. Separate opt-in capture now fetches customer/vendor snapshots;
see [SOS_MASTER_CAPTURE.md](SOS_MASTER_CAPTURE.md). A plain list must be a trusted
complete snapshot, not a partial update: missing optional contact fields become
empty strings. Verify SOS account provenance of input before applying it.
Use actual capture time, not replay time. Capture retains source revisions and its
own success receipts. Full master parity and incremental cursors remain pending.

## Replays, updates and conflicts

Each inbound request commits the native partner and its durable Odoo binding in
the same transaction. An account lock serializes imports; existing partner rows
are also locked. There is no raw-lake claim mutation or second backend checkpoint.
If a batch stops after several successful calls, replay the original captured file.
The server returns created/updated/duplicate/stale. An unchanged newer observation
advances the binding watermark. Older observations cannot overwrite newer ones;
different content at the same observation time raises observation_conflict.
Manual changes to mirrored fields, role ranks or active status raise local_edit_conflict,
even for duplicates. Resolve the conflict by reviewing source and native records;
there is no force/overwrite endpoint. Bindings are read-only for service/configuration
users, and bound partners cannot be deleted because the reference restricts deletion.

Capture time is an observation watermark, not an SOS modification timestamp or
proof of source freshness. Source revision/sync-token semantics and overlapping
captures must be settled before autonomous polling. No deletion propagation,
reverse transport, retries to SOS, order confirmation, stock moves, reservations,
accounting posting or warehouse submission exists in this increment.

## Configuration and execution

The Odoo addon is `addons/bokser_sos_mirror`, version 19.0.0.2.0; it depends on
account and rpc. Installation creates new Odoo tables; therefore installation/
upgrade is a shared database operation and needs the sole designated operations
owner. No owner is designated now and no shared database changes were performed.
Run ORM validation in a disposable local Odoo 19 database first.

A manager creates a company-specific account with stable code. It defaults inactive.
The integration user needs `SOS Mirror Integration Service`, allowed company,
native partner permissions and JSON/2 access. Configuration managers can manage
accounts/read bindings but are not implicitly integration users.
System parameters:
- bokser_sos_mirror.enabled: False by default; True required.
- bokser_sos_mirror.direction: sos_to_odoo by default. two_way fails closed;
  selecting it does not enable an outbound transport.
- bokser_sos_mirror.transaction_cutoff: optional YYYY-MM-DD. Validated now,
  reserved for transaction adapters; it does not filter master partners. Those
  adapters must enforce it before creating any transactions.

The backend defaults to dry run and has no scheduler registration. From its mirror
worktree, use an available environment with httpx installed:

    python -m src.integrations.sos_odoo_mirror --file PATH --entity customer --observed-at 2026-10-09T12:00:00Z

For an existing wrapped lake file, omit --observed-at. Apply requires --apply,
--account ACCOUNT_CODE and --company COMPANY_ID, plus privately provided env vars
SOS_MIRROR_ODOO_URL (HTTPS root URL), SOS_MIRROR_ODOO_DATABASE and
SOS_MIRROR_ODOO_API_KEY. Never commit or paste their values. The client calls
/json/2/bokser.sos.account/import_partner with bearer auth and X-Odoo-Database,
rejects redirects, does not retry automatically and suppresses response bodies
in errors. A rejected/uncertain request is recoverable by replaying the same file.

## Verification and next steps

Local: 11 backend unittest cases and 4 Odoo pure-policy cases pass. The new addon
static checks and existing framework/contract/allocation checks passed.
Runtime: installed in a disposable Docker Desktop Odoo 19.0-20260908 / PostgreSQL
15.19 database, bokser_sos_mirror_local. All eleven Odoo TransactionCase tests
pass. Real certificate-verified HTTPS JSON/2 checks pass for create, duplicate,
update, stale replay, same-time conflict, local-edit conflict, company restriction,
vendor creation, concurrent replay, disabled gate and two-way gate. The backend
client ran inside the isolated container through a temporary TLS proxy; this was
not a browser/UI acceptance check or a production deployment test.

Runtime testing found/fixed two issues: Odoo 19 has no native mobile field; and
SELECT FOR UPDATE alone leaves a waiting request's REPEATABLE READ snapshot stale.
The server now touches the account audit row to trigger Odoo's serialization retry
with a fresh snapshot. Concurrent identical requests return created and duplicate
with one native partner/binding. Eleven ORM tests were rerun after this correction.

The backend scripts/check_sos_mirror_runtime.py is a repeatable synthetic HTTPS
regression, requiring --disposable and a bokser_sos_mirror_local-prefixed database.
Its extra private env vars are SOS_MIRROR_ODOO_ACCOUNT, SOS_MIRROR_ODOO_COMPANY and
optional SOS_MIRROR_TLS_CA. It creates synthetic records; an owner must first
provision/enable the disposable account. Disabled/two-way gates were separately
verified by the isolated harness. No live SOS calls, NAS changes, shared database
migrations, production activation or production runtime acceptance occurred.
Temporary API credentials were revoked and disposable services stopped afterward.

The local harness/evidence is outside Git in
C:/Users/erik/Downloads/Bokser_Production_Baseline/mirror-runtime-20261009.
Its PostgreSQL container preserves the synthetic test DB while stopped; there is
no production data. Do not copy keys or database/runtime bundles into Git. Recreate
an expiring API key and TLS certificate before repeating HTTPS checks.
For ORM validation run Odoo with -d bokser_sos_mirror_local -u bokser_sos_mirror
--test-enable --test-tags /bokser_sos_mirror --stop-after-init --without-demo=True.
Use -i instead of -u only for an initial install; -i on an already installed module
does not rerun the suite. Check that eleven tests actually ran, not just exit code.

Opt-in capture, read-only source verification and the 67 customer dependency/phone
blockers are resolved; see [SOS_MASTER_CAPTURE.md](SOS_MASTER_CAPTURE.md) and
[SOS_PARTNER_MAPPING.md](SOS_PARTNER_MAPPING.md). Current verification is 31 backend
tests, 18 disposable Odoo ORM tests, and 13 real synthetic HTTPS scenarios.
Exact next step: extend master fields/source revision bindings. Production imports
remain disabled pending reviewed company/source mapping, upgrades and activation.
Then add native draft
sales/purchase transactions with cutoff enforcement, products/UOM/currency/tax
resolution and source-link dependencies. Plan remaining accounting/stock/returns
adapters explicitly; draft native records may not represent historical posted
states accurately. Review before posting or creating stock movements.

## Worktree and merge coordination

Both repos use dedicated feature/sos-odoo-mirror branches:
- Windows C:/Users/erik/Code/bokser_app-sos-odoo-mirror, base
  4f5e461c233217203eeb71c26a4ea9416881dfce.
- WSL /home/erik/code/odoo_addons-sos-odoo-mirror, base
  2965a7e375fc357c8c5cb4bd1c388a21c8719806.
Original dirty checkouts and preserved integration branches remain separate.
Coordinate contract/policy changes in both repositories. Merge the addon and
backend as a reviewed pair after tests, and fetch current refs first. Do not
merge preserved local-work branches wholesale. Future shared-file overlap:
backend configs, worker/main.py, SOS client/endpoints/mappers/models and Alembic;
Odoo res.partner, order import, sales fulfillment, account.move/stock models,
security/settings and addon migrations. This slice adds only a new integration
package/test/docs and a new addon/policy test/docs, avoiding those shared files.
Deployment, Odoo upgrades and shared DB migrations have one designated owner at
a time. Do not push production deployment remotes or upgrade NAS as part of
feature development. Other sessions' source and deployed settings must be preserved.

No production inputs, credentials or runtime bundles are needed for this first
increment. The source, tests and this document belong in Git. Earlier alignment
reports and preservation ZIPs stay outside Git under Erik's Downloads; consult
Bokser_Production_Baseline/ALIGNMENT_COORDINATION.md and alignment completion notes
for the last-known production inventory and pending integration work.

Implementation reference: Odoo 19 system-parameter settings support Char, not Date;
the cutoff uses Char with strict server-side ISO-date validation. See
[Odoo 19 res.config.settings source](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/res_config.py).
