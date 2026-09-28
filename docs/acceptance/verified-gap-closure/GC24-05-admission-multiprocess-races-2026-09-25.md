# GC24-05 — Automatic-memory multi-process race coverage

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**State:** three cross-process SQLite race regressions implemented and passing;
GC24-05 remains open.

## Coverage added

1. Two independently spawned worker processes synchronize and attempt to
   claim the same due admission job. Exactly one receives the job, and the
   persisted row remains in one running extract claim.
2. A spawned apply worker pauses inside its SQLite transaction after inserting
   a validated fact. A second spawned process issues a forget while apply is
   holding the write transaction. Once apply commits, forget removes the
   admitted fact. Both operations report success, no fact remains, and the
   admission job retains its completed idempotency receipt.
3. A spawned worker attempts to reclaim an expired claim while another
   spawned process forgets the staged key. Regardless of which serialized
   transaction runs first, the job ends cancelled, its claim and staged
   payloads are cleared, and lease recovery cannot revive forgotten work.

The tests use a temporary SQLite database and synthetic source exchange. They
do not contact a provider or use production memory data. These prove the
tested process-level serialization and claim behavior, not production route
privacy or runtime deployment.

## Verification

- `.venv/bin/python -m pytest tests/unit/test_memory_admission.py tests/unit/test_memory_extraction_worker.py tests/unit/test_memory_automation_acceptance.py -q --tb=short`
  — **77 passed**.
- All three spawned-process race tests pass together.
- `.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
  — **2,912 passed, 4 skipped, 11 warnings, and 2 subtests passed** in 94.60s.
- `.venv/bin/ruff check --select F,I tests/unit/test_memory_admission.py tests/unit/test_memory_extraction_worker.py` — passed.
- `git diff --check` — passed.

## Remaining GC24-05 gates

Verify an eligible confidential model/route before production classification,
complete the planned shadow and benefit/cost observation, then perform staged
Mac acceptance with the existing rollout and rollback thresholds. Production
classification remains fail-closed until those gates pass.
