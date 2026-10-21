---
date: 2026-10-21
system: codex
rows: [WS-05]
prs: [230, 232]
---

# WS-05 subscription retirement staging — 2026-10-21

System: Codex. Session: `01a1573e-ae10-7388-b7c4-e36ff49120e0`.

Claim [#230](https://github.com/Larryfix71566/jarvis-voice-ai/pull/230) merged
as `005e2a4`; all five claim CI checks passed. Implementation
[draft #232](https://github.com/Larryfix71566/jarvis-voice-ai/pull/232) stages
an opt-in application LLM billing guard, subscription defaults and readiness
diagnostics. It does not activate subscriptions or change production.

The full offline run recorded 6,638 passes, 11 skips and two failures. A missing
synthetic credential in the new test is repaired; an inherited audio setting
explains the other failure. The repaired focused group passes 135 tests. The
[existing plan](../plans/MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md#2026-10-21--draft-232-repair-and-bounded-integration-handoff)
records exact evidence, scope and remaining work; no full-suite green claim.

The only pipeline edit is the early readiness guard in `build_pipeline`.
Acceptance owns delegate/Base/Registry edits and the final integrated release.
WS-05's ambiguous historical branch reference is corrected; the separate
WS-17 stale-status checker finding is left to its owner.

Blocked: subscription voice/tool integration, exact workload/runtime receipts,
Codex compatibility, account/overage evidence and eligible private routing.
Standalone direct-API diagnostics now honor the same refusal policy; the
diagnostic guard/check-env group passes 50 offline tests. No provider calls, credential changes, deployment
or private-source transfer occurred. No automatic approval rejection occurred.


Continuation: integrated #231 main `3061408`; roadmap checker now clean.
Buffered Claude voice/tool adapter implemented with 14 synthetic tests passing,
including actual Pipecat registered-handler dispatch. The LLM provider-selection
branch is now also part of the bounded pipeline overlap; delegate/Base/Registry
remain untouched. Codex bundle discovery preserves explicit overrides and
exact-version gates. Read-only status confirms Codex ChatGPT login and, outside the sandbox,
Claude.ai Max login on both installed versions. The earlier sandbox-only
logged-out result was an access artifact; no sign-in or account change occurred. No inference, activation or credential mutation.
See the plan's continuation for precise remaining source/account/live gates.


Frozen runtime `763bfe1` clean unit result: 6,661 passed, 11 skipped, two
subtests passed. Runtime source stays frozen; this follow-up corrects account
metadata and records evidence/remaining acceptance only. Integration/evals and
final-head CI terminal outcomes are recorded on PR #232 when available.


Follow-up: all five final-head checks on `c8f2e56` passed. The installed Codex
0.163.0-alpha.10.2 now has actual localhost positive/hostile-tool evidence under
external-network denial and empty temporary HOME. Candidate inspection does
not authorize an unknown runtime; exact runtime/receipt/operator gates remain.
The directly related six-file subscription test group passes 174 tests after
allowing the three local Unix-socket fixtures. No provider inference occurred.
Full voice provenance is unfinished implementation requiring an expanded
source-policy-only handoff outside the two agreed pipeline regions; the plan
records exact ingress, result, memory and history boundaries. Protected-route
availability and live/account acceptance remain separate decisions.


Confirmed CX-27 source-policy handoff implemented in an isolated follow-up:
host-bound context provenance, monotonic privacy floors, memory/injection/tool
bindings, Base per-run export and Delegate immediate/late transport. Registry
is unchanged; acceptance request/weather/stop/cancellation semantics stay owned
by WS-17. Real Pipecat projection testing repaired an adapter continuation
mismatch; 248 focused tests pass. Earlier `49033ee` has all five CI checks
green and clean local 6,663 unit / 197 integration passes. This new source's
full checks and separate combined preview are pending; PR records terminal
results. Source classification does not grant private egress or activate a
subscription. No inference, credentials, source review or deployment occurred.


The repaired provenance source `acc0bd1` passes clean local 6,677 unit / 197
integration / 13 eval tests. The pinned Claude runtime additionally passes a
16-tool localhost schema/result roundtrip under external-network denial; the
sanitized receipt explicitly excludes live/model/account acceptance. A final
before/after regression adds exact checking of the materialized message
snapshot immediately before execution. The new final-head full results and
combined preview are recorded on PR #232; prior source results stay scoped.
