# GC24-03 receipt — transcript-content log redaction

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** residual diagnostic slice F25 only.

The persistent bot stdout logger previously printed ordinary user and
assistant transcript text. The `scripts/mortimer.sh` launch path captures
bot stdout/stderr in `logs/bot.log`, making those messages persistent. The
logger now emits the existing `USER:` / `MORTIMER:` marker, timing fields,
and a character count without transcript content. This preserves the
existing spoken-acceptance and latency marker format. Ordinary
non-sensitive transcript rows continue to be persisted for memory; the
existing sensitive-turn guard continues to suppress persistence. UI
delivery and response behavior are unchanged.

Synthetic canaries verify that both roles' text is absent from captured
stdout and still present in the ordinary conversation database rows. A
separate sensitive-turn test verifies suppression and confirms assistant
content does not leak to stdout.

Validation on this dirty isolated snapshot:

- `./.venv/bin/python -m pytest tests/unit/test_sensitive_turn.py tests/integration/test_bot_wiring.py tests/unit/test_latency_probe.py -q --tb=short` — **75 passed**, **2 dependency deprecation warnings**.
- `./.venv/bin/ruff check --select F,I jarvis/bot/transcript_log.py tests/unit/test_sensitive_turn.py tests/integration/test_bot_wiring.py scripts/spoken_acceptance.py` — passed.
- `./.venv/bin/python -m compileall -q jarvis/bot/transcript_log.py tests/unit/test_sensitive_turn.py tests/integration/test_bot_wiring.py scripts/spoken_acceptance.py` — passed.
- `git diff --check` — passed.
- `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` — **3,025 passed, 4 skipped, 11 warnings, 2 subtests passed** in 99.55 seconds on the accumulated Python snapshot after F25.

This closes only the transcript-content stdout sink. It does not audit or
close transcript flow through the database, providers, tools, memory,
display, copy/share/export, or telemetry. The full GC24-03 source-to-sink
review remains open. The tree contains many concurrent dirty changes; this
is not a clean-commit, installed-Mac, live-provider, deployment, or release
acceptance. The full suite covers the accumulated Python source/tests before
this receipt-only documentation update; no Python source changed afterward.
