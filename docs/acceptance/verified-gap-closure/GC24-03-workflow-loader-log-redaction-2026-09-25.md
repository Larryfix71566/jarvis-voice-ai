# GC24-03 receipt — workflow loader diagnostics redacted

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** residual diagnostic-log plan slice F5 only.

Malformed workflow YAML now logs only a bounded exception class; invalid
workflow structure logs a fixed reason without the local path. Canary tests
verify source content and paths do not reach logs, valid workflows still load,
and invalid files remain skipped so they do not disable the rest of the
workflow set. Workflow matching and execution behavior are unchanged.

Validation:

- `./.venv/bin/python -m pytest tests/unit/test_workflows.py -q --tb=short` — **22 passed**.
- `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` — **3,043 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- `./.venv/bin/ruff check --select F,I jarvis/workflows.py tests/unit/test_workflows.py` — passed.
- `git diff --check` — passed.

This closes only F5 workflow-loader diagnostic paths. Workflow prompt and
data-flow policy remain open under GC24-03.
