# Mortimer — Remaining Gaps Execution Plan

**Prepared:** 2026-09-25  
**Purpose:** give any implementation model a single, dependency-ordered path
through the gaps confirmed by the current project review, without reopening
accepted product or architecture decisions.  
**Implementation tree:** `codex/isolated-20260924`, currently based on
`977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`.  
**State:** implementation is in progress in the isolated tree. The progress
entries below describe only slices with dated evidence; they do not mean the
remaining work is complete. This plan does not authorize merge, push,
deployment, production memory enablement, or changes to provider accounts.

This is the operational index for the remaining work. Detailed requirements
and thresholds stay in the [Verified Gap Closure
Plan](MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md), the [reviewed gaps
plan](MORTIMER_REVIEWED_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md), the linked
feature plans, and the dated receipts in `docs/acceptance/`. When wording or
code conflicts, pause the affected slice, record the exact mismatch, and
preserve the stricter privacy, safety, and acceptance requirement. Do not
create a parallel architecture to resolve a conflict.

## Intended outcome

Finish the verified execution, privacy, model-access, automatic-memory,
Knowledge Atlas, and candidate-acceptance gaps while preserving Mortimer as
Larry selected it. Each change must be bounded, reversible, testable, and
recorded in a dated receipt. Keep these states distinct: implemented in the
isolated tree, merged, candidate verified, live accepted, and released.

## Decisions that are fixed for every implementer

- Keep Command Console layout 2, compact Conversation at startup, all eight
  scrollable sidecar tabs, the accepted speaker-aware atom/comet orb, the
  working font picker, keyboard/voice controls, and the legacy-layout rollback
  path.
- Keep full answers in the existing response/results area and brief live
  captions in Conversation. A request owns one result identity. Appends,
  tab/display movement, reconnect, and panel reopening must not create a
  second request, fetch, answer surface, or result window.
- Keep the current voice transport, STT/TTS, measured voice feedback, and
  Haiku supervisor role. Do not migrate voice to a subscription route as part
  of this work.
- Keep model, route, workload, privacy, capability, authentication, and
  billing as separate facts. No silent model/route fallback, paid API
  fallback, privacy downgrade, unverified capability claim, or unknown-cost
  value reported as zero.
- Provider tools stay disabled unless the exact runtime is isolated and the
  task-scoped Mortimer bridge, existing permission checks, action registry,
  and sandbox executor are proven together.
- Protected data remains local unless the exact model and route have verified
  confidential-processing capability. A credential, login, catalog listing,
  or public probe is not proof of that capability.
- Keep SQLite as the sole memory system of record. Classification remains
  strict, automatic, quiet, bounded, provenance-aware, reversible, and
  fail-closed. Do not prompt for routine labels, add another memory store,
  replay the recovered 28 exchanges, or bulk-relabel existing memories.
- Keep self-edit in the existing sandbox; preserve the existing spoken-preview
  behavior and PR approval boundary.
- Work only in the named isolated tree. Reconcile shared dirty-file ownership
  before editing and preserve every concurrent change. Do not modify the
  active/main or other model's worktree as part of this plan.

## Verified baseline and open gaps

Evidence below describes the dirty isolated tree, not `main`, the installed
Mac app, or production. Re-run checks before relying on counts.

| Workstream | Verified in current tree | Still open |
|---|---|---|
| GC24-00/01 — baseline and ownership | Isolated branch and dated source/test receipts exist. | Reconcile branch, base, HEAD, dirty/untracked paths, sibling worktrees, file owners, toolchain, and exact candidate/backend/config identity before each increment. Unknown runtime facts stay marked unverified. |
| GC24-02 — execution lifecycle | Existing RTVI voice text flows through JarvisClient.transcript, AppMessageRouter, and ResponseResultRouter; selected cancellation, terminal ownership, replay guards, unknown-outcome logging, direct Pipecat Supervisor tool-run logging, durable one-shot plan_start and app_build_start claims keyed by SubAgent run ID, staged self-edit claims, and safe native Edit-tab run IDs/retries have receipts. Bare self-edit, app-build, and plan starts now refuse missing/oversized IDs before dispatch. | Extend action-specific reconciliation to other mutating caller families and publication/update outcomes; remaining caller lifecycle coverage; one terminal/result/artifact owner across complete provider/tool rounds; provider/tool cancellation and late-write suppression; a shared text-delta consumer only if an inventoried production caller needs it; exact running-candidate voice-to-pane evidence. Same-run claims do not close GC24-02. |
| GC24-03 — privacy | Covered policy floors, protected local-result handoff, fail-closed external MCP denial when sensitivity context is absent/armed, and MCP/watcher/clipboard/agent/admin/memory/startup-maintenance log-redaction slices have receipts. | Complete source-to-sink enforcement and negative canaries for direct and routed continuations, tools, memory, supervisor/TTS, provider persistence, result/display, copy/share/export, logs, telemetry, and subscription paths. |
| GC24-04 — model access | Claude/Codex subscription and SAYGM adapter/config foundations exist; static call-site audit records 26/26 covered, zero review-required, secret-free. | Exact model/runtime/route capability, isolation, cancellation, usage/billing semantics, privacy eligibility, and Mortimer tool-bridge proof. Unsupported combinations must remain unavailable. |
| GC24-05 — automatic memory | Strict shared classifier; staged SQLite admission; budget reservations; evidence checks; forget invalidation; claim fencing; process-race and crash/retry receipts exist. Focused admission/worker/acceptance tests pass 77. | Verified eligible confidential route, shadow quality/benefit/cost observation, then staged Mac rollout and rollback evidence. Production stays disabled and fail-closed until prerequisites pass. |
| GC24-06 — Knowledge Atlas | Per-source refresh lifecycle, last-good state, retry/reconnect, generation guards, run-history refresh, and headless-fixture classification have receipts. Atlas focused tests pass 10/10; full MortimerHost passes 265 with 7 explicit environment/display skips and 0 failures. | Live auth expiry/recovery and source-change journeys; keyboard/VoiceOver acceptance; proof that presentation changes do not duplicate fetches; on-screen graph performance; real unlock delivery; physical monitor journeys; current-candidate acceptance. |
| GC24-07–10 — candidate/release | Historical interface, monitor, and release evidence is retained. | Freeze exact source/app/backend/config; run regressions on that artifact; complete physical Mac/provider/memory journeys; independent review; rollback drill; observation window; reconcile every status row. |

The current verification snapshot recorded in docs/acceptance/IMPLEMENTATION_STATUS.md
is **2,956 Python unit/integration tests passed, 4 skipped, 11 warnings, 2
subtests** and **265 MortimerHost tests, 7 skipped, 0 failures**. The visible
window tests, on-screen graph benchmark, and physical-display journeys require
an interactive display/monitor and are not counted as successful when
skipped. Current test counts do not prove candidate or release acceptance.

## Dependency order

```text
GC24-00/01 reconcile isolated tree and ownership
             ↓
GC24-02 execution lifecycle ──┐
GC24-03 privacy source/sink ──┼──→ GC24-04 model/route evidence
GC24-06 Atlas source/access ──┘             ↓
                                  GC24-05 memory route, shadow, rollout
                                             ↓
                         GC24-07–10 exact candidate, journeys, review,
                                  rollback, observation, release decision
```

**2026-09-25 progress — GC24-02 bounded action claim:** Migration 0029 and
the existing SQLite ownership model now prevent plan_start from launching
twice under distinct provider call IDs within one SubAgent run. Its
content-free status receipt survives replacement of the singleton live-job
slot. Focused DB/admin/MCP/manifest/tenant validation passes **126**; the full
Python unit/integration suite passes **2,930**, with **4 skipped**, **11
warnings**, and **2 subtests**. This does not dedupe across a new SubAgent run
ID, cover other mutation families, or prove external side-effect state. See
the [run-scoped plan-start claim receipt](../acceptance/verified-gap-closure/GC24-02-plan-start-run-scoped-claim-2026-09-25.md).

**2026-09-25 progress — GC24-02 bounded app-build action claim:** the MCP
registry now injects the stable SubAgent run ID into app_build_start while
keeping it hidden from the model-visible schema. The sidecar uses the same
tenant-scoped SQLite claim table, returns duplicate requests as not started,
and supports action-specific status lookup after the singleton slot moves.
Focused app-build, MCP, and registry tests pass **78**; Ruff `F`/`I` and
`git diff --check` pass. Cross-run and direct Supervisor identities remain
open. See the [dated app-build claim
receipt](../acceptance/verified-gap-closure/GC24-02-appbuild-run-scoped-claim-2026-09-25.md).

**2026-09-25 progress — GC24-03 external MCP missing-context guard:** the
registry now calls the authoritative fail-closed sensitivity predicate, so
an unset turn context cannot send arguments to an external MCP child. New
negative canaries cover missing and armed contexts; an explicit unarmed
context preserves allowed public use. The focused registry/SubAgent/
Supervisor suite passes **92** and the full Python unit/integration suite
passes **2,940**, with **4 skipped**, **11 warnings**, and **2 subtests**.
This closes only the registry boundary. See the [dated
receipt](../acceptance/verified-gap-closure/GC24-03-external-mcp-missing-context-fail-closed-2026-09-25.md).

**2026-09-25 progress — GC24-03 mid-task financial-result canary:** when a
local tool introduces a financial detail during a public task, SubAgents now
stop before an unverified external continuation, switch run-log redaction on,
and emit metadata-only activity. The voice Supervisor stops before another
voice-model round and removes the raw tool round from retained history. The
focused SubAgent/Supervisor/run-log suite passes **127**; the full Python
suite passes **2,943**, with **4 skipped**, **11 warnings**, and **2
subtests**. This covers existing financial patterns only, not every private
data type or source/sink. See the [dated
receipt](../acceptance/verified-gap-closure/GC24-03-sensitive-tool-result-midtask-stop-2026-09-25.md).

**2026-09-25 progress — GC24-02 staged self-edit cross-run claim:** confirms
now atomically claim the already-issued staging ID for both planner and
developer-authoring starts. Duplicate requests return not-started, and
action-specific status remains available after the live job slot moves.
Focused admin/self-edit/MCP/app-build/plan/run-log tests passed **212**;
self-edit end-to-end tests passed **3**; the full Python suite passed **2,950**, with
**4 skipped**, **11 warnings**, and **2 subtests**. This covers staged
self-edit only. See the [dated
receipt](../acceptance/verified-gap-closure/GC24-02-selfedit-staged-action-cross-run-claim-2026-09-25.md).

**2026-09-25 progress — GC24-03 startup-maintenance log redaction:** six
best-effort startup exception handlers now retain event and exception class
without raw exception text. Pipeline-wiring tests passed **39**; full Python
unit/integration passed **2,956**, with **4 skipped**, **11 warnings**, and
**2 subtests**. This closes only those six logging paths; the full privacy
source-to-sink phase remains open. See the [dated
receipt](../acceptance/verified-gap-closure/GC24-03-startup-maintenance-log-redaction-2026-09-25.md).

GC24-02, GC24-03, and GC24-06 can proceed in separate bounded slices after
the baseline is reconciled. Deterministic GC24-05 tests may proceed while
route evidence is pending, but no production classifier rollout may start.
Provider-dependent model work and live memory rollout depend on privacy and
capability evidence. Candidate acceptance uses one frozen artifact and
depends on every applicable source, route, privacy, and feature gate.

## Ordered work packages

### 0. Reconcile baseline and ownership — GC24-00/01

Before editing, record branch/base/HEAD, dirty and untracked paths, sibling
worktrees, concurrent owners, toolchain, exact source/test/receipt owner for
the selected slice, and the latest relevant commands/counts. Never overwrite
another model's work or assume the installed candidate matches this tree.
Capture app/backend identity and effective non-secret gates only when the Mac
is available; mark unavailable facts unverified.

**Pass:** a dated baseline names the selected bounded slice, its authoritative
contract, code/test owners, receipt path, and missing proof without losing or
reverting existing edits.

### 1. Finish request lifecycle and action reconciliation — GC24-02

1. Trace the selected caller from admission through provider rounds, tools,
   artifacts, result delivery, logs, and durable writes. Extend the inventory
   rather than assuming that a shared helper makes every caller safe.
2. Preserve the existing RTVI-to-`ResponseResultRouter` voice consumer. Do not
   add a second consumer for those same tokens. Add a generic shared-execution
   delta consumer only when a covered production caller needs it; route it
   through the existing result identity and inherited privacy policy.
3. Ensure one owner emits ordered, correlated progress/text/tool/artifact
   events and exactly one terminal result for the complete provider/tool
   lifecycle. Keep compatibility behavior for callers that do not subscribe
   to events.
4. Carry cancellation/deadline through provider and tool execution, result
   observers, and durable writes. After terminal cancellation/timeout, block
   late text, tool dispatch, artifact/result delivery, UI changes, memory/DB
   writes, and completion notifications. State explicitly that cancellation
   cannot undo an external mutation already committed inside a tool.
5. For mutating calls, persist action-specific dispatch/outcome identity. If
   dispatch may have occurred but the result is unknown, block automatic
   retry, including when a later provider turn supplies a new call ID. Define
   a safe reconciliation path from existing receipts; do not invent a generic
   argument hash as proof that two real-world actions are equivalent. The
   staged self-edit start is now covered by a claim keyed to its issued
   staging ID; inventory and close each other stable-ID caller separately.
6. Preserve the current voice priority and non-voice admission limit. Do not
   add another queue, orchestrator, event bus, result store, or tool executor.

**Required proof:** complete caller inventory; duplicate/malformed ID tests;
one terminal across multiple provider/tool rounds; cancellation before and
during provider/tool work, including non-cooperative adapters; no late
effects; unknown mutation cannot auto-replay under a new call ID; correlated
artifact/tool-result ownership; compatibility parity; and a live candidate
voice-to-one-result journey. Re-run the call-site audit.

**Pass:** each inventoried production caller has one lifecycle/result owner,
unresolved mutations cannot be replayed automatically, and no post-terminal
side effect occurs. Record unsupported streaming/cancellation capabilities
as unavailable.

### 2. Close privacy at every source and sink — GC24-03

1. Extend the call-site inventory to a source-to-sink map recording provenance,
   policy resolution, transformations, and each continuation/destination.
2. Enforce the strictest inherited policy before every provider request and
   continuation, tool/MCP action, memory read/write/staging, supervisor
   handoff, TTS, provider-session persistence, result/display, attachment,
   copy/share/export, log, usage/error telemetry, and direct-mode path.
3. Keep protected full results in the approved local result area. External
   coordination receives only the already-approved bounded status and opaque
   reference. If route or sink eligibility is missing, fail closed before
   sending or persisting content.
4. Use distinct synthetic canaries for each source and sink. Test mixed
   policy, sensitive content introduced mid-task, retries/errors/timeouts,
   cancellation, route preference changes, direct execution, and UI/share
   attempts. Prove forbidden destinations receive neither content nor a
   content-bearing derivative.

**Pass:** every inventoried prohibited path has executable negative tests and
no caller, route preference, exception, or continuation can lower policy.
Keep the existing external voice-provider exception narrowly and accurately
documented.

### 3. Prove each model/route capability — GC24-04

For each configured model/workload/route, consult the official documentation
for the exact pinned runtime and record version, authentication mode, input
types, streaming, structured output, tools, cancellation, limits, failure
envelopes, privacy class, and usage/billing semantics. Probe only synthetic
public data unless the exact confidential route is already verified.

Run subscription clients in a task-scoped isolated process: clean working
directory; allowlisted environment; no project hooks, plugins, MCP, native
tools, or persistent session; bounded input/output; process-group cancellation;
and cleanup on all exits. Parse the documented success/error envelope; exit
code alone is insufficient. Keep route selection separate from billing
evidence and actual account charges. Do not save passwords/OAuth material in
the repo or project vault. Do not enable provider tools until the full
Mortimer bridge, permissions, sandbox, policy, idempotency, and cancellation
proof passes.

**Pass:** a secret-free receipt proves each capability independently. Missing
evidence means the combination remains unavailable; there is no silent API or
privacy fallback.

### 4. Finish automatic-memory route and rollout acceptance — GC24-05

Preserve the current strict classifier, SQLite-only system of record,
provenance/evidence checks, durable staging, shared atomic budgets,
idempotency, forget/delete behavior, claim fencing, bounded retries, and
rollback. Do not reopen schema or classifier design without evidence that the
authoritative memory plan requires it.

1. Keep deterministic durability/concurrency/fault tests and shadow behavior
   current; shadow must not alter live admission, retrieval, prompts, or
   cursor state.
2. Keep live admission disabled until GC24-03 proves the path and GC24-04
   proves a compliant confidential route for the exact classifier.
3. Once both pass, run the existing synthetic shadow evaluator and record
   denominators, quality, false admissions/rejections, latency, cost, errors,
   backlog, and decisions against the already-approved thresholds.
4. Only after shadow passes, follow existing staged Mac rollout, observation,
   backup, and rollback runbook. Roll back only the attributable staged
   revisions through the existing undo path. No replay of the historical 28
   exchanges is part of this plan.

**Pass:** route/privacy receipts, quality and budget thresholds, staged
observation, a restorable database backup, and rollback proof all exist.
Otherwise production remains disabled and fail-closed.

### 5. Complete Knowledge Atlas live behavior and access — GC24-06

Retain the existing store-owned per-source refresh lifecycle, last-good data,
bounded errors, explicit retry, reconnect triggers, and generation guards.
Do not add another client, periodic poller, duplicate websocket, or data
source. A display/tab/layout move must not fetch again.

1. Keep display-dependent tests and the real frame-time assertion active on an
   interactive display. Skip only when their explicit screen/window-server
   precondition is absent. Keep non-display observer, data, and placement
   tests active. Do not weaken thresholds or call skips passes.
2. On the exact Mac candidate, test auth expiry/recovery, source changes,
   partial failures, retry/reconnect, stale-state labels, cancellation, and
   preservation of graph selection/groups/pins.
3. Verify VoiceOver names/status, keyboard focus and refresh/retry, useful
   loading/empty/error states, and reduced-motion/transparency settings.
4. Measure graph responsiveness/resource use on the existing approved fixture
   scale. Count source requests across tab/display moves and reconnects; no
   duplicate fetch is allowed. Verify real screen-unlock delivery and
   connected-display placement separately from injected unit seams.

**Pass:** source recovery, accessibility, no duplicate fetch, on-screen graph
performance, unlock notification, and physical display receipts satisfy the
existing Atlas and monitor contracts.

### 6. Freeze and accept one candidate — GC24-07–10

Begin only after applicable source/privacy/route gates pass. Build one
candidate from the reconciled isolated source and record source SHA/dirty
state, app artifact, backend identity, non-secret effective configuration,
feature gates, and matched test evidence. Run the current regression,
privacy/call-site audit, packaging/signature checks, and performance checks
on that candidate, retaining exact pass/fail/skip counts.

On the physical Mac, complete the remaining applicable journeys on that same
candidate: compact startup; user/Mortimer voice, mute, and orb; one response
identity; research and text/image sharing; eight tabs and font picker;
keyboard/VoiceOver; Knowledge Atlas refresh; a bounded supporting-display
stage; attach/detach/reconnect/rehome without duplicate work; protected-data
handling; disabled/eligible staged memory; and sandboxed self-edit preview,
PR approval, and rollback. macOS Spaces do not substitute for a physical
second display.

Run provider pilots on synthetic public data first, then only explicitly
approved non-voice workloads. Record selected model/route/privacy/auth,
quality denominator, queue/cold/warm/first-useful/total latency, cancellation,
failures, usage-known state, and billing evidence. Preserve approved quality
and latency thresholds. Obtain independent review, demonstrate feature
disablement and rollback, complete the required observation window, and
reconcile every status row to a receipt. A source/config change restarts the
affected candidate evidence.

**Pass:** the exact frozen artifact is traceable through all applicable
regression, physical, provider/memory pilot, independent review, rollback,
and observation receipts. Anything requiring unavailable hardware/provider
evidence remains explicitly open with an owner and next action.

## Handoff contract for every implementation turn

Before editing, the next model must:

1. Read this plan, repository instructions, the authoritative GC24/feature
   contract for its slice, the latest receipt, and the exact source/test files.
2. Recheck `git status`, branch/base/HEAD, sibling worktrees, toolchain, and
   file ownership. The working tree is already dirty; preserve every change.
3. Choose one bounded slice and state its invariant and pass condition. Do
   not combine unrelated UI, execution, model-route, memory, or release work.
4. Add meaningful boundary tests, run focused tests and relevant lint/build
   checks, and run the broader suite when scope/regressions justify it. Keep
   failures and skips visible.
5. Add a dated receipt with exact revision, files, commands, results,
   invariants, limits, and next action. Update the existing status row and
   plan based on evidence; avoid duplicate IDs or stale counts.
6. Check `git diff --check`, changed-document links/manifests when affected,
   and inspect for secrets, raw user content, weakened defaults, fallback,
   duplicate architecture, or unrelated design changes.
7. Leave work uncommitted/unpushed. Never describe source tests as a merge,
   deployment, live acceptance, or release.

Do not include credentials, raw private prompts/results, environment dumps,
or secret-bearing screenshots in code, plans, test output, logs, or receipts.

## Progress update policy

Update this plan and `docs/acceptance/IMPLEMENTATION_STATUS.md` after each
evidence-backed slice. State what changed, the exact receipt and test result,
what remains open, and the next unblocked action. Never convert an environment
skip into a pass or infer an overall completion percentage from overlapping
checklists.
