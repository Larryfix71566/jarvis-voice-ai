# GC24-02 — Direct agent tool-call identity replay guard

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; shared tree remains dirty.  
**State:** same-run direct-mode duplicate identity guard implemented; durable unknown-outcome reconciliation remains open.

## Change

Routed SubAgent and self-edit planner calls already use `execute_chat`, which
rejects a provider tool-call ID already present in the ordered request
history. Direct-mode SubAgent and self-edit planner loops now retain provider
tool-call IDs across completion rounds and reject missing, malformed,
overlong, or repeated IDs before dispatching any tool from that response
batch. This prevents one provider call identity from being executed twice in
these direct-mode runs.

Regressions return the same tool-call ID in two provider rounds. The first
call executes once; the second round terminates with a bounded failure and
does not dispatch the duplicate. The existing end-to-end app-build fixture
now uses distinct IDs across its provider rounds, matching the contract.

The current application does not resume orphaned SubAgent runs after startup;
the run log marks old `running` rows orphaned. This slice does not provide a
durable call-ID receipt across process restart, roll back a tool that already
mutated state before timing out, or deduplicate semantically identical actions
that a provider gives a new call ID. Those remain explicit GC24-02 gaps.

## Verification

- Focused SubAgent suite: **63 passed**.
- Combined SubAgent, UpgradeAgent, and AppBuildAgent suites: **115 passed**.
- Full Python unit/integration suite:
  `RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
  — **2,891 passed, 4 skipped, 11 warnings, 2 subtests passed**.
- Ruff `F`/`I` for both agent loops and affected tests: passed.
- Plan manifest suite: **7 passed**.
- `git diff --check`: passed.

This is dirty isolated-tree evidence, not provider/runtime or Mac acceptance.
