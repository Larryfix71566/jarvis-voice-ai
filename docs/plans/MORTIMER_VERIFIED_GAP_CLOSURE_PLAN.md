# Mortimer — Verified Gap Closure

**Authored:** 2026-09-24, Codex, from repository inspection.
**Status:** Integrated and deployed to the Mac at `539f8f6` on 2026-09-28.
Live release acceptance and provider verification remain open. `ROADMAP.md`
is authoritative for ownership and current state.
**Inspected source:** `4acb4dc2827f292f1236155e3c445d4ec4e9e5a0` (main PR #90).
**Working branch:** `codex/isolated-20260924`.
**Working directory:**
`/Users/larryfix/Documents/Codex/2026-09-09/can/work/codex-isolated-20260924`.

## 1. Outcome and authority

Close the gaps between the implemented Command Console, automatic memory,
model-access plans, and the evidence needed to release them. Preserve the
interface and operating behavior Larry selected. An implementer must not
replace missing evidence with a redesign or treat an existing implementation
as a reason to skip acceptance.

This is an execution addendum to these specifications:

- [Command Console and Atlas](MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md).
- [Automatic memory, section B](MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md).
- [Model Use Enhancements](MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md).
- [Architecture](../ARCHITECTURE.md).
- [Release readiness](../acceptance/adaptive-interface/RELEASE_READINESS.md)
  and [acceptance runbook](../acceptance/ACCEPTANCE_RUNBOOK.md).

Existing protocol schemas, security boundaries, visual decisions, and stricter
acceptance limits in those specifications remain binding. This addendum fixes
the closure sequence and adds the missing implementation contracts below.
Section B's quiet memory policy takes precedence over the historical August
manual-review behavior. No new obligation to classify memories is placed on
the user.

Implement only the next unblocked increment. If the checked-out code has
changed, compare the changed files and update the evidence before editing.
Do not recreate work already merged by Claude. A provider limitation is an
unsupported capability, not permission to bypass a boundary or pick a cheaper
model. Any conflict with a locked decision is a specific blocked item; finish
independent work without silently changing the decision.

## 2. What the inspection establishes

These are source observations at the commit above, not observations of the
currently running app:

1. Layout 2, compact Conversation startup, shared action ownership, response
   grouping, bounded supporting-display presentation, Atlas projections, and
   the comet/orb renderer exist. They need regression and release evidence,
   not another replacement interface.
2. `jarvis/model_execution.py` accepts context and attachments but sends only
   `instructions`. Its contract is not yet the complete execution boundary
   promised by Model Use Enhancements.
3. `jarvis/subscription.py` exposes text-only CLI adapters. Environment-key
   stripping exists, but process/config isolation, tool-boundary enforcement,
   structured failure handling, and cancellation require completion. A
   read-only CLI sandbox alone does not demonstrate that all tools are off.
4. `jarvis/memory_automation.py` supplies a deterministic heuristic classifier
   used by runtime maintenance. The provider shadow runner demonstrates a
   separate synthetic classification path; it does not prove production
   model-backed admission. Existing revisions, queues, budgets, retrieval and
   rollback machinery must be extended rather than replaced.
5. At the inspected base commit, `KnowledgeAtlasView.swift` projected existing
   results and AdminAPI data without a dependable per-source failure/retry
   lifecycle. The isolated worktree now implements store-owned per-source
   refresh state and visible failure/retry status; physical, accessibility,
   reconnect/auth and performance acceptance remain open (GC24-06).
6. Native layout 2 defaults coexist with disabled backend console/sharing,
   memory and routing defaults. That is a deployment compatibility risk to
   check against effective runtime settings, not proof of a live failure.
7. Status files still reconcile mainly against `88b206f`. There are two
   different UI2-21 requirements and an unused duplicate
   `macos/MortimerHost/Placement/ContentWindowRegistry.swift` outside the active
   source tree. Historical wave descriptions need retirement annotations.
8. September 18 receipts establish some one-external-monitor unplug, rehome,
   reconnect and result-ownership behavior. Missing spoken-response,
   duplicate-fetch, sharing, accessibility, current-candidate and observation
   evidence must not be mislabeled as either complete or entirely untested.

The latest recorded deployment is not necessarily the currently running
deployment. A source commit, installed bundle, process path, and loaded backend
configuration are different facts. GC24-00 establishes each.

## 3. Locked design decisions

### Interface and voice

- Keep Command Console/layout 2 and compact Conversation as the normal startup.
  Preserve explicit legacy-layout rollback preferences and all eight sidecar
  tabs, scrollable headers, working font controls, keyboard and voice access.
- Keep full answers in the response/results area, with brief live conversation
  captions. One user/developer request owns one result identity; updates append
  sections. Display moves do not create another request, fetch or subscription.
- Retain one app-owned client, workspace, action coordinator and placement
  owner. One bounded supporting stage shares space between results; preserve
  its existing one-to-four tile policy, pins and return locators. Never create
  nested result windows or duplicate full renderers for the same result.
- Retain the selected atom/comet layout with Crystal option A's glass shell:
  the paired panes, strip light and softer second window, dark wall line,
  speaker-colored wall glow, and visible shell at standby. Keep user/Mortimer
  color distinction and connected idle animation even when the mic is muted.
  Speech intensity comes from measured input/output; idle motion is not a
  fabricated voice level. PR #90 implements and Larry accepted the selected
  shell. Do not resurrect deleted wave paths or obsolete sliders, and do not
  edit Crystal renderer code under this plan.
- Voice, pointer and keyboard invoke the same validated actions. Extend the
  existing settings/results surfaces, typography and Liquid Glass treatment.
  Do not add a competing console or a second audio-input tap.
- Preserve Haiku's voice-supervisor role, current STT/TTS and audio transport.
  No subscription or SAYGM migration of the live voice loop in this plan.

### Models, privacy and memory

- Model identity, access route and workload remain separate. Preserve the
  existing non-voice quality floor and exact model selection. No silent model
  substitution, paid API fallback, privacy downgrade or unlimited retry.
- Use official subscription authentication. The Mac vault remains the source
  for API secrets; do not store account passwords, extract OAuth credentials,
  or copy the vault into a worktree. Retain valid existing sign-ins.
- A subscription route cannot run a tool workload until the existing Mortimer
  permission and sandbox boundary controls every tool operation. Unsupported
  routes remain unavailable; they do not receive a reduced-security fallback.
- Confidential routing requires verified route/model capability. A SAYGM API
  key or ordinary catalog model is not confidential-computing evidence.
- SQLite remains the memory system of record. Reuse existing source evidence,
  revisions, maintenance jobs and usage records. No second memory database,
  new vector service or vendor-owned conversation store is introduced.
- Preserve self-edit beginning after the spoken preview, existing sandbox
  isolation and PR approval boundary. Do not restore an extra spoken approval.
- The completed 28-exchange recovery is not rerun. No bulk historical replay
  is needed to validate new admission or rollout.

## 4. Scope, order and tracking

New closure IDs use `GC24-` to avoid collisions with older gap plans. All are
open at authorship. Checked completion requires the evidence described in
section 15; passing implementation tests alone cannot close a live gate.

- [ ] **GC24-00 — Establish source, runtime and acceptance baseline.** First.
- [x] **GC24-01 — Reconcile status and remove ambiguous ownership.** Closed
  2026-09-25 after source audit, status/ID reconciliation, duplicate-source
  removal, and manifest/documentation checks. See the
  [GC24-01 receipt](../acceptance/verified-gap-closure/GC24-01-status-reconciliation-2026-09-25.md).
- [ ] **GC24-02 — Complete the shared execution contract.** After 00. The
  SubAgent cancellation/run-log slice has a current receipt; the complete
  provider/tool/event lifecycle remains open.
- [ ] **GC24-03 — Enforce policy through every transmission and result sink.**
  After 02; blocks enabling new routes for protected content.
- [ ] **GC24-04 — Complete subscription and SAYGM capability gates.** After
  02/03; text and tool capabilities have separate subreceipts.
- [ ] **GC24-05 — Connect the production memory classifier.** The shared
  `execute_chat` adapter is wired to production and synthetic shadow, with
  confidential route checks and off-loop execution. Still gated on a verified
  confidential route plus the separate durable admission-job/stage/cursor and
  rollout evidence. See the [route-aware classifier receipt](../acceptance/verified-gap-closure/GC24-05-route-aware-classifier-2026-09-25.md).
- [ ] **GC24-06 — Make Atlas freshness and failures visible.** After 00;
  implementation is in progress in the isolated tree; live acceptance remains.
- [ ] **GC24-07 — Complete candidate configuration and local regression.**
  After code increments included in that candidate.
- [ ] **GC24-08 — Close remaining physical Mac journeys.** After 07; run
  monitor-dependent work first when hardware is available.
- [ ] **GC24-09 — Perform staged memory and model-access pilots.** After
  03/04/05/07 for the relevant route; independent of three-display availability.
- [ ] **GC24-10 — Independent verification, rollback and release closure.**
  After relevant prior gates; includes the five-day candidate observation.

Implementation, merge, verification, deployment and user acceptance are
separate states. An unavailable third monitor may block its acceptance row,
but must not prevent completing model, memory, documentation or local tests.

Do not count these rows as extra product requirements when calculating overall
completion. Map them to existing CC/B/MAR/UI2 requirements, deduplicate aliases,
and publish the denominator. Home automation, surveillance, investing, Jev,
local voice migration and unrelated roadmap expansion are outside this plan.

## 5. GC24-00 — Baseline and worktree isolation

**Files:** dated receipt under `docs/acceptance/`; existing status documents.

1. Record this worktree's branch, HEAD, clean/dirty state and remote main HEAD.
   Fetch/read remote state without resetting shared branches. List worktrees;
   inspect concurrent changes read-only. Include Claude's current visual work
   in the collision inventory, not this branch without review.
2. Map each earlier open row to source, tests, dated receipts and its remaining
   condition. Distinguish missing code, missing evidence, known failure,
   unavailable hardware/provider and future roadmap.
3. Inspect running Mortimer executable path/hash, backend process working
   directory/revision, service identities, start times and effective gates.
   Read only allowlisted nonsecret configuration fields. Do not dump process
   environments, decrypted vault contents or authenticated request payloads.
4. Record console/sharing capabilities advertised in the actual session,
   memory enabled/shadow/stage, model-routing enabled, route preferences and
   model profiles. Treat source defaults and effective runtime separately.
5. Establish baseline test results and artifact identity before code changes.
   Old test counts are historical evidence only. A skipped hardware case has
   no current pass result. Keep pre-existing failures visible.

**Pass:** a reproducible source/runtime inventory with unknowns explicitly
named, no writes outside the isolated tree, and a one-to-one closure map.
If the running Mac cannot be inspected, code work continues against the
recorded source; deployment remains unverified.

## 6. GC24-01 — Status accuracy and one source owner

**Files:** `docs/acceptance/IMPLEMENTATION_STATUS.md`, the four feature status/
readiness files it links, `docs/acceptance/ACCEPTANCE_RUNBOOK.md`,
`docs/ARCHITECTURE.md`, `docs/REPO_MAP.md`, and the duplicate registry file.

- Reconcile against GC24-00's exact commit. Separate heuristic memory admission
  from production model-backed classification, and synthetic fixtures from
  live reviewed decisions. Label existing model adapters as text-only until
  their capabilities pass GC24-04.
- Retain UI2-21 for the atom display. Rename the developer-run grouping/Glass
  requirement to UI2-23 after confirming that ID is unused at implementation
  time. If concurrently allocated, use the next free UI2 ID and record the
  mapping. This is identifier maintenance, not a scope change. Historical
  receipts remain immutable; an alias must include both old ID and title.
- Remove only `macos/MortimerHost/Placement/ContentWindowRegistry.swift` after
  proving no package/script references it. Keep the active file at
  `macos/MortimerHost/Sources/MortimerHost/Placement/ContentWindowRegistry.swift`
  and its tests. Do not refactor the placement system as housekeeping.
- Mark superseded wave-depth controls historical. Preserve supported tuning
  actions and stored keys still needed for compatibility. Correct stale
  merge-to-close notes without closing their separate hardware obligations.
- Update operational commands to select the actual candidate worktree and its
  own dependencies. Do not instruct users to execute an `.app` directory or
  borrow the production Python environment to test a different checkout.
- Keep open work above completed work with checkbox status. Architecture docs
  remain visible through the existing Repo/reference and self-edit context
  paths; do not create another architecture store.

**Pass:** all links and manifest checks pass; no ambiguous current ID, duplicate
source owner, unsupported completion claim or change to historical receipts.

## 7. GC24-02 — Complete execution without losing input or lifecycle

**Primary files:** `jarvis/model_execution.py`, `jarvis/model_routing.py`,
`jarvis/llm_client.py`, `jarvis/memory_model.py`,
`jarvis/memory_extraction.py`, `jarvis/memory.py`, `jarvis/usage_ledger.py`,
`jarvis/memory_sweep.py`, `jarvis/agents/base.py`, `scripts/cost_report.py`;
affected callers identified by `scripts/audit_model_call_sites.py` (first
migrated family: `jarvis/kb_digest.py`). Tests in
`tests/unit/test_model_execution.py`, `tests/unit/test_subagent.py`,
`tests/unit/test_usage_ledger.py`, `tests/unit/test_kb_digest.py`,
`tests/unit/test_cost_report.py`, and the existing routing, call-site,
subagent and integration suites.

Lock the following contract before migrating callers:

1. Keep `ModelExecutionRequest` and existing task/parent IDs. Replace permissive
   input handling with validated message/context and attachment records using
   existing message roles and shared-content normalization. Preserve ordering,
   role, source identity and policy. Never stringify a message dictionary or
   silently drop a context/attachment field. Reject unsupported content before
   creating a provider client. Keep attachment byte/size limits from CC6.
2. Add explicit permitted-tool references, output requirements, deadline and
   cancellation to the boundary. Tools are references to Mortimer's registered
   tools, not provider-created grants. Snapshot the effective model/route/
   policy for each task; subsequent preference changes affect new tasks only.
3. Normalize the original plan's lifecycle to `queued`, `started`, `progress`,
   `text_delta`, `tool_request`, `tool_result`, `artifact`, and exactly one
   terminal `completed|cancelled|failed` event. Each event carries task ID,
   parent-request ID and monotonically increasing sequence. Policy travels
   with content; billing, timings and bounded usage metadata accompany the
   terminal result. Unknown usage remains unknown, never zero.
4. Retain `execute_chat` as a compatibility collector of the normalized text
   path. Direct API adapters preserve existing streaming, tool loops, prompts,
   model parameters and response semantics. Do not introduce a second agent
   orchestrator in this module. Migrate one call-site family per commit.
5. Enforce one terminal state. Timeout/cancel stops provider work and prevents
   late text, artifacts, memory writes or tools from reaching the UI/DB.
   Reconcile already-executed tool IDs before any retry; do not retry mutating
   tools automatically. Preserve existing persisted job/run records.
6. Add one process-owned admission coordinator for subscription/background
   model calls: at most two active calls by default, at most one background
   call. Interactive work takes the next free slot; background work cannot
   consume the reserved interactive capacity. This does not throttle the
   voice pipeline. The same counters must apply across the app's async loop and
   synchronous worker threads that submit through the boundary; do not create
   per-loop capacity pools. Pending memory stays in its existing durable
   queue. No Redis, separate daemon or second durable task database.

**Required tests:** context survives identically with role/order; supported
images are forwarded and unsupported images cause zero transmissions; model
selection is immutable during a run; first/terminal event ordering; timeout,
queued/active cancel and late results; duplicate tool-result replay; parent
result grouping; interactive capacity under memory load; direct-API parity.

**2026-09-25 implementation progress:** optional `stream_text` is implemented
for explicitly streaming-enabled routes. Three direct Anthropic profiles opt
in; the Anthropic SDK stream is translated into the existing OpenAI-shaped
chunk interface, and the shared boundary emits policy-labeled text deltas
while collecting a compatibility result. Tool fragments remain buffered
until provider completion and are then validated with the registered schema.
Focused model-execution, Anthropic-shim and route tests pass **125/125**; the
full Python unit/integration suite passes **2,828 tests, 4 skipped, 11
warnings, 2 subtests** on the current tree. No production caller consumes the
deltas yet. This does not complete artifacts, tool-result events, full agent
loop terminal ownership, downstream UI/DB cancellation, or durable recovery.
See the updated GC24-02 receipt.

**Pass:** no accepted input is lost, every migrated caller crosses policy
validation, and baseline direct-API behavior remains covered with unchanged
quality denominators. Static inventory coverage alone is insufficient.

## 8. GC24-03 — End-to-end policy and truthful configuration

**Primary files:** `jarvis/privacy_policy.py`, `jarvis/model_routing.py`,
`jarvis/model_preferences.py`, `config/model_access.yaml`, the execution
boundary, delegate/tool loops, memory-context injection, supervisor/TTS result
handoff, console sharing and telemetry sinks. Use the call-site inventory to
name every sink in the receipt; do not assume a central helper covers them.

1. Derive policy locally from workload plus every source. Combine restrictions
   using the existing strictest rule. Private unlabeled attachments/documents/
   memories remain confidential. A model may tighten classification but cannot
   authorize a privacy downgrade.
2. Validate before each model request, external tool transmission and tool-result
   continuation. Validate the destination independently for supervisor context,
   TTS, logs, exports and provider session persistence. Secrets reach only their
   owning tools. Prompt content and raw provider error text never enter ordinary
   route-readiness reports or usage logs.
3. Return protected results to the existing local result area. Give Haiku only
   a fixed status plus opaque reference when the result policy disallows that
   destination. Keep the full protected result out of later supervisor turns
   and speech-provider input. Preserve allowed personalization rather than
   dropping all memory to pass a privacy test.
4. Validate configuration before activation, including model capability, route
   privacy and current availability. Current direct-API selections for
   confidential/local-only workloads must not be enabled by weakening labels.
   A workload with no compliant route stays unavailable with a reason; voice
   stays on its existing route. Do not invent a local runtime to satisfy a row.
5. Reuse model preference/config ownership and existing console/voice controls.
   Both entry points run the same validation, expose effective route/billing/
   privacy and make explicit fallback choices visible. Empty fallback remains
   empty. An unavailable auth/capability is not an invitation to select API.

**Required tests:** synthetic canaries through memory, tools, attachments,
council, errors, response routing and TTS. For each forbidden destination assert
zero transmissions and no payload in logs. Test mixed-policy context,
mid-task sensitive tool results, unavailable route and preference changes.

**Pass:** a reviewed sink inventory with executable negative tests and no
silent privacy downgrade. No claim of an entirely private voice conversation:
the existing STT/supervisor route remains external.

## 9. GC24-04 — Subscription and SAYGM routes

**Primary files:** `jarvis/subscription.py`, `jarvis/saygm.py`,
`jarvis/model_routing.py`, `config/model_access.yaml`,
`scripts/verify_model_access.py`, and their existing unit suites.

### 9.1 Subscription text capability

- Pin and record each official runtime version, supported launch mechanism,
  model identity and authentication mode. Recheck official provider guidance
  and allowed subscription integration at implementation time. Do not invent
  SDK methods or flags from another release. If an integration is unsupported,
  record that route unavailable; do not emulate a web session.
- Replace inherited project execution context with a per-task temporary working
  directory and an allowlisted child environment. Preserve the supported
  provider-managed sign-in mechanism without copying its credentials. Disable
  project instructions, hooks, plugins, external MCP servers and built-in
  tool execution through verified runtime controls. Test the actual runtime;
  removing known API environment variables alone is not sufficient.
- Send prompt payloads through a supported input channel that avoids putting
  protected content in process-list arguments. Prohibit persistent provider
  sessions across tasks/privacy scopes. Clean temporary content on every exit.
- Parse documented envelopes/events strictly. `is_error`, authentication errors,
  failed terminal events or absent completion are failures even with exit zero.
  Do not use raw JSON/error output as a successful answer. Normalize auth,
  allowance, credit, capability, policy, timeout and provider failures.
- Use an owned child process group and asynchronous cancellation. On timeout
  or cancel, terminate the group, allow at most two seconds to exit, then kill
  and reap it. Tests prove no child remains and no late result is published.
- Report list-price estimates separately from actual billing. A returned
  `costUSD` alone does not establish API billing or subscription-only operation.
  Verify account mode and paid-overage settings where supported; otherwise
  display the unresolved fact, not an assurance of zero cost.

### 9.2 Subscription tool capability

The architecture is fixed: provider runtime -> task-scoped Mortimer tool bridge
-> existing registered permission check -> existing tool/sandbox executor.
The bridge is the only tool surface exposed to that provider task. It reuses
the existing MCP infrastructure, not another unrestricted shell server.

Each request binds task ID, parent ID, tool-call ID, tool name, validated
arguments, deadline and policy to the active task. Validate against that task's
allowed tool set, not model-supplied identity or permissions. Route mutating
development operations through the existing self-edit service/VM. Validate
tool-result policy before returning it to the runtime. Record tool receipts in
the existing run log and deduplicate/reconcile by tool-call identity.

First prove the pinned provider runtime can disable all alternate tools and
use only the scoped bridge. Then test denied filesystem/shell/network/tool
access, invented tool names, cross-task IDs, replay, timeout and cancellation.
Keep subscription `tools` capability false until both the runtime probe and
bridge tests pass. A runtime that cannot enforce this remains text-only;
developer/app-builder subscription migration stays explicitly blocked.

This is a feasibility gate with a fixed boundary, not permission for the next
model to choose a different security architecture to obtain a green result.

### 9.3 SAYGM and route receipts

Use the existing vault-backed catalog code. Capture a redacted current catalog
receipt, exact selected model IDs and capability evidence. Require the existing
confidential catalog checks, including the recognized confidential metadata and
TEE model naming contract; unsupported/ambiguous entries fail closed. Ordinary
models remain approved-external only. If no confidential model is available,
confidential workload enablement remains blocked, even if public synthetic
inference succeeds. Revalidate selected model capability before protected use;
a failed refresh cannot promote or preserve an unverified privacy claim.

Use synthetic public probes for initial account/route checks. Do not repeat
login or ask the user to re-enter an already-present key unless a fresh probe
actually fails authentication. Do not send real memories merely to test access.

**Pass:** separate receipts for each route/model and `text`, `tools`, `images`
or structured-output capability actually needed. Test each workload before
selection; authentication success alone cannot close MAR-E/MAR-F/MAR-G.

## 10. GC24-05 — Production automatic memory classification

**Primary files:** `jarvis/memory_automation.py`, `jarvis/memory_model.py`,
`jarvis/memory_extraction.py`, `jarvis/memory_extraction_worker.py`,
`jarvis/bot/memory_watcher.py`, existing admission hooks in `jarvis/memory.py`,
`scripts/run_memory_provider_shadow.py` and memory acceptance suites.

**2026-09-25 isolated-tree progress:** the maintenance classifier now accepts
evidence only when IDs resolve to stored user conversation turns; only
`exact_update` and `near_duplicate` recall events can add corroboration;
corroboration is checked against distinct turns and sessions; provider output
cannot upgrade assistant/tool/quoted provenance; and per-exchange facts carry
their source user-turn ID. The source-evidence increment's full Python
unit/integration suite passed 2,833 tests with four skips, 11 warnings and two
subtests. The latest full Python unit/integration suite passes 2,848 tests,
4 skipped, 11 warnings and 2 subtests; its focused memory/manifest/DB set
passes 282. See the [GC24-05 source-evidence receipt](../acceptance/verified-gap-closure/GC24-05-memory-source-evidence-2026-09-25.md).
The [route-aware classifier receipt](../acceptance/verified-gap-closure/GC24-05-route-aware-classifier-2026-09-25.md)
records the next increment: the same `execute_chat` adapter is wired to the
production worker and synthetic shadow runner, the DB claim is committed
before model work, and worker execution is off the voice loop. The current
configuration still has no verified confidential production route, so live
provider admission remains fail-closed. Additive migration `0025` and the
queue primitives are now present; their source-identity, stage, claim, retry,
reclaim and forget behavior has focused coverage. End-to-end worker/teardown
enqueue-before-cursor wiring, resumable extract/classify/apply processing,
shared atomic budgets, remaining crash/race cases, and rollout/live evidence
remain open. See the [GC24-05 staging receipt](../acceptance/verified-gap-closure/GC24-05-admission-staging-2026-09-25.md).

1. Implement one production classifier adapter satisfying section B7's exact
   `classify(candidates, *, policy_version)` contract. Both runtime maintenance
   and the shadow runner invoke this adapter. Keep heuristics as a deterministic
   baseline and safe local rejection checks, not a hidden fallback that claims
   a failed model classification succeeded.
2. Use the dedicated memory profile and GC24-02/03 execution path. The classifier
   receives bounded redacted text/source metadata, no tools, no write authority
   and a strict output schema. Model output proposes metadata only.
3. Preserve B7 limits: 20 candidates, 12,000 input characters, 2,000 output
   tokens; at most eight source-turn IDs; confidence in [0,1]; exact enums and
   reason codes. Missing, extra, duplicated or malformed records abstain the
   whole batch. All validation happens before any classification write.
4. Verify returned evidence against actual stored source-turn/session records.
   A row ID or repeated content is not a second independent observation.
   Explicit confidence is 1.0; corroboration needs distinct turns in separate
   sessions and confidence >=0.80. Assistant/quoted content cannot become a
   trusted user preference. Unknown/tentative rows do not enter standing context
   or authorize actions. Preserve intentional legacy compatibility and test it
   separately; do not bulk-relabel existing memories.
5. Wire classification after extraction before new durable admitted facts,
   with a durable admission job when a provider is unavailable.
   Existing metadata-maintenance jobs remain revision/idempotency checked.
   Never keep a SQLite write transaction open across a provider call. Before
   apply, recheck revision, deletion, policy, task cancellation and stage.
6. Preserve reversible same-subject/scope corrections and effective time; no
   destructive rewrite. Preserve query-relevant archived recall and record
   `used_for` only after insertion into the actual prompt.
7. Run only off the active voice path. Retain persisted limits of 100 candidates
   and five model calls per UTC day, one batch or 30 seconds per idle interval,
   and three retries after 60/300/1800 seconds. Failures preserve pending work,
   obey budgets and do not trigger a paid fallback or user cleanup prompt.
8. Keep the existing enabled/shadow/stage switches. Shadow never changes live
   retrieval, prompts or admitted metadata. Audit greeting and review-queue
   producers so ordinary maintenance creates no spoken chore. Only genuinely
   necessary existing action-confirmation flows may interrupt the user.

**Durable admission contract:** the existing `memory_extraction_pending` table
pairs an unfinished user turn with a response; it is not a durable queue for
finished exchanges or unclassified candidates. Do not repurpose it. Add one
additive migration, using the next unallocated migration number, for
`memory_admission_jobs` in the existing SQLite database. This is staging, never
a retrieval source. Its fields are `id`, `idempotency_key UNIQUE`, `user_id`,
`session_id`, `user_turn_id`, `assistant_turn_id`, `policy_version`,
`stage (extract|classify|apply)`, `status (pending|running|complete|failed|cancelled)`,
`candidate_json`, `classification_json`, `attempts`, `next_attempt_at`,
`claimed_at`, `last_error_code`, `created_at`, and `updated_at`. JSON fields
are nullable until their stage produces them, schema-validated and bounded by
the classifier contract. They inherit source privacy and the existing
forget/delete policy. Logs and receipts contain IDs/digests, not these payloads.

The idempotency key is a digest of the canonical user/session/user-turn/
assistant-turn/policy-version tuple. Commit the job before advancing the
extraction cursor past its exchange; only then clear the pairing row. Carry the
actual user-turn ID through the extraction API instead of treating the
assistant-response ID as evidence of a user assertion. The extraction worker
and session teardown converge on this same enqueue path when automation is
enabled. Preserve disabled behavior and shadow's prohibition on changing live
admission; shadow may write its bounded staging/evidence records only.

Commit each stage result before advancing; resume from the last committed stage
after a crash. Do not repeat a completed extraction just because classification
failed. Apply admitted facts, revisions and job completion in one short
transaction after revalidating source existence and policy. Terminal successful
or cancelled jobs drop payloads and keep only the minimal idempotency receipt;
failed jobs retain bounded evidence for the existing retry/inspection path.
Forget/delete purges related staging payloads and invalidates active claims.
Reclaim abandoned jobs under the same bounded retry policy as maintenance.

Admission classification and existing classification-maintenance jobs must
share the existing persisted daily budget accounting, extended with atomic
reservations where necessary. A second worker cannot obtain a separate quota.
Test crashes before/after enqueue, stage commit, apply and cursor advance,
simultaneous teardown/worker enqueue, and deletion during a provider call.
This stages new exchanges; it does not authorize historical backfill.

**Required tests:** all B5/B9 fixtures through the production adapter; live
worker/teardown wiring with a fake provider; malformed batches; source-evidence
fabrication; concurrent correction/forget while classification is running;
restart budgets/retries; no shadow prompt changes; no greeting cleanup; route
failure preserves voice and pending extraction. Include original recovery
idempotency tests without replaying the recovered production exchanges.

**Pass:** the real worker and provider-shadow runner share the tested classifier,
all original acceptance floors pass and implementation status says exactly
which stage is deployed. Real-memory enablement waits for GC24-09.

## 11. GC24-06 — Atlas loading, freshness and failure lifecycle

**Primary files:**
`macos/MortimerHost/Sources/MortimerHost/Display/KnowledgeAtlasView.swift`,
`Stores/AtlasStore.swift` under that same source root, the existing AdminAPI
client and `macos/MortimerHost/Tests/MortimerHostTests/KnowledgeAtlasTests.swift`.

- Keep the existing result/memory/architecture/plan/run projections and graph
  reader. Atlas is a projection, not another persistence or network owner.
- Move refresh ownership into the app-owned Atlas store. Maintain per-source
  `idle|loading|loaded|empty|failed` state, last-success timestamp and a bounded
  error category. Retain last-good cards with an explicit stale indicator on
  failure; distinguish no data from cannot load.
- Refresh on first activation, successful backend reconnect, relevant existing
  source-change events and explicit refresh. Coalesce simultaneous requests;
  permit at most one request per source and reject responses from an obsolete
  connection generation. No aggressive polling or new websocket client.
- Preserve the current bounded previews. Show available totals and a clear
  existing-panel/reader action for the remainder; do not imply 12 memories or
  eight runs are the whole collection. Make source-card actions use existing
  panel/navigation actions and the same voice/action registry. Do not invent
  a new graph data source.
- Add the refresh action to the shared registry and matching protocol fixtures
  only if absent; pointer and voice use the same idempotent coordinator action.

**Pass:** empty, partial failure, expired auth, reconnect, late response and
manual refresh tests; the Atlas displays available useful context without a
research result first; no duplicate fetch on display move or tab switching;
selection/pins survive refresh and previous graph/performance gates hold.

**2026-09-24 implementation progress:** `AtlasStore` owns asynchronous
per-source refresh tasks and generation guards; the Atlas exposes loading,
ready, empty, stale and unavailable states, preserves last-good cards on
failure, coalesces active refreshes, and refreshes after a backend reconnect.
The focused `KnowledgeAtlasTests` suite passed **7/7** at that snapshot. The
same-date headless visibility failures were subsequently rechecked and
classified in the [2026-09-25 fixture receipt](../acceptance/verified-gap-closure/GC24-06-headless-window-fixture-classification-2026-09-25.md).
They are historical evidence, not current failing assertions.

## 12. GC24-07 — Candidate configuration and regression

**Files:** existing launcher/config validation, console capability negotiation,
route-readiness scripts, test suites and acceptance runbook. Package with
`macos/MortimerHost/scripts/bundle.sh`, not the older MortimerShell build script.

1. Add an effective-capability preflight to the existing startup/readiness path.
   A layout-2 client connecting to a server with console/sharing gates disabled
   displays specific unsupported actions truthfully. It must not silently
   switch layout, enable a provider, or advertise a usable disabled action.
2. Record explicit candidate settings and separate memory/routing/sharing
   activation. Routing enablement must validate each affected workload; do not
   break confidential/local-only workloads by flipping a global flag before
   GC24-03/04 readiness. An unavailable workload is explicit, not paid fallback.
3. Use an isolated environment with locked dependencies. If `.venv` is absent,
   create it; do not replace another process's environment. Run from the Codex
   worktree above:

   ```sh
   UV_CACHE_DIR=/private/tmp/mortimer-gap-uv uv venv --python 3.12 .venv
   UV_CACHE_DIR=/private/tmp/mortimer-gap-uv uv pip sync --python .venv/bin/python requirements-lock.txt
   RUN_LIVE=0 .venv/bin/python -m pytest tests/unit tests/integration -q
   RUN_LIVE=0 .venv/bin/python -m pytest tests/evals/sub_agent_evals.py -q
   .venv/bin/python scripts/latency_probe.py --budget tests/fixtures/latency_sample.log
   swift test --package-path macos/JarvisKit
   swift test --package-path macos/MortimerHost
   git diff --check
   ```

   These are implementation-time commands, not a claim they ran when this
   plan was written. Keep offline tests credential-free; the test harness
   isolates vault/cost DB. Do not set `RUN_LIVE=1` to cure a skip. If a toolchain
   cache needs a writable path, configure a cache inside this worktree or
   temporary directory rather than relaxing test isolation.
4. Run the remaining existing CI checks applicable to the touched files,
   including policy/allowlist and web compatibility where applicable. Retain
   integration CI added after the pipeline regression; no skipping tests,
   shrinking eval denominators or deleting failing behavior to get green.
5. Preserve performance gates: existing stricter 33ms graph/frame limits;
   <=16.7ms p95 input work, <=200ms local navigation acknowledgment, and no
   >10% baseline regression. Use the original warm-up/three-measurement method.
   Run graph + panels + attachment + voice stress; no new audio underruns;
   after 20 open/close/upload/cancel cycles and 30 seconds idle, retained memory
   <=baseline+64MiB. A pre-existing breach stays a breach, not a new baseline
   that automatically passes.

**Pass:** exact candidate source/artifact/config, fresh scoped and whole-project
results with executed/failed/skipped counts, and no active unresolved regression.
Changing code after a result invalidates the affected result for that candidate.

## 13. GC24-08 — Remaining physical Mac acceptance

Start with the external monitor when available. Prior one-external-monitor
receipts count as historical evidence; obtain the missing instrumentation and
one current-candidate regression instead of repeating blind unplug loops.

1. **Display ownership:** one full result owner, one supporting stage, bounded
   one-to-four result tiles. Record result/parent IDs, windows, topology and
   fetch/subscription counts. Verify multiple research results, memory graph
   and a developer run with append-only sections. Verify common Glass settings.
2. **Recovery:** close/reopen supporting stage, disconnect/reconnect monitor,
   and separately interrupt/reconnect the backend/voice connection. Preserve
   result identity, selection, draft, pins and bounded window count. Network/
   audio reconnection is not equivalent to physical monitor reconnection.
3. **Topology:** real single/external and mirrored arrangements; three physical
   or OS-recognized displays when available. macOS Spaces alone are not a
   multi-display pass. If hardware is absent, record that case blocked with
   remaining owner/action, not skipped-as-passed or an invented completion date.
4. **Voice:** capture a real user request, actual Mortimer output speech and
   independent measured orb response. Verify connected/muted idle remains
   alive. Full answer appears once in results; brief captions stay in the
   conversation area; return-to-main keeps the same result. Repeat a voice
   command to prove no duplicate fetch/window creation.
5. **Sharing:** real text and image outward preview/copy/save/system picker,
   picker cancel/return and inward staged approval. Show destination/model,
   bounds/progress and cancellation; test reconnect/cleanup. Opening a picker
   does not prove delivery, and a live share to another person requires the
   user's chosen destination and send action.
6. **Accessibility/preservation:** all eight tabs, scroll header, persistent
   font sizing, keyboard focus, VoiceOver, reduced motion/transparency, small
   window and compact startup. Check the approved orb and graph appearance.
7. **Inherited audio/security gates:** carry forward earbud-removal rebuild
   churn, AirPods both ways, AirPods output with built-in mic, C8/P0/T1.3,
   Security V2–V6 and labeled speaker-gate effectiveness. Use their existing
   protocols and thresholds. Keep the speaker gate off until its gate passes.

The existing model-registry split decision row also remains explicitly open
until GC24-00 confirms its current disposition. This plan does not invent the
missing owner decision or treat model-access routing as equivalent closure.

**Pass:** dated exact-candidate receipts, redacted screenshots/accessibility
captures, correlated request/result IDs and event counts for every required
case. Fix a discovered fault in a bounded commit and rerun affected tests.
Missing hardware or user observation remains a named acceptance blocker.

## 14. GC24-09/10 — Pilots, release and rollback

### Model-access pilot

Start with public synthetic text on each approved route, then one selected
non-voice workload. Run identical fixtures/model quality requirements against
the baseline. Record cold/warm queue time, first useful output, total duration,
sequential calls, cancellation, failure category and billing source. Preserve
the original targets: local working acknowledgment <=250ms; short interactive
task median overhead <=1 second; >2 seconds additional p95 needs review before
changing defaults. Research/development use whole-task quality and completion
time, not a one-second limit on every call.

Prove simultaneous voice continuity and priority over background work. Move
tool workloads only after GC24-04's bridge capability passes. Document each
workload that remains API-based, including the voice loop and any unsupported
image/tool path. Subscription login does not mean all API expense is removed.

### Memory pilot

Take and verify a restorable database backup before production changes. Use
the existing vault in place. First rerun provider shadow through GC24-05's
production classifier on synthetic cases. Then one daily-driver day in shadow,
explicit preferences, and finally corroborated inferences, in that order.
Unknown stages fail closed. Record enabled/shadow/stage together.

Use the B5/B9 metric definitions and unchanged baseline fixture hashes. Require
no loss of explicit-preference use/relevant recall, improvement on previously
failing stale/interruptions cases, zero-error baselines still zero, p95 <=200ms
cache hit / <=2s bounded classification call, and no budget overrun. Capture
calls, latency, cost, queue state and privacy/scope/duplicate/stale-use events.
Review the first 20 real reversible decisions with Larry once as acceptance;
this is not an ongoing user classification task. Synthetic fixture rows do
not satisfy this review. Do not promote if the required evidence is absent.

Disable the new admission stage immediately on privacy, unauthorized scope,
duplicate, budget or stale-use regression. Preserve queued evidence and
existing memories; reverse only attributable revisions through the existing
undo path. Do not restore an old database over unrelated new user data as a
routine rollback.

### Final release

Run the existing full-profile independent sandbox verifier against the exact
candidate, including baseline and candidate identity. A unit-test run is not
an independent verifier receipt. Demonstrate layout rollback, routing/memory
disablement and executable rollback without deleting preferences or data.
Build/sign/package through the established host workflow; verify loaded app
and backend identity after promotion using GC24-00's checks.

Complete the separate five-day stable-candidate observation required by UI2-17.
A runtime code/config change starts a new candidate and observation period;
an evidence-only documentation edit does not change the executable candidate.
Record days actually observed, not elapsed time inferred from an old date.
Acceptance requiring the user's appearance/workflow judgment stays pending
until observed; the implementer cannot self-approve it.

**Final pass:** all applicable existing gates have current receipts; unresolved
hardware/provider/decision items are still visibly open. A subset can be
released under the existing feature gates, but neither this plan nor the
parent plans may be labeled fully complete while their requirements remain.

## 15. Evidence, handoff and bounded PRs

For every GC24 increment, append a dated handoff entry below and link the
existing feature status rows. Keep receipts in the existing acceptance
directories; never overwrite an older candidate's evidence. Each receipt must
include:

- Requirement IDs, test case IDs and exact expected/observed outcomes.
- Source commit and clean/dirty status; source fingerprint if uncommitted;
  build/artifact hash, runtime/config identity where applicable.
- OS/toolchain/provider-runtime versions; model/route/billing/capabilities;
  synthetic/live distinction and policy without secrets or protected payloads.
- Commands, fixtures, counts including denominators/failures/skips, timings,
  relevant screenshot/log references and CI/verifier URLs when available.
- What the evidence does **not** establish; remaining blocker and next action.

The next model must be able to determine what changed, where it was tested and
what is safe to do next without relying on this chat. After each increment,
update its checkbox only if its full pass criteria are satisfied; otherwise
record `implementation verified; live acceptance open` or the exact failure.

Use separate reviewable PRs for: reconciliation/housekeeping; execution
contract; privacy/call-site migration; subscription text isolation; tool
bridge/capability activation; production classifier; Atlas lifecycle; release
configuration/regression; acceptance/rollout evidence. Combine only tightly
dependent changes. Each PR states its base, affected contracts, tests, feature
gate state and rollback. Do not merge changes into Claude's worktree or push
directly to main. Rebase only this owned branch when coordinating incoming
work; reread changed contracts before resolving conflicts.

No blanket reapproval is needed for ordinary isolated implementation already
authorized. A new external transmission, provider/account limitation, missing
hardware interaction or changed product decision must be identified precisely;
do all independent preparation before seeking the user's action.

### Handoff log

- **2026-09-25 — GC24-02 opt-in streaming progress.** Added an explicit
  route capability for direct Anthropic streaming profiles, translated pinned
  Anthropic Messages stream text and tool-input events to OpenAI-shaped chunks,
  and added shared-boundary delta emission, compatibility collection,
  finish-marker validation and cancellation/error stream cleanup. Focused tests
  pass **125/125**, cross-caller tests **239/239**, and the Python
  unit/integration suite passes **2,828 passed, 4 skipped, 11 warnings, 2
  subtests**. No production caller consumes the stream yet; tool-result,
  artifact, complete agent-loop terminal ownership, late-write suppression and
  durable recovery remain open. See the
  [GC24-02 receipt](../acceptance/verified-gap-closure/GC24-02-execution-boundary-implementation-2026-09-24.md).

- **2026-09-24 — GC24-02 queued-event cancellation progress.** Moved
  `queued` event delivery inside the execution boundary's guarded timeout so
  cancellation while an asynchronous lifecycle observer handles the initial
  event now emits one sequenced `cancelled` terminal event. The focused
  `test_model_execution.py` suite passes **30 tests**, including the regression
  case. This closes only the pre-start observer-cancellation hole. Streaming,
  artifact/tool-result events, whole tool-loop terminal ownership, downstream
  cancellation and durable reconciliation remain open. See the updated
  [GC24-02 receipt](../acceptance/verified-gap-closure/GC24-02-execution-boundary-implementation-2026-09-24.md).

- **2026-09-24 — GC24-06 Atlas lifecycle progress.** The authenticated Atlas
  source requests are now coordinated by the app-owned `AtlasStore`; a
  per-source health strip distinguishes loading, success, empty, stale and
  unavailable; last-good cards survive failed refresh; explicit retry and
  reconnect refresh are wired; generations reject obsolete responses. The
  focused native suite passes **7/7** including store-owned success and
  stale-on-failure cases. At that snapshot the full MortimerHost run reported
  eight headless WindowServer visibility assertions; these are historical
  results and are superseded by the following fixture-classification receipt.
  GC24-06 stays open for live/auth/reconnect,
  accessibility, source-change, window-move, graph/performance and candidate
  evidence. See the
  [GC24-06 receipt](../acceptance/verified-gap-closure/GC24-06-atlas-refresh-2026-09-24.md).

- **2026-09-25 — GC24-06 headless fixture classification and host regression.**
  The XCTest process exposes no `NSScreen`, so actual-window visibility and
  on-screen graph timing were not valid in this runner. Only three
  WindowServer-dependent tests and the graph benchmark now skip when their
  explicit display precondition is absent; graph-layer dirtiness is checked
  after render-server completion on a real display. Screen unlock is injected
  for deterministic unit testing while production retains its distributed
  notification observer. Focused Atlas tests pass **10/10**; focused fixture,
  placement and graph tests pass **14** with **5** documented skips; full
  MortimerHost passes **265** with **7 skips, 0 failures**. Physical monitor,
  real unlock, visible-window, and on-screen p95 acceptance remain open. See
  the [fixture receipt](../acceptance/verified-gap-closure/GC24-06-headless-window-fixture-classification-2026-09-25.md).

- **2026-09-24 — GC24-03 council workload-floor progress.** Council and
  planning now derive privacy from the static configured workload policy
  (route preferences cannot lower the data-classification floor), combine any
  stricter caller label, and carry policy through pre-provider `too_small`
  persistence. Focused council/planning/CLI suites pass **78 tests**; full
  locked unit/integration suite passes **2,816 passed, 4 skipped, 11 warnings,
  2 subtests passed**. Negative checks cover rejection before client creation,
  weaker caller labels, and SQLite redaction. This closes only this council
  slice; full GC24-03 inventory/canaries remain open. See the
  [council workload-floor receipt](../acceptance/verified-gap-closure/GC24-03-council-workload-floor-2026-09-24.md).
- **2026-09-24 — GC24-03 sensitive SubAgent policy progress.** Routed
  SubAgent requests now combine resolved-route privacy with the inherited
  sensitive-turn signal via strictest-policy, so an approved-external route
  cannot receive that context. The full locked unit/integration suite passes
  **2,813 passed, 4 skipped, 2 subtests passed**; SubAgent eval, call-site
  audit, and latency fixture also pass. This closes one negative transmission
  path only. Other caller sources, supervisor/speech/display/export/log
  sinks, and direct-mode callers remain unaudited and unverified; GC24-03
  remains open. See the
  [GC24-03 progress receipt](../acceptance/verified-gap-closure/GC24-03-sensitive-routed-subagent-2026-09-24.md).
- **2026-09-24 — GC24-02 lifecycle and replay-guard progress.** The execution
  boundary now emits policy-carrying `progress` events at provider request and
  response receipt. It rejects reused tool-call IDs in a completed history and
  rejects provider responses that reuse any call ID from that history. The
  full locked unit/integration suite passes **2,812 passed, 4 skipped, 2
  subtests passed**; the 13-case SubAgent eval, 25-entry call-site audit (zero
  review-required), latency probe, and seven plan-manifest tests pass. This
  does not close GC24-02: token streaming, artifacts, whole-tool-loop result
  events/terminal ownership, cancellation-safe downstream writes, and durable
  crash/retry reconciliation remain open. See the
  [GC24-02 implementation receipt](../acceptance/verified-gap-closure/GC24-02-execution-boundary-implementation-2026-09-24.md).
- **2026-09-24 — GC24-02 implementation update.** In the dirty isolated tree,
  planner cancellation/race handling and shared-boundary migrations for planner,
  council, shared-content vision, and screen vision are implemented. The
  connected vision path still captures its route at connection setup; resolve
  and bind the route per task before closing that subrequirement. The exact
  dirty-tree run passes 2,810 unit/integration tests, with 4 skips and 2
  subtests; SubAgent eval passes 13 cases; call-site audit v2 reports 25
  entries and zero review-required; the fixture latency probe passes. Full
  lifecycle streaming, downstream cancellation, late-write suppression,
  idempotent tool reconciliation, sink-by-sink privacy proof, live Mac/provider
  acceptance, and later closure gates remain open. Details and commands:
  [GC24-02 implementation receipt](../acceptance/verified-gap-closure/GC24-02-execution-boundary-implementation-2026-09-24.md).
  This progress does not close GC24-02 or authorize deployment.
- **2026-09-24 — Planning only, Codex.** Created this execution addendum against
  `96aaf7a` in `codex/isolated-20260924`. All GC24 work remains open. No runtime
  behavior, feature flag, credential, database, provider route or deployment
  changed. Next action: GC24-00, followed by status reconciliation and the
  execution boundary; Atlas work can proceed independently after baseline.
- **2026-09-25 — Baseline refresh.** Main advanced to `8bd5e7e` (#89), which
  changes only `WindowVisibilityTests.swift`; Claude's matching worktree is
  clean at that revision. The inspected-source fingerprint above is updated;
  [GC24-00 receipt](../acceptance/verified-gap-closure/GC24-00-baseline-2026-09-25.md)
  records the runtime inspection limit and remaining unknowns.
- **2026-09-25 — Concurrent PR #90 merged.** Current inspected main is
  `4acb4dc`; its accepted Crystal option A shell replaces the former shell
  while preserving the orb contract. The updated baseline and remaining live
  Crystal checks are recorded in
  [GC24-00 follow-up](../acceptance/verified-gap-closure/GC24-00-main-refresh-2026-09-25.md).
- **Document validation:** all plan links resolve, the eleven closure IDs are
  unique and ordered, code fences/whitespace pass, and all seven existing
  standalone `test_plan_manifests.py` assertions pass by direct invocation.
  This is documentation validation, not a pytest application-suite run or a
  runtime acceptance receipt.
- **2026-09-25 — GC24-02 implementation slice.** The unused execution boundary
  now validates ordered context, ephemeral text/image attachments, source
  policies, workload/capability matches and a cancellable deadline; snapshots
  resolved workload priority; enforces two-slot interactive/background
  admission; validates bounded output and caller-provided tool schemas; returns
  schema-checked tool requests without executing them; and reports ordered
  policy-carrying lifecycle events with known usage metadata. The 325 focused
  execution, ledger, reporting, and migrated-caller pytest cases pass under the
  isolated targeted dependency set; the full project suite remains unrun.
  `kb_digest` and
  procedure description, per-exchange extraction, whole-session memory
  fold-in, both memory-sweep calls, and the delegated-agent tool loop now use
  this boundary when model routing is enabled; the usage ledger separately
  records unknown counts,
  billing source, route, duration and response ID. A real SQLite exercise
  passed. See the
  [GC24-02 progress receipt](../acceptance/verified-gap-closure/GC24-02-execution-input-progress-2026-09-25.md).
  This does not close GC24-02: three production migration targets remain
  (planner, mixed voice/vision pipeline, and council), with
  the supervisor voice path explicitly exempt. Streaming/tool-result/artifact
  events, downstream cancellation, idempotent
  tool reconciliation, locked-environment verification and prevention of late
  durable writes remain.
- **2026-09-25 — GC24-02 caller audit and SubAgent cancellation increment.**
  The current call-site audit now reports **26/26 covered, zero review-required,
  secret-free**, including planner, mixed vision, council and screen paths;
  this supersedes the migration-target sentence in the earlier progress note
  above. Cancellation during an active SubAgent tool call now finalizes its
  run-log record as `cancelled`, propagates to the tool coroutine, prevents a
  second provider round, and emits no `agent_done` success event. Focused
  run-log/SubAgent/integration tests pass **92**; the full Python
  unit/integration suite passes **2,870**, with **4 skipped**, **11 warnings**,
  and **2 subtests**. The new evidence is in the
  [GC24-02 cancellation receipt](../acceptance/verified-gap-closure/GC24-02-cancellation-terminal-2026-09-25.md).
  This closes only the run-log cancellation slice; production text-delta
  consumption, exactly-one terminal across the entire provider/tool loop,
  late side-effect suppression, and mutating-tool reconciliation remain open.
- **2026-09-25 — GC24-03 MCP exception-log redaction.** `SkillRegistry.call()`
  now logs only a bounded exception-class code instead of raw MCP exception
  text. A canary test confirms the exception message cannot appear in logs;
  the tool's existing failure-result contract is preserved. Focused
  registry/run-log/SubAgent tests pass **104**, and the full Python
  unit/integration suite passes **2,871**, with **4 skipped**, **11 warnings**,
  and **2 subtests**. See the
  [GC24-03 receipt](../acceptance/verified-gap-closure/GC24-03-mcp-exception-log-redaction-2026-09-25.md).
  This closes one logging sink only; all other source-to-sink checks remain.
- **2026-09-25 — GC24-03 watcher log redaction.** Research, plan, progress,
  and reminder watchers now log bounded exception categories instead of raw
  exception messages; malformed reminder responses are no longer written to
  logs. Content-canary tests cover all four watcher paths. Focused watcher
  tests pass **48**, and the full Python unit/integration suite passes
  **2,871**, with **4 skipped**, **11 warnings**, and **2 subtests**. See the
  [GC24-03 watcher receipt](../acceptance/verified-gap-closure/GC24-03-watcher-log-redaction-2026-09-25.md).
  This closes only these watcher log paths; GC24-03 remains open.
- **2026-09-25 — GC24-03 clipboard and command-title log redaction.** The
  clipboard sidecar warning now omits its path and raw exception; the
  `show_commands` tool no longer logs user-authored titles and reports arm
  exceptions by bounded class only. Tests invoke the registered clipboard
  tool and exercise the command handoff with canary strings. The combined
  clipboard/watcher/pipeline suite passes **107**, and the full Python
  unit/integration suite passes **2,873**, with **4 skipped**, **11 warnings**,
  and **2 subtests**. See the
  [GC24-03 clipboard receipt](../acceptance/verified-gap-closure/GC24-03-clipboard-log-redaction-2026-09-25.md).
  This closes only those logging paths; GC24-03 remains open.
- **2026-09-25 — GC24-03 agent/delegation/event/findings log redaction.**
  SubAgent matcher and observer failures, specialist findings reads,
  upgrade-agent callbacks, and supervisor event callbacks now avoid logging
  raw exception text, tracebacks, agent-supplied paths, or untrusted failure
  reason text. Canary tests cover the bounded paths. The focused suite passes
  **165**; the full Python unit/integration suite passes **2,877**, with **4
  skipped**, **11 warnings**, and **2 subtests**. Ruff `F`/`I` and
  `git diff --check` pass. See the
  [GC24-03 receipt](../acceptance/verified-gap-closure/GC24-03-agent-event-findings-log-redaction-2026-09-25.md).
  This closes only these selected log paths; GC24-03 remains open.
- **2026-09-25 — GC24-03 admin job log redaction.** Admin self-edit,
  app-build, research, planning, council, model-route status, and selected
  read-only status failures no longer log user prompts, generated summaries,
  research URLs, publication notices, or raw exception text. Asynchronous job
  error fields use bounded exception classes as well. Bounded state/count
  signals remain. Successful local task results remain visible and are an open
  response/display sink.
  Focused admin tests pass **129**; the full Python unit/integration suite
  passes **2,878**, with **4 skipped**, **11 warnings**, and **2 subtests**.
  See the [GC24-03 admin-log/status receipt](../acceptance/verified-gap-closure/GC24-03-admin-job-log-and-status-redaction-2026-09-25.md).
  This closes only selected admin logging paths; GC24-03 remains open.
- **2026-09-25 — GC24-03 memory diagnostic redaction.** Memory-context
  filtering, write-rejection, extraction, sweep, and watcher logs now use
  aggregate counts, bounded policy reasons, and bounded exception classes;
  memory keys, session IDs, promoted fact names, raw exception text, and
  tracebacks are omitted. Tier-cap observability and drop counters remain.
  Focused memory/remember/sweep/watcher tests pass **158**; the full Python
  unit/integration suite passes **2,883**,
  with **4 skipped**, **11 warnings**, and **2 subtests**. Ruff `F` and
  `git diff --check` pass. See the
  [GC24-03 memory-log receipt](../acceptance/verified-gap-closure/GC24-03-memory-log-redaction-2026-09-25.md).
  Other memory maintenance logs and all non-memory source-to-sink gaps remain.
- **2026-09-25 — GC24-02 delegate terminal lifecycle.** The existing
  delegate-card event owner now emits exactly one terminal event for normal
  completion, unexpected detached-run failure, and session-shutdown
  cancellation. Status-observer failures no longer change task execution;
  late-delivered exceptions contain only a bounded error class. Focused
  delegate tests pass **56**; the full Python unit/integration suite passes
  **2,887**, with **4 skipped**, **11 warnings**, and **2 subtests**. Ruff
  `F` and `git diff --check` pass. See the
  [GC24-02 delegate lifecycle receipt](../acceptance/verified-gap-closure/GC24-02-delegate-terminal-lifecycle-2026-09-25.md).
  The full provider/tool lifecycle and late-side-effect suppression remain
  open.
- **2026-09-25 — GC24-03 protected specialist-result handoff.** A confidential
  or local-only SubAgent now requires an awaited local result sink and returns
  only a fixed status plus opaque reference to its caller. A missing sink is
  rejected before model-client construction; route clients for protected
  workloads are deferred until route and sink checks pass. Static workload
  privacy is combined with route and sensitive-turn policy, so a user route
  preference cannot lower it. Protected activity, logs, result presentation,
  and copy/share/export paths receive bounded handling; native copy/share/
  export actions are rejected. The full unit/integration suite passes
  **2,867 passed, 4 skipped, 11 warnings, 2 subtests**; focused native
  share/action tests pass **19/19**. The handoff is one covered path only.
  Full source-to-sink inventory, verified confidential route capability, and
  direct-mode/provider-sink proofs remain open. See the
  [protected local-result receipt](../acceptance/verified-gap-closure/GC24-03-protected-local-result-handoff-2026-09-25.md).
- **2026-09-25 — GC24-02 SubAgent cancellation-result suppression.** The
  multi-round SubAgent loop now detects a cancellation request even when a
  provider or tool adapter catches cancellation and returns a value. It
  suppresses that value before usage/run-log writes, tool-result events, or a
  subsequent provider round. The focused SubAgent suite passes **62**; the
  combined SubAgent/run-log/integration/bot-wiring suites pass **128**; the
  full Python unit/integration suite passes **2,889**, with **4 skipped**,
  **11 warnings**, and **2 subtests**. Ruff `F`/`I`, plan manifest (**7/7**),
  and `git diff --check` pass. See the
  [GC24-02 cancellation-suppression receipt](../acceptance/verified-gap-closure/GC24-02-subagent-cancellation-suppression-2026-09-25.md).
  This does not roll back a mutation already performed inside a tool or
  reconcile unknown outcomes; those and the other provider/tool caller
  families remain open.
- **2026-09-25 — GC24-02 direct-mode tool-call identity replay guard.** Routed
  SubAgent and self-edit planner calls already reject a provider tool-call ID
  present in request history. Direct-mode SubAgent and self-edit planner calls
  now keep an ID set across provider rounds and stop before dispatch if a
  batch contains a missing, malformed, overlong, or reused identity. The
  end-to-end app-build fixture now supplies distinct IDs across rounds.
  Focused SubAgent tests pass **63**, and combined SubAgent/UpgradeAgent/
  AppBuildAgent suites pass **115**; the full Python unit/integration suite
  passes **2,891**, with **4 skipped**, **11 warnings**, and **2 subtests**.
  Ruff `F`/`I`, plan manifest (**7/7**), and
  `git diff --check` pass. See the
  [GC24-02 tool-call replay receipt](../acceptance/verified-gap-closure/GC24-02-tool-call-identity-replay-2026-09-25.md).
  The existing startup path orphans stale runs rather than resuming them, but
  durable unknown-mutation receipts, rollback, and cross-caller replay proof
  remain open.
- **2026-09-25 — GC24-02 live Supervisor tool-call identity guard.** The
  Supervisor now validates the complete provider tool-call batch before
  dispatch. Empty, oversized, duplicate-in-batch, or reused-across-round IDs
  fail closed with the existing bounded response; an invalid batch dispatches
  no tools and logs no IDs or arguments. Focused Supervisor/orchestrator tests
  pass **36**, and the full Python unit/integration suite passes **2,894**,
  with **4 skipped**, **11 warnings**, and **2 subtests**. Ruff `F`/`I`,
  `git diff --check`, and changed-document relative-link checks pass. See the
  [Supervisor replay receipt](../acceptance/verified-gap-closure/GC24-02-supervisor-tool-call-identity-replay-2026-09-25.md).
  This closes only same-turn ID replay for the Supervisor. Production delta
  consumption, full-loop terminal ownership, cancellation and late-write
  suppression, durable unknown-mutation reconciliation, and remaining callers
  stay open.
- **2026-09-25 — GC24-02 verify the existing voice result stream.** Source
  tracing confirmed the live RTVI `bot-llm-text` path already appends token
  chunks to one `JarvisClient.transcript` entry; `AppMessageRouter` forwards
  transcript updates to the existing `ResponseResultRouter`, which retains
  one result identity. JarvisKit inbound-frame tests pass **2/2**, a new
  stub-transport integration through `AppMessageRouter` and the workspace
  passes **1/1**, and MortimerHost result-router tests pass **7/7**. This
  corrects the earlier broad claim that no production response consumer
  exists. The integrated test uses a stub transport, not the running backend
  or installed Mac candidate; that live journey remains open. Generic
  shared-execution `ModelExecutionEvent` deltas still lack a native consumer.
  See the [voice response-stream
  receipt](../acceptance/verified-gap-closure/GC24-02-existing-voice-response-stream-path-2026-09-25.md).
- **2026-09-25 — GC24-02 unknown tool outcome observability.** Agent-event
  migration 0028 stores provider tool-call identity; SubAgent cancellation
  after tool dispatch records a metadata-only unknown-outcome event; run
  details, CLI, and MCP expose calls without a correlated result. The focused
  migration/runlog/SubAgent/MCP/e2e suite passes **124**; the full Python
  unit/integration suite passes **2,917**, with **4 skipped**, **11
  warnings**, and **2 subtests**. Ruff `F`/`I` and `git diff --check` pass.
  See the [unknown-outcome observability
  receipt](../acceptance/verified-gap-closure/GC24-02-unknown-tool-outcome-observability-2026-09-25.md).
  This is an operator reconciliation signal only. Cross-request action
  idempotency/reconciliation across new provider IDs, mutation rollback, and
  other caller families remain open; this does not close GC24-02.
- **2026-09-25 — GC24-02 direct Supervisor tool outcome visibility.** The live
  Pipecat tool adapter now creates a sensitive run-log record for each direct
  Supervisor tool, correlates provider call IDs, and scopes nested MCP events
  to that run. Normal outcomes are persisted before the Pipecat callback;
  cancellation and post-dispatch exceptions write metadata-only unknown
  outcomes, and cancellation suppresses the late callback. Durable SQLite and
  JSONL tests prove arguments, result text, and exception text are redacted;
  cancellation-swallowing and disabled-logging cases are covered. The focused
  Supervisor/runlog/MCP/SubAgent suite passes **116**; focused pipeline wiring
  tests pass **73**; the full Python unit/integration suite passes **2,923**,
  with **4 skipped**, **11 warnings**, and **2 subtests**. Ruff `F`/`I` and
  `git diff --check` pass. See the [direct Supervisor runlog
  receipt](../acceptance/verified-gap-closure/GC24-02-supervisor-direct-tool-runlog-2026-09-25.md).
  This closes only direct-tool outcome visibility. Unknown mutations are not
  reconciled or made idempotent; other callers and live-candidate acceptance
  remain open.
- **2026-09-25 — GC24-02 run-scoped planning-start claim.** Migration 0029
  adds a tenant-scoped, payload-free one-shot claim for mcp-selfedit
  plan_start, keyed by the existing injected SubAgent run ID. A retry with a
  different provider tool-call ID in that same run returns its prior
  content-free status and launches no duplicate job. Status can be queried by
  action_run_id after the singleton live-job slot changes; an evicted active
  state is reported as unknown and must not be retried automatically.
  Focused DB/admin/MCP/manifest/tenant tests pass **126**; the full Python
  unit/integration suite passes **2,930**, with **4 skipped**, **11 warnings**,
  and **2 subtests**. See the [run-scoped plan-start claim
  receipt](../acceptance/verified-gap-closure/GC24-02-plan-start-run-scoped-claim-2026-09-25.md).
  This does not cover a fresh SubAgent run ID, direct Supervisor handlers, or
  other mutating tools, so cross-run action reconciliation remains open.

## 2026-09-28 current-main integration checkpoint

Checkpoint `44cb8ae` preserves the isolated implementation before merging main
`2e6f769`. Main's workflow/status, supervised registry and notices behavior
are being retained alongside execution/privacy/Skills work. Migration IDs
were reserved and renumbered in ROADMAP before use; a read-only production
check found only main's IDs through 0027. The main-schema upgrade regression
preserves existing notices and is idempotent (20 DB tests passed).

Twenty conflict files now have merged resolutions staged. Memory pipeline
semantics await CX-07's decision, and Swift navigation awaits the requested
Skills placement choice. The merge cannot be committed until those conflicts
are resolved. Independent merged-tree checks: 475 workflow/key-health/Skills
validation tests, 79 auth/bind/service-token tests, 70 web-tool tests, and 10
native packaging tests passed. These are targeted checks, not full acceptance.
Auth remains dormant unless explicitly enabled; the current route inventory
has 79 sidecar decorators, including all ten main workflow/status routes. Its
whole-app auth test must still run after the memory imports are resolved.

## Appendix — archived overlapping gap plans (2026-09-28)

The following twelve documents were overlapping execution indexes identified
by [review F7](../reviews/CROSS_SYSTEM_PLAN_EVAL_2026-09-27.md). Their complete
original bodies are preserved under `docs/archive/`; each former `docs/plans/`
path remains as a redirect stub. These links map historic scope to the current
GC24 topics for retrieval only. A topic's appearance here is not evidence that
its implementation, verification, deployment, or acceptance gate is complete.
Use this plan and `ROADMAP.md` for current scope and status.

| Archived document | Related GC24 topics (topic names in §4) |
| --- | --- |
| [Newly verified gaps](../archive/MORTIMER_NEWLY_VERIFIED_GAPS_IMPLEMENTATION_PLAN.md) | GC24-00 baseline; 01 status; 02 execution; 03 privacy; 04 routes; 05 memory; 06 Atlas; 07 candidate; 08 physical; 09 pilots; 10 release |
| [Remaining gaps implementation](../archive/MORTIMER_REMAINING_GAPS_IMPLEMENTATION_PLAN.md) | GC24-00 baseline; 01 status; 02 execution; 03 privacy; 04 routes; 05 memory; 06 Atlas; 07 candidate; 08 physical; 09 pilots |
| [Gaps implementation, 2026-09-25](../archive/MORTIMER_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md) | GC24-00 baseline; 02 execution; 03 privacy; 04 routes; 05 memory; 06 Atlas; 07 candidate |
| [Review gaps, 2026-09-25](../archive/MORTIMER_REVIEW_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md) | GC24-00 baseline; 02 execution; 03 privacy; 04 routes; 05 memory; 06 Atlas; 07 candidate |
| [Reviewed gaps, 2026-09-25](../archive/MORTIMER_REVIEWED_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md) | GC24-00 baseline; 02 execution; 03 privacy; 04 routes; 05 memory; 06 Atlas; 07 candidate |
| [Post-review gap closure, 2026-09-25](../archive/MORTIMER_POST_REVIEW_GAP_CLOSURE_PLAN_2026-09-25.md) | GC24-00 baseline; 02 execution; 03 privacy; 04 routes; 05 memory; 06 Atlas; 07 candidate |
| [Implementation gaps execution, 2026-09-25](../archive/MORTIMER_IMPLEMENTATION_GAPS_EXECUTION_PLAN_2026-09-25.md) | GC24-00 baseline; 02 execution; 03 privacy; 04 routes; 05 memory; 06 Atlas; 07 candidate |
| [Remaining gaps execution, 2026-09-25](../archive/MORTIMER_REMAINING_GAPS_EXECUTION_PLAN_2026-09-25.md) | GC24-00 baseline; 02 execution; 03 privacy; 04 routes; 05 memory; 06 Atlas; 07 candidate |
| [Fresh review implementation, 2026-09-25](../archive/MORTIMER_FRESH_REVIEW_IMPLEMENTATION_PLAN_2026-09-25.md) | GC24-00 baseline; 02 execution; 03 privacy; 04 routes; 05 memory; 06 Atlas; 07 candidate |
| [Current review gaps, 2026-09-25](../archive/MORTIMER_CURRENT_REVIEW_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md) | GC24-02 execution; 03 privacy; 04 routes; 05 memory; 06 Atlas; 07 candidate |
| [Next gaps, 2026-09-25](../archive/MORTIMER_NEXT_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md) | GC24-02 execution; 03 privacy; 04 routes; 05 memory; 06 Atlas; 07 candidate |
| [Model-neutral gap implementation, 2026-09-25](../archive/MORTIMER_MODEL_NEUTRAL_GAP_IMPLEMENTATION_PLAN_2026-09-25.md) | GC24-02 execution; 03 privacy; 04 routes; 05 memory; 06 Atlas; 07 candidate |

The archived versions preserve their original proposed order, requirements,
and historical evidence. Where that evidence describes a test or prior
observation, it remains historical; consult each current GC24 row and its
acceptance record before treating any gate as satisfied.

## 2026-09-28 approved merge decisions implemented/in progress

Larry approved the memory sequence (echo filtering → durable classification/
admission → saved memory → automatic contradiction settlement), assigned its
integration to Codex, and approved separate Skills navigation beside Workflows.
Those merge resolutions are underway. CX-12's three original Anthropic
`streaming: true` flags are restored, with the split-file digest updated to the
exact output of the lossless migration renderer. No model identity, credential,
access route or voice setting changed.

After memory modules parsed, all 73 whole-app auth, architecture endpoint and
registry-split tests passed. This includes runtime enumeration and unauthorized
requests against all 79 sidecar routes. The registry scan found the Skills
evaluation CLI naming the deleted legacy registry; it now uses the shared
`registry_source` resolver. Its 45 budget/review tests pass without live calls.
Full merged Python and native acceptance still remain open.

### Final integration checkpoint and provenance correction

All 31 merge conflicts are resolved. The approved memory sequence passes 333
focused tests; exact-once supervisor dispatch survives a voice retry. Broad
Python integration: 4,851 pass, four skipped, two outstanding human deny-list
failures. JarvisKit: 219/zero failures. Host: 372 executed/seven skips/zero
failures. Logs are in the main-integration-2026-09-28 Skills receipts.

The earlier description of CX-12 as main losing streaming flags was incorrect.
Those flags existed in Codex's pre-merge live registry; Git's rename merge
carried them into main's historical YAML fixture instead of its new live pool.
Both main historical snapshots are now unchanged, the approved flags exist in
the live profile pool, and an explicit overlay test proves all other fields
stay equal. The registry suite passes 59 with three appropriate historical
byte-snapshot skips. No acceptance criterion was relaxed.

Human-only protection entries, live provider comparison and review, physical
displays/accessibility/voice, soak/latency and exact release acceptance remain
open. No deployment or runtime activation occurred.


### 2026-09-28 — staged Mac deployment completed

PR #96 merged as `539f8f6`; all GitHub workflows passed. DEPLOY-MAIN then
verified that exact commit: JarvisKit 219 tests/zero failures, MortimerHost
372 tests/seven environment skips/zero failures, Python 4,860 passes/seven
skips/two subtests passed. Release measurements: Skills selection-to-layout
p95 14.480 ms wide / 7.911 ms compact; crystal orb p50/p95 4.841/13.370 ms
versus legacy p50 4.833 ms. All original performance gates pass.

At 20:19 EDT the script backed up databases, code and the prior app, installed
and opened the production app, and restarted vault/bot/extractor/admin/costs.
Production HEAD and bundle revision both equal `539f8f6`; all six processes
were independently rechecked alive with the intended production paths.
Admin/vault returned HTTP 200; bot returned the expected 307. The deployment
receipt reports `deployed` with no problems. Database migrations through
`0036_skill_step_check_receipts` are present (0035 remains reserved).

Receipt: `docs/acceptance/skills-workspace/receipts/rendering-performance-2026-09-28/deployment-receipt.json`.
Local rollback: `~/MortimerRollback/release-539f8f6-20260928-201417/ROLLBACK.sh`.
This closes staged source deployment, not live feature acceptance or activation.
No runtime feature flags or provider routes were deliberately changed by this
operation. Remote enabled-mode acceptance, provider/VM/voice/display/accessibility
and plan-specific activation/rollback gates remain open where previously open.


### 2026-09-28 — repeated WS-01 integration instruction reconciled

Fetched main and read its AGENTS/ROADMAP; current work was already committed
and merge returned already up to date. The former conflicts are integrated
in deployed `539f8f6`, with both workflow/status and Codex privacy/memory changes
preserved. ROADMAP §3 now records the reserved migration names as applied,
not pending renumbering. No applied migration was renamed or replayed.
Focused R1/database/watcher checks passed 140 tests; the exact merged-release
full-suite and deployment receipt above remain the release evidence.
