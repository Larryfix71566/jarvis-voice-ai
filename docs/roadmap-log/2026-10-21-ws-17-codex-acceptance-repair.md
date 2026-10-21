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


## Full backend and local-weather compatibility follow-up

Full host backend on `cdc8672`: 6,846 passed, 15 skipped, two subtests passed,
19 warnings, 261.78 seconds. This is an offline environment-isolated run.
The full native run stalls without a terminal verdict; a retained local stack
sample shows the dispatch soft limit reached with blocked AppKit animation
threads. Only its verified test runner processes were terminated. This run
is non-passing, not a native acceptance pass or a proven product defect.
A fresh bounded unbuffered full-native repeat is required.

Read-only checks against the existing public voice-evaluation fixtures find
two additional local-weather classification failures (“umbrella today” and
“week ... weather-wise”). They are repaired and retained as regression cases;
explicit city qualifiers also cannot acquire a contradictory appended
qualifier. Expanded affected verification passes 215 tests, eight deprecation
warnings, in 8.54 seconds. The prior full backend result remains scoped to
`cdc8672`; final source needs its own complete repeat.

Provider handoff update: WS-05 now retains both the early readiness guard and
the Google/Anthropic/OpenAI provider-selection constructor branch in pipeline,
as committed at `763bfe1`. Acceptance changes touch neither region. Shared
delegate/Base/Registry acceptance ownership remains permitted. No provider
activation, security setting, deployment or acceptance checkbox change.


## Time-before-place authority correction and preserved failed runs

Full host backend on `30bbcea`: 6,848 passed, 15 skipped, two subtests passed,
19 warnings, 277.43 seconds. Its five CI checks pass. Five extra real-Registry
checks prove bound correct-city weather/radar hits preserve native timestamps
without provider fetch, wrong-city refusal before query/fetch, and both private
input floors. These are overlapping checks, not additive acceptance totals.

Static review then proves a further target-order defect: “umbrella today in
Exampleburg” and “rain today in Exampleburg” incorrectly grant device-local
execution. Real adapter/parser regressions fail five cases, including a
multi-city phrase hidden behind a time word. Time qualifiers are now removed
only as complete trailing phrases; named targets after time words are parsed
first, and multiple targets remain unclear. A 55-phrase synthetic matrix also
finds three local “right now”/“the week” forms, repaired without turning named
requests into local ones. The final affected group passes 898 tests, ten
warnings, in 11.89 seconds; all 55 matrix cases pass with no model calls.

The just-started `30bbcea` independent VM run is deliberately interrupted for
this demonstrated source correction, before any check completes. Its own
cleanup deletes its allocated tasks and confirms preexisting records/assets,
settings and production unchanged. It remains non-passing. The bounded full
host-native repeat reaches its 600-second deadline at an actual window-capture
case and is retained as timed out (exit 124), not passed. No test, permission,
physical prerequisite or assertion is removed or waived. A fresh isolated
capture control and final-source original twelve-check verification follow.

Parent owns the pending explicit cross-system review consent request. The
locally prepared `30bbcea` source packet is obsolete; no packet was transmitted.
Regenerate exact source/fingerprints for the repaired commit before review.
No canonical human/visual checkbox, owner, service or deployment change.


## Stop-turn dispatch authority and native terminal diagnostics

Full host backend on `b1db9a9`: 6,856 passed, 15 skipped, two subtests passed,
19 warnings, 244.64 seconds. Two further actual-adapter cases prove a model
could start a fresh delegation on an explicit task-stop turn; the ordinary
speech-stop control passes. An immutable accepted-request task-stop flag now
refuses new delegate dispatch on that same turn, using the identical bounded
command parser as existing cancellation. It does not infer control from a
newer mutable voice turn or add a tool/wire privilege. The affected group now
passes 901 tests, ten warnings, in 11.91 seconds.

The full native diagnostic with one isolated worker schedules all 580 cases
and exits nonzero after 164.07 seconds. Two actual capture tests fail through
ScreenCaptureKit (`-3811`; audio/video capture startup failure), including the
independent fresh capture control. Its existing permission preflight passes;
missing authorization is not established. Two VoiceDisplayAuditRegression test
processes also crash at unchanged `WindowLookup.swift:38` with nil `NSApp`
under per-test isolation. These diagnostics do not replace the original full
profile or waive any assertion. Original host stalls, deadline timeout, two
capture failures and isolation crashes remain non-passing evidence. No native
runtime/test source, Screen Recording setting or production process is changed
by these diagnostics. Final native/privacy/physical acceptance remains open.

Freeze this stop-turn correction, refresh complete backend/CI and original
independent twelve-check verification, and regenerate the source-only review
packet. Parent owns pending review consent and provider release coordination.


## Frozen-source automated evidence complete; remaining gates held

Frozen `d242ba4` passes full host backend (6,859 passes, 15 skips, two subtests,
19 warnings), five CI jobs and strict roadmap drift (zero errors/warnings).
The original twelve-check independent profile passes after fresh supported
recovery: candidate backend 6,662 passes/11 skips/two subtests; native 580
executed/eight prerequisite skips/zero failures. Exact commands/log hashes and
source/test fingerprints are verified in the
[scrubbed receipt](../acceptance/command-console/receipts/ws17-acceptance-repair-2026-10-21.md).

Preserve both interrupted attempts and all non-passing host native evidence.
The first frozen-source attempt loses its orchestrator during executor transport
loss. No guest test remains before recovery; its orphan child is disposed and
the exact candidate refrozen before all twelve checks rerun. Owned cleanup and
preservation checks pass; production, settings and prior records are unchanged.
The scheduled cleanup job stays paused. Post-VM serial capture still fails SCK
-3811 despite preflight, with no competing tests. Resource contention is not
established as cause. No permission change or waiver.

Static source review awaits parent-managed consent; no packet was transmitted
and no verdict exists. Provider owns the newer combined tool-dispatch conflict,
retaining stop refusal plus source-policy scope. Base/Registry have no acceptance
edits; exact shared regions/two metadata conflicts are documented in #233.
Combined source must be reviewed and reverified. This publication changes docs
only; runtime/test bytes match `d242ba4` and its own CI is separate. No owner,
human/visual checkbox, deployment or observation gate closes.

Publication validation: 57 existing roadmap reader/event/drift contracts pass
(two deprecation warnings); strict checker remains zero errors/warnings. Runtime
and test trees are byte-identical to `d242ba4`; publication CI is distinct.


## Integrated offline verification complete — 2026-10-21

Provider preview `794a298` is fetched and verified by actual tree/parent graph
and content equivalence with provider `b1f07a2` plus acceptance `d242ba4`.
Stop-turn refusal remains inside source-policy/run-log scope. All twelve original
independent checks pass; candidate backend 6,728 passes/11 skips/two subtests,
native 580 executed/eight prerequisite skips/zero failures, JarvisKit 235 passes.
Full combined host backend: 6,925 passes/15 skips/two subtests, 19 warnings,
244.89s. Exact commands, hashes, manifests and limits are in the
[integrated receipt](../acceptance/command-console/receipts/ws05-ws17-integrated-2026-10-21.md).
Owned cleanup and unchanged source/settings/production/prior-asset checks pass;
no tests remain active and paused cleanup stays paused. Owner-supplied 421-test
conflict check was inspected, not independently rerun. Earlier non-passing runs
remain unchanged; no unrun integrated CI or cross-review verdict is inferred.

Host UI/capture needs an unlocked awake interactive desktop before a meaningful
recheck; historical SCK failures are not proven explained. No new permission or
unchanged retry. Parent-managed source-review/live consent and runtime/overage
proof remain pending; protected full-context export still needs an eligible
private/local route or activation remains held. No merge/deploy or human/visual
checkbox closure. One focused session follows release gates, then actual release
and WS-06 observation. This docs publication keeps runtime/test bytes at `d242ba4`.

Validation: strict combined-source roadmap against explicit main `3061408` has zero errors/warnings (no warn-only flag); missing origin/main in the handoff was resolved by the full hash. Publication contracts pass 57 tests/two warnings/3.58s; all 144 checkbox and29 owner lines and standalone runtime/test bytes remain unchanged.
