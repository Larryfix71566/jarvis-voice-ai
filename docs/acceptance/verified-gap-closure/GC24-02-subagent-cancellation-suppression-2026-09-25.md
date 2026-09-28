# GC24-02 — SubAgent cancellation suppresses returned provider/tool values

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; shared tree remains dirty.  
**State:** one SubAgent cancellation-suppression slice implemented and tested; GC24-02 remains open.

## Change

The SubAgent multi-round loop now checks whether its current task has a pending
cancellation immediately after each provider completion and registered-tool
call, before usage/run-log writes, result activity events, or another provider
round. This protects against an adapter that catches `CancelledError` during
cleanup and returns a late value anyway. It also checks before dispatching
each tool in a parallel-call batch.

Regressions prove that a provider which absorbs cancellation cannot start the
tool it returned, and a tool which absorbs cancellation cannot publish its
result or start a second provider round. Existing cancellation behavior and
delegate-card ownership are retained.

This does not undo a side effect already performed inside a mutating tool,
prove cancellation semantics for every provider/tool adapter, or reconcile an
unknown tool outcome after process failure. Those remain open GC24-02 work.

## Verification

- Focused SubAgent suite: **62 passed**.
- SubAgent, run-log, run-log integration, and bot-wiring suites: **128 passed, 2 warnings**.
- Full Python unit/integration suite:
  `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
  — **2,889 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- Ruff `F`/`I` for `jarvis/agents/base.py` and `tests/unit/test_subagent.py`: passed.
- `git diff --check`: passed.

This is isolated dirty-tree evidence only. It does not prove provider-wide
cancellation, mutation rollback/reconciliation, production delta consumption,
Mac behavior, merge, deployment, or release acceptance.
