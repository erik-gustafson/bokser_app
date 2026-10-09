# Deployed source baseline

The October 9, 2026 read-only audit confirmed NAS production main at 4f5e461c233217203eeb71c26a4ea9416881dfce and core image sha256:32c03aed7555571c5836e9c45d7fc4c7df93fb7038923d71c1df010ae4dcf497. All 192 scanned deployment checkout files matched that committed source; all 144 files shared with the running core worker matched. This document itself is repository documentation, not a deployed source change.

Pending Acenda/Amazon integration source, Acenda revision ab72e1c69043, catalog/debug edits and the SOS delay removal are preserved on feature/local-integration-work-20261009, not part of this deployed baseline. Application DB revision observed was f3a91c2d7e60. Do not deploy the pending branch or apply its migration solely to align Git.

The KSP accepted test milestone is complete as reported in v1.43. Shared five-minute preview remains limited to bokser_test/company 2/synthetic warehouse 85; shared submissions and shipment writes remain off. Retain delivery 170 submitted/unshipped with its acknowledged binding and no package events. Six legacy loader exceptions and OS High findings remain separate open work.

NAS source: /volume1/docker/bokser_app. Actual lake mount: /volume1/docker/data_lake/prod. Active private JSON state, Gmail token and KSP journal remain on protected NAS mounts; do not restore old snapshots. The installed post-receive hook matched nas-hooks/post-receive.production during the audit. Normal production pushes can affect the entire stack.

Source reconstruction and GitHub synchronization do not restart services, change settings, run upgrades or apply migrations. Use isolated worktrees/feature branches, flag overlapping models/config/worker/SOS and migration files with the mirror session, and assign one operations owner before any deployment, Odoo upgrade or shared migration.

## Existing local test discrepancies

On this unchanged production source, shipment-sync tests reproduce one disabled-KSP expectation failure and one numeric REF fixture error. Two Acenda JSON-serialization tests also fail because timestamps remain datetime objects. These pre-existing discrepancies were not repaired in the deployed baseline capture and are separate from reported gateway acceptance.
