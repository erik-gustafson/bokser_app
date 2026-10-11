# Master fields and source revisions — 2026-10-10

Current development checkpoint: wire schema 3, addon 19.0.0.3.0. This supersedes
the source-revision and primary-master-field limitations in the earlier mapping
notes. It does not mean the full mirror or production rollout is complete.

The GET capture now projects structured contact names, company name, alternate
phone, fax, vendor account number, customer billing/shipping and vendor address,
and SOS terms/currency IDs. It preserves all five address lines and whitespace.
Only explicit nested fields cross the capture boundary. Credentials, raw notes,
arbitrary custom-field values and alternate-address bodies are excluded.

Wire schema 3 requires these complete fields plus a nonnegative decimal sync_token.
Partial historical captures containing syncToken fail with
incomplete_master_capture_recapture_required; retain them as historical evidence.
Never edit old captures to invent missing fields. Legacy wire schemas 1/2 remain
supported for existing clients; a schema-3 binding cannot downgrade. New production
automation must use complete schema-3 captures.

SOS documents syncToken as the current record version, with older versions rejected
by its update API: https://developer.sosinventory.com/apidoc/Customer and
https://developer.sosinventory.com/apidoc/Vendor (documentation's published JavaScript
bundle was inspected because the pages require JavaScript). We perform GETs only;
no SOS mutation was used to test version increments. Source version takes priority
over capture time for schema 3. Lower versions are stale; equal versions with
different managed business values raise source_revision_conflict; higher versions
update or advance the watermark for unchanged data. Business hashes exclude both
watermarks. The observation watermark never decreases. Local native edits, including
owned children, fail even on duplicate/stale input. Upgrading legacy bindings checks
their old fingerprint and timestamp and refuses adoption of pre-existing new fields.

Native mapping:
- Customer billing or vendor address maps to street/street2/city/zip/country/state.
  Address lines 3–5 use additive SOS fields, preserving each source line separately.
- Customer/vendor masters are independent native commercial partners (is_company).
  A hierarchical master uses native Other Address type and its source parent_id:
  native Contact type otherwise replaces its billing address with the parent's.
  This was reproduced and covered by an Odoo regression. Source person contacts
  become a separately bound native Contact; shipping becomes native Delivery.
  This establishes independent account/address identity; SOS billWithParent behavior
  and transaction accounting semantics remain future work.
- Structured contact components are retained in the binding's managed master_source;
  the native contact name composes the nonempty components in their original order.
- Terms map to native customer/supplier payment terms. Currency maps to a native
  res.currency relation stored as SOS Currency; transaction currency behavior awaits
  the transaction adapters. Company name, alternate phone, fax and vendor account
  number have additive native partner fields and are visible on its form.
- Owned contact/shipping identities are fixed roles under an account/entity/SOS-ID
  binding. They never adopt an existing native contact by name/email. Source removal
  archives an owned child; reappearance reuses that child. Unmanaged children remain
  untouched. Manual edits, moves, deletions or company changes cause conflicts.

Reviewed References configuration maps (account, kind, source_key) to exactly one
native country, state, payment term or currency. No fuzzy/name-based adoption,
implicit country default or reference creation occurs during import. Terms/currency
keys are SOS IDs. Country keys preserve source text. State keys are the exact source
country + '|' + source stateProvince, including an empty country prefix where needed.
A reviewed state mapping can supply its native country; disagreement with a country
mapping fails. Missing/inactive/wrong-company targets fail before partner creation.
Only the mirror configuration group can create mappings; integration users only
read company-scoped mappings. Mappings are immutable and cannot be deleted once
their account has bindings; corrections require a reviewed migration, not a live edit.

Current read-only source evidence (local date October 10; capture UTC date October 11):
295 active customers and 489 vendors were recaptured privately. With the final mapper,
292 customers validate individually, three fail alternate_address_identity_review_required;
all 489 vendors validate including the complete batch graph. Customer batch import
fails before any request, without skipping the three records. Local normalization
does not verify real native reference mappings, tenant/company ownership or production.
Country/terms/currency/state requirements are inventoried privately. The captures'
original readiness metadata remains historical and unchanged.

Alternate addresses have no documented immutable ID in the inspected source. Their
bodies are not silently omitted from an import: nonempty lists explicitly block it.
An approved child-identity strategy remains necessary for the three customers.
Custom-field values need an explicit approved field allowlist/mapping; archival and
deletion of source masters also remain pending. Active-only captures do not authorize
archiving absent master records. Incremental capture, scheduling, all transactions,
dedup/adoption, tenant/company confirmation, merges and production acceptance remain
pending. Pre-cutover is SOS → Odoo only; two-way execution still fails closed.

Validation completed:
- 39 backend tests and four offline Odoo policy tests pass.
- Disposable Odoo 19 upgrade installs the new fields/views/reference model;
  all 28 ORM tests pass, including hierarchical address independence, vendor terms,
  version ordering, references and local edits.
- 20 actual certificate-verified HTTPS scenarios pass using synthetic records only,
  including concurrency, native master fields, source versions and child-edit conflicts.
- Full source GET pagination was checked; first-page recheck still cannot prove an
  atomic multi-page SOS snapshot. No real contacts were imported into Odoo.

The isolated local fixture/API keys are inactive/revoked, temporary TLS/API files
removed, and containers stopped. No NAS deployment, shared upgrade/database migration,
SOS writes or production activation occurred. There is no designated production owner.

Coordination: both feature/sos-odoo-mirror worktrees must merge as a pair. Shared
res.partner extensions/views, commercial identity, company-dependent payment terms,
reference ACL/rules, new bokser_sos_reference table and binding Json/revision columns
overlap with other Odoo/integration work and require merge review. This branch has no
backend business-database/Alembic migration. Preserve original dirty checkouts and
the other local integration/preservation branches; do not merge them wholesale.

Private files outside Git, under Downloads/Bokser_Production_Baseline:
- sos_master_nested_schema_20261010.json contains schema/types only.
- private-sos-master-captures/master_capture_summary_20261010.json points to immutable
  new captures and checksums; master_mapping_assessment_20261010.json holds readiness,
  blocked SOS IDs and reviewed-reference requirements. These are private contact data.
- mirror-runtime-20261009/master_orm_tests_20261010.log and
  master_api_results_20261010.json retain synthetic runtime evidence. Provisioning,
  cleanup and TLS-proxy helpers contain no credentials; regenerate temporary keys
  before another disposable API check. The committed regression script requires the
  owner to provision synthetic reference fixtures 42/11/US/US|NY.

Exact next step: verify current paired repository/deployment state, then implement a
reviewed stable alternate-address identity strategy and the approved custom-field
mapping. Use private reference requirements to prepare reviewable native mappings
after confirming the source tenant and Odoo company. Do not enable/import production
records or apply shared upgrades until one deployment/migration owner is designated.
