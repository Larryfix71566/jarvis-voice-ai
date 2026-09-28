# GC24-03 — Clipboard handoff log redaction

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; shared working tree remains dirty.  
**State:** clipboard logging paths hardened and tested; GC24-03 remains open.

## Change

The clipboard sidecar bridge now logs only a bounded exception-class code;
the request path and raw exception text are omitted. The `show_commands`
handoff no longer logs command titles, and clipboard-arm exceptions are
reported by error class without a traceback. It retains command count and
whether output was requested/armed, which is sufficient operational status
without logging user-authored command text.

Tests exercise the actual registered `clear_clipboard` tool with a failing
sidecar client and exercise `show_commands` with canary strings in both the
command title and exception. Those strings do not appear in captured logs.

## Validation

- Focused clipboard, watcher, and pipeline integration suite:
  **107 passed**.
- Full Python unit/integration suite:
  `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
  — **2,873 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- Ruff `F`/`I` on touched clipboard, watcher, pipeline, and test files — passed.
- `git diff --check` — passed.

These are isolated dirty-tree results. No provider, network, vault, live
database, installed Mac candidate, or production memory setting was used.

## Limits

This closes only the clipboard and command-title logging paths. It does not
close GC24-03 logging or transmission through other providers, tools, memory,
supervisor/TTS, response/display, provider state, telemetry, sharing/export,
or database sinks. The broader source-to-sink inventory and negative canaries
remain required.
