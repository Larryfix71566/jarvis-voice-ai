# GC24-01 — Status reconciliation and duplicate ownership

**Date:** 2026-09-25  
**Source baseline:** `8bd5e7e58272962dfab4454850c8961515286904`  
**Implementing branch:** `codex/isolated-20260924`  
**Scope:** acceptance/status documentation and removal of an uncompiled,
unreferenced duplicate Swift source file. No runtime flags, provider routes,
credentials, database or deployment changed.

## Changes

- Added the same #89 source/test-count reconciliation and GC24-00 receipt link
  to `IMPLEMENTATION_STATUS.md`, adaptive release readiness, Command Console,
  memory and model-use status. Marked counts as the PR commit's report, not a
  fresh test run, and kept deployment/runtime identity unverified.
- Corrected the consolidated memory row: deterministic heuristic policy is
  implemented, while the production B1 classifier remains heuristic and
  model-backed admission stays open.
- Corrected the Atlas row: existing projections are implemented; source
  freshness/error/retry behavior and live/accessibility gates remain open.
- Kept UI2-21 for the atom display and assigned UI2-23 to the unchanged
  developer-run grouping/Glass gate. A repository-wide search confirmed the
  new ID was unused before assignment. Historical UI2-21 references remain
  attributable by title.
- Removed `macos/MortimerHost/Placement/ContentWindowRegistry.swift`. Package,
  script, CI and test searches found no code reference. The canonical file
  under `macos/MortimerHost/Sources/MortimerHost/Placement/` and its tests
  remain. Updated the Command Console acceptance row and parent implementation
  plan to record the sole source owner.
- Updated the acceptance runbook to require the exact candidate checkout,
  rather than its stale, dirty historical `release-review` worktree path.

## Validation and limits

- `git diff --check`: passed.
- `tests/unit/test_plan_manifests.py`: its seven standalone assertions passed
  by direct invocation. This was not a full pytest run.
- New plan relative links, ordered closure IDs, fences and whitespace: passed.
- Package/script/test search: no reference to the removed duplicate; canonical
  source and its test manifest entry remain.
- No Swift build was run because the deleted file was outside SwiftPM's source
  tree and no code in the package changed.

This closes documentation/ownership reconciliation only. GC24-00's running
process, loaded configuration, test execution and current artifact identity
remain unverified. No deployment or feature-acceptance row was closed.
