# GC24-05 — Simultaneous admission-worker claims

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**State:** concurrency regression implemented and tested in the dirty isolated tree; no production rollout.

## Change

The existing claim test covered two worker connections sequentially. This
increment adds a barrier-synchronized test in which two independent SQLite
connections attempt to claim the same due job at the same time. Exactly one
connection receives the job; after both calls finish, its state is one running
extract claim with the expected claim timestamp. The test exercises the
existing `BEGIN IMMEDIATE` single-owner transaction without changing queue
semantics or adding a process-specific lock.

The companion [apply claim-fencing receipt](GC24-05-admission-apply-claim-fencing-2026-09-25.md)
proves a lease-replaced stale apply owner cannot write while the replacement
claim applies once.

## Verification

- Focused memory admission/worker/acceptance suite:
  `.venv/bin/python -m pytest tests/unit/test_memory_extraction_worker.py tests/unit/test_memory_admission.py tests/unit/test_memory_automation_acceptance.py -q --tb=short` — **74 passed**.
- Full Python unit/integration suite:
  `.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` —
  **2,908 passed, 4 skipped, 11 warnings, and 2 subtests passed**.
- Ruff `F`/`I` checks for touched worker/test files — passed.
- `git diff --check` — passed.

These results cover the current dirty isolated snapshot only. They do not prove
multi-process production behavior, concurrent forget/reclaim ordering,
confidential provider capability, Mac rollout, or release acceptance.
