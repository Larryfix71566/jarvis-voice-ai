# GC24-03 receipt — knowledge-base digest diagnostics redacted

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** residual diagnostic-log plan slice F10 only.

Digest empty/rejected/write/flush diagnostics no longer include session IDs,
scanner reasons, provider/KB error text, digest content, or tracebacks. A
bounded exception class remains on the best-effort outer failure path. Tests
verify failure and rejection events remain visible, the private canaries stay
out of logs, the KB flush still runs after failures, and digest failure still
returns `False` without breaking the pipeline.

Validation:

- `./.venv/bin/python -m pytest tests/unit/test_kb_digest.py -q --tb=short` — **9 passed**.
- `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` — **3,045 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- `./.venv/bin/ruff check --select F,I jarvis/kb_digest.py tests/unit/test_kb_digest.py` — passed.
- `git diff --check` — passed.

This closes only the listed digest diagnostic sinks; full KB/prompt/provider
data-flow and persistence privacy remain open under GC24-03.
