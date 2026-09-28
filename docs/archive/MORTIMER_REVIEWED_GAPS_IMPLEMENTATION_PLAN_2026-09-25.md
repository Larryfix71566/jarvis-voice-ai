# Mortimer — Reviewed Gaps Implementation Plan

> **Archived 2026-09-28 — superseded as an execution index.** The canonical plan is [MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md](../plans/MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md). This archive preserves the original requirements and evidence for history; it does not mark any gate complete.


**Prepared:** 2026-09-25; refreshed after the latest caller-level execution review  
**Purpose:** provide one model-neutral, implementation-ready plan for the gaps confirmed by the latest source and plan review.  
**Target:** isolated repository worktree `codex/isolated-20260924`, currently based on `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`.  
**Status:** planning and handoff only; this document does not assert that open work is complete or authorize merge, push, deployment, production enablement, or Mac-vault access.

This plan consolidates execution order and acceptance gates. Detailed feature contracts remain authoritative in the linked plans and receipts. Where documents or code disagree, pause only the affected slice, record the exact conflict, and preserve the stricter privacy, safety, and acceptance requirement. Do not invent architecture to resolve ambiguity.

## Target outcome

Close the remaining implementation and evidence gaps while preserving Mortimer’s accepted design and architecture: Command Console layout 2; compact Conversation as the startup view; all eight scrollable sidecar tabs; the approved speaker-aware atom/comet orb; existing voice transport and Haiku supervisor role; one request with one result identity; SQLite as the memory system of record; the established self-edit sandbox; and current app-owned action, permission, and presentation owners.

## Decisions every implementer must preserve

- Full answers and research appear in the existing response/results area. Conversation keeps brief live captions. Updates append to the same request result; monitor changes, tab switches, reconnects, and reopening do not duplicate requests or windows.
- Do not redesign the interface, change the live voice loop/STT/TTS/audio transport, replace the supervisor, or add another orchestrator/result store as part of gap closure.
- Keep model, route, workload, privacy, capability, and billing source distinct. Never silently change model/route, lower privacy, replay an action with unknown outcome, or report unknown spend as zero.
- Subscription-backed runtimes remain tool-disabled until task isolation and the Mortimer-owned allowlisted action bridge are proven. Existing permission checks and sandbox remain authoritative.
- Protected data stays local unless both the chosen model and route have verified capability. Login, key presence, model listing, or a public probe alone is not evidence of private processing.
- Keep memory strict, provenance-aware, bounded, automatic, quiet, and SQLite-backed. Do not add user labeling, heuristic success fallback, a second memory database, bulk relabeling, or historical 28-exchange replay.
- Work only in the designated isolated worktree. Reconcile current dirty files and concurrent owners before touching shared files; preserve their edits.
- Keep implementation, merge, deployment, live candidate acceptance, and release acceptance as separate states. Every closure claim needs a dated receipt with exact source revision, command, result counts, limitations, and remaining gates.

## Reviewed baseline and remaining gaps

These are findings in the reviewed isolated source tree, not claims about `main`, the installed Mac app, or production.

| Workstream | Present evidence | Remaining gap |
|---|---|---|
| **GC24-00/01 — baseline and ownership** | Current source status and several dated implementation receipts exist. | Refresh the exact branch/base/HEAD, dirty-file and worktree ownership, toolchain, and app/backend/config identity before each increment. Map each open acceptance row to an owner and evidence path. Runtime facts unavailable to the model stay explicitly unverified. |
| **GC24-02 — execution lifecycle** | Shared execution infrastructure, selected cancellation and terminal-owner fixes, provider tool-call replay guards, and the existing RTVI transcript-to-`ResponseResultRouter` voice path have focused receipts. SubAgent run logs now correlate call IDs and surface unresolved/unknown outcomes; the [Pipecat Supervisor direct-tool adapter](../acceptance/verified-gap-closure/GC24-02-supervisor-direct-tool-runlog-2026-09-25.md) also has durable redaction, call-correlation, nested-MCP, exception, and cancellation evidence. | This is visibility, not action idempotency: determine/implement action-specific reconciliation across new provider call IDs; complete caller-by-caller lifecycle and artifact/tool-result ownership; propagate cancellation and suppress late writes at every downstream sink; prove remaining caller parity; and observe the exact candidate voice-frame-to-result-pane journey. A generic `ModelExecutionEvent.text_delta` consumer is conditional: add one only if an inventoried production caller needs it. |
| **GC24-03 — privacy** | Policy floors, protected local-result handoff for covered specialist calls, and multiple redacted logging/status paths have receipts. | Complete source-to-sink inventory and negative canaries for all direct and routed continuations, tools, memory, supervisor/TTS, provider persistence, display/result, copy/share/export, telemetry/logs, and subscription runtime paths. |
| **GC24-04 — model access** | Claude/Codex subscription and SAYGM configuration/adapter foundations and a 26/26 call-site inventory receipt exist. | Independently prove each configured model/route capability, process isolation, usage/billing semantics, cancellation and failure behavior, privacy eligibility, and tool bridge. Unsupported combinations remain unavailable. |
| **GC24-05 — automatic memory** | Shared strict classifier; staged SQLite extract/classify/apply; budget reservation; provenance/evidence checks; forget invalidation; fencing, rollback/retry, process-race and crash receipts. | Prove route eligibility for confidential classification, complete shadow quality/benefit/cost observation, then perform the approved staged Mac rollout and rollback. Production remains disabled/fail-closed until gates pass. Do not replay historical exchanges. |
| **GC24-06 — Knowledge Atlas** | Per-source refresh lifecycle, last-good retention, retry/reconnect, generation checks, and run-history refresh have focused receipts; focused Atlas suite passes 10. Full MortimerHost suite passes 265 with 7 explicit skips and no failures. The historical window-visibility failures are classified as requiring a visible WindowServer; unlock callback logic has a deterministic injected unit test. | Live source authentication expiry/recovery and mutations; VoiceOver/keyboard accessibility; no duplicate fetch on presentation changes; actual on-screen graph scale/performance; real unlock delivery; physical display and current-candidate acceptance. See the [headless fixture receipt](../acceptance/verified-gap-closure/GC24-06-headless-window-fixture-classification-2026-09-25.md). |
| **GC24-07–10 — candidate and release** | Historical interface, monitor, and release evidence exists. | Freeze exact candidate/source/config; rerun regression; complete physical Mac journeys, provider and memory pilots, independent review, rollback drill, observation window, and final plan/status reconciliation. |

Use the latest dated receipts referenced by [implementation status](../acceptance/IMPLEMENTATION_STATUS.md) and the [post-review gap closure plan](../plans/MORTIMER_POST_REVIEW_GAP_CLOSURE_PLAN_2026-09-25.md). Older test totals are historical snapshots; rerun relevant checks before relying on them.

## Dependency order

```text
GC24-00/01 ownership baseline
          ↓
GC24-02 execution lifecycle ──┐
GC24-03 privacy source/sink ──┼─→ GC24-04 model/route proof
GC24-06 Atlas live/accessibility│
          ↓                    │
GC24-05 memory route + shadow ←┘
          ↓
GC24-07–10 frozen candidate, physical journeys, review, rollback, observation
```

GC24-02, GC24-03, and GC24-06 can proceed in independent bounded slices after baseline reconciliation. GC24-05 may complete local deterministic tests while provider/privacy evidence is pending, but no live classifier rollout may begin. Candidate and release gates depend on applicable source, route, and privacy gates.

## Work packages and acceptance

### 0. Reconcile baseline and ownership — GC24-00/01

1. Record branch, base and HEAD, dirty/untracked files, linked worktrees, concurrent owners, runtime/toolchain, and current test baseline without printing secrets or user data.
2. For each open row, name the authoritative contract, code owner, tests, latest receipt, next bounded slice, and missing evidence.
3. When a Mac candidate is available, capture app bundle identity, backend revision, and effective **non-secret** gates/config. Mark inaccessible facts unverified.

**Pass:** dated baseline with no lost concurrent work; every remaining row has an owner and evidence path.

### 1. Complete request execution lifecycle — GC24-02

1. Trace every shared-execution caller across admission, provider rounds, registered tools, artifact/result sinks, logs, and durable writes. Preserve existing per-caller behavior unless its contract requires a change.
2. **Close the newly found live Pipecat Supervisor direct-tool observability gap first.** Inspect the existing dirty diff and tests in `jarvis/bot/pipeline.py` and `tests/unit/test_supervisor_tool_registration.py` before editing; preserve the live tool schemas, handler behavior, Pipecat result callback contract, voice response routing, and permission/action owners. Give each invocation a stable run ID and provider `tool_call_id`; scope the existing run logger around the handler so registry/MCP detail correlates to that run; record only redacted metadata and bounded status/error class, never arguments or result text. A normal return must be recorded before returning its value to Pipecat. Cancellation after dispatch must produce one unknown-outcome receipt, suppress a late result callback, and propagate cancellation. Exceptions must produce a bounded unknown/failure record and preserve existing caller error semantics. Keep run logging behind the existing setting and avoid adding a second execution or result store.
3. For this direct Supervisor slice, test successful correlated result, sensitive-data redaction, cancellation while the handler is blocked, cancellation swallowed by an adapter, exception after dispatch, and disabled logging. Assert call identity is present where available, arguments/results are absent from persisted logs, no callback occurs after cancellation, and the task ends with one terminal status. Run the focused Supervisor/runlog/MCP/SubAgent suites, Ruff `F`/`I`, and `git diff --check`; then run the full Python unit/integration suite because the live pipeline wiring changes.
4. Ensure one owner correlates the complete provider/tool loop, emits monotonic events, and records exactly one terminal outcome. Give tool results and artifacts stable request/call identity.
5. Propagate timeout/cancellation through provider, tool, UI observer, and durable-write boundaries. After termination, reject late text, dispatch, artifacts, UI updates, notifications, memory changes, and writes. State clearly that cancellation cannot undo a mutation already committed inside a tool.
6. Store a durable receipt for each mutating tool dispatch. If dispatch may have occurred but no terminal result is known, mark the outcome unknown and block automatic retry/replay until reconciled. A new provider call ID must not bypass a prior unresolved action.
7. Preserve the existing RTVI voice stream path; do not add a second consumer for those tokens. Add a shared text-delta consumer only for a production caller that is inventoried and demonstrably needs it, using the existing result owner and inherited policy.
8. On the exact candidate, verify one spoken request streams/appends into one result identity and stays singular through completion, cancellation, tab/display movement, reconnect, and reopen.

**Required checks:** direct Pipecat Supervisor correlation/redaction/cancellation cases above; multi-round one-terminal lifecycle; malformed/duplicate IDs; active and queued cancellation; non-cooperative provider/tool; late-write suppression; unknown mutation/reconciliation; event ordering and deduplication; protected-result policy; compatibility parity; caller inventory coverage; candidate voice-to-pane receipt.

**Pass:** each inventoried production caller has one lifecycle/result owner; unknown mutations cannot be auto-replayed; no post-terminal side effects occur; candidate journey is evidenced.

### 2. Complete privacy source-to-sink enforcement — GC24-03

1. Extend the model call-site inventory into a data-flow map: origin, provenance, policy resolution, transformations, and every continuation or output destination.
2. At each boundary, enforce the strictest inherited policy before sending or persisting: provider requests and continuations, tools/MCP, memory read/write/staging, supervisor context, TTS, provider session persistence, result/display, share/export/copy, telemetry, logs, and direct execution.
3. Keep protected full results local. Where the existing contract permits external coordination, expose only its fixed status and opaque reference. If no eligible route/sink exists, fail closed with a bounded reason.
4. Run unique synthetic-secret canaries through each path, including errors, retries, cancellation, logging, and direct-mode branches. Assert forbidden destinations receive no secret and no receipt/error/event exposes it.

**Pass:** source-to-sink matrix is complete and mechanically checked; each prohibited path has a negative canary; no unverified path is described as safe.

### 3. Prove model and route capabilities independently — GC24-04

For every configured model/workload/route, record exact model identity, runtime/version, auth source, supported text/image/stream/tool behavior, cancellation, privacy class, rate/size limits, failure modes, and usage/billing semantics. Verify each capability in an isolated, task-scoped process with clean working directory, allowlisted environment, no project instructions/hooks/plugins/MCP/provider tools, no persistent session, bounded process-group cleanup, and no late child output. Parse provider success/error envelopes; exit status alone is insufficient. Keep unknown billing unknown and unsupported combinations disabled. Tools stay disabled until the Mortimer permission-checked action bridge is proven end to end.

**Pass:** secret-free evidence separates model identity, route, individual capability, isolation, billing, and privacy. No subscription-free, confidential, or tool-capable claim is inferred from login, key presence, or probe alone.

### 4. Finish memory durability and staged acceptance — GC24-05

1. Preserve the existing SQLite schema/ownership, strict classifier, provenance, budgets, idempotency, deletion semantics, and authoritative memory plan.
2. Retain and extend deterministic fault/process-kill tests at enqueue, extract, classify, apply, cursor/pairing, forget, and lease-reclaim boundaries. Every state must resume safely exactly once or reach a safe terminal state; forget must not permit resurrection.
3. Keep production classification disabled until GC24-03 and GC24-04 establish an eligible confidential model/route. Then run the existing shadow evaluator and record denominators, classification quality, latency, cost, errors, backlog, and decisions against already approved thresholds.
4. If shadow thresholds pass, follow existing staged Mac rollout gates, observation period, and rollback runbook. No historical 28-exchange replay is in scope.

**Pass:** deterministic durability and concurrency tests pass; route/privacy evidence passes; shadow thresholds and staged rollout/rollback have dated receipts. Otherwise production stays fail-closed.

### 5. Complete Knowledge Atlas acceptance — GC24-06

1. The headless fixture limitation is now documented: the test process has no `NSScreen` and cannot activate a regular app. Keep the actual-window tests and graph frame benchmark active on an interactive display; skip only those cases when their explicit display precondition is absent. Keep observer, render, and placement tests that do not require a visible screen active. Re-run the complete host suite after source changes.
2. Validate expired authentication, refresh, reconnect, source mutation, partial failure, stale last-good data, retries, and recovery for each source on the candidate.
3. Verify keyboard-only and VoiceOver labels/focus/announcements; preserve all existing Atlas information and reading state.
4. Measure graph responsiveness/resource use on the approved fixture scale; changing tabs, display, size, or presentation must not duplicate fetches.

**Pass:** fixture issue is resolved/classified with evidence; source lifecycle, accessibility, no-duplicate-fetch, performance, and candidate receipts meet the existing Atlas contract.

### 6. Freeze and accept the release candidate — GC24-07–10

Only start after its source and route prerequisites pass.

1. Freeze source SHA, app bundle, backend revision, non-secret effective config, feature gates, and matching test evidence.
2. Run the current regression on that exact candidate, recording passes, failures, skips, warnings, and environment.
3. Complete only missing physical Mac journeys: compact startup; voice/mute/orb; single response identity; monitor connect/disconnect/reconnect/rehome; Atlas; text/image sharing; privacy; memory disabled/eligible staged route; sandboxed self-edit approval and rollback.
4. Obtain independent review, demonstrate rollback, complete the already-required observation period, and reconcile every status row to its receipt.

**Pass:** candidate identity matches evidence and each required hardware/provider/privacy/memory/Atlas/review/rollback/observation gate has an accepted dated receipt. Merge, deployment, and production enablement remain separate explicitly authorized steps.

## Model handoff protocol

Before each implementation slice, the model must:

1. Read this plan, the authoritative workstream contract, latest relevant receipt, and repository instructions.
2. Reconcile current branch/HEAD/dirty state and shared-file ownership; do not assume old test totals remain current.
3. Select one bounded slice with a specific pass condition. Avoid combining unrelated UI, model-route, memory, or lifecycle work.
4. Add or update meaningful tests at the owning boundary; run the focused tests and relevant lint/type/build checks. Run broader checks when scope or regressions justify it.
5. Write a dated receipt with exact commands and counts, changed files/behavior, failures/skips, limitations, source revision, and remaining parent gates. Update the feature status and this plan only when the evidence supports the wording.
6. Stop the affected slice if implementation conflicts with an accepted contract, privacy boundary, or another worker’s unreviewed edits. Record the mismatch and continue independent work.

Never include credentials, raw private prompts/results, complete environment dumps, or secret-bearing screenshots in source, plans, logs, receipts, or test output.

## Progress updates

**2026-09-25 — GC24-02 unknown tool outcome observability:** agent-event
migration 0028 now persists tool-call identity; SubAgent cancellation after
dispatch records a metadata-only unknown outcome; run detail, CLI, and MCP
surface calls without a correlated result. The migration/runlog/SubAgent/MCP/
end-to-end focused suite passes **124 tests**. The full Python unit/integration
suite passes **2,917 tests**, with **4 skipped**, **11 warnings**, and **2
subtests**; Ruff `F`/`I`, changed-document local-link checks, and
`git diff --check` pass. This is an operator signal, not action idempotency:
cross-request reconciliation across new provider IDs, other caller families,
and live-candidate proof remain open. See the [dated receipt](../acceptance/verified-gap-closure/GC24-02-unknown-tool-outcome-observability-2026-09-25.md).

**2026-09-25 — GC24-02 live Supervisor direct-tool run logging:** the
Pipecat adapter now writes one sensitive/redacted run per direct tool call,
correlates the provider call ID across tool-call/result events, scopes nested
MCP events to that run, and records an unknown outcome on cancellation or a
post-dispatch exception. Cancellation is re-raised and a late handler result
is not sent to Pipecat. Durable tests inspect SQLite and JSONL, including
secret canaries, nested MCP correlation, cancellation swallowed by a handler,
exceptions, and disabled logging. The focused runlog/SubAgent/MCP/Supervisor
suite passes **116 tests**; the pipeline-fixture regression passes **73**;
the full Python unit/integration suite passes **2,923**, with **4 skipped**,
**11 warnings**, and **2 subtests**. Ruff `F`/`I` and changed-source
`git diff --check` pass. See the [direct Supervisor runlog
receipt](../acceptance/verified-gap-closure/GC24-02-supervisor-direct-tool-runlog-2026-09-25.md).
This remains observability, not action idempotency or proof of side-effect
state. Cross-request reconciliation, other caller families, and live-candidate
voice-to-pane evidence remain open.

**2026-09-25 — GC24-06 headless fixture classification:** focused Atlas tests
pass **10/10**. The prior visible-window assertions could not run because the
XCTest process exposes zero screens and cannot activate as a regular app. The
three actual-window checks and the on-screen graph benchmark now skip only
under that explicit condition; the graph benchmark still asserts that no layer
is waiting after render-server completion when it runs on a display. Screen
unlock notification delivery is injectable for deterministic unit coverage;
production still observes the documented macOS distributed notification.
Focused visibility/placement/performance tests pass **14** with **5**
environment/display skips and no failures; the full MortimerHost suite passes
**265** with **7 skips** and no failures. External-display and live on-screen
acceptance remain open. See the [GC24-06 fixture
receipt](../acceptance/verified-gap-closure/GC24-06-headless-window-fixture-classification-2026-09-25.md).

**2026-09-25 — GC24-02 run-scoped plan-start claim:** migration 0029 adds a
tenant-scoped, content-free action claim. The existing injected SubAgent run
ID now allows plan_start retries with a new provider tool-call ID to return
the prior status instead of launching a second planning job. Focused DB,
admin, MCP, manifest, and tenant tests pass **126**; the full Python
unit/integration suite passes **2,930**, with **4 skipped**, **11 warnings**,
and **2 subtests**. This protects one tool within one SubAgent run only; fresh
SubAgent run IDs, direct Supervisor handlers, other mutation families, and
actual external side-effect reconciliation remain open. See the [dated
receipt](../acceptance/verified-gap-closure/GC24-02-plan-start-run-scoped-claim-2026-09-25.md).

**2026-09-25 — GC24-02 run-scoped app-build-start claim:** the MCP registry
injects the SubAgent run ID into app_build_start and hides it from the
model-visible tool schema. The sidecar uses the tenant-scoped action-claim
table, blocks duplicate starts, and supports action-specific status lookup.
Focused app-build/MCP/registry validation passes **78**; Ruff `F`/`I` and
`git diff --check` pass. Fresh-run/direct-Supervisor replay, complete caller
lifecycle, and side-effect reconciliation remain open. See the [app-build
receipt](../acceptance/verified-gap-closure/GC24-02-appbuild-run-scoped-claim-2026-09-25.md).

**2026-09-25 — GC24-03 external MCP fail-closed context:** `SkillRegistry`
now uses the authoritative sensitivity predicate; missing context blocks
external MCP dispatch before the child receives arguments. Negative canaries
cover missing, armed, and explicitly unarmed contexts. Focused
registry/SubAgent/Supervisor tests pass **92**; the full Python suite passes
**2,940**, with **4 skipped**, **11 warnings**, and **2 subtests**. This does
not close the other privacy sources and sinks. See the [receipt](../acceptance/verified-gap-closure/GC24-03-external-mcp-missing-context-fail-closed-2026-09-25.md).

**2026-09-25 — GC24-03 sensitive tool output mid-task:** SubAgents now stop
before a non-confidential provider continuation after the existing financial
detector recognizes sensitive tool output; run logging and activity events
switch to protected forms. The live Supervisor stops before another voice
provider round and removes the raw tool round from in-memory history. Focused
SubAgent/Supervisor/run-log tests pass **127**; the full suite passes **2,943**,
with **4 skipped**, **11 warnings**, and **2 subtests**. This does not claim
general private-data detection or close the voice exception. See the [receipt](../acceptance/verified-gap-closure/GC24-03-sensitive-tool-result-midtask-stop-2026-09-25.md).

## Immediate next action

Staged self-edit confirmation now has an atomic cross-run claim keyed by its
server-issued staging ID and a durable status lookup; see the [dated
receipt](../acceptance/verified-gap-closure/GC24-02-selfedit-staged-action-cross-run-claim-2026-09-25.md).
Next, reconcile the remaining mutating caller families against existing
stable action identities and continue caller lifecycle and source-to-sink
coverage in independent bounded slices. Do not use argument hashes as action
equivalence. Do not start a live route, production memory enablement, merge,
deployment, or release claim until its explicit evidence gates pass.
