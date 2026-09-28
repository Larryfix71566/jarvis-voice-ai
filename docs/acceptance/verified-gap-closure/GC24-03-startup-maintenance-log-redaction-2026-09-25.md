# GC24-03 — Startup maintenance exception-log redaction

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base/HEAD:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2` (dirty worktree)  
**Status:** implemented and tested in the isolated worktree only; not merged,
deployed, or live-Mac accepted.

## Gap and invariant

Six best-effort startup failure handlers logged raw exception strings for
run-log pruning, council pruning, orphan-run reconciliation, key-health probe
startup, screen-retention pruning, and memory-sweep startup. Such exception
messages can include local paths, request details, or other data outside the
approved diagnostic fields. Startup remains best-effort and continues after
these failures; diagnostics now retain the failure event and exception class
only.

## Changes

- Added one startup diagnostic helper that emits `event` and
  `error_type=ExceptionClass` without formatting or logging the exception
  object.
- Routed the six identified startup catch blocks through that helper.
- Added canary tests for each event proving exception text is absent and the
  error class remains visible.

## Verification

- `.venv/bin/python -m pytest tests/integration/test_bot_wiring.py -q --tb=short`
  — **39 passed**.
- `.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
  — **2,956 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- Ruff `F` and `I` on `jarvis/bot/pipeline.py` and
  `tests/integration/test_bot_wiring.py` — pass.
- `git diff --check` — pass.

## Limits and next action

This closes only six startup maintenance logging paths. It does not prove
complete source-to-sink privacy, general sensitive-data recognition, provider
route eligibility, or log safety outside these handlers. Continue the
GC24-03 inventory and negative canaries across provider continuations, tools,
memory, supervisor/TTS, persistence, result/display, copy/share/export, other
logs/telemetry, and direct-mode paths. Keep unsupported paths fail-closed.
