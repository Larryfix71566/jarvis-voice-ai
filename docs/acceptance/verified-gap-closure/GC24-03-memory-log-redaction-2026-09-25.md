# GC24-03 memory log redaction

**Date:** 2026-09-25  
**Scope:** memory-context filtering, memory write rejection, session
extraction, memory sweep, and memory watcher diagnostics. This is a partial
GC24-03 receipt.

## Change and privacy boundary

Memory and sweep diagnostics now retain aggregate counts, bounded drop
reasons, and bounded exception class names without recording memory keys,
session IDs, promoted fact names, exception text, or tracebacks. The per-tier
cap signal retains only the set of affected tier labels and total count, and
staging expiry logs a count rather than keys, so existing cleanup/drop-count
observability remains intact. Accepted memory and the rendered prompt
behavior are unchanged.

Canary tests cover rejected memory keys/session identifiers, a context read
failure, a provider/client failure during extraction, ordinary extraction
without keys or session IDs in the info log, failed merge/sweep attempts,
staging expiration, and watcher timeout/failure paths.

## Verification

- Focused memory, sweep, watcher, and remember-tool suite: **158 passed**.
- Full unit/integration suite:
  `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
  — **2,883 passed, 4 skipped, 11 warnings, 2 subtests**.
- Ruff `F` checks on memory implementation and test files: passed.
- `git diff --check`: passed.

This closes only the listed memory diagnostic paths. It does not close GC24-03:
memory source-to-provider transmission, prompt/display sinks, and the remaining tool, voice, sharing/export,
telemetry, provider-persistence, and direct-mode sinks require the complete
source-to-sink inventory and negative canaries. This is isolated dirty-tree
evidence, not a production or Mac candidate claim.
