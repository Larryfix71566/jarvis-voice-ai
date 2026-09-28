# GC24-03 receipt — missing vault path redacted

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** residual diagnostic-log plan slice F12 only.

When the configured local vault file is absent, the startup event remains
visible without printing the filesystem path. Secret injection continues to
return zero and leaves environment fallback behavior unchanged.

Validation:

- `./.venv/bin/python -m pytest tests/unit/test_tenant.py tests/unit/test_vault.py tests/unit/test_usage_ledger.py -q --tb=short` — **39 passed**.
- `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` — **3,045 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- Ruff `F`/`I` and `git diff --check` — passed.

This closes only F12; vault encryption, keychain access, and secret-handling
acceptance remain separate requirements.
