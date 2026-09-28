# GC24-05 — Shared atomic classifier-budget reservations

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; working tree remains dirty.  
**State:** reservation ledger and existing maintenance-worker integration implemented; admission-stage integration remains open.

## Change

Migration `0026_memory_classification_budget` adds a durable reservation
ledger and a reservation link on `memory_maintenance`. The existing
`process_classification_jobs` now reserves one call and its candidate count
atomically before invoking the configured classifier. SQLite's
`BEGIN IMMEDIATE` serializes competing workers. If the shared daily limit
would be exceeded, claimed maintenance rows return to `queued` without
consuming retry attempts. Existing pre-migration maintenance rows remain
counted as legacy usage; reserved rows are counted once through the ledger.

This is only the shared-budget foundation. The durable
`memory_admission_jobs` stages do not yet call this reservation API, and the
exchange worker/teardown are still not wired to enqueue and resume those
stages. Do not report GC24-05 complete or enable live admission on this
receipt.

## Validation

- `tests/unit/test_db.py`, `tests/unit/test_memory_automation.py`,
  `tests/unit/test_memory_automation_acceptance.py`, and
  `tests/unit/test_memory_admission.py`: **74 passed** at initial focused run;
  after adding the tenant-schema assertion, the equivalent set plus
  `tests/unit/test_tenant_columns.py` passed **75 tests**.
- Regression coverage verifies legacy/reserved usage aggregation, two
  independent connections sharing a quota, and two concurrent workers being
  unable to consume the last call twice.
- Ruff `F`/`I` on changed Python/test files — passed.
- `git diff --check` — passed.
- Temporary SQLite databases only; no live provider, vault, Mac runtime, or
  production database was accessed.
- Complete Python unit/integration run after the schema fix:
  **2,850 passed, 4 skipped, 11 warnings, 2 subtests passed**.

## Next

Use this reservation API from the durable exchange-admission classifier stage
before its provider call; then implement extraction/teardown enqueue-before-
cursor plus resumable extract/classify/apply and re-run crash/race tests.
