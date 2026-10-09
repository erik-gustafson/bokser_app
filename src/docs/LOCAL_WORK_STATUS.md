# Preserved local integration work

This branch captures the original local source as reviewed during October 9 repository alignment. It is not the production baseline and does not enable integrations or apply migrations. Original checkouts and runtime private state are preserved.

Pending work includes the Acenda ship-advice import fields/migration and adapter, Amazon sandbox backend/Compose/schema, catalog/debug edits, and a local removal of the 15-minute SOS shipment selector delay. The timing bypass requires explicit functional review before any rollout. Production application DB remains at f3a91c2d7e60; ab72e1c69043 is a pending child revision.

Local verification: 41 Amazon mocked tests, 10 Acenda ship-advice tests, one Alembic-chain test and three model-metadata tests passed. The older shipment queue suite has one failed disabled-KSP expectation and one invalid numeric REF fixture error; two Acenda JSON-serialization tests also fail. All four outcomes reproduce on unchanged production-source worktree, so they are existing test/behavior discrepancies, not introduced by copying source. This branch is not declared deployment-ready.

No production source/config/services, journal/stock events, Odoo modules or database schema were changed. Keep this branch separate from the deployed baseline; coordinate Acenda model/revision and worker/SOS/config overlap with the mirror session before merges.
