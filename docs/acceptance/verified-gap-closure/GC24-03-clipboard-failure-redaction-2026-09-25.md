# GC24-03 receipt — clipboard failure output redacted

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** residual diagnostic-log plan slice F9 only.

Clipboard clear/read failures retain exit-code diagnostics and return static
user-facing errors. Subprocess stdout is omitted from logs and tool results,
including partial clipboard data from failed reads. The existing explicit
clear-to-arm, one-read-per-arm, and disarm-on-failure behavior remains intact.

Validation:

- `./.venv/bin/python -m pytest tests/unit/test_clipboard.py -q --tb=short` — **28 passed, 1 dependency warning**.
- `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` — **3,045 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- `./.venv/bin/ruff check --select F,I jarvis/clipboard.py tests/unit/test_clipboard.py` — passed.
- `git diff --check` — passed.

This closes only clipboard failure-output sinks; clipboard data-flow policy
and memory/transcript exclusion acceptance remain separate requirements.
