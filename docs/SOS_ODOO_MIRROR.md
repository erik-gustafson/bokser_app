# SOS to Odoo mirror: first development increment

Last verified locally: 2026-10-09. This is development source, not a deployed mirror.
Re-read live Git refs, other worktrees and NAS deployment state before merging or operating.

## Scope and decisions

The full agreed scope is vendors, purchase orders, receipts, customers, estimates,
sales orders, invoices, sales receipts, payments, returns, RMAs and shipments.
Reuse the SOS lake, existing SOS client and native Odoo records. Mirror business
records without triggering extra business functionality. Before cutover only
SOS to Odoo is allowed, except separately authorized SOS push tests.
Historical transaction cutoff and direction are system parameters.

This increment implements complete, non-hierarchical, non-archived customer/vendor
contact snapshots into native `res.partner` only. Its binding is unique by
(account, entity, SOS ID); account identity/company cannot be changed after creation.
Name/email matching is deliberately not an identity rule. A customer and vendor
with the same numeric ID have separate bindings and separate partners.
Adoption/deduplication of existing Odoo partners needs a reviewed mapping before use
on a real dataset. It currently creates new partners; it does not adopt existing ones.
Only name, email, phone, mobile and website transfer. Customer/vendor rank and
company are set by the server. Addresses, terms, currencies, hierarchy, archival,
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

The new manual consumer accepts either a plain JSON list of complete source
snapshots with explicit capture time, or the existing RawPayloadWriter envelope
(metadata source_system=sos_inventory, entity_name=customer/vendor,
written_at_utc with timezone, record_count, payload list). It does not fetch SOS
or discover customer/vendor files automatically. A plain list must be a trusted
complete snapshot, not a partial update: missing optional contact fields become
empty strings. Verify SOS account provenance of input before applying it.
Use actual capture time, not replay time. Real customer/vendor fetching, API field
coverage and independent incremental source checkpoints are next work.

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

The Odoo addon is `addons/bokser_sos_mirror`, version 19.0.0.1.0; it depends on
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

Local: 10 backend unittest cases pass (contract, batch validation, mocked HTTPS);
4 Odoo pure-policy unittest cases pass. Python AST, XML parsing and addon manifest
reference checks pass. Existing offline Odoo framework/contract/allocation checks
are also run at this checkpoint; consult session completion notes for results.
These checks do not prove ORM, record-rule, view-install or actual API behavior.
Eleven Odoo TransactionCase tests are supplied in addons/bokser_sos_mirror/tests but
have NOT run. No live SOS calls, Odoo JSON/2 calls, deployment, installation,
activation, shared database migration or runtime acceptance occurred.

Exact next step: provision a disposable Odoo 19 database with account and rpc,
install bokser_sos_mirror there and run its tagged post-install ORM tests. Fix
any registry/ACL/view failures in these feature worktrees before merging. Then
verify a create/replay/update/local-conflict through JSON/2 using synthetic data.
Next implement opt-in customer/vendor capture using the existing SOSClient and
RawPayloadWriter, with complete-page validation, source provenance and independent
consumer progress; extend master fields/dependency mappings. Then add native draft
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
