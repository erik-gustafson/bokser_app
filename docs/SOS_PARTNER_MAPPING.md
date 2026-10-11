Current checkpoint: see [Master fields and source revisions](SOS_MASTER_FIELDS_AND_REVISIONS.md) for wire schema 3, addon 19.0.0.3.0, current source blockers and validation. Earlier counts and limitations below are historical.

# Customer dependency resolution — 2026-10-10

Last verified against the private 2026-10-09 capture: all 295 customers and 489
vendors validate, with zero mapping blockers. The original files and checksums
are unchanged. All 66 child customers reference captured parents; maximum depth
is one, no missing parents/cycles. Both phone numbers in the one dual-phone record
are retained. These are local validation results, not production imports.

Wire schema 2 carries nullable parent_source_id and a separate mobile value.
Native res.partner.phone retains the source primary number (mobile-only falls back
to phone); res.partner.bokser_sos_mobile stores the source mobile number, exposed
as SOS Mobile on the native partner form. No phone number is concatenated/dropped.
Odoo 19 has no native mobile field, so this additive field is owned by the mirror.
Coordinate other res.partner/view/migration work before merging.

The entire batch is validated and topologically ordered before network calls.
Parents import before children, including multi-level graphs. Missing parents,
self references, cycles, duplicate IDs and vendor hierarchies fail before import.
Individual Odoo calls resolve parents only through customer bindings in the same
account/company; missing/inactive/wrong-company or locally edited parents fail.
The server independently rejects native parent cycles. Children remain native
contacts with company-specific parent_id; names/emails never establish identity.

Payload hashes include source parent identity. Target fingerprints include native
parent_id and SOS Mobile in addition to existing managed fields/ranks/active flag.
Local edits to either new field cause conflicts. Wire schema 1 remains supported
for existing clients/bindings. Bindings record schema_version; new bindings use 2.
An unchanged legacy record can upgrade at the same observation time when the
original managed-field payload/fingerprint agrees; older snapshots stay stale.
Unexpected existing parent/mobile values require schema_upgrade_review_required;
local edits are never adopted silently. Downgrading a schema-2 binding is forbidden.

Capture metadata's old ready/blocked counts describe its historical mapper.
The import consumer recomputes every record and the whole graph with the current
mapper rather than trusting historical counts. It does not edit the captured file,
skip blocked records, or regenerate capture timestamps. Source-scope matching and
pagination metadata validation still apply. A dry run prints aggregate counts only.

Validation completed:
- 31 backend contract/capture/dependency tests pass.
- Four offline Odoo policy tests and existing static framework checks pass.
- Disposable Odoo 19 upgrade/view installation and all 18 ORM tests pass.
- Thirteen actual certificate-verified HTTPS scenarios pass, including concurrent
  replay, parent/child creation, both phone fields, child replay and missing parent.
- Original real customer/vendor batches dry-run successfully, checksums unchanged.

Actual Odoo testing used synthetic contacts only, on the isolated local
bokser_sos_mirror_local database. No captured real records were imported into Odoo,
no SOS writes occurred and no NAS/deployed addon/settings changed. No browser visual
acceptance or production runtime check is implied. Addon version is 19.0.0.2.0.

Schema changes are additive: res.partner.bokser_sos_mobile and binding.schema_version
(existing bindings default to 1). Upgrade only the disposable database during
development. Shared deployment, upgrades and migrations require one designated
owner; none is designated for production. This session owned the disposable runtime
only; temporary API keys are revoked and its services stopped after verification.

Remaining work: master addresses/contact/terms/currency, source revision enforcement
(syncToken is captured but not yet in the Odoo wire contract), actual source tenant/
company confirmation, and all transaction entities/cutoff adapters. Coordinate paired
repo merges; retain pre-cutover SOS-to-Odoo restrictions and separate worktrees.

Private evidence remains under Erik's Downloads/Bokser_Production_Baseline:
private-sos-master-captures retains immutable real contact captures;
mirror-runtime-20261009 retains synthetic DB/test artifacts. The new API result is
parent_api_results_20261010.json; the current ORM log contains 18 successful tests.
All source/tests/specifications belong in the paired feature branches. Runtime data,
contact snapshots and credentials remain outside Git.
