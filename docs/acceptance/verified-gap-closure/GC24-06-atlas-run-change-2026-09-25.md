# GC24-06 — Atlas run-source change refresh

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**State:** implementation and focused regression suite pass in the isolated tree; current-candidate acceptance remains open.

## Change

Knowledge Atlas now observes the app-owned `AgentRunStore.lastCompleted`
projection and refreshes only the run-history source when an agent completes.
It does not refresh memory, plans, architecture, or result cards for this
event, and the existing store coalesces an in-flight run-source refresh.

Regression tests exercise independent per-source behavior: when the
architecture refresh fails after a successful memory refresh, memory remains
loaded, the architecture source is marked failed/stale, and both last-good
projections remain available. Additional store tests verify duplicate refresh
requests coalesce and an explicit retry recovers after an authentication-like
transient failure.

## Validation

- `SWIFT_MODULECACHE_PATH=/private/tmp/mortimer-swift-module-cache CLANG_MODULE_CACHE_PATH=/private/tmp/mortimer-swift-module-cache SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/mortimer-swift-module-cache swift test --disable-sandbox --package-path macos/MortimerHost --cache-path /private/tmp/mortimer-swift-package-cache --filter KnowledgeAtlasTests` — **10 tests, 0 failures**.
- `swiftc -frontend -parse -target arm64-apple-macosx14.0` on the edited Atlas
  view and test file: passed.
- `git diff --check`: passed.

## Still open

This change does not prove source-change coverage for memory/plans,
accessibility, display-move fetch counts, graph performance, or current
candidate behavior. Continue the remaining GC24-06 candidate and physical-Mac
acceptance checks.
