# GC24-05 — Apply-stage claim fencing

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**State:** implementation and tests in the dirty isolated tree; not merged or enabled in production.

## Change

The durable memory worker now passes the apply job's captured `claimed_at`
value into the atomic apply transaction. The transaction selects only the
running apply row with that exact claim. If a lease has been recovered and
another worker owns the replacement claim, the stale worker rolls back before
reading source evidence or writing a memory fact, shadow row, or completion
state. The current claim can still apply and complete normally.

The regression stages a real exchange through extraction and classification,
claims its apply stage, expires and reclaims the lease, and invokes apply using
the old and replacement claim timestamps. It asserts that the old claim writes
nothing, the replacement claim remains running and intact, and the current
claim writes one memory record and completes the job once.

## Verification

- Focused memory admission/worker/acceptance suite:
  `.venv/bin/python -m pytest tests/unit/test_memory_extraction_worker.py tests/unit/test_memory_admission.py tests/unit/test_memory_automation_acceptance.py -q --tb=short` — **74 passed**.
- Full Python unit/integration suite:
  `.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` —
  **2,908 passed, 4 skipped, 11 warnings, and 2 subtests passed**.
- Ruff `F`/`I` checks on the worker and test file — passed.
- `git diff --check` — passed.

These counts describe the current dirty isolated snapshot. They are not clean
commit, Mac candidate, confidential provider route, or release evidence.

## Remaining GC24-05 work

This closes the stale apply-owner gap only. Broader multi-process duplicate
worker proof and concurrent forget/reclaim races across apply, verified
confidential route evidence, shadow/benefit observation, and staged Mac
enablement and rollback remain open. Production classification remains
fail-closed until the route and rollout gates pass.
