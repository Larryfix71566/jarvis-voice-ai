# GC24-03 receipt — usage-ledger diagnostics redacted

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** residual diagnostic-log plan slice F13 only.

Usage debug output now contains normalized token/cache counters only. Unknown
rung warnings are static while the original rung is still recorded in the
ledger. Persistence failures log only a bounded exception class. Canary tests
cover provider usage fields, user-controlled rung labels, and DB error/path
details; ledger persistence behavior remains best-effort.

Validation:

- `./.venv/bin/python -m pytest tests/unit/test_tenant.py tests/unit/test_vault.py tests/unit/test_usage_ledger.py -q --tb=short` — **39 passed**.
- `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` — **3,045 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- Ruff `F`/`I` and `git diff --check` — passed.

This closes only F13 diagnostic output. Usage completeness, cost attribution,
and provider billing evidence remain open under GC24-04.
