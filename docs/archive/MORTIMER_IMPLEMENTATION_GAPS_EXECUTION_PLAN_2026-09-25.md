# Mortimer — Implementation Gaps: Model-Ready Execution Plan

> **Archived 2026-09-28 — superseded as an execution index.** The canonical plan is [MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md](../plans/MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md). This archive preserves the original requirements and evidence for history; it does not mark any gate complete.


**Prepared:** 2026-09-25  
**Purpose:** one ordered, model-neutral handoff for the implementation and
acceptance gaps confirmed in the current isolated-tree review. It fixes the
product and architecture decisions so an implementing model can execute
bounded slices without redesigning Mortimer.  
**Worktree:** `codex/isolated-20260924`, based on
`977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; this is an extensively dirty
tree containing concurrent changes.  
**Authority:** use this document for task order and current gaps; the linked
feature and closure plans remain authoritative for detailed schemas,
thresholds, and rollback requirements. A stricter requirement in an existing
spec wins. This plan is not a claim of merge, deployment, candidate acceptance,
or release readiness.

## Goal

Finish the gaps confirmed by the latest source review while preserving the
accepted Mortimer experience and architecture. Work only in the isolated
worktree. Deliver small reviewable changes with focused tests and dated
receipts. Never infer live or release acceptance from source tests.

## Fixed decisions

- Keep Command Console/layout 2, compact Conversation as startup, all eight
  scrollable sidecar tabs, the approved atom/comet orb, user/Mortimer speaker
  colors, connected idle animation while muted, and measured voice feedback.
- Full answers and research belong in the existing response/results area;
  Conversation keeps brief live captions. One request owns one result identity.
  Appending, moving a display, reconnecting, reopening a pane, or changing tabs
  must not issue another model request or create another result window.
- Keep the existing bounded supporting display and the current app-owned
  window, placement, action, and result owners. Pointer, keyboard, and voice
  use the same validated action registry.
- Preserve model identity, workload, access route, privacy, capability, and
  billing as separate values. Do not silently substitute models/routes, lower
  privacy, retry an unknown mutation, or treat unknown usage as zero. Keep
  Haiku in its existing voice-supervisor role and leave the current voice,
  STT, TTS, and transport unchanged.
- Subscription adapters cannot execute tools until provider-runtime isolation
  and the task-scoped Mortimer bridge are proven. Registered Mortimer
  permissions and the existing sandbox remain the only tool execution path.
- Keep protected data local unless both model and route have verified
  capability. A credential, catalog entry, login, or public probe is not
  confidential-route evidence.
- SQLite remains the sole memory system of record. Keep routine classification
  and maintenance automatic and quiet. Do not ask users to label ordinary
  memories, replay the recovered 28 exchanges, bulk-relabel records, or create
  another memory database.
- Preserve self-edit preview behavior and the existing sandbox/PR approval
  boundary. Do not deploy, merge, push, or access the Mac vault from this
  implementation work.

## Verified baseline and current gaps

The source/worktree audit reports model call-site inventory **26/26 covered,
zero review-required, secret-free**. The latest complete Python run recorded
for the dirty isolated snapshot passed **2,913 tests, 4 skipped, 11 warnings,
and 2 subtests**; memory admission/worker/acceptance focused tests passed
**77**. These results apply only to that snapshot. Re-run affected suites after
code changes. The installed Mac candidate, effective live configuration, and
release state are not verified by these counts.

| Gate | Verified progress | Remaining proof/work |
| --- | --- | --- |
| GC24-00/01 baseline and status | Main snapshot and current isolated work have been compared; source status is documented. | Refresh branch/base/SHA, dirty-file ownership, concurrent-worker changes, current app/backend/config identity, and map every open acceptance row before each new code slice. Unknown runtime facts stay explicitly unknown. |
| GC24-02 execution lifecycle | Shared execution boundary, selected caller migrations, identity-only tool-result event, cancellation handling in selected SubAgent/delegate paths, replay guards in selected tool loops, and provider-late-result suppression in the direct voice Supervisor have evidence. The existing RTVI transcript-to-result route remains the voice stream path. The generic native text-delta consumer is conditional: no current production caller opts into shared `stream_text`. | Finish one terminal/result owner across every inventoried provider/tool loop; tool/artifact identity and reconciliation; cancellation and late-write suppression across all callers and tool outcomes; durable unknown-mutation handling; remaining caller parity; exact live candidate frame-to-pane proof. Do not add a parallel generic stream consumer unless an inventoried production workload actually needs one. See the [Supervisor late-cancellation receipt](../acceptance/verified-gap-closure/GC24-02-supervisor-late-provider-cancellation-2026-09-25.md). |
| GC24-03 privacy | Static workload floors, protected local specialist-result handoff, UI copy/share/export controls, and redaction receipts cover selected paths. | Complete source-to-sink inventory and negative canaries for tool continuations/results, memory injection/staging, supervisor/TTS, sharing/export, telemetry/logging, provider persistence, result/display, and direct-mode paths. Keep fail-closed behavior for any unproven sink. |
| GC24-04 model routes | Claude/Codex/SAYGM configuration and adapters exist; call-site inventory is covered. | Produce per-model/per-route capability, isolation, privacy, and billing evidence. Prove the task-scoped tool bridge before enabling any subscription tool. Keep unverified routes/tools disabled. |
| GC24-05 automated memory | Strict route-aware classifier, durable extract/classify/apply staging, shared budget reservations, evidence checks, forget invalidation, claim fencing and atomic apply exist. Stale-owner, simultaneous SQLite-connection claim, spawned-process duplicate claim, forget/apply, forget-versus-lease-reclaim, and crash/retry tests pass in receipts. Focused admission/worker/acceptance suite passes 77 tests. | Verify an eligible confidential route before production classification; complete shadow/benefit observation and staged Mac rollout. Production stays disabled/fail-closed until gates pass. See the [multi-process race receipt](../acceptance/verified-gap-closure/GC24-05-admission-multiprocess-races-2026-09-25.md). |
| GC24-06 Knowledge Atlas | Store-owned refresh, last-good state, generation guards, retry/recovery/coalescing, and run-history refresh are implemented in the isolated tree. | Prove auth expiry/recovery, source-change reliability, keyboard/VoiceOver/reduced-motion use, no duplicate fetch on view/display changes, graph/frame performance, and exact candidate behavior. Resolve or explicitly disposition the eight headless window-visibility fixture failures. |
| GC24-07–10 candidate/release | Historical receipts and runbooks exist. | Freeze exact candidate/app/backend/config/gate identity; run current regression; complete physical Mac voice, display, share, Atlas, model, and memory journeys; conduct staged pilots, independent review, rollback drill, and required observation window. |

## Ordered work packages

Work sequentially by dependency. A passing implementation test closes only
that source slice, never its live or release gate.

### 0. Reconcile current ownership and baseline — GC24-00/01

1. Record current branch, base/current commit, dirty/untracked files, linked
   worktrees, and known concurrent edits. Do not reset, clean, overwrite, or
   transplant another worker's files.
2. Before editing a file, inspect its diff and current receipt; establish
   ownership or coordinate by leaving the file untouched and updating only a
   nonconflicting plan/receipt.
3. Map each open requirement to code owner, tests, existing receipt, missing
   evidence, and next bounded action. Record installed app/backend/config and
   feature-gate identity only when directly observable; otherwise say
   “unverified.” Never print secrets or full process environments.

**Pass:** dated baseline and ownership map; no source changes in this package.

### 1. Complete execution lifecycle — GC24-02

Read `MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md` and the execution boundary
contract first. Continue by caller family, preserving direct-mode behavior.

1. Audit each inventory row against the current shared boundary. Preserve
   ordered role-aware context, supported attachments, immutable admitted
   model/route/policy, deadline, cancellation, parent identity, and
   allowlisted tool references. Reject unsupported inputs before provider
   creation or transmission.
2. Give each admitted request exactly one terminal owner across provider
   streaming, tool loops, artifacts, caller cancellation, timeout, and
   shutdown. Keep monotonically ordered validated lifecycle events. Tool and
   artifact events carry identity/metadata only unless their existing
   policy-approved result owner explicitly receives content.
3. Suppress every late result, tool dispatch, UI update, artifact, or durable
   write after cancellation/timeout. For a mutating call with an unknown
   outcome, persist a stable operation identity and reconcile before any
   retry; never blindly replay it.
4. Migrate one inventoried caller family at a time. Preserve its prompts,
   stream behavior, tools, and result semantics; prove compatibility parity
   before moving to the next family.
5. Connect shared `text_delta` events only if a current inventoried production
   workload opts into `stream_text` and requires UI delivery. Reuse the
   existing request/result identity and policy checks. The current RTVI voice
   transcript path already feeds the existing result router and must not gain
   a competing consumer.
6. Demonstrate that queued background work cannot starve interactive voice
   work, without adding a second voice transport or per-event-loop quota.

**Required evidence:** role/context and attachment preservation; reject-before-
send; one terminal under success/error/cancel/timeout/shutdown; no late writes;
tool/artifact identity and replay handling; durable unknown-mutation
reconciliation; compatibility tests per migrated caller; inventory coverage;
and a live candidate voice frame-to-pane receipt.

**Pass:** every inventoried production caller has one validated execution and
result lifecycle; unsupported or cancelled work has no side effects; the exact
candidate shows one spoken response appended to one result identity.

### 2. Close privacy source-to-sink gaps — GC24-03

Use the call-site and data-flow inventories; do not declare a sink covered by
central routing alone.

1. Resolve policy from workload and all source provenance, combining to the
strictest restriction. User/provider text cannot loosen it.
2. Enumerate and gate every outbound or persistent sink: initial and continued
provider requests, tools/results, memory reads/writes/staging, supervisor,
speech/TTS, provider persistence, result panes, display stage, share/export,
telemetry, logs, and direct execution.
3. For local-only/confidential work, keep the complete answer on the approved
local result surface. Send the supervisor only its fixed status and opaque
reference when the policy requires that separation.
4. Add synthetic unique canaries and prove absence at every prohibited sink,
including exceptions, retries, cancellation, and direct-mode branches.
5. If route or sink capability cannot be proven, block before transmission
with a clear fixed reason. Do not invent local execution or silently fall
back to a public route.

**Pass:** complete source/sink matrix with positive approved-path and negative
canary evidence; no unresolved path is represented as safe.

### 3. Finish durable automatic-memory proof — GC24-05

Follow `MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md`; SQLite remains authoritative.

1. Add independent-process tests for two workers claiming one due item and
   for forget racing a lease reclaim/apply. Verify one claim/write and no
   resurrection after forget, including reopen/restart.
2. Retain the existing claim timestamp fencing, transactional apply,
   provenance, revisions, idempotency, source-turn evidence, budget caps,
   retry/backoff, and user deletion semantics. Do not broaden classification
   or add interactive labeling.
3. Keep the production gate off until a selected model **and** route pass the
   confidential-compute/privacy evidence required by the plan. A login, API
   key, or provider probe is insufficient.
4. Run synthetic shadow comparison and benefit/cost observation using the
   existing evaluator. Write a redacted receipt with denominators, failures,
   cost/latency, and decision against the established thresholds.
5. Perform the staged Mac rollout and rollback only after route acceptance;
   record each gate and observation period. Do not replay historical exchanges.

**Pass:** multi-process durability proof, eligible route evidence, thresholds
met, and staged Mac acceptance. Until then classification stays fail-closed.

### 4. Verify model access route by route — GC24-04

Follow `MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md` and its per-model matrix.

1. For each configured model/workload/route, record exact model identity,
   auth source, capability, privacy class, billing source, latency, limits,
   and failure behavior. Do not infer subscription billing from CLI login or
   zero-reported cost.
2. Verify subscription and API routes independently, with secret-free
   receipts. Preserve manual route selection and explicit failure; no silent
   fallback or credential output.
3. Prove provider process isolation and that tool calls can only invoke the
   registered, permission-checked Mortimer bridge inside the current
   self-edit sandbox. Until that is proven, subscription mode is text-only or
   unavailable for tool workloads.
4. Verify SAYGM security claims at the route/model/workload level before
   assigning protected data. Catalog presence or public endpoint success is
   not enough.

**Pass:** evidence matrix and runtime tests for every enabled route; unsafe or
unverified combinations remain disabled with actionable status.

### 5. Complete Knowledge Atlas behavior and accessibility — GC24-06

Follow `MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md`; retain source-owned refresh
and existing result/window ownership.

1. Test expired authentication, refresh, reconnect, partial source failures,
   retry, stale last-good display, and recovery for each source.
2. Cover source mutation events and run-history completion without duplicate
   fetches when users change tabs, move displays, reopen panels, or resize.
3. Validate keyboard-only navigation, VoiceOver labels/focus order, reduced
   motion, graph density, and frame/performance limits on representative
   graphs.
4. Reproduce the eight headless window-visibility fixture failures. Fix them
   if they are product/test defects; otherwise document why the fixture is
   invalid and provide a replacement assertion plus live candidate evidence.

**Pass:** source lifecycle and accessibility receipts, performance within the
existing plan thresholds, and no duplicate network/model request on
presentation changes.

### 6. Candidate, hardware journeys, and release gates — GC24-07–10

Do this only after source gates above are ready.

1. Build and freeze the exact candidate; record app, backend, configuration,
   feature flags, and source revisions without secrets.
2. Run the full current regression on that candidate and retain the exact
   counts, skips, warnings, failures, and environment.
3. Complete physical Mac acceptance for startup, voice feedback and muted
   idle, one response identity, monitor connect/disconnect/reconnect,
   research/result sharing, Atlas, accessibility, model routing, and memory
   fail-closed/eligible-route behavior.
4. Run only approved staged pilots. Obtain independent review, rehearse
   rollback, and complete the required observation window.
5. Mark implementation, merge, deployment, live acceptance, and release as
   separate states. Do not claim an end-to-end closure from a source test.

**Pass:** exact candidate and configuration verified; all physical journeys,
pilots, reviews, rollback, and observation gates recorded as accepted.

## Handoff and status rules

- Before each task, reconcile the current worktree and latest receipt. If a
  conflicting implementation or contradictory spec appears, stop only that
  slice, record the conflict, and continue independent work.
- Every increment records files changed, behavior, focused command and exact
  result, full-suite impact if run, known limitations, and remaining parent
  acceptance. Keep failed/skipped tests in the denominator.
- Update the feature status, the verified-gap status, and this plan's relevant
  row after each accepted increment. Do not delete prior evidence; supersede
  it with dated receipts.
- A test pass closes only the tested source behavior. Route readiness,
  candidate identity, Mac acceptance, deployment, and release require their
  own evidence.
- Never include credentials, tokens, raw private prompts/results, or full
  environment dumps in plans, logs, receipts, screenshots, or test output.

## Next action

Reconcile the exact current tree and file ownership, then continue the smallest
unblocked GC24-02 lifecycle slice (caller ownership, cancellation/late-write,
or unknown-mutation reconciliation). Keep any production text-delta consumer
conditional on a real inventoried caller. Do not turn on confidential model
routes, production memory, subscription tools, or release gates without the
separate evidence described above.
