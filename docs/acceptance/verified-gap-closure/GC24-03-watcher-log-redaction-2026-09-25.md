# GC24-03 — Watcher error-log redaction

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; shared working tree remains dirty.  
**State:** four watcher logging paths hardened and tested; GC24-03 remains open.

## Change

Research, plan, progress, and reminder watchers now log only a bounded
exception-class code when their fetch/call fails. The reminder watcher also
stops logging the raw invalid response body when reminder JSON cannot be
parsed. This preserves the watchers' existing recovery and speaking behavior
while keeping exception and response content out of application logs.

Each affected error path has a content canary assertion proving that the raw
sentinel is absent from `caplog`; tests also verify useful bounded error
categories remain available.

## Validation

- Focused watcher suite:
  `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit/test_research_watcher.py tests/unit/test_plan_watcher.py tests/unit/test_progress_watcher.py tests/unit/test_reminders_watcher.py -q --tb=short`
  — **48 passed**.
- Full Python unit/integration suite:
  `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
  — **2,871 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- Ruff `F`/`I` on the four watchers and corresponding tests — passed.
- `git diff --check` — passed.

These are isolated dirty-tree results. No provider, network, vault, live
database, installed Mac candidate, or production memory setting was used.

## Limits

This closes only these watcher logging paths. Other raw exception/response
logging remains under the GC24-03 source-to-sink audit, including shared
content/clipboard, planner and council errors, status/telemetry, direct and
routed memory, provider persistence, supervisor/TTS, sharing/export, and
result/database sinks.
