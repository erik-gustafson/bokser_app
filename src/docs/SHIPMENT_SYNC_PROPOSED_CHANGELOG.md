# Proposed shipment sync changes

Date: 2026-09-08  
Status: Implemented locally after review; not deployed.

## Implementation outcome

- Queue attempts are atomically claimed as `processing` and committed before posting. Completion and failures are saved in separate per-item transactions. An interrupted attempt remains held rather than becoming eligible for another automatic post.
- Success is recorded as `sent`; failures before posting or explicit client-error responses are recorded as `failed`. Timeouts, server errors, malformed success responses, and persistence errors after posting are held as `reconcile` when that status can be saved.
- Completed shipments with changed source payloads are held as `reconcile`. Identical imports preserve their status, shipment ID, and attempt history. Failed records are not automatically retried, including after a changed import.
- KSP mapping is executable for testing, with corrected date handling and empty-item validation. KSP remains excluded from normal queue selection, so posting is still disabled.
- Sutton's enqueue path now uses `invoice` instead of the placeholder `column_name` and shares the warehouse duplicate-prevention policy.
- Shipment client automatic retries are disabled to avoid replaying uncertain POST requests. This client instance also performs shipment lookup GET requests, which now use the same single-attempt policy.
- Shipment IDs are validated from either `data.id` or a top-level `id`. This is covered with mocked responses; no live shipment-create response was captured.
- Validation: 13 new regression tests and 16 existing Sutton/SOS tests pass. The async database tests use isolated SQLite with `aiosqlite` (listed in `tests/requirements.txt`) and mocked SOS calls. They do not validate PostgreSQL locking under concurrent workers.
- No live queue records were changed, KSP was not enabled, and no deployment was performed. Existing pending records still need reconciliation before replay.

The sections below retain the reviewed proposal and its rationale. The conservative reconciliation policy above was selected for changed completed shipments and uncertain outcomes; no automatic replay policy was added.

Shipment posts can succeed in SOS while their local queue records remain pending. The primary cause is that queue records are loaded in a session that closes before processing. A different session commits without tracking those records. A local reproduction confirmed that assigning `sent` and incrementing attempts leaves the stored record at `pending` with zero attempts.

## 1. Persist queue completion and failures

File: `src/worker/jobs/push_data/sos/sos_shipment_sync.py`

- Load each queue record in the session responsible for updating it.
- Persist the successful shipment ID, `status="sent"`, attempt count, timestamp, and cleared error together.
- Commit each completed queue item so a later item's failure does not roll back earlier completion records.
- After a database failure, roll back before recording the failure using a valid transaction.
- Keep `sent` as the completion status; no new `done` status is proposed.

Expected behavior: a successful post removes that row from the pending selection. Failure details also survive the session closing.

An SOS post and a database commit cannot be atomic. If SOS accepts a shipment but local persistence fails, log that outcome distinctly for reconciliation rather than treating it as proof that posting failed. Per-item commits reduce this window but do not eliminate it.

## 2. Correct the KSP path before enabling it

File: `src/worker/jobs/push_data/sos/sos_shipment_sync.py`

- Serialize the original shipment date once for the header. The previous commented path serialized an ISO string again, causing `TypeError: combine() argument 1 must be datetime.date, not str`.
- Validate that shipment details and item lines exist before accessing their first elements.
- Apply the same completion and failure persistence as the active sources.
- Keep KSP posting disabled until its fixes and validation have been reviewed. Making the commented code correct does not itself authorize activating KSP posting.

Expected behavior when enabled: valid KSP shipments reach posting; incomplete data produces a recorded failure instead of an indexing or date-conversion exception.

## 3. Prevent unchanged imports from reopening completed work

File: `src/worker/jobs/process_data/warehouses/process_shipment_data.py`

- Compare the incoming payload hash with the existing queue hash before resetting queue state.
- Preserve `sent`, the SOS shipment ID, and attempt history when the same payload is imported again.
- Do not automatically create another SOS shipment when a previously sent source changes. Route that case for reconciliation until an update policy is agreed.
- Review the equivalent unconditional reset in Sutton's `post_sales_report_to_sos_ship_sync()` so the same behavior is consistent across sources.

Expected behavior: repeated ingestion of identical KSP or Productiv data does not trigger duplicate shipment creation.

Review decision: define how changed payloads for already sent shipments should be handled—update the existing SOS shipment, create an additional shipment where appropriate, or require manual reconciliation. The implementation must not silently choose new-shipment creation.

## 4. Record failures and disabled-source skips clearly

File: `src/worker/jobs/push_data/sos/sos_shipment_sync.py`

- Persist an actionable error for missing source records, missing or ambiguous sales orders, invalid mapping, missing templates, and empty shipment lines.
- Count each processing attempt consistently and record its timestamp.
- Exclude intentionally disabled KSP work from active processing while leaving it available for later activation.
- Make logs distinguish posting success, committed queue completion, processing failure, and an uncertain outcome after a post.

Expected behavior: rows no longer remain silently pending after an attempted processing failure. Disabled KSP work is not reported as an invalid source on every run.

Review decision: the current selector processes only `pending` records. Recording `failed` therefore requires an explicit retry/reset policy; no automatic retry of failed or uncertain posts is included in this proposal.

## Validation before deployment

- A successful mocked SOS post persists `sent`, the shipment ID, timestamp, and one attempt.
- A failed post and a mapping failure persist their errors without losing earlier successful records.
- Re-running the worker does not repost a completed record.
- Re-importing an unchanged warehouse payload preserves completion.
- Changed payloads for sent records follow the reviewed reconciliation policy.
- The KSP path accepts valid dates and handles empty details/items without indexing errors, while remaining disabled in normal execution.
- A simulated local commit failure after SOS success produces a distinguishable reconciliation log.
- Confirm the actual SOS shipment-create response structure before finalizing shipment-ID extraction; the current code reads a top-level `id` and has not yet been validated against a captured response.

Tests should use isolated database records and mocked SOS calls, with no live shipment creation.

## Deployment and existing queue records

- Rebuild the production image and recreate the worker to load the changes.
- The session and date fixes do not require a schema migration. Any later schema changes for retries or reconciliation should be reviewed separately.
- Reconcile existing pending records against SOS before replaying them: some may already have been posted while their local updates were lost.
- Do not bulk reset, mark sent, delete, or replay existing queue records as part of these code fixes.

The fixes described in the implementation outcome are now present locally. Deployment and existing queue reconciliation remain separate actions.
