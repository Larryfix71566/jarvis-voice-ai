# GC24-03 receipt — tenant identity diagnostic redacted

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** residual diagnostic-log plan slice F11 only.

Invalid `JARVIS_USER_ID` values still fall back to `local`; the warning now
records only the fixed event and fallback flag. The invalid value is not
written to logs.

Validation:

- `./.venv/bin/python -m pytest tests/unit/test_tenant.py tests/unit/test_vault.py tests/unit/test_usage_ledger.py -q --tb=short` — **39 passed**.
- `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` — **3,045 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- Ruff `F`/`I` and `git diff --check` — passed.

This closes only F11; tenant isolation and the broader privacy model are
separate open requirements.
