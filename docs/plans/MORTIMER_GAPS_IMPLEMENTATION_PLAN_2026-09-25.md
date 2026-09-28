# Mortimer — Current Verified Gaps Implementation Plan

**Prepared:** 2026-09-25  
**Purpose:** give any capable model a bounded, ordered implementation plan for
the gaps verified in the current isolated source tree, without reopening
accepted product, interface, security, or architecture decisions.  
**Worktree:** `codex/isolated-20260924`, based on `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; the tree was dirty when this plan was prepared.  
**Scope:** complete the remaining implementation and acceptance work. This is
not a release claim and does not authorize deployment, merge, push, or access
to the Mac vault.

This plan supplements the [Verified Gap Closure plan](MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md)
and the [Newly Verified Gaps plan](MORTIMER_NEWLY_VERIFIED_GAPS_IMPLEMENTATION_PLAN.md).
The feature plans linked there remain authoritative for detailed schemas,
budgets, design, and acceptance thresholds. If a difference is found, stop
that slice, record the exact discrepancy, and preserve the stricter existing
requirement; do not invent a new architecture to resolve it.

## Outcome

Close the source and evidence gaps below while preserving the current Mortimer
product: Command Console/layout 2, compact Conversation at startup, the eight
sidecar tabs, the approved atom/comet orb, current voice transport and
supervisor role, one request/one result identity, the existing SQLite memory
system, the established self-edit sandbox, and the existing app-owned
presentation/action owners.

Implementation is staged. A passing unit test does not turn on a feature, a
merge does not prove the Mac candidate, and a user-reported check without a
dated receipt does not close a gate.

## Decisions fixed for every implementer

- Keep the selected interface and behavior. Full Mortimer answers and research
  results belong in the existing response/results area; Conversation retains
  brief live captions. Append updates for one request to its one result
  identity. A monitor move, tab change, reconnect, or reopen must not start a
  second request or create another result window.
- Keep the existing user/Mortimer speaker colors, connected idle animation
  while muted, audio-reactive orb behavior, bounded shared supporting stage,
  shared action registry, and eight scrollable sidecar tabs. Do not replace or
  regress these while closing backend or release gaps.
- Keep Haiku in its existing supervisor role. Do not migrate the live voice
  loop, STT, TTS, or audio transport in this scope.
- Keep model identity, workload, route, privacy, capability, and billing
  source distinct. No silent model/route fallback, privacy downgrade,
  arbitrary retry, or conversion of unknown usage to zero.
- A subscription adapter remains unavailable for tools until its runtime
  isolation and the task-scoped Mortimer bridge are proven. Mortimer's
  registered permission/action path and existing sandbox remain the only tool
  execution path. Unsupported provider behavior stays explicitly unavailable.
- Preserve SQLite as the memory system of record. Routine classification and
  maintenance stay quiet and automatic. Do not ask the user to classify
  ordinary memories, replay the 28 historical exchanges, bulk-relabel memory,
  create another memory database, or use heuristics as a hidden successful
  model fallback.
- Keep protected data local unless the selected model **and** route have
  verified capability. A key, model listing, public probe, or login alone is
  not proof of confidential processing.
- Continue only in the designated isolated worktree. Reconcile changes from
  other workers before editing shared files. Do not reset, overwrite, or
  transplant another worker's changes without understanding and preserving
  them.

## Verified starting point

The current source tree is ahead of the original main snapshot. The following
are source/worktree findings, not merged, deployed, or live-Mac claims:

| Area | Verified in this tree | Still open |
| --- | --- | --- |
| Model call-site inventory | The current isolated audit reports 26/26 covered, zero review-required, and secret-free. Planner, mixed voice/vision, and route-aware memory classification entries are included. The live supervisor remains the named voice exception. | The audit proves inventory ownership, not lifecycle correctness or complete policy coverage. |
| Shared execution | Context, attachment, routing, cancellation, usage, tool schema validation, and opt-in Anthropic streaming infrastructure exist in the dirty tree. The live voice path aggregates RTVI `bot-llm-text` in `JarvisClient.transcript`; `AppMessageRouter` passes it to the existing `ResponseResultRouter`, which updates one result identity. Client-frame tests pass 2/2, the full stub-transport-to-response-result integration test passes 1/1, and result-router tests pass 7/7. See the [voice response-stream receipt](../acceptance/verified-gap-closure/GC24-02-existing-voice-response-stream-path-2026-09-25.md). SubAgent cancellation finalizes its run-log record; `delegate_task` UI events have an idempotent terminal owner; returned values after absorbed cancellation are suppressed; direct-mode SubAgent/self-edit planner loops reject reused provider tool-call IDs across rounds; the live Supervisor validates whole tool batches before dispatch and now suppresses late provider responses after cancellation. | The exact live candidate's frame-to-pane journey remains unverified. No production consumer routes generic `ModelExecutionEvent.text_delta` events from shared-execution callers to the existing result owner. Add one only for inventoried workloads that need it, with policy gating and existing request/result identity. Terminal ownership across every provider/tool caller, artifact/tool-result event ownership, end-to-end downstream cancellation/late-write suppression, durable unknown-mutation receipts, and coverage of remaining callers remain open. See the [delegate lifecycle receipt](../acceptance/verified-gap-closure/GC24-02-delegate-terminal-lifecycle-2026-09-25.md), [cancellation-suppression receipt](../acceptance/verified-gap-closure/GC24-02-subagent-cancellation-suppression-2026-09-25.md), [Supervisor late-cancellation receipt](../acceptance/verified-gap-closure/GC24-02-supervisor-late-provider-cancellation-2026-09-25.md), [SubAgent/planner replay receipt](../acceptance/verified-gap-closure/GC24-02-tool-call-identity-replay-2026-09-25.md), and [Supervisor replay receipt](../acceptance/verified-gap-closure/GC24-02-supervisor-tool-call-identity-replay-2026-09-25.md). |
| Privacy | Sensitive-turn and static workload floors are enforced for covered routed SubAgent and council paths. Confidential/local-only SubAgent output now requires an awaited local result sink; missing sink or non-private route fails before provider use, route preferences cannot lower the configured floor, and the external supervisor gets only a fixed status/reference. The native result pane blocks copy/share/export for protected payloads. | End-to-end source and sink inventory, especially tool continuations, memory injection, supervisor/TTS, share/export, telemetry, provider persistence, response/display, and direct-mode paths, with negative canary evidence. See the [protected local-result receipt](../acceptance/verified-gap-closure/GC24-03-protected-local-result-handoff-2026-09-25.md). |
| Model access | Claude/Codex subscription and SAYGM foundations/configuration exist. | Per-model and per-route capability evidence, isolated runtime proof, accurate billing evidence, and any protected-model claim. Tool access remains gated. |
| Automatic memory | Existing SQLite revisions, budgets, rollback, evidence verification, and shadow tooling exist. A single strict classifier is shared by production and synthetic shadow; migrations 0025–0027 add durable staging, shared atomic budget reservation, and digest-only shadow metadata. Idle worker and teardown enqueue before cursor/pairing advancement and drain resumable extract/classify/apply stages under explicit gates. Claim timestamp fences stage transitions and atomic apply; stale owners cannot write. Separate-connection and spawned-process tests prove single claims; cross-process forget/apply and forget/lease-reclaim tests leave no fact or staged payload. Crash tests cover apply rollback, enqueue/cursor recovery, stage commits, and retries. Focused admission/worker/acceptance suites pass 77 tests. See the [multi-process race receipt](../acceptance/verified-gap-closure/GC24-05-admission-multiprocess-races-2026-09-25.md) and linked prior receipts. | Verify an eligible confidential route before production classification; complete shadow/benefit observation and staged Mac rollout. Production stays fail-closed. |
| Knowledge Atlas | Store-owned per-source refresh lifecycle, stale last-good retention, retry/reconnect, and generation checks are implemented. Latest focused Atlas suite passes 10; latest full MortimerHost suite passes 265 with 7 explicit skips and no failures. The eight historical window-visibility assertions are classified as requiring a visible WindowServer; only those three window tests and the on-screen graph benchmark skip when no screen is available. Unlock callback logic has a deterministic injected unit seam. | Live auth expiry/recovery, reliable source-change behavior, VoiceOver/keyboard, no duplicate fetch on presentation changes, on-screen graph/performance, real unlock delivery, connected-display journeys, and current-candidate acceptance. See the [GC24-06 fixture receipt](../acceptance/verified-gap-closure/GC24-06-headless-window-fixture-classification-2026-09-25.md). |
| Candidate/release | Historical interface, monitor, and release receipts exist. | Exact running source/config identity, current regression, physical Mac journeys, provider/memory pilots, independent review, rollback drill, and observation window. |

**2026-09-25 isolated-tree validation:** after the live Supervisor tool-call
identity guard, admission claim fencing, and apply rollback/crash tests,
the latest complete Python unit/integration run passed **2,913 tests, 4
skipped, 11 warnings, and 2 subtests**, including protected-result
pre-client, route-preference-floor,
SubAgent cancellation-during-tool, MCP/watcher/clipboard/agent-event/admin/
memory log-redaction
regressions.
The durable-admission focused suite passed **84**; the Atlas focused Swift
suite passed **10**; focused execution/Anthropic-stream/routing
tests passed **126**; focused memory automation/policy/worker/manifest/DB
tests passed **282** at the prior classifier increment; an earlier
migration/budget/admission set passed **75**. Targeted Ruff `F`/`I` and
`git diff --check` passed. The current call-site audit reports **26/26 covered,
zero review-required**, secret-free. See the [2026-09-25 inventory receipt](../acceptance/model-use-enhancements/receipts/model-call-site-inventory-2026-09-25.json),
the [GC24-02 implementation receipt](../acceptance/verified-gap-closure/GC24-02-execution-boundary-implementation-2026-09-24.md),
the [GC24-02 cancellation receipt](../acceptance/verified-gap-closure/GC24-02-cancellation-terminal-2026-09-25.md),
the [GC24-02 delegate lifecycle receipt](../acceptance/verified-gap-closure/GC24-02-delegate-terminal-lifecycle-2026-09-25.md),
the [GC24-02 cancellation-suppression receipt](../acceptance/verified-gap-closure/GC24-02-subagent-cancellation-suppression-2026-09-25.md),
the [GC24-02 SubAgent/planner tool-call replay receipt](../acceptance/verified-gap-closure/GC24-02-tool-call-identity-replay-2026-09-25.md),
the [GC24-02 Supervisor tool-call replay receipt](../acceptance/verified-gap-closure/GC24-02-supervisor-tool-call-identity-replay-2026-09-25.md),
the [GC24-03 exception-log receipt](../acceptance/verified-gap-closure/GC24-03-mcp-exception-log-redaction-2026-09-25.md),
the [GC24-03 watcher-log receipt](../acceptance/verified-gap-closure/GC24-03-watcher-log-redaction-2026-09-25.md),
the [GC24-03 clipboard-log receipt](../acceptance/verified-gap-closure/GC24-03-clipboard-log-redaction-2026-09-25.md),
the [GC24-03 agent/event-log receipt](../acceptance/verified-gap-closure/GC24-03-agent-event-findings-log-redaction-2026-09-25.md),
the [GC24-03 admin job-log/status receipt](../acceptance/verified-gap-closure/GC24-03-admin-job-log-and-status-redaction-2026-09-25.md),
and the [GC24-03 memory-log receipt](../acceptance/verified-gap-closure/GC24-03-memory-log-redaction-2026-09-25.md),
and the [GC24-05 source-evidence receipt](../acceptance/verified-gap-closure/GC24-05-memory-source-evidence-2026-09-25.md).
This validates this dirty source tree only; it does not prove production
stream consumption, provider capability, Mac behavior, merge, or release.

Use the latest linked receipts for exact commands and counts. Do not copy
counts from a prior snapshot into a new receipt. Before each task, rerun the
relevant checks and capture the actual result.

## Ordered implementation phases

Only start a phase after its prerequisites pass. Each phase ends with a dated
receipt and an updated status row. Implement one bounded slice at a time.

### Phase 0 — Reconcile ownership and the exact baseline (GC24-00/01)

Before editing, record branch, base/current revision, dirty files, sibling
worktrees, concurrent changes, and the code/test/receipt owner for every
requirement. Inspect the exact app/backend identity and effective non-secret
feature gates only when the Mac is available. Do not print process
environments, credentials, user content, or vault data. Mark unavailable facts
as unverified rather than inferring them.

**Pass:** dated baseline; current files reconciled with existing work; every
open requirement mapped to its code owner, tests, receipt, and missing proof.

### Phase 1 — Complete shared execution lifecycle (GC24-02)

**Keep the current boundary and route selection.** Do not add another
orchestrator or parallel result store.

The SubAgent run-log cancellation record and `delegate_task` UI terminal-event
slice are already covered by dated receipts; do not redo those slices. Next,
trace request ownership through every provider/tool round, assign exactly one
terminal owner to the full loop and its artifact/tool-result outcomes, and
prove cancellation reaches provider/tool execution while preventing late
UI/database effects. Preserve the existing voice response path: RTVI
`bot-llm-text` updates flow through `JarvisClient.transcript`,
`AppMessageRouter`, and `ResponseResultRouter`; do not add a second consumer
for those same voice tokens. Prove that path end to end on the current
candidate. For inventoried shared-execution callers that need live results,
route validated `ModelExecutionEvent.text_delta` events through a single
policy-aware adapter into the same result owner and request identity. A
run-log row or delegate-card terminal alone does not prove provider work
stopped or downstream effects were suppressed.

**2026-09-25 progress:** the SubAgent loop now detects cancellation even when
an awaited provider or tool adapter catches cancellation and returns. It
suppresses the returned value before execution-result logging, tool-result
events, or another provider round. See the [cancellation-suppression
receipt](../acceptance/verified-gap-closure/GC24-02-subagent-cancellation-suppression-2026-09-25.md).
This does not roll back a mutation already performed inside a tool; unknown
mutating outcomes and other caller families remain open.

**2026-09-25 progress:** direct-mode SubAgent and self-edit planner loops now
reject a reused provider tool-call identity before redispatch; routed loops
already reject IDs present in request history. Startup marks old active runs
orphaned rather than resuming them. Durable unknown-mutation receipts and
deduplication across a newly issued ID remain open. See the [tool-call replay
receipt](../acceptance/verified-gap-closure/GC24-02-tool-call-identity-replay-2026-09-25.md).

**2026-09-25 progress:** the existing live voice stream was traced from RTVI
frames through `JarvisClient.transcript`, `AppMessageRouter`, and
`ResponseResultRouter`. Client-frame aggregation tests pass **2/2**, a new
stub-transport integration test through all native owners passes **1/1**,
and response-router tests pass **7/7**. These tests establish the local
source-to-result path, not a running candidate journey. Generic
`ModelExecutionEvent.text_delta` delivery to the native result owner remains
unimplemented for shared-execution callers. See the [voice response-stream
receipt](../acceptance/verified-gap-closure/GC24-02-existing-voice-response-stream-path-2026-09-25.md).

**2026-09-25 progress:** the live Supervisor loop now validates each complete
tool-call batch before dispatch. Empty, oversized, repeated, or duplicate
provider IDs stop the turn with the existing bounded response and do not
partially execute the batch. This protects same-turn identity only; durable
unknown-mutation reconciliation, cancellation/late-write suppression, and the
shared-execution event consumer remain open. The existing live RTVI-to-results
consumer is separate and has no new end-to-end candidate receipt yet. See the [Supervisor replay
receipt](../acceptance/verified-gap-closure/GC24-02-supervisor-tool-call-identity-replay-2026-09-25.md).

1. Retain explicit opt-in streaming. Only profiles with a verified streaming
   capability may stream. Keep the compatibility collector for callers that
   do not subscribe to events.
2. Wire one production consumer to the existing app-owned response/results
   owner. It must append deltas to the request's existing result identity and
   obey the inherited `DataPolicy` before displaying, speaking, logging,
   persisting, or sharing any content. Do not create a second visible answer
   surface.
3. Define and enforce one request lifecycle through provider rounds and the
   full registered-tool loop: monotonic correlated events, zero or more
   progress/text/tool/artifact events, and exactly one terminal event. A
   tool call is not complete merely because the provider emitted its request.
4. Propagate deadline and cancellation from the owning request through the
   provider stream, tool execution owner, UI observer, and durable write path.
   After cancellation/timeout, suppress all late text, artifacts, tool calls,
   UI changes, memory writes, and completion notifications.
5. Reconcile mutating tool-call IDs against existing receipts before any
   retry or restart. Never automatically replay an action whose execution
   outcome is unknown. Preserve raw arguments only where the existing
   permission-gated executor requires them, and never include them in public
   progress events.
6. Preserve the current interactive/background admission limit and voice
   priority. Do not add a second queue or apply non-voice limits to voice.

**Tests required:** streaming delta accumulation and order; unsupported
profile fails before client creation; confidential output cannot enter an
external event/result sink; text/artifact/tool events obey policy; cancellation
before admission and during provider/tool execution; timeout and late
completion; exactly one terminal across multiple provider/tool rounds;
idempotent tool-result reconciliation after unknown outcome; parent/request
grouping; compatibility collector parity; voice priority during queued
background work.

**Pass:** the production result consumer receives only validated events and
the request has exactly one terminal outcome with no late side effects. Record
any remaining provider-specific capability limitation; do not label streaming
as end-to-end complete if a consumer or sink remains untested.

### Phase 2 — Prove privacy at every transmission and result sink (GC24-03)

Start from `scripts/audit_model_call_sites.py` and expand it to cover data
flows beyond completion calls. For each source, label provenance locally and
combine workload, context, attachment, memory, tool-result, and artifact
restrictions with the existing strictest-policy rule. User/provider content
cannot loosen that result.

Inventory and enforce before each of these boundaries:

- model request and every continuation, including council, planner, memory,
  vision, background and subscription adapters;
- tool request, tool result, MCP/external action, supervisor context, speech
  synthesis, and voice/display handoff;
- result rendering, attachment/share destination, export/copy, run log,
  usage/error telemetry, SQLite staging/history, and provider-session state.

For every forbidden destination, add a synthetic canary test proving both
zero transmission and zero persistence. Test protected and mixed-policy
inputs, sensitive data introduced mid-task, no explicit caller label, route
preference changes in-flight, unavailable compliant route, and error/timeout
paths. Logs and status messages may include bounded reason codes and opaque
IDs, never prompts, memory content, credentials, or raw provider errors.
Keep the existing voice exception accurately scoped; do not claim the whole
voice conversation is local/private.

**Pass:** source-to-sink inventory is complete, each sink has an executable
negative test, all checks occur before the sink, and no route or caller can
weaken source policy. Protected content remains available locally where the
approved product requires it.

### Phase 3 — Connect automatic memory classification to durable admission (GC24-05)

**2026-09-25 isolated-tree progress:** the same strict provider classifier is
now called through `execute_chat` by both the production worker and the
synthetic shadow runner. Live candidates retain a confidential policy label;
the runner has a separate `memory_shadow` workload limited to
approved-external synthetic fixtures. The idle watcher and teardown drain run
classification plus their SQLite connection in a worker thread, and commit
the claim before the provider call. There is no heuristic success fallback
after provider or route failure. Full suite: 2,848 passed, 4 skipped, 11
warnings, 2 subtests; memory/manifest/DB set: 282 passed. See the [GC24-05
classifier receipt](../acceptance/verified-gap-closure/GC24-05-route-aware-classifier-2026-09-25.md).
Current model policy has no verified confidential production route; the
provider worker therefore fails closed until one is configured and accepted.
This classifier receipt predates the durable-admission worker increment below;
do not treat its interim statement about admission staging as current.

**2026-09-25 durable-admission progress:** migrations `0025`–`0027` provide
durable staging, shared classifier-budget reservations, and digest-only shadow
metadata. The idle worker and teardown now enqueue finished exchanges before
cursor/pairing advancement, then resume bounded extract → classify → apply
stages. The worker reserves shared budget before provider classification and
atomically applies eligible rows with job completion. Extraction uses
user-authored evidence; live admission requires the classifier to cite the
current source turn. Per-key forget cancels staged candidates even before a
memory row exists. The path requires both settings and the explicit environment
gate; shadow records remain content-free and do not enter live memory. Focused
validation passes 84 tests; the full Python unit/integration suite passes
2,857 tests with 4 skipped, 11 warnings, and 2 subtests. No verified
confidential production route is configured, so production classification
remains fail-closed. See the [GC24-05 admission worker receipt](../acceptance/verified-gap-closure/GC24-05-admission-worker-2026-09-25.md).

**2026-09-25 claim-fencing progress:** the worker now passes its `claimed_at`
lease identity to stage commits, budget deferral, retry/failure, and
completion. Reclamation compares the exact claim it observed. This prevents
an expired worker from committing late extraction/classification output over
a replacement claim. Stale-result regressions cover extract and classify
after closing/reopening the database; the focused admission/worker/acceptance
suites pass **62**, and the full Python suite passes **2,896** (4 skipped, 11
warnings, 2 subtests). Per-boundary process-kill proof remains open. See the
[claim-fencing receipt](../acceptance/verified-gap-closure/GC24-05-admission-claim-fencing-2026-09-25.md).

**2026-09-25 apply, enqueue, cursor, and stage crash progress:** an injected exception
and abrupt child-process exit during apply prove SQLite rollback, lease
recovery, and one successful retry. Parameterized child exits immediately
before the per-session enqueue commit and after that commit but before the
global cursor update prove rollback/replay behavior: the missing enqueue is
created once, or the existing idempotency key is reused, and the cursor
advances with exactly one durable job. Child exits immediately after durable
extract/classify stage commits resume from the next stage and produce exactly
one fact. Additional child exits after extract/classify stage updates but
before commit prove the previous stage and payload remain intact and retry
after lease recovery. A child exit after the completion update but before
commit proves SQLite restores the whole apply unit, after which lease recovery
completes it once. The focused admission/worker/acceptance suite passes
**74 tests**. Multi-process duplicate worker and cross-process
forget/reclaim coverage,
route acceptance, and staged Mac rollout remain open. See the
[apply/enqueue/stage/completion crash receipt](../acceptance/verified-gap-closure/GC24-05-admission-apply-rollback-2026-09-25.md).

**2026-09-25 multi-process progress:** two spawned-process regressions now
prove exactly-one claim under independent worker processes and forget during
an in-flight atomic apply across separate processes. The focused
admission/worker/acceptance suites initially passed **76 tests**. A third
spawned-process race now covers forget versus expired-lease recovery; the
focused suite passes **77 tests**. The tested races end with no duplicate
claim, no resurrected forgotten work, and no forgotten fact. Confidential-
route acceptance and staged Mac rollout remain open. See the
[multi-process race receipt](../acceptance/verified-gap-closure/GC24-05-admission-multiprocess-races-2026-09-25.md).

Read the automatic-memory plan's current B5/B7/B9 limits before changing
memory code. Reuse the existing SQLite system, classifier contract, revisions,
budgets, rollback, and deletion mechanisms.

1. Use one strict `classify(candidates, *, policy_version)` adapter from both
   the production worker and provider shadow path. Deterministic heuristics
   may reject unsafe/low-quality items or provide a named baseline; they may
   not disguise provider failure as successful model classification.
2. Send only bounded, policy-approved, redacted candidates. The classifier
   proposes metadata only; it has no database write authority or Mortimer
   tools. Validate the entire batch and verify each evidence reference against
   stored source turns before applying any row. Assistant quotes are not proof
   of a user preference.
3. Add only the specified additive admission-job migration if inspection
   confirms it is still absent. Persist an idempotent job before advancing an
   extraction cursor. Keep provider calls outside SQLite write transactions.
   Commit each durable stage and recheck source revision, deletion/forget,
   policy, cancellation, and stage identity before application.
4. Reuse persisted atomic quotas across workers, maintain bounded retries, and
   preserve pending jobs after transient failures. Shadow mode must not alter
   live admission, retrieval, prompts, or the source cursor. Forget/delete
   must purge staged payloads and invalidate work in flight.
5. Keep the worker quiet, low-priority, reversible, and outside the voice
   response path. No memory-cleanup prompt, greeting, historical replay, or
   bulk relabel.

**Tests required:** contract floors and bounds; malformed, missing, duplicate,
extra, and unsupported rows abstain as a whole; fabricated evidence rejected;
correction/forget races; crash/restart at every enqueue/stage/apply/cursor
boundary; duplicate workers; shared-budget race; provider timeout/failure
preserves pending work; shadow prompt/retrieval invariance; deleted staging
payloads; voice latency/priority unchanged.

**Pass:** production and shadow use the same tested strict adapter and
idempotent durable job flow. Keep rollout disabled/staged until synthetic and
daily-driver pilot gates pass. Never replay the 28 historical exchanges as
part of this phase.

**2026-09-25 budget-reservation increment:** migration `0026` adds a shared
atomic reservation ledger. Both maintenance and durable exchange-admission
classification reserve the candidate/call budget before provider execution.
A concurrent two-worker regression proves only one worker can reserve the
final call. See the [budget reservation receipt](../acceptance/verified-gap-closure/GC24-05-shared-budget-reservations-2026-09-25.md)
and the [admission worker receipt](../acceptance/verified-gap-closure/GC24-05-admission-worker-2026-09-25.md).

### Phase 4 — Verify model access one model/route/capability at a time (GC24-04)

At implementation time, verify the official documentation for the exact
pinned provider runtime and record its version and supported auth, text,
image, streaming, structured-output, tool, and cancellation capabilities.
Test the subscription process in a task-scoped clean directory with an
allowlisted environment, no project hooks/plugins/MCP/native tools, no
persistent session, bounded stdin/output, process-group cancellation, and
cleanup on every exit. Parse only the provider's documented completion
envelope; an exit code alone is insufficient.

Do not store passwords or OAuth state in the project vault/repository. Do not
claim API-cost elimination based on login or a list-price estimate; separate
route selection, reported usage, provider billing evidence, and actual account
charges. Keep tools disabled unless the Mortimer bridge, permission checks,
existing sandbox executor, policy enforcement, idempotency and cancellation
are all proven together. A missing capability stays unavailable; no
subscription-to-API fallback is added.

For SAYGM, use synthetic public inputs for basic capability probes. A
confidential claim requires current catalog metadata meeting the existing
confidential plus documented TEE criteria. Never test access by transmitting
real memories.

**Pass:** secret-free per-model/per-route receipts state exactly which
capabilities and billing facts are proven. A model can be selected only for
verified capabilities and policy. No provider's tool execution is enabled by
this phase without the full bridge proof.

### Phase 5 — Finish Knowledge Atlas behavior and accessibility (GC24-06)

Retain the existing store-owned, per-source lifecycle, stale last-good cards,
bounded error states, explicit retry, reconnect triggers, and generation
guards. Do not add a second client, periodic polling, duplicate websocket, or
new data source. Do not fetch merely because the Atlas moved between displays
or tabs.

Add only reliable existing source-change triggers. Test independent partial
failure, expired auth followed by recovery, cancellation, manual retry,
stale freshness labeling, and preservation of graph selection/groups/pins.
On the identified Mac candidate, validate VoiceOver names/status, keyboard
refresh/retry, useful empty/loading states, reduced motion/transparency,
fetch counts during tab/display moves, and existing graph/frame budgets.
Retain and investigate the recorded headless `WindowVisibilityTests`
failures; do not weaken thresholds or count them as passes.

**2026-09-25 isolated-tree progress:** Atlas now refreshes only the run-history
source when the app-owned `AgentRunStore` reports a completed agent run. A
focused suite now passes 10 tests covering independent source failure,
last-good retention, per-source request coalescing, and recovery after a
transient failure. See the [GC24-06 run-source
receipt](../acceptance/verified-gap-closure/GC24-06-atlas-run-change-2026-09-25.md).
Live source-change coverage beyond agent run completion and candidate
acceptance remain open.

**Pass:** focused tests plus live candidate receipts prove truthful source
status, recovery, accessibility, performance, and no duplicate requests.

### Phase 6 — Exact candidate, physical journeys, pilots, and release (GC24-07–10)

1. Build one candidate from the reconciled source using the established native
   bundle workflow. Record source revision, dirty state, artifact identity,
   backend identity, configuration digest, and effective non-secret gates.
   Keep interface, routing, memory and sharing switches independent.
2. Run all required Python, Swift, integration, evaluation, privacy/call-site,
   performance, package/signature and diff checks. Record executed/pass/fail/
   skip counts; do not remove existing failures or treat skips as passes.
3. On the physical Mac, complete only outstanding user journeys on that same
   candidate: compact startup, voice input/output and orb feedback, full
   response placement, research sharing, attachment consent/cancel/reconnect,
   all eight tabs, font picker, keyboard/VoiceOver, graph refresh, one bounded
   external-display stage, attach/detach/reconnect, and no duplicate request
   or window. macOS Spaces do not count as multiple physical displays.
4. Run model pilots on synthetic public data first, then explicitly approved
   non-voice workloads. Capture selected model, route, privacy, auth mode,
   quality denominator, queue/cold/warm/first-useful/total latency, failures,
   cancellation, usage-known state and billing evidence. Preserve current
   latency/quality thresholds; do not change defaults to make a pilot pass.
5. Run memory shadow and staged pilots under the existing budget and rollback
   rules, with a verified restorable database backup before any production
   memory mutation. Roll back only attributable staged revisions through the
   existing undo path.
6. Obtain independent review; demonstrate interface, route and memory
   disablement plus executable rollback without deleting preferences/data.
   Start/complete the required observation window on the exact stable
   candidate. Any source/config change restarts affected candidate evidence.

**Pass:** one candidate is traceable from source/config through regression,
physical acceptance, pilot, independent review, rollback, and observation.
Missing hardware/provider/observation evidence remains clearly open with an
owner and next action.

## Per-task handoff contract

Before editing, the next model must:

1. Read this plan, the matching GC24 authority section, the relevant feature
   plan, the latest receipt, `git status`, and the exact source/test files.
2. Reconcile concurrent work and select one bounded phase/subtask. Do not
   modify files owned by another in-flight change until ownership is clear.
3. Add or update meaningful tests, run the narrow suite and all affected
   suites/audits, and retain every failure and skip in the report.
4. Add a dated receipt with exact branch/base/current revision, changed files,
   commands, counts, preserved invariants, live evidence (if any), limitations,
   and next unblocked action. Update the existing status row and link the
   receipt; do not create duplicate status IDs.
5. Run `git diff --check`, check documentation links/manifests when affected,
   and inspect the diff for secret data, copied vault content, weakened
   defaults, fallback behavior, unrelated design changes, and obsolete status
   claims.
6. Leave the work uncommitted and unpushed unless the user separately asks.
   Never claim merge, deployment, live acceptance, or release from source-only
   tests.

## Closure language

Use these labels consistently: **planned**, **implemented in isolated tree**,
**merged**, **candidate verified**, **live acceptance complete**, and
**released/closed**. State which artifact and receipt support each label.
Do not give an overall completion percentage unless the status owner has
published a deduplicated requirement denominator.
