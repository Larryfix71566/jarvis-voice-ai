# GC24-05 — Fence stale automatic-memory admission workers

**Status:** Implemented and tested in the isolated worktree; production
classification remains fail-closed pending a verified confidential route.

**Worktree:** `codex/isolated-20260924`  
**Base/current HEAD:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Changed source/tests:** `jarvis/memory_admission.py`,
`jarvis/memory_extraction_worker.py`, `tests/unit/test_memory_admission.py`

## Gap and change

Admission jobs are reclaimed after a worker claim lease expires. Before this
change, stage transitions matched only job ID, `running` status, and stage. A
slow worker whose lease had been reclaimed could therefore return later and
write output into a replacement worker's claim.

The claim's existing `claimed_at` value now acts as a fencing token. The
worker passes its claim timestamp to extraction/classification saves, budget
deferral, retry/failure, and atomic completion. Updates compare the timestamp
in the same SQL predicate as job ID/status/stage. Reclamation also compares
the timestamp it selected, so it cannot fail a newer claim. Cancellation
still invalidates all claims for the affected source as before. No schema,
provider, event, or memory-store change was added.

Regression tests close/reopen the database, reclaim a stale extract or
classify claim, start a replacement claim, and prove the old worker cannot
commit output or change retry state while the new worker can proceed.

## Verification

- `.venv/bin/python -m pytest tests/unit/test_memory_admission.py tests/unit/test_memory_extraction_worker.py tests/unit/test_memory_automation_acceptance.py -q --tb=short` — **62 passed**.
- `.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` — **2,896 passed, 4 skipped, 11 warnings, 2 subtests**.
- `.venv/bin/ruff check --select F,I jarvis/memory_admission.py jarvis/memory_extraction_worker.py tests/unit/test_memory_admission.py` — passed.
- `git diff --check` — passed.

## Remaining limits

This closes the stale-worker write race for fenced transitions and adds
simulated restart coverage for extract/classify claims. It is not a process
kill test at every database boundary. Apply-stage rollback under forced
mid-transaction failure, the verified confidential provider route, shadow
and staged Mac acceptance, and production rollout remain open. Production
memory admission remains fail-closed until its route gate is independently
verified.
