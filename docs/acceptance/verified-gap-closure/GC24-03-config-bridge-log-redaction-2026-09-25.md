# GC24-03 receipt — configuration bridge diagnostic redacted

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** residual diagnostic-log plan slice F4 only.

When typed settings cannot be loaded, the bridge logs the exception class
without its message, path, or configuration value. Its best-effort dotenv
fallback and `setdefault` precedence remain unchanged. A canary test asserts
the fallback still applies while private path/value strings are absent from
the log.

Validation:

- `./.venv/bin/python -m pytest tests/unit/test_config.py -q --tb=short` — **17 passed**, **8 existing degraded-Tavily warnings**.
- `./.venv/bin/ruff check --select F,I jarvis/config.py tests/unit/test_config.py` — passed.
- `./.venv/bin/python -m compileall -q jarvis/config.py tests/unit/test_config.py` — passed.
- `git diff --check` — passed.

This closes only F4. Settings validation, configuration transport,
environment scoping, and the wider GC24-03 privacy audit remain open.
