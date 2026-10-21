---
date: 2026-10-21
system: codex
rows: [WS-17]
prs: [231, 233]
---

# WS-17 acceptance repair — approved claim

Larry approved the complete bounded repair plan, including routine claim,
isolated implementation, synthetic verification, gated merge and coordinated
rollback-protected release. Registered branch:
`codex/ws17-acceptance-repair-20261021`, from main `005e2a4`.

CX-27 preserves WS-05 subscription-retirement ownership and holds overlapping
delegate/Base/Registry edits for coordination. No runtime edit, test execution,
production mutation, provider call, external-agent disclosure or acceptance
checkbox change is made by this claim. Existing plan contains the dispatch.


## Weather dispatch and first-arrival witness

Claim #231 merged as `3061408` before runtime edits. The committed WS-05
handoff in `504f911` permits WS-17 delegate/Base/Registry edits; WS-05 retains
provider paths and its four-line pipeline readiness guard. Release remains held
for coordinated integration.

Two invented named-city forms and an older-call ownership case failed before
the repair (three failures, one passing local control). Accepted input now
captures an immutable weather target with its request; device lookup refuses
named/unclear targets before location, network or display work. Native cache
lookup also refuses a different generated target. Legacy direct paths remain
compatible. No provider, credentials, configuration or presentation contract
changes.

Focused Python: 77 passed, eight deprecation warnings. Expanded dispatch/cache/
privacy/SDK/wiring group: 208 passed, eight deprecation warnings, 8.73 seconds.
The expanded group's first run found an unresolved “weather there” parser case
(one failure, 207 passes); that case is repaired and included in the green run.
Actual native SDK/router/store witnesses: two passed, zero failures. The new
witness proves that a wrong first local result consumes the same request's
opening before the correct named result; it does not justify changing the
one-winner focus policy. Fixtures are synthetic and no provider calls occurred.

These are working-tree checks based on `3061408`; exact committed-source/full
suite, independent verification, review and CI remain required. No live
acceptance checkbox is closed and no deployment occurred. Next slice repairs
explicit task cancellation/duplicate handling and truthful reporting using
existing governance, within the committed handoff.


## Explicit task lifecycle slice

Draft [#233](https://github.com/Larryfix71566/jarvis-voice-ai/pull/233) starts
with weather commit `5286327`. Its committed-source focused repeat passed
208 tests in 8.75 seconds; strict roadmap validation passed with zero errors
and zero warnings.

Four synthetic task-control regressions fail before this slice. Session-local
pending operations now suppress exact duplicates while preserving distinct
sibling work. Speech barge-in retains the detached task and reports that it
continues on the next accepted user turn. Explicit bounded task-stop commands
request cancellation; ambiguous single-task stops with multiple pending tasks
make no change and ask for a choice. A bare speech “stop” is not task
cancellation. Cancellation cannot undo actions already performed and is not
reported as completed merely because requested. Cancelled orphaned work does
not deliver a stale success.

The control hook runs once at the exact accepted-input boundary, never from a
copied or injected model context. Its content-free lifecycle note expires on
the next accepted turn and preserves the real user message for existing voice
workflow tracking. No model tool, schema, privilege, durable queue or provider
setting is added. The combined lifecycle/boundary/weather/wiring group passes
223 tests, eight deprecation warnings, in 10.60 seconds. This is a focused
working-tree check, not the full release gate or live acceptance.


## Truthful reporting and measurable lifecycle slice

Task-control commit: `5f1b6b8`. Reporting guidance now explains automatic
formatted-roadmap emission/main-window selection, historical deployment
headers versus verified installed build, operator-reported passes versus
verified evidence versus reviewed canonical Git readback, and truthful
missing-runner handoff. Existing selfedit documentation governance remains
mandatory. The Developer's core stays within its existing size budget; no
execution tool or capability grant is added. Acceptance reminders are bounded
to relevant turns and tombstoned on the next user turn. They do not assert
that an observation persisted or any checkbox changed.

Content-free display request/sequence breadcrumbs and monotonic delegation
terminal elapsed time support trace correlation without transcript, task,
location or result contents. The expanded reporting/dispatch/lifecycle/privacy
group passes 710 tests, ten warnings, in 9.33 seconds. Warnings include SDK
and audio deprecations plus the existing reply-guard test callback's unawaited
coroutine warning. Model compliance and live/visual behavior remain unverified.

Separate read-only investigation: the Skills runtime-inventory endpoint
explicitly returns 503 when bearer authentication/identity is unavailable or
inventory capacity is full. The reporter logs only exception type, so the
reviewed production 503 status alone does not identify which branch fired.
No authentication/security setting is changed. The isolated memory parsing
warning has no demonstrated causal connection to weather or foreground
selection. Neither unrelated warning is converted into an acceptance pass.

Next: freeze committed source, run required full host and independent checks,
refresh CI and obtain the required independent review within authorized
privacy boundaries. No production/deployment or human acceptance change.
