# GC24-05 — Durable admission queue foundation

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; working tree remains dirty.  
**State:** additive migration and queue primitives implemented; extraction/teardown integration remains open.

## Change

Migration `0025_memory_admission_jobs` adds the plan's staging-only queue to
the existing SQLite database. `jarvis/memory_admission.py` provides canonical
idempotency over user/session/user-turn/assistant-turn/policy, verifies that
source turns exist and have the expected roles/session/user, bounds and
validates candidate/classification JSON, and applies compare-and-set
`extract → classify → apply` transitions. Claims use `BEGIN IMMEDIATE`, commit
before work, and are limited to 20 jobs. Retry and abandoned-claim recovery
follow the existing bounded 60/300/1800-second policy. Completion and forget
cancellation remove staged payloads while retaining idempotency receipts.

Forgetting an admitted fact now also cancels pending admission jobs linked to
its source user turn, preventing an in-flight classification from later
re-admitting that exchange. Focused tests cover migration, duplicate enqueue,
source identity, single-owner claims, stage payload bounds and order, retries,
reclaim, terminal cleanup, and forget during a running claim.

## Validation

- Memory admission, database migration, memory delete, and manifest tests:
  **135 passed**.
- Broader memory/manifest/DB focused suite: **282 passed**.
- Complete Python unit/integration suite: **2,848 passed, 4 skipped, 11
  warnings, 2 subtests passed**.
- Ruff `F` and `I` checks on touched migration/queue/memory/test files — passed.
- `git diff --check` — passed.
- Tests use temporary SQLite databases; no live vault, provider, user database,
  Mac runtime, or network request was used.

## Still open

The extraction worker and session teardown do not yet enqueue a finished
exchange before advancing the global cursor/clearing its pairing row. No worker
yet resumes the queue's extraction/classification/application stages, applies
admitted metadata atomically after rechecking source/policy/deletion, or writes
the planned shadow evidence for newly extracted candidates. Atomic daily-budget
reservations shared with `memory_maintenance`, simultaneous teardown/worker
enqueue, all crash boundaries, and staged rollout remain unverified. No live
memory behavior was enabled by this increment.
