# GC24-05 — Admission apply transaction rollback

**Date:** 2026-09-25
**Worktree:** `codex/isolated-20260924`
**Scope:** deterministic failure injection after a memory write has started in
the staged automatic-memory apply transaction.

## Change

Added `TestAdmissionApplyRollback` regressions to
`tests/unit/test_memory_extraction_worker.py`. The exception test stages a real
user/assistant exchange, completes extraction and classification, then wraps
the production fact-admission function so it performs its normal SQLite writes
and raises before the apply transaction can finish. The process-exit test
runs a child worker which calls `os._exit` immediately after the same fact
write, while SQLite's apply transaction is still open.

The regression proves that the transaction rolls back the memory fact,
associated recall-event write, shadow metadata, and job completion together.
The outer worker then records one bounded retry while preserving the `apply`
stage and both staged payloads. A subsequent worker invocation reopens the
database, completes the retry once, creates exactly one memory/shadow record,
and clears the staged payload. In the child-exit test, SQLite recovery leaves
no partial fact/recall/shadow state and the job remains running at apply with
its payload intact; lease recovery then schedules and completes it once. This
proves abrupt process-exit recovery at the apply transaction boundary only.

A separate parameterized crash test terminates the polling worker immediately
before the per-session commit and immediately after that commit but before the
cursor update. The first case recovers the rolled-back enqueue on replay; the
second reuses the persisted idempotency key on replay. Both advance the cursor
and leave exactly one durable admission job.

Additional child-process tests terminate workers immediately after durable
extract-stage and classify-stage transitions. The extract case reopens at
`classify` with candidates intact; the classify case reopens at `apply` with
both candidate and classification payloads intact. Both resume through apply
and produce one completed memory fact.

The stage-save transaction tests wrap the worker's existing SQLite connection
only in the child process. They allow the `UPDATE` for candidate/classification
data to execute, then exit from the next `commit()` call before SQLite commits.
After reopening, the job remains `running` at its original stage with no
partial transition. Lease recovery returns it to a retryable state, and the
stage is rerun before a single fact is applied. The child environment contains
only the test database path, the automation gate, and `PYTHONNOUSERSITE`.

The terminal-completion crash test exits after the `status='complete'` SQL
update executes but before its transaction commits. On reopen, the completion
update, new fact, and shadow metadata are all absent, while the claimed job is
still `running` at `apply` with both staged payloads. Lease recovery then
reapplies the unit once and clears the payloads.

## Verification

Command:

```text
.venv/bin/python -m pytest tests/unit/test_memory_extraction_worker.py tests/unit/test_memory_admission.py tests/unit/test_memory_automation_acceptance.py -q --tb=short
```

Result: **71 passed** across the worker, admission, and memory-automation
acceptance suites.

After adding the extract/classify stage-restart cases, the complete Python
unit/integration suite passed **2,905 tests, 4 skipped, 11 warnings, and 2
subtests** in 93.70 seconds.
This is evidence for the exact dirty isolated tree at that run, not a clean
main-branch or release result.

Targeted `ruff check --select F,I` on `jarvis/memory_extraction_worker.py`
and `tests/unit/test_memory_extraction_worker.py` passed after import ordering
was corrected. `git diff --check` passed.

## Remaining gates

- Process-kill/reopen for remaining cursor/pairing edge cases and any other
  untested boundaries. Tests now cover exit before terminal completion commit,
  exits before extract/classify stage-save commits,
  immediately after committed extract/classify saves, enqueue rollback before
  commit, committed enqueue before cursor advancement, and interrupted apply.
- Concurrent forget/reclaim/duplicate-worker race coverage beyond the current
  focused stale-claim tests.
- A currently verified confidential production route and route acceptance.
- Mac shadow/benefit observation, staged enablement, rollback drill, and
  observation period.

Production memory classification remains disabled/fail-closed until its route
and staged rollout gates pass. No vault, provider, historical replay, merge,
or deployment was used for this slice.
