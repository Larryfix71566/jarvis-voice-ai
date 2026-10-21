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
