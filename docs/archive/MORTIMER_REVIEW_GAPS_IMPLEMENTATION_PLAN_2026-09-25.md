# Mortimer — Review-Gap Implementation Plan

> **Archived 2026-09-28 — superseded as an execution index.** The canonical plan is [MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md](../plans/MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md). This archive preserves the original requirements and evidence for history; it does not mark any gate complete.


**Prepared:** 2026-09-25
**Purpose:** provide a model-neutral, implementation-ready sequence for the
gaps that remain after the latest code and plan review.
**Target tree:** isolated worktree `codex/isolated-20260924`, based on
`977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; this tree already contains
uncommitted and concurrent work.
**Scope:** remaining source, evidence, live-candidate, and release gates. This
plan does not authorize merging, pushing, deployment, using the Mac vault, or
changing accepted product behavior.

This is a navigational handoff, not a replacement for the detailed contracts
in the [Current Verified Gaps plan](../plans/MORTIMER_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md),
the [Newly Verified Gaps plan](../plans/MORTIMER_NEWLY_VERIFIED_GAPS_IMPLEMENTATION_PLAN.md),
the [Post-Review Gap Closure plan](../plans/MORTIMER_POST_REVIEW_GAP_CLOSURE_PLAN_2026-09-25.md),
or the authoritative feature plans they cite. If code, receipts, or plans
disagree, stop the affected slice, document the precise discrepancy, and
preserve the stricter privacy, safety, and acceptance requirement. Do not
resolve uncertainty by inventing architecture.

## Target outcome

Close the verified gaps while retaining Mortimer's accepted interface,
behavior, and architecture: Command Console layout 2; compact Conversation as
the startup view; the eight scrollable sidecar tabs; the approved speaker-aware
atom/comet orb; current voice transport and Haiku supervisor role; one request
and one result identity; SQLite as the memory system of record; the existing
self-edit sandbox; and the existing app-owned presentation, permission, and
action owners.

The plan separates implementation evidence from operational acceptance. Unit
tests, a green build, a merged change, or a past Mac observation cannot stand
in for the exact candidate, physical journey, provider route, rollback, or
observation evidence required by a later gate.

## Binding constraints for every implementing model

- Work only in the designated isolated worktree. First reconcile the dirty
  files and ownership with the latest baseline; preserve concurrent work.
- Keep full answers and research in the existing response/results area and
  short live captions in Conversation. Append updates to the same request
  result. Never create another result window for a streaming update, monitor
  change, tab switch, reconnect, or reopen.
- Keep model, route, workload, privacy policy, capability, and billing source
  as distinct facts. No silent route/model fallback, privacy downgrade,
  arbitrary retry, or missing-usage-as-zero behavior.
- Subscription-backed runtimes remain tool-disabled until task isolation and
  the Mortimer-owned, allowlisted tool bridge are proven. Existing registered
  permission/action execution and sandbox boundaries remain authoritative.
- Protected data stays local unless both the selected model and route have
  verified capability. A credential, account login, model listing, or public
  probe alone is not confidential-processing evidence.
- Memory remains SQLite-backed, strict, provenance-aware, bounded, automatic,
  and quiet. No user labeling flow, synthetic success fallback, second memory
  database, bulk relabel, or historical 28-exchange replay is part of this
  plan.
- Do not change the live voice loop, STT, TTS, audio transport, selected
  interface, or approved orb while closing unrelated gaps.
- Every increment must leave a dated receipt with exact commands, pass/skip/
  failure counts, source revision, limitations, and remaining gates. Update
  the relevant status row in the same increment.

## Verified gap register

| ID | Confirmed state | Remaining work |
| --- | --- | --- |
| GC24-02 — execution lifecycle | Shared execution infrastructure, cancellation improvements, ID replay guards, SubAgent/delegate terminal ownership, and the existing RTVI-to-transcript-to-response-result path have focused test receipts. | Generic `ModelExecutionEvent.text_delta` has no production native result consumer for any inventoried caller that needs it; exact running-candidate voice frame-to-pane journey; terminal ownership across remaining provider/tool callers; artifact/tool-result event ownership; cancellation and late-write suppression through every downstream sink; durable reconciliation of unknown mutating tool outcomes; remaining caller coverage. |
| GC24-03 — data privacy | Policy floors and protected local-result behavior are implemented for covered routed paths; several logs and status surfaces have redaction receipts. | Complete source-to-sink inventory and executable negative canaries for every remaining direct/routed continuation, tool result, memory injection, supervisor/TTS, provider persistence, result/display, copy/share/export, telemetry, SQLite staging, and subscription path. |
| GC24-04 — model access | Claude/Codex subscription and SAYGM adapter/configuration foundations exist; a call-site inventory receipt exists. | Per-model and per-route capability evidence; provider/runtime isolation; supported prompt, image, streaming, tool, and cancellation behavior; correct usage/billing evidence; protected-route proof. Keep unsupported combinations unavailable and tools disabled. |
| GC24-05 — automatic memory | Shared strict classifier, durable staging, resumable extract/classify/apply stages, budgets, digest-only shadow metadata, forget cancellation, claim-timestamp fencing, apply rollback/retry, enqueue/cursor recovery, extract/classify rollback before stage-save commit and restart after committed transitions, and terminal-completion rollback are covered by child-process tests ([claim fencing](../acceptance/verified-gap-closure/GC24-05-admission-claim-fencing-2026-09-25.md), [apply/enqueue/stage/completion crash](../acceptance/verified-gap-closure/GC24-05-admission-apply-rollback-2026-09-25.md)). | Broader concurrent forget/reclaim/duplicate-worker proof; route acceptance for a verified confidential provider path; Mac shadow/benefit observation; staged Mac enablement and rollback. Production stays disabled/fail-closed until route and rollout gates pass. |
| GC24-06 — Knowledge Atlas | Per-source refresh lifecycle, last-good retention, retry/reconnect, generation checks, and run-history refresh support have focused receipts. | Live auth expiry/recovery and source-change behavior; VoiceOver/keyboard; proof presentation/display changes do not duplicate fetches; graph scale/frame-time acceptance; current candidate acceptance. Eight headless window-visibility fixture failures recorded in the Atlas receipt must be diagnosed or explicitly classified before that gate closes. |
| GC24-07–10 — candidate/release | Historical monitor, interface, and release evidence exists. | Freeze and identify exact source/config candidate; rerun regression; physical Mac journeys; provider/memory pilot; independent review; rollback drill; required observation window; final evidence reconciliation. |

Evidence links and current test counts are maintained in the [status document](../acceptance/IMPLEMENTATION_STATUS.md), [current gap plan](../plans/MORTIMER_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md), and the dated receipts under `docs/acceptance/verified-gap-closure/`. Treat receipt counts as snapshot-specific, not as a current pass guarantee.

## Ordered execution sequence

Run one bounded slice at a time. The order below is dependency-aware; do not
start a dependent live or release gate just because its implementation work
has begun.

### 0. Establish ownership and baseline — GC24-00/01

1. Capture branch, base and HEAD, dirty/untracked files, linked worktrees,
   concurrent owners, toolchain, and baseline test results.
2. Map each open item in the gap register to its source owner, existing tests,
   authoritative plan, receipt, and missing proof. Reuse completed receipts;
   do not redo accepted slices.
3. Where a Mac candidate is available, record executable, backend revision,
   effective non-secret gates, and model route. Mark unavailable evidence
   unverified. Never print process environments, vault contents, or user data.

**Acceptance:** dated baseline, no lost concurrent edits, and every remaining
item has a bounded owner and evidence path.

### 1. Finish execution ownership and cancellation — GC24-02

1. Inventory every caller of the shared execution boundary and trace one
   request through admission, provider rounds, registered tools, artifacts,
   UI/result sinks, logs, and durable writes.
2. Add a generic streaming consumer only for inventoried shared-execution
   callers that require live results. Route validated events through the
   existing app-owned response/result owner and the same request/result ID;
   apply the inherited data policy before render, speech, persistence, log, or
   sharing. Preserve the compatibility collector for callers that do not
   subscribe to deltas. Do not add a second consumer for RTVI voice tokens;
   the existing transcript path already feeds `ResponseResultRouter`.
3. Define exactly one lifecycle owner across the full provider/tool loop:
   monotonic correlated events and exactly one terminal state. Give artifacts
   and tool results an explicit existing owner, with policy and request
   identity carried through.
4. Propagate deadline/cancellation to the provider, registered action, UI
   observer, and durable-write boundary. After timeout/cancel, reject late
   text, tool dispatch, artifact, result, notification, memory, and database
   effects. Never imply that cancellation rolls back a mutation already
   committed inside an action.
5. Before retry/restart, reconcile mutating tool calls against durable
   execution receipts. If an action may have run but its outcome is unknown,
   block automatic replay and surface a bounded reconciliation state.
6. Prove the existing RTVI-to-results path against the exact candidate on Mac;
   verify one request produces one result while updates append, and monitor,
   reconnect, and presentation changes do not duplicate it.

**Required evidence:** out-of-order and duplicate events; one terminal across
multiple tool/provider rounds; active and queued cancellation; non-cooperative
provider/tool completion; late-write suppression; safe unknown-mutation
recovery; result identity; policy-blocked stream; compatibility parity; and
live candidate journey. The authoritative GC24-02 contract defines any
additional workload-specific tests.

**Acceptance:** every inventoried migrated caller has a single lifecycle and
result owner; no forbidden or post-terminal side effect occurs; candidate
voice/result flow is observed. Generic streaming is not called complete until
the consumer and live sink are tested.

### 2. Close the complete privacy source-to-sink map — GC24-03

1. Expand the existing call-site inventory to include data origins and every
   continuation/result destination, not only model completion calls.
2. Resolve effective policy from workload and all content provenance; combine
   restrictions using the strictest existing rule. Content cannot reduce its
   own restriction.
3. At each outbound or persistence boundary, check the resolved policy before
   provider request/continuation, tool/MCP action, memory injection, supervisor
   context, TTS, result rendering, attachment transfer, export/copy/share,
   logs/telemetry, SQLite staging/history, and provider-session persistence.
4. Keep protected full results local. Where the established contract permits
   an external supervisor to coordinate, provide only fixed status and an
   opaque reference. If no compliant route exists, fail closed with a clear
   bounded state.
5. Run synthetic canaries containing unique secrets through every inventoried
   route and sink. Assert zero forbidden transmissions and no secret in logs,
   errors, events, database, receipts, or user-visible external surfaces.

**Acceptance:** inventory is complete and mechanically checked; each forbidden
sink has a negative test; allowed personalization and voice behavior remain
intact; route absence cannot downgrade the policy.

### 3. Prove model/route capability and cost independently — GC24-04

1. For each configured model/route pair, inspect the official pinned runtime
   contract and record version, auth method, prompt input, image, stream, tools,
   cancellation, and usage/billing semantics.
2. Test each capability independently in an isolated task-scoped process:
   clean working directory; allowlisted environment; no project instructions,
   hooks, plugins, MCP or provider-native tools; no persistent session; safe
   input; process-group cancellation; bounded cleanup; no child or late output.
3. Parse provider-specific success and error envelopes. Distinguish auth,
   quota/allowance, unsupported capability, timeout, cancellation, and
   provider failure. Exit code zero alone is not proof of model output.
4. Separate list-price estimates from observed account billing. Never report
   unknown spend as zero. Keep each unsupported model/route/capability
   unavailable.
5. Keep provider tools disabled until the Mortimer task-scoped bridge,
   permission checks, action allowlist, result validation, and sandbox are
   proven end to end.

**Acceptance:** secret-free evidence separately establishes model identity,
route, individual capabilities, isolation, billing evidence, and privacy floor.
No claim that subscription access is free or confidential without direct
evidence.

### 4. Complete memory durability proof before enabling production — GC24-05

1. Preserve the shared strict classifier and current SQLite schema/ownership;
   inspect the authoritative memory plan before migration or policy changes.
2. Add deterministic fault injection at every extract, classify, and apply
   transaction boundary. Terminate/reopen the worker or database between
   stages and prove the job is either resumable exactly once or safely
   terminal, with no partial memory/shadow/budget/job state.
3. Retain both apply fault regressions: one throws after the fact write, and
   one terminates a child worker at the same point. Prove transaction rollback
   leaves no partial memory, recall event, shadow metadata, or completion, and
   prove lease recovery allows one later successful retry. Extend process-
   kill/reopen injection to enqueue, extract/classify stage commits, and
   cursor/pairing boundaries not covered yet. Verify forget, retry, and claim
   fencing under concurrent/reclaimed claims.
4. Keep live provider classification disabled until GC24-04 and GC24-03 prove
   a supported route satisfies memory privacy. Then run shadow-only route
   acceptance, inspect redacted metrics and classifier quality, and compare
   with the approved evaluator thresholds.
5. Follow the existing staged memory rollout configuration. Start with
   shadow/observation, then only the already approved bounded stage; record
   benefit, cost, error, backlog, and rollback thresholds. Do not replay the
   historical 28 exchanges as part of this plan.

**Acceptance:** restart/fault suite and apply rollback proof pass; budget and
claim invariants hold; route acceptance is documented; each rollout stage has
a dated, redacted receipt and demonstrated rollback. No production enablement
before these gates.

### 5. Finish Atlas accessibility and live lifecycle acceptance — GC24-06

1. Reproduce and classify all eight recorded headless window-visibility
   failures. Do not hide them with broad skips; separate genuine app defect
   from unsupported headless display behavior with a focused fixture.
2. Verify source authentication expiry, recovery, source changes, last-good
   retention, retry, and partial-source failure in a live candidate.
3. Verify keyboard-only and VoiceOver navigation, names, focus order, refresh
   announcements, and graph labels without removing existing information.
4. Measure graph responsiveness and resource usage at the approved fixture
   scale. Confirm switching tabs/displays or reopening Atlas does not duplicate
   fetches or lose reading state.

**Acceptance:** authoritative Atlas thresholds pass and live source/auth and
accessibility receipts exist; fixture failures are resolved or precisely
classified and still visible in status.

### 6. Freeze candidate, run user journeys, and close release gates — GC24-07–10

1. Freeze an exact source revision, app bundle, backend revision, non-secret
   effective config, and test evidence. Ensure Mac candidate corresponds to
   that source/config tuple.
2. Run only missing required journeys on the physical Mac: startup/compact
   Conversation, voice in/out and mute behavior, one-result streaming,
   monitor connect/disconnect/reconnect/rehome, Atlas, text/image share,
   privacy restrictions, memory shadow and staged behavior, and sandboxed
   self-edit with approval/rollback. Record observations with redaction.
3. Complete an independent review and a rollback drill against the frozen
   candidate. Keep failed, skipped, blocked, and unavailable tests in the
   receipt; do not turn them into passes by inference.
4. Complete the required observation period and reconcile every plan/status
   row with a receipt. Preserve unresolved items as open with owner and next
   action.

**Acceptance:** candidate identity matches evidence; every required physical,
provider, privacy, memory, Atlas, and rollback gate has a dated receipt; the
observation window is complete. Merge/deploy remains a separate explicitly
authorized action.

## Model handoff checklist

Before each increment, the implementing model must:

1. Read this plan, the relevant detailed feature/closure contract, latest
   receipt, and applicable `AGENTS.md` instructions.
2. Verify current branch, revision, dirty state, owner of target files, and
   the exact test baseline. Do not assume this document's counts are current.
3. State the single bounded slice and its pass condition in the receipt before
   editing; preserve accepted behavior and concurrent work.
4. Implement and test only that slice. Run focused tests first, then required
   broader checks when justified by changed boundaries.
5. Record changed files, commands, counts, warnings/skips/failures, exact
   limitations, and follow-up gaps in a dated receipt. Update
   `docs/acceptance/IMPLEMENTATION_STATUS.md` and the relevant plan status in
   the same change.
6. Inspect the final diff for unrelated changes and verify document links.
   Do not commit, push, merge, deploy, inspect/use the vault, or edit another
   worktree unless separately authorized.

## Completion language

Use **implemented in isolated tree** for code and tests only; **verified on
candidate** only for the exact identified app/config; **pilot accepted** only
after the required live/provider observation; and **release closed** only
after all applicable GC24-00–10 gates and rollback evidence pass. A gap remains
open whenever its required evidence is missing, even when its source change
has landed.
