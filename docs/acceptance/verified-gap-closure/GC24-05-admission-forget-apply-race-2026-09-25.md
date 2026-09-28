# GC24-05 — Forget racing with atomic memory apply

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**State:** deterministic race regression implemented and tested in the dirty isolated tree; no production rollout.

## Change and evidence

A worker applies a staged, explicitly supported memory fact in one SQLite
transaction. This test starts that transaction, pauses it after the fact write,
and starts `delete_fact` from a second connection. SQLite serializes the
deletion behind the apply transaction; after apply commits, the forgetting
operation removes the fact. A fresh database connection confirms no matching
fact remains and the admission job has a terminal state. This verifies the
user-visible privacy outcome for the apply/forget ordering without changing
forget semantics or introducing another transaction owner.

The test is deterministic rather than timing-based: an SQLite trace callback
signals when the second connection starts the memory `DELETE`, and only then
does the test release the apply transaction.

## Verification

- Focused memory admission/worker/acceptance suite:
  `.venv/bin/python -m pytest tests/unit/test_memory_extraction_worker.py tests/unit/test_memory_admission.py tests/unit/test_memory_automation_acceptance.py -q --tb=short` — **74 passed**.
- Full Python unit/integration suite:
  `.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` —
  **2,908 passed, 4 skipped, 11 warnings, and 2 subtests passed**.
- Ruff `F`/`I` checks and `git diff --check` — passed.

These results apply to the dirty isolated snapshot only. Cross-process forget
and lease-reclaim orderings, confidential provider capability, Mac rollout,
and release acceptance remain open.
