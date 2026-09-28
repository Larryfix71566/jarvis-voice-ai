# Mortimer — Fresh Review Implementation Plan

> **Archived 2026-09-28 — superseded as an execution index.** The canonical plan is [MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md](../plans/MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md). This archive preserves the original requirements and evidence for history; it does not mark any gate complete.


**Prepared:** 2026-09-25  
**Purpose:** give any implementation model a precise, dependency-ordered path
through the gaps still open in the latest source review, without reopening
accepted product, interface, privacy, or architecture decisions.  
**Target:** isolated worktree `codex/isolated-20260924`, based on
`977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; the tree is already dirty and has
concurrent changes.  
**State:** implementation in progress in the isolated worktree. The progress
entry below records one bounded source slice; the remaining gaps are open. It
does not authorize merge, push, deployment, production memory enablement, or a
release claim.

This is the current review handoff, not a replacement for acceptance
thresholds. The [Verified Gap Closure plan](../plans/MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md)
and existing GC24 feature plans remain authoritative for detailed contracts;
the [Remaining Gaps Execution Plan](../plans/MORTIMER_REMAINING_GAPS_EXECUTION_PLAN_2026-09-25.md),
[Implementation Status](../acceptance/IMPLEMENTATION_STATUS.md), and dated
receipts provide current evidence. If this plan and an authoritative contract
differ, stop that slice, record the mismatch, and preserve the stricter
requirement. Do not make a new architecture decision to resolve ambiguity.

## Intended result

Close the remaining execution-lifecycle, privacy, model-access, automatic
memory, Knowledge Atlas, and candidate-acceptance gaps. Keep implementation,
merge, candidate verification, live acceptance, and release as distinct
states. This document does not assert that the dirty worktree, installed Mac
app, or production runtime is in sync.

## Product and architecture decisions that are fixed

- Retain Command Console layout 2, compact Conversation at startup, all eight
  scrollable sidecar tabs, the selected speaker-aware atom/comet orb, current
  voice transport/STT/TTS, and Haiku's supervisor role.
- Full answers and research remain in the existing response/results area;
  Conversation carries brief live captions. One user request owns one result
  identity. Updates append to it. Reconnects, display moves, tab switches, and
  panel reopening must not repeat work or create another result window.
- Keep the existing app-owned request/result, display-placement, permission,
  action-registry, tool-execution, and sandbox/self-edit owners. Do not add a
  parallel queue, orchestrator, event bus, result store, tool executor, or
  memory database.
- Keep model identity, access route, workload, privacy policy, capability,
  authentication, and billing evidence separate. No silent fallback,
  arbitrary retry, privacy downgrade, or unknown-usage-as-zero behavior.
- Provider tools remain disabled until the pinned runtime is isolated and the
  task-scoped Mortimer bridge, permissions, action registry, sandbox, and
  cancellation boundaries pass together. Credentials, catalog entries, and
  successful public probes do not establish confidential processing.
- SQLite remains the sole memory system of record. Classification and routine
  maintenance remain strict, automatic, quiet, bounded, provenance-aware,
  reversible, and fail-closed. Do not prompt for routine labels, replay the
  historical 28 exchanges, or bulk-relabel existing memories.
- Preserve the existing self-edit sandbox and spoken-preview behavior; PR
  approval remains the external change boundary.
- Make changes only in the designated isolated worktree. Reconcile dirty-file
  ownership before editing and preserve every concurrent change.

## Verified gap register

| Workstream | Already evidenced in this tree | Still open |
|---|---|---|
| GC24-00/01 baseline and ownership | Isolated branch and dated source/test receipts exist. | Reconcile branch/base/HEAD, dirty and untracked paths, sibling worktrees, concurrent owners, toolchain, and exact runtime identity before each increment. |
| GC24-02 execution lifecycle | Existing RTVI transcript-to-`ResponseResultRouter`; selected cancellation suppression and terminal ownership; same-run/provider-call ID guards; run-scoped durable claims for `plan_start` and `app_build_start`; staged self-edit and publication cross-run claims; native Edit tab sends a per-action `run_id` and retains the immutable action/backend across transport retries; bare self-edit, app-build, and plan starts without IDs now fail closed before dispatch; unknown-outcome observability. | Inventory/reconcile remaining mutating caller families and publication/update outcomes; single terminal/result/artifact ownership across full provider/tool loops; downstream cancellation and late-write suppression; generic shared-execution streaming only where an inventoried production caller needs it; exact candidate voice-to-pane evidence. |
| GC24-03 privacy | Policy floors; protected local-result handoff; fail-closed external MCP when sensitivity is absent/armed; scoped log-redaction receipts across MCP, watcher, clipboard, agent/event, admin/status, memory, voice, workflow, KB digest, council/upgrade, screen, and procedures/skills/usage. | Complete source-to-sink map and negative canaries for every continuation and sink: providers, tools, memory, supervisor/TTS, persistence, display, copy/share/export, logs/telemetry, and direct paths. The residual diagnostic plan indexes F1–F25, including transcript-persistence errors and content, reminder, client-message, route-refusal, and branch-label fields; revalidate implementation and receipts against the current tree. Follow the detailed [remaining exception-log redaction plan](../plans/MORTIMER_GC24-03_REMAINING_EXCEPTION_LOG_REDACTION_PLAN_2026-09-25.md). Existing detectors do not prove general private-data detection. |
| GC24-04 model access | Claude/Codex subscription and SAYGM foundations/configuration; 26/26 static call-site inventory. | Per-model/route capability, isolation, cancellation, privacy eligibility, usage/billing semantics, and complete Mortimer tool-bridge proof. Unsupported combinations stay unavailable. |
| GC24-05 automatic memory | Strict shared classifier; staged SQLite admission; evidence checks; budgets; forget invalidation; claim fencing; process-race and crash/retry receipts. | Eligible confidential route evidence, shadow quality/benefit/cost observation, then staged Mac rollout and rollback evidence. Production remains disabled/fail-closed until prerequisites pass. |
| GC24-06 Knowledge Atlas | Per-source refresh lifecycle, last-good state, retry/reconnect, generation guards, run-history refresh; headless-window fixture classification; Atlas cards now expose their summary and source in the accessibility value. | Live auth-expiry/recovery and source-change journeys; mounted keyboard/VoiceOver traversal; no duplicate fetch on presentation change; on-screen graph performance; real unlock delivery; physical display journeys; current-candidate acceptance. |
| GC24-07–10 candidate and release | Historical interface, monitor, and release receipts. | Freeze exact source/app/backend/config; test that artifact; physical Mac journeys; provider/memory pilots; independent review; rollback drill; observation window; status-to-receipt reconciliation. |

The current full-suite counts in older receipts are snapshot-specific. Re-run
checks for the exact source being changed; never copy an old count into a new
receipt. Hardware/provider omissions are open gates, not passes or failures
inferred from unit tests.

**2026-09-25 progress — staged self-edit cross-run claim:** staged self-edit
confirms now claim their issued staging ID in the existing SQLite action
ledger before planner or authoring work starts. Duplicate requests stay
`started: false`; action status can be recovered after the live job slot moves.
Focused admin/self-edit/MCP/app-build/plan/run-log tests passed **212**;
focused self-edit/MCP/end-to-end tests passed **144**, including the three
self-edit end-to-end journeys. The full Python unit/integration suite passed
**2,950**, with **4 skipped**, **11 warnings**, and **2 subtests**.
This closes only staged self-edit confirms; bare legacy starts and other
mutating caller families remain open. See the [dated receipt](../acceptance/verified-gap-closure/GC24-02-selfedit-staged-action-cross-run-claim-2026-09-25.md).

**2026-09-25 progress — startup maintenance log redaction:** six startup
best-effort catches now log only the event and exception class, preserving
their non-blocking behavior. The pipeline-wiring suite passed **39** and the
full Python unit/integration suite passed **2,956**, with **4 skipped**, **11
warnings**, and **2 subtests**. This closes only those six log sinks. See the
[dated receipt](../acceptance/verified-gap-closure/GC24-03-startup-maintenance-log-redaction-2026-09-25.md).

**2026-09-25 newly identified GC24-02 slice — self-edit publication replay:**
staged self-edit starts are protected across runs, but final PR preparation
still needs its own durable action claim. The existing persisted sandbox
`session_id` is the candidate stable identity shared by background finish and
native submit. Verify that it is unique and survives the existing recovery
path before using it. Claim only after validation succeeds and before
submission dispatch; validation failures must remain repairable. A possibly
dispatched submission whose outcome cannot be proved must become
`unknown`/reconciliation-needed and must never be automatically retried.
Provide bounded status lookup after the in-memory job slot moves, and cover
duplicates, restart, claim-store failure, cancellation, and post-dispatch
exceptions. Preserve the existing PR review/merge boundary. Do not persist
goals, diffs, provider output, or secrets in the claim receipt. The bounded
implementation and isolated tests are complete for background finish and
native submit; see the [dated receipt](../acceptance/verified-gap-closure/GC24-02-selfedit-publication-cross-run-claim-2026-09-25.md).
This does not establish live GitHub publication or close other mutation
families.

**2026-09-25 progress — bare legacy self-edit start:** the registry injects
the owning SubAgent `run_id` into `selfedit_start`, strips it from the
model-visible schema, and existing `plan_start`/`app_build_start` callers
already use the same run-scoped identity contract. The deprecated bare
`/api/selfedit/run` path now uses that identity in a distinct
`mcp-selfedit.run_start` claim scope, separate from staged-preview claims;
duplicate starts do not dispatch, and status can recover from the receipt
after the live job slot moves. A later reconciliation slice now refuses
direct bare requests without a stable `run_id` before any job dispatch.
Focused admin, end-to-end, MCP self-edit, and run-ID injection tests passed
**157** for the original injected-identity behavior. See the
[dated receipt](../acceptance/verified-gap-closure/GC24-02-selfedit-run-scoped-bare-start-claim-2026-09-25.md).

**2026-09-25 progress — Knowledge Atlas accessibility content:** Atlas cards
now announce their summary and source alongside the type/title label, with a
hint distinguishing result navigation from informational cards. The change
does not alter the visual card, workspace selection, or result identity.
`KnowledgeAtlasTests` passed **12/12**; the full MortimerHost target passed
**267**, with **7 hardware/display-gated skips**. A mounted `NSHostingView`
test verifies the rendered accessibility label and value, but this is not a
live VoiceOver or keyboard acceptance; its standard AX press also invokes
the existing result-selection callback. See the
[dated receipt](../acceptance/verified-gap-closure/GC24-06-atlas-card-accessibility-content-2026-09-25.md).

**2026-09-25 progress — workflow and KB digest log redaction:** malformed
workflow YAML can echo source text in parser tracebacks; session-digest
failures can echo provider or knowledge-base error content. These paths now
log bounded failure names/types without tracebacks, source lines, or backend
messages. Canary-focused suites passed **31** and the full Python
unit/integration suite passed **2,967**, with **4 skipped**, **11 warnings**,
and **2 subtests**. Ruff `F`/`I` and `git diff --check` passed. This closes
only these two classes of log sinks. See the
[dated receipt](../acceptance/verified-gap-closure/GC24-03-workflow-and-kb-digest-log-redaction-2026-09-25.md).

**2026-09-25 progress — voice-pipeline teardown log redaction:** five
shutdown exception paths now log only event, exception class, and session ID;
the six startup best-effort catches share the same helper. This prevents
tracebacks from exposing provider/backend or derived content while preserving
the existing best-effort shutdown behavior. `test_bot_wiring.py` passed **44**;
the full Python unit/integration suite passed **2,972**, with **4 skipped**,
**11 warnings**, and **2 subtests**. Ruff `F`/`I`, compileall, and
`git diff --check` passed. See the [dated receipt](../acceptance/verified-gap-closure/GC24-03-voice-pipeline-teardown-log-redaction-2026-09-25.md).

**2026-09-25 newly indexed GC24-03 residual log sinks:** a follow-up source
scan found additional traceback or path-bearing exception logs across memory
extraction, speaker/audio gates, council/upgrade orchestration, screen
pruning, procedures/skills, and usage/shared-content accounting. No code
change or closure is claimed by this inventory. Implement one bounded area at
a time under the [remaining exception-log redaction plan](../plans/MORTIMER_GC24-03_REMAINING_EXCEPTION_LOG_REDACTION_PLAN_2026-09-25.md),
after reconciling current code, existing receipts, and dirty-file ownership.

**2026-09-25 progress — memory extraction/worker log redaction:** the current
source still contained traceback output and memory/session/cursor identifiers
despite an older scoped receipt. Those current paths now retain only bounded
events, aggregate counts, admission categories, and bounded exception class
names. The focused extraction/worker suites passed **64**; Ruff `F`/`I`,
compileall, and `git diff --check` passed. See the [slice A receipt](../acceptance/verified-gap-closure/GC24-03-memory-extraction-worker-log-redaction-2026-09-25.md).
This does not close memory data flow or any remaining GC24-03 sinks.

**2026-09-25 progress — speaker and audio-gate log redaction:** profile,
metadata, model, WAV, capture, scoring, and delivery diagnostics now omit
paths, raw exception text/tracebacks, transcript content, and turn IDs while
keeping bounded event/error classes and existing score/window/duration
metrics. Focused speaker suites passed **69** with **2 dependency deprecation
warnings**; Ruff `F`/`I`, compileall, and `git diff --check` passed. See the
[slice B receipt](../acceptance/verified-gap-closure/GC24-03-speaker-audio-log-redaction-2026-09-25.md).
This does not close audio data flow or remaining GC24-03 sinks.

**2026-09-25 progress — slice E, procedures/skills/usage/shared content:**
procedure, skill parsing, TTS/LLM usage, and shared-content diagnostics now
omit raw content, paths, identifiers, exception text, and tracebacks while
preserving best-effort behavior. Focused suites passed **131** with **1
dependency deprecation warning**; Ruff `F`/`I`, compileall, and
`git diff --check` passed. See the [slice E receipt](../acceptance/verified-gap-closure/GC24-03-procedures-skills-usage-log-redaction-2026-09-25.md).

**2026-09-25 plan refresh — residual slice F:** the expanded source scan
indexed twenty-five candidate sinks with source/test owners, canaries, and
unchanged-behavior requirements. F1–F25 are tracked in the dedicated
[slice plan](../plans/MORTIMER_GC24-03_REMAINING_EXCEPTION_LOG_REDACTION_PLAN_2026-09-25.md)
as the bounded diagnostic execution handoff. Reconcile every row against
current source, tests, and dated receipts before closing it. The full privacy
source-to-sink audit remains open regardless of log-slice completion.

**2026-09-25 progress — native Edit-tab self-edit action identity:** the
native Edit tab now sends a UUID action ID on its bare-goal start, which the
existing sidecar SQLite claim ledger persists under the self-edit start
scope. If the HTTP request fails before a response, the view model retains
the original goal, planner, ID, and AdminAPI endpoint; Retry / Check Run
resubmits that same action rather than creating a second job. The claim
receipt still remains authoritative for status after the in-memory job slot
moves. The sidecar refuses deprecated bare requests without a stable
`run_id` and rejects IDs over 256 characters before dispatch; staged starts
remain keyed by their issued staging ID. Focused admin/self-edit/app-build/
MCP/end-to-end/registry tests passed **176**, with **1 warning**; the full
Python unit/integration suite passed **3,026**, with **4 skipped**, **11
warnings**, and **2 subtests**. Swift source parsing passed. The focused Swift
package test was attempted but stopped while fetching the pinned WebRTC
binary artifact after producing no download progress; compiled Swift and
live app behavior remain unverified. See the [native caller
receipt](../acceptance/verified-gap-closure/GC24-02-native-edit-tab-action-id-2026-09-25.md).

**2026-09-25 progress — app-build start identity fail-closed:** the current
`app_build_start` MCP helper now refuses to call the sidecar without the
registry-injected execution ID. The sidecar independently refuses missing,
blank, or overlong IDs before dispatch, retaining the existing one-shot
SQLite claim/status path. Focused app-build/self-edit/MCP/registry tests
passed **218**; the full Python unit/integration suite passed **3,030**, with
**4 skipped**, **11 warnings**, and **2 subtests**. Ruff `F`/`I`, compileall,
and `git diff --check` passed. See the [app-build identity
receipt](../acceptance/verified-gap-closure/GC24-02-appbuild-start-requires-action-id-2026-09-25.md).
Other mutation families and full provider/tool terminal ownership remain
open.

**2026-09-25 progress — plan-start identity fail-closed:** the registered
`plan_start` caller already receives its owning SubAgent ID. The MCP helper
now refuses confirmed starts without it, and `/api/plan/start` independently
refuses missing or overlong IDs before document reads, claims, or worker
dispatch. Valid calls always use the existing SQLite claim and status path.
Focused planning/MCP/registry tests passed **109**; Ruff `F`/`I`, compileall,
and `git diff --check` passed. The full-suite rerun exposed that the separate
plan-review test fixture still modeled a direct sidecar call; it now supplies
the injected ID used by the registered action. The focused planning-review/
MCP/registry suite passed **117**, and the full Python unit/integration suite
passed **3,033**, with **4 skipped**, **11 warnings**, and **2 subtests**. See the [plan
start identity receipt](../acceptance/verified-gap-closure/GC24-02-plan-start-requires-action-id-2026-09-25.md).

**2026-09-25 progress — website-research start identity:** the confirmed
`research_compare_start` MCP action now receives the injected SubAgent ID;
preview remains ID-free. MCP and sidecar both refuse confirmed dispatch
without a valid ID. The sidecar uses the existing SQLite action claim to
prevent duplicate paid crawls, and `research_status` looks up the matching
action instead of silently reporting a later job. Focused research/MCP/
registry tests passed **71**, with **1 skipped**; the full Python
unit/integration suite passed **3,039**, with **4 skipped**, **11 warnings**,
and **2 subtests**. Ruff `F`/`I`, compileall, and `git diff --check` passed.
See the [research identity receipt](../acceptance/verified-gap-closure/GC24-02-research-start-action-id-2026-09-25.md).

**2026-09-25 progress — transcript stdout sink:** F25 now omits user and
assistant transcript content from the persistent bot log while retaining
role/timing markers, ordinary memory rows, sensitive-turn suppression, and
UI behavior. Focused suites passed **75**; the full Python unit/integration
suite on the accumulated snapshot passed **3,025**, with **4 skipped**, **11
warnings**, and **2 subtests**. Ruff `F`/`I`, compileall, and
`git diff --check` passed. See the [F25 receipt](../acceptance/verified-gap-closure/GC24-03-transcript-content-log-redaction-2026-09-25.md).
This closes one persistent log sink only; GC24-03 content flow through
providers, memory, tools, display, export, and telemetry remains open.

**2026-09-25 progress — council and upgrade log redaction:** exception
tracebacks/messages were removed from council and upgrade-agent best-effort
failure paths; proposer/judge exception strings, user-choice labels, and
unknown outcome values are no longer logged. Focused council/upgrade unit and
integration suites passed **88**; Ruff `F`/`I`, compileall, and
`git diff --check` passed. See the [slice C receipt](../acceptance/verified-gap-closure/GC24-03-council-upgrade-log-redaction-2026-09-25.md).
This does not close council content data flow or remaining GC24-03 sinks.

**2026-09-25 progress — screen and pruning log redaction:** screen logs no
longer include questions, model answers, paths, display identifiers, raw
retention settings, exception text, or tracebacks; capture, retention, and
pruning behavior remain unchanged. Focused screen tests passed **28**; Ruff
`F`/`I`, compileall, and `git diff --check` passed. See the [slice D
receipt](../acceptance/verified-gap-closure/GC24-03-screen-log-redaction-2026-09-25.md).
Low-confidence image retention and broader screen data flow remain open.

## Dependency order

```text
0. Reconcile baseline and file ownership
                 ↓
1. GC24-02 mutation identity / lifecycle ─┐
2. GC24-03 complete privacy boundaries ──┼─→ 3. GC24-04 route/capability proof
4. GC24-06 Atlas live behavior ──────────┘                  ↓
                                              5. GC24-05 memory shadow/rollout
                                                           ↓
                                  6. GC24-07–10 frozen candidate and release gates
```

GC24-06 source/test work may proceed independently after ownership is
reconciled. Deterministic GC24-05 tests may proceed while route evidence is
pending, but production memory may not. Provider-dependent tests and memory
rollout depend on privacy and route evidence. Candidate acceptance depends on
all applicable source, configuration, privacy, and feature gates.

## Implementation sequence

### 0. Reconcile source, evidence, and ownership — GC24-00/01

Before each code slice, record current branch, base/HEAD, dirty/untracked
paths, sibling worktrees, concurrent file owners, relevant receipts, and
toolchain. Map each acceptance item to its source owner, test, receipt, and
missing proof. Identify app/backend/config/runtime only through non-secret
evidence when available; otherwise label it **unverified**. Do not reset,
clean, transplant, or overwrite work to make the tree appear tidy.

**Pass:** a dated baseline names one bounded slice, owner, files, contract,
test command, receipt path, and unresolved evidence without losing changes.

### 1. Reconcile mutating actions across fresh runs — GC24-02

Prior same-SubAgent-run claims and provider-call-ID replay guards do not stop
the same confirmed user action from being issued in a new run. Extend the
existing SQLite execution-action ownership only for a mutating caller that
already has a stable, issued action identity (for example, an existing staged
self-edit approval ID). Do not treat goal text, a provider call ID, matching
arguments, or a generic argument hash as proof that two actions are the same.

1. Inventory each mutation family and identify its existing stable approval,
   staging, or action ID. If none exists, document the gap and required
   product/contract decision; do not invent an identity scheme in this slice.
2. Claim the action atomically before dispatch, scoped to the correct tenant
   and action type. Persist only a content-free receipt with claim state,
   timestamps, and safe reconciliation metadata; do not store raw arguments
   or result text in the receipt.
3. Make duplicate requests return “not started” plus the existing bounded
   status. Preserve live status when the action is active; if the receipt says
   dispatch may have happened but outcome is unknown, block automatic retry
   and expose a reconciliation-needed state.
4. Cover terminal completion, failure-before-dispatch, cancellation,
   exception-after-dispatch, database unavailable, stale job slots, restart,
   and two concurrent requests. Be explicit that a local claim cannot undo an
   external mutation already committed by a tool.
5. Migrate one inventoried caller family at a time. Preserve its existing
   preview, permission, sandbox, approval, and result behavior.

**Required proof:** fresh-run duplicate suppression under the same stable
action ID; distinct action IDs remain independent; claim-store failure blocks
dispatch; unknown outcome cannot auto-replay; restart/status lookup remains
truthful; no sensitive content enters receipts; caller behavior and existing
same-run protection remain intact.

**Pass:** each claimed caller has a stable identity, exactly one dispatch
owner, and a safe unknown-outcome path. Claims cover only the callers named by
their receipts; do not report all mutation families closed by one integration.

### 2. Finish lifecycle, cancellation, and result ownership — GC24-02

Trace inventoried callers through admission, all provider/tool rounds,
artifacts, UI delivery, logging, and durable writes. Keep the current voice
RTVI-to-transcript-to-result path; do not add a second voice consumer. Add a
generic shared-execution delta consumer only when an inventoried production
caller needs one, and route it through the existing result identity and
inherited policy. Assign one owner for ordered events and one terminal state
for the full provider/tool loop. Carry cancellation/deadline through provider
and tool execution; suppress every late text, tool dispatch, artifact, UI,
memory, and DB effect after terminal cancellation. Preserve the known limit
that cancellation cannot reverse an already committed external mutation.

**Pass:** caller inventory is current; tests prove one terminal, request/result
identity, compatibility behavior, queued/active cancellation, non-cooperative
late completion suppression, event ordering, and a live candidate voice-to-one
result journey.

### 3. Complete privacy source-to-sink enforcement — GC24-03

Extend the inventory from model call sites to content sources, transformations,
continuations, persistence, and display/share sinks. Resolve policy from
provenance and the strictest existing workload/data rule before each provider
round, tool/MCP call, memory read/write/stage, supervisor handoff, TTS,
provider-session persistence, result/display, attachment transfer,
copy/share/export, log, telemetry, and direct-mode path. Keep protected full
results local; use only the already-approved bounded status and opaque
reference for permitted external coordination. Use distinct synthetic
canaries and prove forbidden sinks receive neither content nor a derivative.

**Pass:** every inventoried prohibited path has an executable negative test;
missing route/sink eligibility fails closed; no preference, retry, error, or
continuation lowers policy. Do not claim general sensitive-data recognition
from the existing financial detector.

### 4. Prove model, route, privacy, and billing separately — GC24-04

For each configured model/workload/route, verify the exact pinned runtime and
document authentication, prompt/input types, streaming, structured output,
tools, limits, cancellation, error envelope, privacy class, and usage/billing
semantics. Run only synthetic public data until confidential-route capability
is independently verified. Isolate subscription CLIs in a clean,
task-scoped process with allowlisted environment, no project hooks/plugins/MCP
or native provider tools, bounded I/O, process-group cancellation, and cleanup.
Parse provider envelopes; exit code alone is not success. Keep route selection
separate from billing evidence. Do not save passwords or OAuth material in
the repository or project vault.

**Pass:** secret-free, route-specific evidence proves each capability on its
own. Any unsupported or unverified combination remains unavailable; no
subscription/API fallback is introduced. Tools remain disabled until the
Mortimer bridge and permission/sandbox path pass end to end.

### 5. Complete automatic-memory route and staged acceptance — GC24-05

Preserve the strict classifier, SQLite system of record, evidence/provenance,
budgets, idempotency, forget/delete, claim fencing, rollback, and quiet
maintenance. Keep shadow non-mutating with respect to live admission,
retrieval, prompts, and cursors. Do not reopen schema/classifier design absent
contradictory evidence from its authoritative plan. Keep production disabled
until GC24-03 and GC24-04 establish an eligible confidential route. Then run
the existing synthetic shadow evaluator and approved thresholds; only after
passing may a staged Mac rollout begin with backup, observation, and proven
rollback. Do not replay the historical 28 exchanges.

**Pass:** route/privacy receipts, quality and budget thresholds, redacted
benefit/cost/error/backlog observation, restorable backup, staged rollout, and
rollback evidence. Otherwise remain disabled and fail-closed.

### 6. Finish Atlas live behavior and accessibility — GC24-06

Keep the existing per-source store-owned refresh lifecycle, last-good state,
retry, reconnect, and generation guards. Do not add a duplicate client,
poller, websocket, or fetch on presentation movement. Classify the recorded
headless visibility skips without weakening tests. On the exact candidate,
verify auth expiry/recovery, source changes, partial failure, retry/reconnect,
stale labels, and selection/group/pin preservation. Verify keyboard and
VoiceOver names/focus/refresh, reduced-motion/transparency, loading/empty/error
states, graph frame/resource performance at approved fixture scale, unlock
delivery, and physical display placement.

**Pass:** all required data, accessibility, performance, no-duplicate-fetch,
unlock, and physical-display journeys have receipts on the same candidate.

### 7. Freeze and accept one candidate — GC24-07–10

After applicable source, privacy, and route gates pass, freeze the exact source
SHA/dirty state, app artifact, backend identity, non-secret effective
configuration, gates, and matched test evidence. On that artifact run
regressions, audits, packaging/signature and performance checks. Complete the
applicable physical Mac journeys: compact startup; user/Mortimer voice and
mute/orb; one result identity; research/text/image sharing; tabs and picker;
keyboard/VoiceOver; Atlas; bounded supporting display; attach/detach/reconnect
without duplicate work; protected-data handling; staged memory; and sandboxed
self-edit preview, PR approval, and rollback. Run model/memory pilots only
under their verified route and privacy gates. Obtain independent review,
demonstrate feature disablement and rollback, complete the approved observation
window, and reconcile every status row to evidence. A changed source/config
restarts the affected candidate proof.

**Pass:** the exact frozen artifact has all applicable regression, physical,
provider/memory pilot, independent review, rollback, and observation receipts.
Unavailable hardware/provider evidence stays open with a named owner and next
action. Do not substitute macOS Spaces for physical multi-display acceptance.

## Model handoff contract

At every handoff, the next model must read this plan, repository instructions,
the authoritative slice contract, latest receipt, and exact source/tests;
reconcile `git status`, branch/base/HEAD, sibling worktrees and file ownership;
choose one bounded invariant; add boundary tests; run focused tests and
applicable lint/build/audit; add a dated receipt with exact commands and
counts; update the existing status row; and review for secrets, raw user
content, weakened defaults, hidden fallback, duplicate architecture, and
unrelated UI changes. Keep work uncommitted and unpushed unless separately
authorized. Never label a skipped, hardware-gated, or provider-gated check a
pass.

## First implementation action

Staged and run-scoped self-edit starts, app-build starts, planning starts,
website-research starts, startup-maintenance log redaction, and self-edit PR
publication replay have dated receipts. The app-build PR submission now also
uses the persisted sandbox session ID for a separate replay claim. A focused
mutation audit found that `app_create` has no stable ID linking its preview to
the confirmed repository creation, and directly exposed `app_register` has no
durable action claim. Resolve the issued approval-ID contract and whether
`app_register` remains directly callable before changing either path; see the
[mutation identity audit receipt](../acceptance/verified-gap-closure/GC24-02-mutating-caller-identity-audit-2026-09-25.md).
Do not promote a provider tool-call ID or argument hash into a new identity
contract. Continue auditing other caller families against stable action
identities and claim receipts, then proceed with lifecycle and source-to-sink
work in bounded slices. Do not start a live provider route, production memory
enablement, merge, deployment, or release claim before its explicit gates.

**2026-09-25 progress — app-build submission:** the admin endpoint now claims
the persisted sandbox session identity before PR dispatch, requires a
validated nonempty proposal set, returns a saved PR URL after a duplicate,
and blocks an ambiguous prior attempt. Focused admin/MCP/integration tests
passed **76**; the updated full Python unit/integration suite passed **3,053**
with **4 skipped**, **11 warnings**, and **2 subtests**. The MCP exposes a
submission-specific status lookup and the authoring endpoint's
timing-sensitive test now waits for the documented asynchronous startup state.
See the [GC24-02 app-build submission receipt](../acceptance/verified-gap-closure/GC24-02-appbuild-submit-session-claim-2026-09-25.md)
and [current implementation plan](../plans/MORTIMER_CURRENT_REVIEW_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md).
