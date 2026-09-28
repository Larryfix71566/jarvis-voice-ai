# GC24-03 receipt — client app-message log redaction

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** residual diagnostic slices F20–F21 only.

The `voice/set` handler no longer prints the client-supplied voice value, and
the `ui/noop` handler no longer prints the client-supplied spoken reason. A
closed mapping emits only `[appmsg] voice_set_received` or
`[appmsg] ui_noop_received`; unknown message types produce no log event.
Voice catalog validation, current-voice reconciliation, TTS settings, the
existing reason length guard, and the exact reason passed to TTS are unchanged.

Validation on this dirty isolated snapshot:

- `./.venv/bin/python -m pytest tests/integration/test_bot_wiring.py -q --tb=short` — **52 passed**, **2 dependency deprecation warnings**.
- `./.venv/bin/ruff check --select F,I jarvis/bot/pipeline.py tests/integration/test_bot_wiring.py` — passed.
- `./.venv/bin/python -m compileall -q jarvis/bot/pipeline.py tests/integration/test_bot_wiring.py` — passed.
- `git diff --check -- jarvis/bot/pipeline.py tests/integration/test_bot_wiring.py` — passed.

This closes only these two stdout fields and the static event mapping. It is
not a full end-to-end client-message/TTS privacy audit. The worktree contains
many concurrent dirty changes; this is not a clean-commit, live Mac, provider,
deployment, or release acceptance.
