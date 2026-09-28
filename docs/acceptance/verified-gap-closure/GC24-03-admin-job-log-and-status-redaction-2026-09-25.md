# GC24-03 admin job log and status-error redaction

**Date:** 2026-09-25  
**Scope:** admin sidecar diagnostic logs for self-edit, app-build,
research, planning, council, model-route status, and read-only status jobs.
This is a partial GC24-03 receipt.

## Change and privacy boundary

Admin job logs no longer include user-authored goals/focus, model-generated
summaries, research URLs, raw publication notices, or raw exception messages
and tracebacks in the covered paths. Failure logs and asynchronous job-error
fields use a bounded exception class; state transitions retain only bounded
status, site count, presence flags, or opaque run correlation where applicable.
The model-route status failure now returns a generic unavailable message
instead of raw exception text.

The job status API still returns local task content and detailed job errors to
the authorized UI, preserving its existing interaction behavior. This receipt
does not claim that those response/display sinks are policy-validated; they
remain part of the open end-to-end GC24-03 audit.

Canary tests cover self-edit crash prompts and exception text, app-build crash
data, research URLs/focus/provider exception text, and publication notices.
The status checks verify that the raw exception is absent from the job response.
Planning and council error paths are included in the focused run.

## Verification

- Focused admin suite: **129 passed, 1 warning**.
- Full unit/integration suite:
  `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
  — **2,878 passed, 4 skipped, 11 warnings, 2 subtests**.
- Ruff `F` checks on the changed admin server and three test files: passed.
- `git diff --check`: passed.

This receipt closes only the listed admin logging/status-error paths. It does
not close GC24-03; response/display, provider persistence, memory, tools,
supervisor/TTS, sharing/export, telemetry, and direct-mode sinks still need a
complete source-to-sink inventory and negative canaries. Results describe the
dirty isolated worktree, not a deployed Mac candidate.
