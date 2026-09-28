# GC24-03 receipt — screen capture and pruning log redaction

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base/HEAD at start:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**State:** verified in the dirty isolated tree; concurrent route and shared-
content work in the same files was preserved.

## Change

Screen-retention, prune, low-confidence retention, capture, route, and model
failure logs now omit raw environment values, local directories and image
paths, display identifiers, provider/model response text, questions, and
tracebacks. Successful and low-confidence captures log only outcome,
bounded counts/thresholds, and latency; failure logs retain the event,
outcome, and bounded exception class. Existing result values, capture-file
cleanup, low-confidence retention, and pruning behavior are unchanged.

## Verification

- `./.venv/bin/pytest -q tests/unit/test_mcp_screen_logic.py --tb=short`
  — **28 passed**.
- `./.venv/bin/ruff check --select F,I mcp_servers/mcp_screen/logic.py tests/unit/test_mcp_screen_logic.py`
  — passed.
- `./.venv/bin/python -m compileall -q mcp_servers/mcp_screen/logic.py tests/unit/test_mcp_screen_logic.py`
  — passed.
- `git diff --check` — passed.
- Canary tests cover successful and low-confidence response logs, capture
  errors, prune and retention-write errors, and malformed retention settings.
  They assert that question/answer text, paths, display IDs, raw settings,
  exception messages, and traceback data do not reach captured logs.
- A source search found no `logger.exception`, `exc_info=True`, raw answer,
  path, retention-value, or exception-message fields in this module's logs.

## Still open

The existing low-confidence image retention behavior remains unchanged and
needs review in the broader screen-data retention/source-to-sink audit. This
receipt does not prove screen-content route eligibility, persistence, or
result-display privacy. Slice E and the full GC24-03 audit remain open. No
live screen permission, display, provider, installed Mac, deployment, or
release check was run.
