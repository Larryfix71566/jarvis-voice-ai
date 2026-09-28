# GC24-03 receipt — knowledge-base diagnostics redacted

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** residual diagnostic-log plan slices F2 and F7 only.

Unreachable-KB diagnostics retain the event and bounded exception class while
omitting the configured endpoint and backend exception body. Rejected writes
retain a stable event while omitting the scanner reason and document ID.
Connection failure returns and write-rejection behavior are unchanged.

Validation:

- `./.venv/bin/python -m pytest tests/unit/test_mcp_kb_logic.py -q --tb=short` — **13 passed**.
- `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` — **3,039 passed, 4 skipped, 11 warnings, 2 subtests passed** on the same accumulated source snapshot.
- `./.venv/bin/ruff check --select F,I mcp_servers/mcp_kb/logic.py tests/unit/test_mcp_kb_logic.py` — passed.
- `git diff --check` — passed.

This receipt closes only F2 and F7 logging. Knowledge-base data flow,
fallback behavior outside these tested error paths, and the wider GC24-03
source-to-sink audit remain open.
