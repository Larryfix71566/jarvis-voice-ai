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
