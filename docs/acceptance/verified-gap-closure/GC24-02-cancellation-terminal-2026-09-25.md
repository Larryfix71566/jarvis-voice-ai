# GC24-02 — SubAgent cancellation terminal record

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; shared working tree remains dirty.  
**State:** SubAgent run-log cancellation slice implemented and tested; GC24-02 remains open.

## Change

When a caller cancels `SubAgent.run()`, the SubAgent now writes a fixed,
content-free terminal reply, persists `cancelled` as the run status, and
re-raises `asyncio.CancelledError`. The run-log status derivation and CLI
filter accept this terminal status.

An integration test cancels during an active registered-tool call and verifies
that cancellation reaches the tool coroutine, the run record finishes as
`cancelled`, no second provider round starts, and no `agent_done` success event
is emitted. This demonstrates cancellation propagation through this tested
SubAgent/tool path only. It does not prove an already-running mutating action
was rolled back or safely reconciled.

## Validation

- Focused run-log/SubAgent/integration suite:
  `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit/test_runlog_store.py tests/unit/test_subagent.py tests/integration/test_runlog_end_to_end.py -q --tb=short`
  — **92 passed**.
- Full Python unit/integration suite:
  `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
  — **2,870 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- Ruff `F`/`I` on the touched cancellation/run-log Python files — passed.
- `git diff --check` — passed.
- Plan manifest suite — **7 passed**.
- `RUN_LIVE=0 .venv/bin/python scripts/audit_model_call_sites.py --require-covered`
  — **26/26 covered, zero review-required, secret-free**.

No provider, network, vault, live database, installed Mac candidate, or
production memory setting was used. These are isolated dirty-tree results, not
merge, deployment, or release evidence.

## Remaining GC24-02 work

The terminal run record is not a full execution lifecycle. Still required:
one production consumer for validated model events; exactly one terminal
across complete provider/tool loops; artifact/tool-result event ownership;
late-output and durable-write suppression across cancellation/timeout; and
idempotent reconciliation for unknown mutating-tool outcomes. GC24-03 source-
to-sink acceptance also remains open.
