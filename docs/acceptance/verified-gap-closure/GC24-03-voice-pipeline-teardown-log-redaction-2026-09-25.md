# GC24-03 receipt — voice-pipeline teardown log redaction

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**State:** code and tests verified in the dirty isolated tree; full privacy
source-to-sink and candidate acceptance remain open.

## Change

The voice-pipeline shutdown path had five best-effort exception catches that
used traceback logging: session memory extraction, memory admission,
automated-memory drain, KB digest, and STT usage-ledger recording. Exceptions
from model, database, or content processing can carry provider/backend
details or derived user data. These catches now use `_log_best_effort_failure`,
which records only the event name, exception class, and opaque session ID.
The six existing startup best-effort catches use the same helper. Shutdown
continues to be best-effort and non-blocking.

## Verification

- `./.venv/bin/pytest -q tests/integration/test_bot_wiring.py` — **44
  passed**.
- `./.venv/bin/pytest -q tests/unit tests/integration` — **2,972 passed, 4
  skipped, 11 warnings, and 2 subtests passed**.
- Ruff `F`/`I`, `compileall`, and `git diff --check` — passed for affected
  source and tests.
- Canary coverage injects a recognizable exception string for all eleven
  startup/teardown failure event categories and confirms it does not reach the
  captured log.

## Still open

This receipt covers only these best-effort voice-pipeline exception sinks.
It does not prove all sensitive sources, continuations, persistence, provider,
tool, display, copy/share/export, or telemetry sinks are covered, nor does it
prove general sensitive-data detection or live candidate/release acceptance.
