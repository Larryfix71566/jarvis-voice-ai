# Mortimer — Next Gaps Implementation Plan

**Prepared:** 2026-09-25  
**Purpose:** execution-ready, model-neutral handoff for the gaps confirmed by
the latest source and plan review. It preserves accepted product and
architecture decisions and tells an implementer where to proceed, where to
stop, and what evidence is required.  
**Target:** isolated worktree `codex/isolated-20260924`, baseline
`977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; the worktree is dirty and has
concurrent changes.  
**State:** implementation remains in progress. This document is a plan, not
proof of a merged change, Mac deployment, production enablement, or release.

## Authority and use

Use this as the short execution index for the next increments. Detailed
requirements and acceptance thresholds remain in the [Verified Gap Closure
Plan](MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md), [Current Review Gaps
Implementation Plan](MORTIMER_CURRENT_REVIEW_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md),
[Security Hardening Plan](MORTIMER_SECURITY_HARDENING_PLAN.md), [Model Use
Enhancements Plan](MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md), [Automatic Memory
Plan](MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md), [Command Console and Atlas
Plan](MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md), [GC24-03 residual diagnostic
plan](MORTIMER_GC24-03_REMAINING_EXCEPTION_LOG_REDACTION_PLAN_2026-09-25.md),
and [Implementation Status](../acceptance/IMPLEMENTATION_STATUS.md). The
feature plans own policy and thresholds; dated receipts own what was actually
tested. If documents or code conflict, stop only that slice, record the
conflict, and preserve the stricter approved contract. Do not guess a new
architecture.

## Fixed product and architecture

- Keep the selected Command Console layout, compact Conversation startup,
  eight sidecar tabs, speaker-aware orb, current voice transport, and existing
  speech/keyboard action registry.
- Keep complete answers and research in the response/results area, with brief
  live captions in Conversation. One request keeps one result identity across
  streaming, retries, cancellation, display moves, and reconnects.
- Keep current owners for request/result routing, display placement,
  permissions, tool execution, self-edit sandbox, and SQLite memory. Do not
  add a parallel queue, orchestrator, event bus, result store, tool executor,
  or memory database.
- Keep exact model identity, workload, route, capability, privacy eligibility,
  authentication, and billing evidence distinct. No silent fallback,
  arbitrary retry, privacy downgrade, or unknown-usage-as-zero.
- Keep Haiku in its accepted supervisor role and preserve the existing voice
  path. Subscription login or a successful probe does not prove isolation,
  confidential-content eligibility, capability, or free usage. Provider tools
  remain unavailable until the existing permission-checked Mortimer bridge is
  proven end to end.
- Keep memory automatic, quiet, strict, bounded, provenance-aware,
  reversible, and fail-closed; SQLite remains the system of record. Do not
  ask for routine labels, replay the historical 28 exchanges, or bulk-relabel
  existing memories.
- Preserve spoken-preview and PR-approval boundaries for self-edit. Do not
  merge, push, publish, deploy, change provider accounts, enable production
  memory, or claim release acceptance under this plan.
- Before touching any source, reconcile this dirty tree and concurrent file
  owners. Never reset, clean, or overwrite unrelated changes.

## Verified starting point

| Gap | Evidence in current isolated tree | Remaining work |
|---|---|---|
| GC24-02 — action lifecycle | Existing voice transcript-to-result route; selected run/action claims, tool-call replay guards, cancellation suppression, terminal-owner and unknown-outcome receipts. | Finish mutation-caller identity inventory and lifecycle proof. `app_create` has no durable issued preview/action ID; direct `app_register` has no durable approval claim. These contracts must be resolved before implementation—do not substitute argument hashes or infer user intent. Reconcile cancellation, late writes, artifacts, and one terminal/result owner across every production caller. Obtain exact-candidate spoken-request-to-single-results-pane evidence. |
| GC24-03 — privacy | Protected local-result handoff; bounded redaction receipts; native protected-result share-action tests pass 16; protected renderer canary tests pass 2. Protected rendering now shows only the local body, suppresses ancillary image/link/command/clipboard fields and alternate Sources/Connections views. | Complete a source-to-sink map and negative canaries across model/provider continuations, tools/MCP, memory, Supervisor/TTS, persistence, logs/telemetry, results/displays, copy/share/export, retries, errors, and direct paths. Preserve the explicit T4a same-session Supervisor-history behavior. The security plan assigns protected-history handling to T4b; do not “fix” it by deleting history or substituting placeholders. Reconcile all F1–F25 diagnostic rows to current code and receipts; redaction receipts do not prove content-flow closure. |
| GC24-04 — model access | Subscription/API foundations and a static inventory of 26/26 call sites. Checked SAYGM resolution now treats a supplied environment mapping as authoritative and refuses before catalog access if its configured key is missing; see the [explicit-environment receipt](../acceptance/verified-gap-closure/GC24-04-explicit-environment-credential-isolation-2026-09-25.md). | For each exact model × route × workload, prove identity, capabilities, isolation, privacy eligibility, cancellation/failure behavior, tool bridge, and usage/billing semantics. Unsupported or unproved combinations stay unavailable without fallback. |
| GC24-05 — automatic memory | Shared strict classifier, staged SQLite admission, provenance/evidence, bounded budgets, forgetting invalidation, claim fencing, and crash/retry/process-race receipts. | Prove an eligible confidential route using GC24-03/04 evidence; run approved shadow observation and report quality, user benefit, latency, cost, errors, and backlog against existing thresholds; then complete staged Mac acceptance and rollback. Keep production disabled/fail-closed until all gates pass. |
| GC24-06 — Knowledge Atlas | Per-source refresh/last-good/retry/generation lifecycle, run-history refresh, accessibility content, and headless-fixture classification receipts. | On the candidate, verify authentication expiry/recovery, source changes and failures, keyboard/VoiceOver, no duplicate fetch on presentation changes, visible graph performance, real unlock delivery, and physical display journeys. |
| GC24-07–10 — candidate/release | Prior UI, monitor, and release receipts. | Freeze and identify one exact source/app/backend/config candidate; run that candidate's regression; complete missing physical/provider/memory journeys; independent review; rollback drill; observation window; and status-to-receipt reconciliation. |

The latest full Python suite recorded in the current review plan is **3,054
passed, 4 skipped, 11 warnings, and 2 subtests** for its specific dirty
snapshot. Focused Swift receipts cover the two protected-renderer tests and
16 share-action tests. These counts are historical snapshot evidence; rerun
relevant checks after each change and never copy old results into a new
receipt. Neither focused nor full unit tests establish live provider, Mac,
physical-display, deployment, or release acceptance.

**2026-09-25 progress — checked-route credential boundary:** an explicit
empty environment previously fell through to the process environment for
the SAYGM catalog credential. Route resolution now fails before catalog
access in that case. The focused route/SAYGM/memory/model-execution set passed
**66**; see the [dated receipt](../acceptance/verified-gap-closure/GC24-04-explicit-environment-credential-isolation-2026-09-25.md).
This does not establish provider isolation or close the broader GC24-04
capability and billing gates.

## Ordered work packages

### 0. Reconcile ownership and baseline

Before each slice, record branch, base/HEAD, dirty and untracked paths,
sibling worktrees, code/test/receipt owners, and available toolchain. Read the
current status row, authoritative feature contract, and latest relevant
receipt; inspect the current source instead of trusting old line numbers.

**Pass:** one bounded slice has a named source/test owner, governing
contract, and current baseline. Preserve all work already in the tree.

### 1. Close remaining GC24-02 action identities and lifecycle

Start with the [mutating caller identity audit](../acceptance/verified-gap-closure/GC24-02-mutating-caller-identity-audit-2026-09-25.md).
First obtain the approved `app_create` preview/confirmation identity contract
and decide whether `app_register` remains directly callable. Treat these as
explicit product/security stop gates; do not implement a guessed scheme.
After the contract is available, bind the exact approved preview to a durable
claim in the existing action ledger, claim before dispatch, expose bounded
status/reconciliation, and mark uncertain dispatch as unknown without
automatic replay. Then inventory each production mutation caller through
provider rounds, tool dispatch, artifact/result publication, UI updates,
notifications, memory, and durable writes. Reuse current lifecycle/result
owners. Add duplicate/replay, changed-preview, restart/recovery, claim-store
failure, cancellation, non-cooperative operation, late-write, and
unknown-outcome tests. Do not claim cancellation rolls back an external
mutation that already committed.

**Pass:** no unresolved mutation auto-replays; each action has one durable
identity and terminal/result owner; cancellation suppresses later effects;
the exact candidate shows one spoken request updating one existing result.

### 2. Complete GC24-03 privacy source-to-sink proof

Use the existing call-site inventory and protected-result tests as inputs, not
as proof of full coverage. Trace sensitivity/provenance through every
continuation and every sink, including ordinary and protected content,
provider tool loops, direct-mode paths, errors, retries, and cancellation.
At existing boundaries enforce the strictest inherited policy before
processing or persistence. Keep protected full results local; where approved
external coordination is allowed, send only the approved fixed status and
opaque reference. Add unique synthetic-secret negative canaries at each
prohibited sink. Cover persistence, Supervisor/TTS, external providers,
display/result paths, ancillary payloads, and logging/telemetry. Reconcile
the F1–F25 diagnostic inventory against current source and receipts. Keep the
protected history work assigned to the accepted T4b contract; if its
authoritative T4b contract is missing or ambiguous, mark it blocked and
continue independent privacy sinks.

**Pass:** checked-in source-to-sink matrix; negative canary per prohibited
path and failure/continuation branch; every remaining sink has a documented
approved disposition; status clearly separates scoped logging/rendering
closures from complete privacy closure.

### 3. Prove GC24-04 model route behavior

For each configured model, workload, and route, record exact model/runtime,
credential source (without secret values), text/image/stream/tool capability,
cancellation, isolation, privacy eligibility, limits, failure semantics, and
usage/billing basis. Exercise routes independently with the approved isolated
runner, allowlisted environment, no persistent session, bounded child-process
cleanup, and no project hooks/tools unless that capability is explicitly
under test. Parse result and error envelopes; a zero exit status alone is not
success. Do not infer confidentiality or zero cost from account status,
catalog, or a public probe.

**Pass:** secret-free route/workload matrix and receipts prove each supported
capability and its limits. Anything unproved is unavailable and has no
fallback.

### 4. Complete memory shadow and staged rollout gates

Keep the existing strict classifier, SQLite ownership, provenance/evidence,
budget reservation, fencing, forgetting, and rollback semantics. Complete any
remaining deterministic crash/concurrency coverage found by source review.
Only after GC24-03/04 establishes eligible confidential routing, run the
existing shadow evaluator and compare measured quality, user value, latency,
cost, errors, and backlog against the already-approved thresholds. If those
pass, follow the existing staged Mac rollout, observation, and rollback
procedure. Do not change thresholds or replay the historical 28 exchanges.

**Pass:** route/privacy proof, shadow thresholds, staged Mac acceptance, and
rollback each have separate dated evidence; otherwise production stays
disabled/fail-closed.

### 5. Finish GC24-06 live Atlas acceptance

On the exact candidate exercise every supported source through auth expiry
and recovery, mutation, stale last-good content, partial failure, retry, and
reconnect. Verify keyboard-only and VoiceOver focus, labels, values, and
announcements. Show tab, presentation, window size, and display movement do
not create duplicate fetches. Measure the graph on a visible display using
the approved fixture. Verify actual macOS unlock notification and physical
monitor connect/disconnect/rehome flows. Keep headless skips limited to
tests that truly need a visible WindowServer.

**Pass:** per-source, accessibility, fetch identity, performance, unlock,
and physical-display receipts match the existing Atlas acceptance contract.

### 6. Freeze, verify, and hand off one candidate

Only after source-level prerequisites pass, record exact source SHA, app
bundle identity, backend revision, and non-secret effective feature
configuration. Run regression on that exact candidate and complete the
required compact-startup, voice/orb, single-result, monitor, Atlas,
text/image-sharing, privacy, eligible-memory, and sandboxed self-edit
journeys. Obtain independent review, prove rollback, observe for the existing
required window, and reconcile every status row to a dated receipt. Keep
implementation, merge, deploy, production enablement, and release as separate
states.

**Pass:** all required gates are evidenced against the same frozen candidate;
no status is advanced on the basis of an earlier source snapshot or a test
that did not exercise the relevant boundary.

## Per-slice handoff protocol

Any model continuing this work must, for each bounded slice:

1. Read this plan, the feature contract, current status row, relevant receipt,
   repository instructions, and current source.
2. Reconcile dirty ownership and state the invariant before editing. Do not
   overwrite user/concurrent work or broaden the slice.
3. Make only the smallest compatible change; add meaningful regression tests
   at the boundary. Keep credentials, prompts, results, memory contents, and
   private paths out of receipts and logs.
4. Run focused tests, required lint/build checks, and broader regressions when
   the boundary warrants them. Review the diff for unrelated changes and
   privacy, cancellation, accessibility, and visual regressions.
5. Add a dated receipt with exact snapshot identity, commands, counts,
   skips/failures, and residual gaps. Update `IMPLEMENTATION_STATUS.md` only
   to the level that receipt proves.
6. Leave the work uncommitted and unpushed. If a provider, physical Mac,
   product contract, or T4b policy is unavailable, record that precise gate
   and continue independent work.

**Current next action:** resume at Work Package 0, then implement only
well-specified GC24-02/03/04/05/06 slices. The `app_create`/`app_register`
identity and any missing T4b private-history policy are explicit stop gates;
all independent, contract-complete work remains actionable.
