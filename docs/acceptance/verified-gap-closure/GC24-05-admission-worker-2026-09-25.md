# GC24-05 — Durable admission worker integration

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; working tree remains dirty.  
**State:** staged extraction/classification/application is implemented in this isolated tree; live provider rollout remains disabled and unaccepted.

## Change

The idle extraction worker now persists finished user/assistant exchanges into
the migration-0025 queue before advancing its cursor. Session teardown stages
finished pairs and drains a bounded number of stages without changing the
global extraction cursor. Both paths require the explicit settings and
`JARVIS_MEMORY_AUTOMATION_ENABLED` gates. The default legacy path remains
available when the gate is off.

The worker claims and commits before doing provider work, then resumes one
bounded `extract → classify → apply` stage at a time. The extraction request
contains only user-authored evidence and validates the confidential route
before client creation. Classification reserves against the shared migration
0026 daily ledger before calling the strict configured classifier. Exhausted
budget defers the job; provider/route failure does not silently fall back to
heuristics. Eligible memory writes, content-free shadow metadata, and terminal
job completion are committed atomically. Migration 0027 stores only candidate
digests and classification metadata for shadow review, never candidate text.

Live application rechecks the source exchange and evidence, requires the
classifier to cite the current user turn, and rejects non-user provenance.
Forgetting one key now cancels matching queued/in-flight staged candidates
even when no memory row has been created yet; cancellation clears staged
candidate and classification payloads.

## Validation

- Focused worker, extraction, admission, watcher, DB migration, and tenant
  tests: **84 passed**.
- Ruff `F`/`I` checks on touched Python files: passed.
- `git diff --check`: passed.
- Full Python unit/integration suite: **2,857 passed, 4 skipped, 11 warnings,
  2 subtests passed** in 87.81 seconds (`RUN_LIVE=0 .venv/bin/python -m pytest
  tests/unit tests/integration -q --tb=short`).
- Tests use temporary SQLite databases and synthetic fixtures. No Mac vault,
  provider, live user database, or production route was accessed.

## Boundaries and remaining work

- Current policy has no verified confidential production route, so
  provider-backed live classification remains fail-closed.
- The feature gate remains off by default. This receipt does not enable live
  memory automation or authorize deployment.
- Full process-crash and multi-worker race coverage across every enqueue,
  stage, apply, forget, and cursor boundary remains open.
- Mac staged shadow/benefit observation and subsequent rollout acceptance
  remain open. Historical 28-exchange replay is out of scope.
