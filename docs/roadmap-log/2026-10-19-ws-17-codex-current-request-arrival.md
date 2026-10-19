---
date: 2026-10-19
system: codex
rows: [WS-17]
prs: []
---

# Current-request foreground implementation checkpoint

Session: `01a1140b-72bf-76bc-bc11-ac283fa6b0e2`; isolated implementation branch
`codex/ws17-current-request-arrival-20261018`, based on merged claim #225
`c244963`. Wire reservation `b587cd5` precedes source edits. Candidate request
IDs are host-owned and ephemeral, captured synchronously at real accepted-input,
aggregator and SDK function dispatch boundaries. The native router matches exact
input/session/generation/request identity and permits one foreground winner.
Fresh weather reuses the original native UUID/source time/expiry. Unknown,
background, superseded, cancelled and duplicate arrivals preserve focus;
supporting-display ownership and independent Atlas navigation remain protected.

Exact baseline and candidate reproduce the execution-sandbox XCTest allocator
abort. The identical normal-host baseline command passes eight cases; candidate
focused native verification passes 41. Final focused Python verification passes
135. Later final-source full suites and independent review remain pending.
Original failures are retained locally; no test assertion, runtime check,
skip list, budget or timeout was weakened. No source-policy, model, endpoint,
credential, installation, production/history, deployment or live-acceptance
change occurred. Only source/synthetic tests may enter the review packet;
raw production logs and operational metadata remain local.

00:54 UTC checkpoint: 206 final focused Python tests pass. The same single
SDK/transport/router/store second-city witness fails two baseline foreground
assertions and passes the candidate; its test-only baseline overlay was removed.
The 36 affected native regression/private-capture cases pass with all privacy
assertions intact. Original full-run failures are preserved and classified in
the existing plan; final-source full clean-host suites and review remain open.

Full `6d777eb` results: Python 6,802 passed / 15 skipped; JarvisKit 235 passed;
MortimerHost 572 executed / five prerequisite skips / zero failures. Python
dotenv contamination reproduces all five failures on unchanged baseline;
process-only isolation resolves them without assertion changes. A later actual
upstream SDK probe finds a provenance defect despite those passes. Both linked
broadcast and copied-boundary red cases are repaired; 207 focused checks pass.
The old review packet is withheld; full Python repeat/new packet/review pending.
No production, credential, deployment or live-acceptance change.

Publication checkpoint: exact implementation `0f2af66` has 6,803 local Python
passes and all twelve independent VM checks passed. Candidate native: 572
executed / eight prerequisite skips / zero failures; local native: five skips.
Claude's final bounded reconciliation reports no blocking findings: 1 INVALID,
2–4 NON-BLOCKING, with original reports/limits preserved. Scrubbed evidence:
`docs/acceptance/command-console/receipts/ws17-current-request-2026-10-19.md`.
The publication adds documentation/evidence only; runtime/test identity is
checked against `0f2af66`. Final-head CI, merge, deployment and live acceptance
remain open; no production operation or checkbox closure.

Additional #226 review checkpoint: ordinary-window winner accounting reproduces
nine failed assertions in two real-router tests. Actual-renderer/resolved-owner
repair passes 31 related native cases. SDK upstream tool-result continuation
provenance remains under validation. Prior `0f2af66` receipts do not clear this
changed runtime; final-source checks/review must refresh. PR stays draft; no
merge, deployment or acceptance closure.

SDK continuation checkpoint: four real PipelineWorker/function-result/assistant
upstream flows reproduce missing provenance (current, deferred, superseded,
cancelled). Public synchronous causal-frame hooks plus direction-independent
provider scoping repair the path; 14 provenance tests pass. Source changed;
full affected checks/new-source review and twelve-check verification remain
pending. No production, merge/deploy or acceptance change.

Deferred-interruption follow-up: actual SDK bot-speaking→result A→interruption
→new request B reproduces B's lost binding on `c5c5b45`. Retire only the
abandoned pending flush; preserve immutable still-running/late call ownership.
All 16 provenance tests pass. Preceding full host checks: Python 6,807 / 15
skips; native 574 / five prerequisite skips / zero failures; JarvisKit 235.
New-source full backend/review/twelve-check verification pending; no acceptance
checkbox, production, merge or deployment change.

Roadmap-refresh follow-up: seven actual-router assertions reproduce queued
pointer/main fallback and winner-consumption failure. Existing actual-renderer
predicate repairs the early branch; 39 related native cases pass. The prior
`e29973d` VM attempt is deliberately stopped/superseded; owned resources removed,
preexisting assets unchanged. Six Claude findings await bounded source/policy
reconciliation; full affected native/new-source review/twelve-check verification
refresh next. No production, acceptance, merge or deployment change.

Cache-hit follow-up: eight real-router assertions reproduce closed supporting
window main-fallback failure and unconsumed visible-winner ownership. Minimal
router-only actual-renderer accounting passes all 58 related cache/TTL/privacy,
router, roadmap and provenance tests. Cache/source guards, TTL, fetch timestamps
and UUIDs unchanged. Preceding `8ac4f30` full native: 575 executed / six explicit
display/activation skips / zero failures; no VM started for that source. New
source review/full native/independent verification and CI remain open.
