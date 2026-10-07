---
date: 2026-10-07
system: codex
rows: [WS-17]
prs: [173, 194]
---

# CC7a.4 weather reuse: scope and contract before code

Larry assigned the remaining WS-17 implementation to Codex; claim #194 is on
main `e7b099b`. This docs-only expansion uses the separate clean branch
`docs/ws17-reuse-scope-20261007`. The implementation `Where` remains
`codex/ws17-closure-20261007`; no other workstream is reassigned.

The existing Command Console plan §7.2 now records the selected contract:
native `WorkspaceStore` is the sole cache/freshness owner; a canonical-UUID
`weather_reuse` query has typed subject/tool/days/units and optional originating
run arguments; explicit `result_reopen` remains a separate cached-selection
action. Genuine miss/expiry/incomplete capability permits the existing guarded
fetch; ambiguity, stale identity/revision and timeout refuse without silently
fetching. Original public weather/radar/place source and optional aliases stay
in bounded native memory, with metadata-only inventory. `weather_source` is
capped at 16 KiB encoded JSON, `subject_key` at 200 characters, and aliases at
8 strings of 120 characters. Preserve finite source-fetch epochs including zero
and expiry no later than fetch time plus 900 seconds; replay never resets TTL.

The scope adds only `jarvis/bot/weather_reuse.py`, associated tests, and a
weather-only request-owned ContextVar hook in registry `_invoke` after existing
guards. The classified finish/envelope, source/protection rules and shared
registry lifecycle remain unchanged. Native same-key refresh preserves UUIDs,
pins/comparison/scroll/Output; automatic reuse retains the current New/no-jump
contract. No process-global callback, backend TTL mirror, new model/route,
environment/config key, credential, allowlist change or production change is
authorized by this documentation.

Claude's historical source and PR #173 remain attributed. Cross-review,
exact-build verification and Larry's UI2-22…25/WS-21 live acceptance remain
required. No implementation or full acceptance checkbox is closed here.

Validation: session-start roadmap checker on `e7b099b` returned 0 errors and
0 warnings. On this docs-only candidate, `git diff --check` passed and
`python3 scripts/check_roadmap.py --receipts /Users/larryfix/MortimerRollback/logs`
returned 0 errors and 0 warnings. A block comparison confirms only WS-17 changes;
its ownership, implementation `Where`, prior evidence, every checklist state and
the Production line are preserved. No runtime test/provider/production operation
was performed for this documentation slice.

System: Codex. Session: `codex://threads/01a088c1-681c-70b0-ad7e-50ad6bccf83f`.
