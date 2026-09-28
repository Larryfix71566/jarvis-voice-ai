# GC24-02 — Shared execution tool-result lifecycle event

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**State:** implemented and tested in the dirty isolated tree; no Mac candidate or release claim.

## Change

The shared execution boundary already validated tool results in the request
context and emitted `tool_request` metadata for tool calls returned by a
provider. It did not emit the matching `tool_result` lifecycle event when the
caller returned with validated tool-result context on the next model round.
The boundary now emits one identity-only `tool_result` event for each such
context item after admission and before the next provider request. The event
contains task and parent request IDs, tool-call ID/name, sequence, and the
strictest effective data policy. It does not contain result text or arguments.

Tool execution remains owned by the existing caller and registered action
path. No provider tool authority, second result store, or new streaming UI
consumer was added. No current production caller opts into `stream_text`; the
separate voice RTVI transcript path remains the existing streaming-to-results
path. Keep a generic event consumer conditional on an inventoried caller that
actually needs it.

## Verification

- `.venv/bin/python -m pytest tests/unit/test_model_execution.py -q --tb=short` —
  **38 passed**.
- `.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` —
  **2,909 passed, 4 skipped, 11 warnings, and 2 subtests passed**.
- Ruff `F`/`I` checks on the execution boundary and its unit tests — passed.
- `git diff --check` — passed.

The result covers the dirty isolated source snapshot. It does not prove the
full caller lifecycle, live voice/result-pane behavior, Mac candidate,
provider capability, or release acceptance.
