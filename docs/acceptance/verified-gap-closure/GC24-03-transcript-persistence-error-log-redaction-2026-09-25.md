# GC24-03 receipt — transcript persistence error redaction

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** residual diagnostic slice F19 only.

`jarvis.bot.transcript_log._persist` previously printed the raw database
exception to stdout. The supported launcher captures that output in the bot
log. The failure line now retains only the stable event and bounded exception
class. Persistence remains best-effort, with the existing fail-closed
sensitive-turn guard and audio behavior unchanged. A synthetic exception
message canary verifies that the failure is still visible and its message is
not emitted. Import ordering in the two touched files was also normalized so
the configured F/I lint check could be run cleanly.

Validation on this dirty isolated snapshot:

- `./.venv/bin/python -m pytest tests/unit/test_sensitive_turn.py tests/integration/test_bot_wiring.py -q --tb=short` — **68 passed**, **2 dependency deprecation warnings**.
- `./.venv/bin/ruff check --select F,I jarvis/bot/transcript_log.py tests/unit/test_sensitive_turn.py` — passed.
- `./.venv/bin/python -m compileall -q jarvis/bot/transcript_log.py tests/unit/test_sensitive_turn.py` — passed.
- `git diff --check -- jarvis/bot/transcript_log.py tests/unit/test_sensitive_turn.py` — passed.

This closes only the raw exception-message field in the transcript
persistence failure diagnostic. It does not close transcript content data
flow or the broader GC24-03 source-to-sink audit. The worktree contains many
concurrent dirty changes; this is not a clean-commit, live Mac, provider,
deployment, or release acceptance.
