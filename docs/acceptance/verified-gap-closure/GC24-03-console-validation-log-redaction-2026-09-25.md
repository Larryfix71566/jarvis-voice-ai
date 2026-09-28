# GC24-03 receipt — console validation diagnostics redacted

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** residual diagnostic-log plan slice F6 only.

Console validation diagnostics use fixed rejection events and do not format
client-supplied values or `ValueError` content. Canary tests exercise the
actual inventory validator and prove rejected inventory is not applied; they
also exercise `ConsoleSession.accept` for a malformed request and prove the
action callback is not called and the invalid field is not echoed. Focused
helper tests separately prove both validation rejection event names remain
observable. Accepted console behavior is unchanged.

Validation:

- `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/integration/test_bot_wiring.py tests/unit/test_agent_events.py tests/unit/test_console_protocol.py -q --tb=short` — **78 passed, 2 dependency warnings**.
- `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` — **3,045 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- `./.venv/bin/ruff check --select F,I jarvis/bot/pipeline.py tests/integration/test_bot_wiring.py` — passed.
- `git diff --check` — passed.

This closes only the tested console-validation diagnostic and no-dispatch
paths. Broader console authorization, privacy, and source-to-sink checks stay
open under GC24-03.
