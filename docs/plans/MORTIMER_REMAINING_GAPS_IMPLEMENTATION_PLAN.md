# Mortimer — Remaining Gaps Implementation Plan

**Purpose:** A model-agnostic execution sequence for closing the verified gaps without redesigning accepted behavior or weakening security, privacy, or release gates.

**Source baseline:** `4acb4dc2827f292f1236155e3c445d4ec4e9e5a0` (main, PR #90).  
**Implementation worktree:** `codex/isolated-20260924`, based on `977f50b` plus uncommitted work.  
**Plan reconciliation:** 2026-09-24 against the current isolated worktree.  
**Acceptance authority:** [Verified Gap Closure](MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md), [Model Use Enhancements](MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md), [Automatic Memory Consolidation](MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md), [Command Console and Knowledge Atlas](MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md), [Architecture](../ARCHITECTURE.md), and the existing acceptance runbook.

**Model-ready supplement:** [Newly Verified Gaps Implementation Plan](MORTIMER_NEWLY_VERIFIED_GAPS_IMPLEMENTATION_PLAN.md) restates the ordered work, locked decisions, per-phase tests and handoff requirements for a model taking over implementation. The Verified Gap Closure plan remains the acceptance authority.

**Current-tree refresh (2026-09-25):** use [Current Verified Gaps Implementation Plan](MORTIMER_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md) for the latest code-audit state and next steps. It supersedes stale next-action statements here when the current isolated tree has already advanced; the linked authority documents still control acceptance.

**Use:** This is the model-neutral implementation sequence for the remaining
verified gaps. Each phase states the existing owner, invariants, required
tests, and evidence needed to close it. Implementers must inspect the current
tree and linked authority documents before each slice; this plan is not
permission to redesign accepted behavior.

This document orders the remaining work. It does not replace the linked specifications, schemas, thresholds, or protocols. Source changes and tests are not proof of merge, deployment, or live acceptance.

## Fixed decisions

- Keep Command Console/layout 2, compact Conversation startup, all eight sidecar tabs, and the accepted atom/comet orb. Full answers belong in the response/results area; Conversation keeps brief live captions. One request has one result identity and updates append to it.
- Keep one app-owned action coordinator, workspace, result-placement owner, model execution boundary, and SQLite memory store. Supporting displays share one bounded stage; they do not create duplicate requests or nested result windows.
- Pointer, keyboard, and voice use the same validated action path. Preserve Haiku's existing supervisor role and current STT/TTS/audio transport; this plan does not migrate the live voice loop.
- Keep model identity, route, workload, privacy, and billing source separate. Never silently substitute a model/route, weaken privacy, treat unknown usage as zero, or automatically retry a mutating tool.
- Use official provider-managed subscription sign-in. API secrets stay in the existing Mac vault; never copy credentials or OAuth tokens into the repo, worktree, logs, or readiness output.
- Ordinary memory classification remains quiet and automatic. No recurring user cleanup/classification prompts, new memory database, bulk historical replay, or replacement of the memory system.
- Self-edit stays in the existing isolated sandbox with PR approval as its boundary. Preview speech continues to start sandbox work.
- Do not edit the accepted orb renderer, revive removed wave paths/controls, add another console, invent local-model infrastructure, or expand into unrelated roadmap work.

When documents conflict, follow the linked authoritative specification and record the discrepancy before proceeding. Do not guess at architecture.

## Verified position and remaining gaps

The selected interface and most console, response ownership, routing, and automatic-memory foundations exist. The current installed executable, backend revision, and effective feature gates still need exact-candidate verification.

The current isolated tree now routes the upgrade planner, council proposer/judge/planning/shadow, delegated-agent tool loop, and shared-content/screen vision through the shared execution boundary when routing is enabled. Planner cancellation is translated into its structured cancelled result, including the race where provider completion competes with cancellation. Shared-content route selection is per offer, disclosed before consent, and bound to that approved batch at execution. The boundary emits provider-request/response progress and rejects reused tool-call IDs in a validated history or new response. Sensitive-turn policy now tightens routed SubAgent requests before transmission. The supervisor voice route remains an explicit exception. The full locked unit/integration suite, SubAgent eval, and latency probe have passed on this dirty tree; this is not merge, Mac, or live-provider acceptance. Token streaming, artifact/tool-result lifecycle, downstream cancellation, late-write prevention, durable retry reconciliation, the remaining privacy sinks, and all later release gates remain open.

Other open gaps: end-to-end policy at every transmission/result sink; proven subscription/SAYGM capabilities; production memory admission; Atlas freshness and failure handling; candidate regression; remaining physical Mac journeys; and staged pilots, independent verification, rollback, and release evidence. Use the linked status documents for current row states. Historical receipts are not current-candidate proof.

## Execution order

Use the isolated worktree. Before each phase, inspect current source and merged work so changes are not recreated. Keep each caller family in a bounded, reviewable commit. Update linked statuses and dated receipts with exact commit, commands, pass/fail/skip counts, and remaining blockers. Separate **implemented**, **merged**, **deployed**, **verified**, and **accepted**.

### 0. Reconcile source, runtime, and ownership (GC24-00/01)

Record branch/commit/dirty state, remote main, sibling worktrees, and concurrent Claude changes. Map each open requirement to source, tests, receipts, and remaining proof. Inspect the actual candidate executable/backend process and effective non-secret gates when the Mac is available. Reconcile ambiguous IDs and duplicate ownership only as narrowly specified by GC24-01.

Never reset shared branches or overwrite concurrent changes. Do not dump process environments, vault contents, authenticated payloads, or secrets. If runtime inspection is unavailable, continue source work and mark runtime and deployment unverified.

**Pass:** exact baseline and one-to-one requirement map; unknowns and missing hardware/provider evidence are named; no writes outside the isolated tree.

### 1. Finish the execution boundary (GC24-02)

1. Review and validate current delegated-agent context/tool-history support. Mortimer's registered tool registry remains the only source and executor; validate arguments against its current schema.
2. Migrate planner using its existing workload profile, prompt, parameters, and output semantics. Any sync adapter must call the same boundary and must not create another orchestrator or change route selection.
3. Council proposer/judge/planning/shadow calls now cross the boundary in this worktree when routing is enabled. Validate both routed and legacy behavior and record full regression evidence before considering this slice closed.
4. Migrate mixed voice/vision without moving the voice supervisor, STT, TTS, or audio transport. Preserve image approval, bounds, source identity, and route capability checks.
5. Emit correlated `queued`, `started`, `progress`, `text_delta`, `tool_request`, `tool_result`, `artifact`, and exactly one terminal `completed|cancelled|failed` event. `execute_chat` remains a collector over this lifecycle.
6. Propagate deadline/cancellation and suppress late text, artifacts, tools, UI updates, and database writes after cancellation. Reconcile executed tool IDs; never automatically replay mutating tools.
7. Preserve the two-slot non-voice admission limit and one-background maximum. Interactive work gets the next free slot. Do not throttle voice or add another queue/database.

**Tests:** role/order/policy preservation; rejected input causes zero provider calls; immutable per-task route/model; exactly-one terminal; queued and active cancellation with no late writes; duplicate tool-result reconciliation; direct-API behavior and quality denominators; interactive capacity during background work. Run call-site audit and focused suites after each family.

**Pass:** all permitted migrated callers validate before transmission; every remaining production call site has a named owner; inventory alone is insufficient.

### 2. Enforce policy at every sink (GC24-03)

Partial progress: routed SubAgent requests now combine route policy with the
inherited sensitive-turn signal before provider-client creation. See the
[GC24-03 progress receipt](../acceptance/verified-gap-closure/GC24-03-sensitive-routed-subagent-2026-09-24.md).
Council/planning now inherit the static workload privacy floor, prevent route
preferences or request labels from lowering it, and carry it into too-small
round persistence paths. See the [council policy receipt](../acceptance/verified-gap-closure/GC24-03-council-workload-floor-2026-09-24.md).
This does not replace the required caller/source/sink inventory or close any
other sink family.

**Additional concrete gap found during current-tree review:** Council policy
must inherit the configured workload privacy floor even when the caller omits
an explicit `data_policy`/`privacy` field, then combine that floor with any
stricter request/context policy. Do not derive the effective policy from the
selected route alone: that can make unlabeled council inputs appear less
restricted than the workload configuration. Apply this consistently to
proposer, judge, planning, and shadow continuations, before client creation
and before durable payload/score writes. This council substep is implemented
and covered by the dated [council workload-floor receipt](../acceptance/verified-gap-closure/GC24-03-council-workload-floor-2026-09-24.md).
The overall GC24-03 phase remains open until the other sink families below
are inventoried and negatively tested. An explicit request label may tighten,
never weaken, the configured workload floor.

Build a reviewed sink inventory from the call-site audit. Combine workload and each context, memory, attachment, tool result, and artifact using the existing strictest-policy rule. Validate before provider requests, external tools, tool-result continuations, supervisor context, TTS, console sharing, exports, run/usage logs, and provider session persistence. Full protected results stay in the existing local result area. When blocked, Haiku receives only the specified fixed status and opaque reference; never forward protected content to speech or later supervisor turns. Preserve allowed personalization.

Readiness/usage reports contain no prompts, content, raw provider errors, or secrets. Validate route capability/configuration before activation. An unavailable compliant route stays unavailable with a reason; no paid fallback or privacy downgrade.

**Tests:** synthetic canaries through memory, attachment, tools, council,
errors, response routing, logs, exports, and TTS. Include council calls with
no explicit request label as well as stricter labels. Forbidden destinations
prove zero transmission and no persisted payload. Cover mixed policy,
sensitive tool-result continuation, unavailable routes, and preference
changes during a task.

**Pass:** all sinks named and negatively tested; no route can weaken source policy; existing voice limitations remain accurately stated.

### 3. Prove subscription and SAYGM capabilities (GC24-04)

Verify current official Claude/Codex runtime versions, supported invocation, authentication, and controls using official documentation at implementation time. Use a task-scoped temporary working directory and allowlisted child environment. Disable project instructions, hooks, plugins, MCP, and built-in tools with verified runtime controls; avoid process-argument prompt contents; do not copy sign-in state. Parse documented response envelopes strictly. Treat error envelopes, failed terminal events, missing completion, auth/limit errors, and timeouts as failure even with exit code zero. Use a process group, terminate/reap on cancellation, clean task files on every exit, and separate price estimates from actual billing. Do not assert zero overage without provider-supported evidence.

Keep subscription adapters text-only until proven. Tool architecture is fixed: provider runtime → task-scoped Mortimer bridge → registered permission check → existing sandbox executor. The bridge is the only provider tool surface; keep tool capability disabled until isolation and bridge tests pass. Code changes continue through the existing self-edit sandbox and PR boundary.

Use the existing vault-backed SAYGM catalog. Record redacted model/capability receipts. Only recognized confidential metadata plus the documented TEE naming rule can establish confidential inference; ordinary models remain approved-external. Revalidate before protected use; failed/stale catalog data cannot preserve a confidentiality claim.

**Tests/evidence:** current receipts per provider/model and required text, tools, images, or structured-output capability; denied shell/filesystem/network and alternate tools; invented/cross-task IDs, replay, cancellation, timeout, error envelopes, and no surviving child. Synthetic public probes only; never send real memories to test access.

**Pass:** only individually verified capabilities are selectable. Login alone does not prove route readiness or API-cost elimination.

### 4. Connect automated memory admission (GC24-05)

Implement one production `classify(candidates, *, policy_version)` adapter shared by runtime maintenance and provider shadow. Heuristics remain a deterministic baseline and safe rejection checks, never a hidden success-shaped fallback. Use the dedicated memory profile and Phases 1–2 policy/execution boundaries. Classifier output proposes metadata only and has no tools/write authority.

Keep existing B5/B7/B9 and GC24-05 limits: 20 candidates, 12,000 input chars, 2,000 output tokens, up to eight source-turn IDs, exact enums/reason codes, confidence [0,1]. Any malformed, duplicate, extra, missing, or unsupported row abstains the whole batch before writes. Verify evidence against actual stored turn/session records; repeated content is not corroboration. Explicit statements remain confidence 1.0; inferences follow the distinct-turn/session threshold. Assistant/quoted content cannot become user preference. Tentative facts do not enter standing context or authorize actions.

Add only the specified additive `memory_admission_jobs` migration in the existing SQLite DB. Do not reuse `memory_extraction_pending`. Use canonical source/policy idempotency keys; persist a job before advancing extraction cursors; commit each stage before advancing; revalidate source, revision, deletion state, policy, cancellation, and stage before apply. Provider calls stay outside DB write transactions. Share persisted daily budget reservations; preserve 100-candidate/five-call daily limits and bounded retries. Preserve pending work on failure; shadow cannot change retrieval/admission; forget/delete purges staging payloads. No bulk relabeling or cleanup prompts.

**Tests:** production and shadow fixtures; malformed responses and fabricated evidence; concurrent correction/forget; restart/retry/budget races; crashes around enqueue, stage commits, apply, cursor advance; concurrent worker/teardown enqueue; provider failure; unchanged shadow retrieval; no cleanup greeting. Historical production replay is out of scope.

**Pass:** durable, resumable, idempotent production admission is proven. Real memory enablement waits for the staged pilot.

### 5. Make Atlas freshness and failures visible (GC24-06)

Keep Atlas as a projection over existing sources. Move refresh ownership to the existing app-owned store. Track `idle|loading|loaded|empty|failed`, last success, and bounded error category per source; retain last-good cards with a stale marker and distinguish empty from unavailable. Refresh on first activation, backend reconnect, existing source-change events, and explicit refresh. Coalesce overlap and reject obsolete connection generations. No polling loop, duplicate websocket, persistence source, or graph service.

Keep bounded previews, display available totals and existing-reader actions, and route actions through the shared idempotent voice/action registry. Display moves/tab changes must not duplicate fetches. Preserve graph, pins, selection, and accepted appearance.

**Current worktree progress (2026-09-24):** the store-owned per-source refresh lifecycle, freshness/error states, retry, reconnect and stale-card retention are implemented; focused Atlas tests pass 7/7. See the [GC24-06 receipt](../acceptance/verified-gap-closure/GC24-06-atlas-refresh-2026-09-24.md). Live authentication, source-change, accessibility, display-move, performance and candidate evidence remain open. The full native suite has eight headless `WindowVisibilityTests` fixture failures; keep these visible.

**Tests:** empty, partial failure, auth expiry, reconnect, late response, manual retry, selection/pin preservation, no duplicate fetch on display move or tab switch, and existing graph/performance gates.

**Pass:** useful before a research result, truthful about data vs. load errors, and recoverable after transient failures.

### 6. Build and verify one exact candidate (GC24-07)

Add truthful effective-capability preflight to existing launch/connection paths. A layout-2 client connected to a disabled server feature reports that feature as unavailable; do not auto-switch layout, turn on providers, or show dead actions. Keep routing, memory, and sharing activation independent and validate each affected workload. Package with `macos/MortimerHost/scripts/bundle.sh`.

Create/sync the isolated locked environment and run the exact GC24-07 commands, all affected Python/Swift suites, integration/evaluation, call-site/policy audits, latency probes, build/package checks, and `git diff --check`. Record executed/pass/fail/skip counts. Do not call skipped display tests passed, shrink eval denominators, delete failures, or redefine a breached baseline. Keep graph/frame, navigation, retention, queue, voice, and no-underrun budgets from the authoritative plan.

**Pass:** exact source, artifact, and configuration with current full regression evidence and no unresolved active regression. Code/config changes invalidate affected candidate results.

### 7. Complete remaining physical Mac journeys (GC24-08)

On the exact candidate, run an instrumented supporting-display journey: one full result owner, one bounded shared stage, append-only multi-results, graph, and developer run. Record request/parent IDs, windows, topology, and fetch/subscription counts. Separately test monitor loss/return, backend/voice reconnect, single/external/mirrored arrangements, and three recognized displays only if available. macOS Spaces are not a multi-monitor pass.

Verify real user speech and Mortimer output, independent orb response, alive connected/muted idle state, captions vs. full results, stable return to main, and repeat-voice-command deduplication. Verify real text/image share preview, copy/save/system picker, cancel/return, destination/model, approval, progress/cancel/reconnect/cleanup. Walk eight tabs, scrollable header, persistent font size, keyboard, VoiceOver, reduced motion/transparency, compact startup, and approved graph/orb. Carry forward the named AirPods, speaker, security, and labeled-speaker protocols.

**Pass:** dated, redacted exact-candidate receipts with correlated IDs and event counts. Missing hardware or observation stays blocked with an owner and next action, never marked passed.

### 8. Pilot, independently verify, rollback, release (GC24-09/10)

**Model pilot:** Public synthetic text first, then one approved non-voice workload per route. Compare identical quality fixtures/denominators to baseline. Record queue/cold/warm latency, first useful output, total time, cancellation/failure, and billing source. Preserve <=250 ms local acknowledgment, <=1 s median additional overhead for short interactive tasks, and review >2 s additional p95 before changing defaults. Evaluate research and development as whole tasks. Prove voice priority under background load. Move tool workloads only after Phase 3 bridge proof. List remaining API workloads and reasons; subscription access does not mean all API costs disappear.

**Memory pilot:** Back up and verify the restorable DB before production changes; use the existing Mac vault in place. Run synthetic provider shadow, one daily-driver shadow day, explicit preferences, then corroborated inference. Keep enabled/shadow/stage separate. Use unchanged B5/B9 hashes and gates; review the first 20 real reversible decisions once with Larry, not as an ongoing user task. Do not promote on recall, stale/duplicate/scope/privacy, p95, or budget regression. On failure, disable the new stage, preserve queued evidence/memories, and undo only attributable revisions through the existing undo path.

**Release:** Run the full-profile independent sandbox verifier on the exact candidate/baseline. Demonstrate layout rollback, routing/memory disablement, and executable rollback without deleting preferences/data. Build/sign/package through the established workflow and verify loaded app/backend identity. Complete the separate five-day stable-candidate observation; runtime code/config changes restart it. User-observation acceptance remains pending until observed.

**Pass:** Current evidence per route/workload/stage; independent verifier and rollback receipts; all applicable gates closed or visibly blocked. No claim of full release while required live acceptance remains outstanding.

## Progress and handoff requirements

For every slice, update linked status documents and add a dated receipt under `docs/acceptance/verified-gap-closure/`. Include requirement IDs, exact source commit, changed files, preserved invariants, commands and pass/fail/skip counts, runtime/provider/hardware evidence, limitations, and next unblocked action. Keep open items above completed items; map substeps to existing CC/B/MAR/UI2 requirements instead of inflating the denominator.

## First next actions

1. On the Mac, exercise two shared-content offers in one connected session with a route preference change between them. Verify the displayed provider/model matches each offer and each approved batch executes on its disclosed route. Keep the voice supervisor, STT, TTS, and transport unchanged.
2. Complete the shared lifecycle contract across migrated callers: token-level text/artifact/tool-result events, exactly-once terminal state across complete tool loops, cancellation propagation, suppression of late UI/database writes, and durable reconciliation of tool results. Keep the existing registry and sandbox as the only tool executor.
3. Re-run the call-site audit after each caller family and update GC24-02 evidence. The current static inventory reports 25 entries with zero review-required; the full locked unit/integration suite and SubAgent eval pass for this dirty snapshot, but GC24-02 remains open until the lifecycle contract and remaining production ownership are satisfied.
4. Close GC24-03's end-to-end sink inventory and negative privacy canaries before enabling protected-content routes. Then continue phases 3–8 in order. Mac candidate, hardware journeys, live provider capability, pilots, rollback, and release remain separate gates.
