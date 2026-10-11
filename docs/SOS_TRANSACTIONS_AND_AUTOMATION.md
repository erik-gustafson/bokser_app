# SOS inbound mirror — development checkpoint, 2026-10-10

Erik (`erik@bokserhome.com`) is the source-account owner and designated owner of deployment, Odoo upgrades and shared migrations. The target Odoo database/company and approved custom-field IDs are still pending. The job is disabled by default; this checkpoint is not deployed or production-enabled.

## Scope and behavior

Customers/vendors include contacts, all five address lines, hierarchy, alternate addresses, reviewed terms/currency, explicit archive/reactivation and owner-approved custom fields. Transactions cover purchase orders, item receipts, estimates, sales orders, invoices, sales receipts, payments, returns, RMAs and shipments. Source revisions, statuses, totals, fulfillment facts and dependencies are retained. Transaction addresses use owned native partner records; invoice/stock lines link to reviewed native sales/purchase/return dependencies.

Every imported document stays in draft. Imports do not confirm orders, post accounting entries, reconcile payments, reserve inventory, validate stock moves or submit WMS work. A source field named Reserve Inventory is metadata only. Payment allocations and source completed/voided states remain source facts. The integration is SOS → Odoo only before cutover. Two-way mode fails closed.

Source identity is account/entity/SOS ID. Partner names/emails are not adoption keys. Native products, warehouses, journals, taxes, terms, currencies, countries/states and payment methods require reviewed reference rows. Defaults require explicit rows keyed `default`. Unmapped values, inconsistent totals, local edits and unsupported dependency types fail closed. Bound documents cannot be deleted through normal native unlink. Source lines referenced by another mirrored document cannot be removed automatically.

## Automation and recovery

The scheduled job uses the existing SOS client and reads the loader's current OAuth token from `auth_tokens` in a read-only transaction. It never refreshes or rotates that token. A dedicated token is optional, not currently required. Routine transaction deltas consume existing SOS lake files through read-only manifest queries and independent private receipts. Initial/daily full reconciliation and full master capture use strict GET scans with the existing token. Set `SOS_MIRROR_USE_EXISTING_LAKE=false` to use strict API deltas instead. The existing loader can return partial page results after a page exception; the mirror therefore validates its own full pages/counts/IDs/source revisions instead of trusting that cursor's completeness. Do not silently change shared loader behavior during rollout.

Private state is `<SOS_MIRROR_JOURNAL_ROOT>/_mirror_capture/captures.sqlite3`; there is no new backend business-database migration. Pinning includes HTTPS origin, database, source account code and company ID, never a credential. Stage snapshots and scan cursors atomically. Deliveries use expiring leases, replay-safe Odoo bindings, capped retries and durable blocked errors. Dependencies wait for queued parents. Previously staged deliveries can run before a new scan. Initial and daily reconciliation scan full transactions; delta scans overlap five minutes. Masters are full scans including explicit archived records. SOS list APIs provide no atomic snapshot; first-page revalidation/count checks cannot prove every page stayed immutable throughout a scan.

Missing records in a full scan become review candidates. Absence never causes automatic native deletion/archival. Review/fix blocked conflicts and mappings before requeuing. Preserve the private journal across restarts/deployments; do not delete it to bypass identity/conflict checks. An expired run lease recovers after two hours; delivery leases recover after two minutes.

## Configuration (names only; no secret values)

`SOS_MIRROR_USE_EXISTING_LAKE=true`, `SOS_MIRROR_JOB_ENABLED=false`, `SOS_MIRROR_SOURCE_OWNER_CONFIRMED=false`, `SOS_MIRROR_ACCOUNT_CODE`, `SOS_MIRROR_COMPANY_ID`, `SOS_MIRROR_ODOO_URL`, `SOS_MIRROR_ODOO_DATABASE`, `SOS_MIRROR_ODOO_API_KEY`, `SOS_MIRROR_ODOO_CA_BUNDLE`, `SOS_MIRROR_JOURNAL_ROOT`, `SOS_MIRROR_CUSTOM_FIELD_IDS` (JSON integer array), `SOS_MIRROR_INTERVAL_MINUTES=5`, `SOS_MIRROR_RECONCILIATION_HOURS=24`, `SOS_MIRROR_DELIVERY_LIMIT=1000`.

Odoo gates: `bokser_sos_mirror.enabled=false`, `bokser_sos_mirror.direction=sos_to_odoo`, `bokser_sos_mirror.transaction_cutoff` (reviewed ISO business date or empty), account active flag, allowed company, service integration group, reviewed references and account `approved_custom_field_ids` (JSON array of canonical ID strings). Approvals must agree on both sides. Changing approval scope for an already staged source revision requires a reviewed contract/state migration; do not rewrite historical hashes.

Manual operations load existing private environment configuration; do not pass credentials as CLI arguments:

```
python -m src.integrations.sos_odoo_mirror.runner --status
python -m src.integrations.sos_odoo_mirror.runner --run
python -m src.integrations.sos_odoo_mirror.runner --run --reconcile
python -m src.integrations.sos_odoo_mirror.runner --retry-reviewed-blocked
```

The existing master capture CLI accepts `--include-archived` and repeated owner-approved `--custom-field ID`. Custom field 24 (Casepack Size) is item metadata: product creation/metadata synchronization is outside this draft transaction adapter; existing products must be reviewed/mapped separately.

## Verification and remaining rollout

Local backend unit checks: 76 passed. Disposable Odoo 19 database `bokser_sos_mirror_local`: 40 ORM runtime tests passed; 20 existing partner/master HTTPS scenarios and 28 transaction HTTPS scenarios passed. These use synthetic data. Real SOS endpoints were read-only schema-probed; all ten responded successfully. Production Odoo imports, scheduling, shared upgrades and target/company mappings have not been verified by this checkpoint.

Next: verify both feature worktrees/remote heads and current NAS deployment; confirm the target database/company, custom-field IDs and historical cutoff with Erik; recapture full masters with wire v4 and gather sanitized reference inventories; prepare reviewed native reference rows and a disabled rollout. Obtain a fresh backup and one owner-controlled deployment window before shared upgrades. Upgrade Odoo with the backend job disabled, verify gates/ACLs and real dry-run mappings, then import/reconcile a reviewed pilot before enabling scheduling. Verify accounting, stock and fulfillment remain unchanged by draft imports. The 40 ORM checks also pass with `bokser_sales_fulfillment` installed; backend pipeline/restart and lake-integrity checks pass with synthetic data. Production scheduler/restart recovery and real dataset verification remain pending.

Merge the backend and addon feature branches as a coordinated pair. Preserve original dirty checkouts and other sessions. Shared overlaps include `src/core/config.py`, `src/core/configs/__init__.py`, `src/worker/main.py`, the SOS loader/state code, addon manifests/security/native partner/sale/purchase/stock/account models, shared schemas and Odoo upgrades. Do not promote unrelated features or run the production deploy script merely to synchronize GitHub.

## Restore procedure

Erik must stop both the backend mirror job and Odoo mirror gate, wait for active runs to finish, then take a fresh Odoo database/filestore/addon backup and private journal snapshot as one quiesced checkpoint. Preserve backend private state and existing SOS loader cursors. Restore the paired code/database/filestore/journal checkpoint together. If newer journal acknowledgements survive an older Odoo restore, use `python -m src.integrations.sos_odoo_mirror.runner --replay-reviewed-all` only after owner review with delivery stopped; it resets acknowledgements while preserving immutable snapshots, hashes and target pin. Native idempotency/conflict gates still apply. Then run reconciliation and verify counts before re-enabling scheduling. Never delete/recreate native bindings or clear local-edit hashes to force a replay.

Shared compatibility change: `addons/bokser_sales_fulfillment/models/stock.py` allows the `bokser_sos_` metadata namespace through its write guard. WMS fields continue to require fulfillment actions. Coordinate this file with the fulfillment session before merge/deployment.
