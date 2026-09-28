# GC24-03 receipt — memory extraction and worker log redaction

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base/HEAD at start:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**State:** verified in a dirty isolated tree; other concurrent changes were
preserved. This receipt covers only the listed Python memory extraction and
worker log paths.

## Change

Current source still emitted tracebacks from recall-event writes, exchange
extraction, and worker tick failures. The extraction logs also exposed
memory keys, promoted keys, session IDs, rejected candidate keys, and the
worker cursor. These logs now retain bounded event names, aggregate fact /
observation / row / exchange counts, the existing admission stage and
rejection reason categories, and bounded exception class names. They omit
exception text, tracebacks, memory keys and values, session IDs, job IDs, and
cursor IDs. Invalid poll/orphan timeout configuration warnings no longer
echo the raw environment value.

Return values and the best-effort failure behavior remain unchanged. No
memory admission, extraction prompt, routing, retry, or persistence behavior
was changed by this slice.

## Verification

- `./.venv/bin/pytest -q tests/unit/test_memory_extraction.py tests/unit/test_memory_extraction_worker.py --tb=short`
  — **64 passed**.
- `./.venv/bin/ruff check --select F,I jarvis/memory_extraction.py jarvis/memory_extraction_worker.py tests/unit/test_memory_extraction.py tests/unit/test_memory_extraction_worker.py`
  — passed.
- `./.venv/bin/python -m compileall -q jarvis/memory_extraction.py jarvis/memory_extraction_worker.py tests/unit/test_memory_extraction.py tests/unit/test_memory_extraction_worker.py`
  — passed.
- `git diff --check` — passed.
- Canary tests verify that exception text, backend details, private paths,
  memory keys, and session identifiers are absent from captured logs while
  events and safe aggregate/error-class diagnostics remain observable.

## Still open

This closes slice A's current memory extraction/worker log paths only. The
broader memory source-to-provider, prompt, persistence, display, and sharing
boundaries remain subject to the full GC24-03 source-to-sink plan. Slices B–E
in the [remaining exception-log redaction plan](../../plans/MORTIMER_GC24-03_REMAINING_EXCEPTION_LOG_REDACTION_PLAN_2026-09-25.md)
remain open. The full Python suite, live provider behavior, installed Mac
candidate, deployment, and release were not tested by this receipt.
