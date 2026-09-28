# GC24-02 — Supervisor late provider response after cancellation

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**State:** one direct voice-Supervisor cancellation boundary is implemented
and tested; GC24-02 remains open.

## Change

The live Orchestrator now checks whether its task has a pending cancellation
immediately after an awaited provider completion and before it records or
commits the assistant reply. This handles adapters that absorb cancellation
and return a late response: the response is not logged as a completion, added
to conversation history, or persisted as an assistant turn. The original user
turn remains recorded. No voice model, provider route, transport, tool
permission, or response routing changed.

This receipt covers provider completion only. It does not establish safe
reconciliation of mutations from a tool that absorbs cancellation, cancellation
across every caller, or full request lifecycle ownership.

## Verification

- `.venv/bin/python -m pytest tests/unit/test_orchestrator.py tests/unit/test_supervisor_tool_registration.py -q --tb=short`
  — **37 passed**, 2 dependency deprecation warnings.
- `.venv/bin/ruff check --select F,I jarvis/agents/supervisor.py tests/unit/test_orchestrator.py`
  — passed.
- `git diff --check` — passed.
- `.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
  — **2,913 passed, 4 skipped, 11 warnings, and 2 subtests passed** in 95.29s.

## Remaining GC24-02 work

Continue caller-by-caller cancellation and late-write audit, including
tool-side unknown mutation identity/reconciliation, complete tool/artifact
ownership, and current-candidate voice frame-to-result acceptance. Keep the
existing RTVI transcript-to-result path as the sole live voice result path.
