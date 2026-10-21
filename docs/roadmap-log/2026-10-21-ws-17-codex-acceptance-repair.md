---
date: 2026-10-21
system: codex
rows: [WS-17]
prs: [231]
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
