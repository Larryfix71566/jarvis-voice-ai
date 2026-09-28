# Mortimer — Post-Review Gap Closure Plan

**Prepared:** 2026-09-25; reconciled to latest isolated-tree receipts 2026-09-25  
**Purpose:** Give any implementation model an ordered, decision-complete path
to close the gaps confirmed by the latest source and plan review.  
**Implementation tree:** `codex/isolated-20260924`, based on
`977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; the working tree is already dirty.  
**Scope:** source implementation and acceptance evidence. This plan does not
authorize merge, push, deployment, provider-account changes, or production
memory enablement.

**Review refresh:** 2026-09-25. This handoff now distinguishes a terminal
SubAgent cancellation record, which is implemented in the current dirty tree,
from end-to-end cancellation across provider/tool/UI/database work, which
remains open. Re-run the named checks before relying on prior counts.

This is a focused handoff supplement to the [Current Verified Gaps
Implementation Plan](MORTIMER_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md), the
[Verified Gap Closure plan](MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md), and the
feature plans linked there. The feature/GC24 plans own schemas, thresholds,
and acceptance protocols. If a detail differs, stop and record the conflict;
preserve the stricter existing requirement. Do not invent a replacement
architecture.

## Target outcome

Close the verified implementation gaps while retaining Mortimer's selected
Command Console, response/results ownership, voice behavior, model/privacy
boundaries, existing sandbox, and SQLite memory system. Every increment must
be isolated, testable, reversible, and accompanied by a dated receipt. Keep
the words **implemented**, **merged**, **candidate verified**, **live accepted**,
and **released** separate.

## Locked design and safety decisions

- Keep compact Conversation as startup, all eight scrollable sidecar tabs,
  the approved atom/comet orb, current voice supervisor/STT/TTS/transport,
  and one app-owned response/result identity per request. Full answers go to
  the existing results area; Conversation carries brief live captions.
- Keep one shared execution boundary, action registry, placement owner, and
  bounded supporting-display stage. Display movement or reconnection must
  never start a duplicate request, fetch, or result window.
- Keep Haiku in its supervisor role. Do not migrate the live voice loop as
  part of these gaps.
- Keep model, route, workload, privacy, capability, and billing as separate
  facts. No silent substitution, API fallback, privacy downgrade, guessed
  capability, or unknown-usage-as-zero behavior.
- Provider tools remain unavailable until runtime isolation and the
  task-scoped Mortimer bridge are both proven. Mortimer's registered action
  and existing sandbox remain the only execution path.
- Keep SQLite as the only memory system of record. Classification remains
  quiet and automatic; do not add cleanup prompts, user labeling, another
  memory store, historical replay of the 28 exchanges, or bulk relabeling.
- Protected data stays local unless the exact model and route have verified
  capability. A key, login, catalog row, or public probe alone is insufficient.
- Continue only in the named isolated worktree. Reconcile file ownership and
  concurrent changes before editing; preserve all existing dirty work.

## Verified starting state

This is an isolated source-tree review, not a claim about main, the installed
Mac app, or production settings.

| Workstream | Present in the reviewed tree | Gap this plan closes |
| --- | --- | --- |
| Model-call inventory | 26/26 reviewed call sites covered; zero review-required; secret-free receipt. | The inventory does not prove event lifecycle, privacy sink behavior, provider capability, or Mac acceptance. |
| Shared execution (GC24-02) | Shared context/routing/usage boundary, policy-tagged events, opt-in Anthropic stream support. Voice RTVI `bot-llm-text` is aggregated into the transcript and fed to the existing result router; focused tests cover client aggregation (2), a stub transport-to-result integration (1), and result updates (7). SubAgent cancellation finalizes its run-log record; delegate-task UI events have an idempotent terminal owner; returned values after absorbed cancellation are suppressed; direct-mode SubAgent, self-edit planner, and live Supervisor loops reject malformed or reused provider tool-call IDs before dispatch. Durable SubAgent runlog call IDs now identify unresolved/unknown outcomes (124 focused tests pass; see the [observability receipt](../acceptance/verified-gap-closure/GC24-02-unknown-tool-outcome-observability-2026-09-25.md)). | No production consumer connects generic shared-execution `ModelExecutionEvent.text_delta` events to the existing result owner; live candidate source-to-pane proof; terminal semantics across every provider/tool caller, artifact/tool-result ownership, end-to-end downstream cancellation and late-write suppression, cross-request action reconciliation/idempotency across new provider call IDs, and remaining caller coverage remain open. See the [voice response-stream receipt](../acceptance/verified-gap-closure/GC24-02-existing-voice-response-stream-path-2026-09-25.md), [cancellation receipt](../acceptance/verified-gap-closure/GC24-02-cancellation-terminal-2026-09-25.md), [delegate lifecycle receipt](../acceptance/verified-gap-closure/GC24-02-delegate-terminal-lifecycle-2026-09-25.md), [cancellation-suppression receipt](../acceptance/verified-gap-closure/GC24-02-subagent-cancellation-suppression-2026-09-25.md), [SubAgent/planner replay receipt](../acceptance/verified-gap-closure/GC24-02-tool-call-identity-replay-2026-09-25.md), and [Supervisor replay receipt](../acceptance/verified-gap-closure/GC24-02-supervisor-tool-call-identity-replay-2026-09-25.md). |
| Privacy (GC24-03) | Sensitive SubAgent and council policy floors/redaction are implemented for covered paths. Protected specialist results remain local; MCP, watcher, clipboard/command-title, selected agent/delegation/event/findings, admin job/status errors, and memory diagnostics suppress raw exception, response, path, notice, URL, memory key/session, or user-authored task text with canary coverage. Successful task results remain visible in the established local UI and require end-to-end policy validation. See the [protected-result](../acceptance/verified-gap-closure/GC24-03-protected-local-result-handoff-2026-09-25.md), [MCP log](../acceptance/verified-gap-closure/GC24-03-mcp-exception-log-redaction-2026-09-25.md), [watcher log](../acceptance/verified-gap-closure/GC24-03-watcher-log-redaction-2026-09-25.md), [clipboard log](../acceptance/verified-gap-closure/GC24-03-clipboard-log-redaction-2026-09-25.md), [agent/event log](../acceptance/verified-gap-closure/GC24-03-agent-event-findings-log-redaction-2026-09-25.md), [admin log/status](../acceptance/verified-gap-closure/GC24-03-admin-job-log-and-status-redaction-2026-09-25.md), and [memory log](../acceptance/verified-gap-closure/GC24-03-memory-log-redaction-2026-09-25.md) receipts. | Prove every sink end to end: tool continuations, memory, voice supervisor/TTS, sharing/export, telemetry/logging, provider persistence, response/display, and direct mode. The local-first path must deliver the full answer only to the approved local result surface and return only a fixed status plus opaque reference to the supervisor. |
| Automatic memory (GC24-05) | Strict route-aware classifier; source-evidence validation; migrations 0025–0027; durable worker/teardown enqueue before cursor or pairing advancement; resumable extract/classify/apply stages; shared atomic budget reservations; digest-only shadow metadata; forget cancels staged work; claim-timestamp fencing across stage transitions and atomic apply; stale apply-owner regression; simultaneous SQLite connections claim one due job exactly once; deterministic forget-during-apply regression leaves no fact; child exits prove apply and terminal-completion rollback/retry, enqueue/cursor recovery, and extract/classify recovery before commit and after committed transitions. Latest focused admission/worker/acceptance run passes 74 tests. | Multi-process duplicate-worker and cross-process forget/reclaim race coverage; a currently verified confidential production route; Mac shadow/benefit observation; and staged rollout remain. Production remains disabled and fail-closed. See the [admission worker receipt](../acceptance/verified-gap-closure/GC24-05-admission-worker-2026-09-25.md), [claim-fencing receipt](../acceptance/verified-gap-closure/GC24-05-admission-claim-fencing-2026-09-25.md), [apply-claim fencing receipt](../acceptance/verified-gap-closure/GC24-05-admission-apply-claim-fencing-2026-09-25.md), [concurrent claims receipt](../acceptance/verified-gap-closure/GC24-05-admission-concurrent-claims-2026-09-25.md), [forget/apply receipt](../acceptance/verified-gap-closure/GC24-05-admission-forget-apply-race-2026-09-25.md), and [apply/enqueue/stage/completion crash receipt](../acceptance/verified-gap-closure/GC24-05-admission-apply-rollback-2026-09-25.md). |
| Model access (GC24-04) | Claude/Codex/SAYGM adapters/configuration foundations and call-site coverage. | Per-model/route capability, isolation, privacy and billing receipts; no provider tool enablement without the complete Mortimer bridge proof. |
| Knowledge Atlas (GC24-06) | Store-owned per-source refresh lifecycle, generation guard, stale last-good state, retry/reconnect. | Live auth expiry/recovery, source-change reliability, accessibility, no duplicate fetch on presentation changes, graph/performance and candidate proof. Eight headless window-visibility failures remain recorded. |
| Candidate/release (GC24-07–10) | Historical receipts and runbooks. | Exact current build/config identity, regressions, physical Mac journeys, pilots, independent review, rollback drill and observation window. |

### Newly confirmed execution detail — 2026-09-25

`SubAgent.run()` now catches `asyncio.CancelledError`, writes a fixed,
content-free terminal run-log reply, marks the run `cancelled`, then
re-raises cancellation. `_derive_status` and the run-log CLI accept that
terminal status, and an integration regression asserts cancellation is
propagated while the run record is finalized. This closes only the run-log
orphaning slice for a cancelled SubAgent.

It does **not** prove cancellation reaches every provider stream, registered
tool, result consumer, UI observer, or durable write. GC24-02 must still
prevent late text, tool execution, artifact delivery, memory/database writes,
and completion notifications after cancellation or timeout, and must produce
exactly one terminal event across multiple provider/tool rounds. Preserve the
existing run-log change and extend its coverage; do not replace it with a
second lifecycle or event system.

Relevant owners for this slice are `jarvis/agents/base.py`,
`jarvis/model_execution.py`, the existing registered-tool executor and its
callers, the app-owned response/results consumer, `jarvis/runlog/store.py`,
and the integration/unit tests for execution, SubAgent, run-log, memory, and
result delivery. Before editing, inspect the current implementation and
`git status`; files are shared with concurrent work in this dirty worktree.

Latest recorded test evidence is in the linked current-gap plan and dated
receipts: Python unit/integration **2,908 passed, 4 skipped, 11 warnings,
2 subtests**; durable-admission focused suite **84 passed**; Atlas focused
Swift suite **10 passed**; protected-result native share/action suite
**19 passed**; targeted Ruff `F`/`I`, Swift parsing, and
`git diff --check` passed. The full MortimerHost suite still has eight
headless window-visibility fixture failures. These counts apply to the dirty
isolated source snapshot, not a candidate or release. Re-run relevant checks
after changes; never copy these counts into a new receipt as if freshly
executed.

## Ordered work packages

### 0. Reconcile the baseline and ownership — GC24-00/01

Before modifying a shared file, record current branch/base/HEAD, dirty paths,
linked worktrees, concurrent edits, and the source/test/receipt owner for each
work package. Compare the exact files and current tests with the receipts
below. Identify runtime facts as verified or unknown; do not infer running
app/backend identity or effective gates from a repository build.

**Acceptance:** dated baseline and ownership map; no changes overwritten; all
unknown runtime/provider/hardware facts explicitly remain unverified.

### 1. Finish the execution lifecycle — GC24-02

Keep the current boundary and app-owned response/results consumer. Preserve
the existing voice route from RTVI `bot-llm-text` through the transcript and
`ResponseResultRouter`; do not add another consumer for those same voice
tokens. Its source path is covered by a stub-transport integration test, while
the running Mac candidate journey remains open. Once lifecycle and policy are
enforced, wire one production consumer for generic shared-execution events
from inventoried callers that need streaming; append deltas to the existing
request/result identity. Normalize ordered, correlated progress/text/tool/
artifact events and exactly one terminal event across the complete provider
and registered-tool loop. Carry deadline and cancellation through provider,
tool owner, UI observer and durable write. Suppress every late output or side
effect after cancellation/timeout. Reconcile mutating tool IDs before retry
or restart; an unknown outcome is not automatically replayed. Preserve the
compatibility collector for callers that do not subscribe to events.

Do not add another orchestrator, event bus, result store, tool executor, or
background queue. Keep voice priority and current non-voice admission limits.

**Required proof:** production consumer test; ordering and parent identity;
one terminal over multiple provider/tool rounds; cancellation before/during
provider and tool execution; timeout/late completion with no UI/DB effects;
artifact and tool-result policy; duplicate/unknown mutating-tool receipt;
compatibility parity; background saturation with voice priority.

**Implementation order within this package:** the SubAgent run-log
cancellation record, `delegate_task` UI terminal-event slice, and SubAgent
post-cancellation result suppression are covered by dated receipts; do not
redo those slices. Next trace request ownership from
admission through each provider/tool round, assign exactly one terminal owner
to the full loop and artifact/tool-result outcomes, and prove cancellation
reaches provider/tool execution while preventing late UI/database effects.
Only then wire the generic shared-execution event consumer to the existing
result owner. Keep each step bounded and preserve a receipt of the invariant
tested. A run-log row or delegate-card terminal alone does not prove provider
work stopped or downstream effects were suppressed.

The latest SubAgent cancellation-suppression increment is recorded in the
[GC24-02 cancellation-suppression receipt](../acceptance/verified-gap-closure/GC24-02-subagent-cancellation-suppression-2026-09-25.md).
Direct-mode SubAgent and self-edit planner tool-call ID replay protection is recorded in the
[GC24-02 SubAgent/planner tool-call replay receipt](../acceptance/verified-gap-closure/GC24-02-tool-call-identity-replay-2026-09-25.md), [GC24-02 Supervisor tool-call replay receipt](../acceptance/verified-gap-closure/GC24-02-supervisor-tool-call-identity-replay-2026-09-25.md). The existing voice path is documented in the [voice response-stream receipt](../acceptance/verified-gap-closure/GC24-02-existing-voice-response-stream-path-2026-09-25.md); SubAgent unknown outcomes are now visible in durable run details, but action-specific reconciliation across new call IDs and remaining caller coverage remain open (see the [observability receipt](../acceptance/verified-gap-closure/GC24-02-unknown-tool-outcome-observability-2026-09-25.md)).

**Acceptance:** each migrated call site has a named owner; the live production
consumer and all relevant sinks are tested; no late side effect; audit rerun
has no unreviewed call sites. Streaming is not “complete” before consumer and
terminal lifecycle are proven.

### 2. Complete privacy source-to-sink enforcement — GC24-03

Extend the reviewed call-site inventory into a source-to-sink map. Resolve
policy locally from workload and input provenance, then apply the existing
strictest-policy rule to attachments, memory, tool results, artifacts and
provider output. Test policy before every provider request/continuation,
external action, supervisor handoff, TTS, display/share/export, SQLite or
provider-session write, and usage/error/status log. Keep protected results in
the approved local result area; status surfaces may carry only allowed
bounded reason codes and opaque IDs.

**Required proof:** synthetic canaries for every inventoried sink; forbidden
sinks show zero transmission and zero payload persistence; mixed-policy and
mid-task sensitive tool-result cases; no caller label and route preference
changes; error/timeout paths; unavailable compliant route fails closed. Keep
the existing voice exception accurately described.

**Acceptance:** complete sink inventory with executable negative tests. A
shared helper or a clean static audit alone does not close this phase.

#### Protected specialist result handoff (required GC24-03 subtask)

The concrete regression is a confidential/local-only specialist answer
returning through the ordinary delegate tool-result channel, where an
external supervisor can receive the full text. The implementation must use
the existing app-owned display transport and result identity; do not create
a second orchestrator, result store, or UI surface.

1. Before creating a provider client, resolve effective privacy from the
   workload, source provenance, and selected route. If confidential/local-only
   work has no verified private route or no local result sink, fail closed
   without sending content.
2. For a permitted private run, await delivery of the complete answer to the
   existing local response/results surface before the delegate call returns.
   The external supervisor receives only a fixed content-free status and an
   opaque reference. Provider exceptions, timeouts, and sink failures must
   not put answer text, prompts, tool arguments, or raw provider errors into
   events, logs, or status messages.
3. Carry the protected policy label to the native result payload and all
   subsequent operations. Selection, clipboard copy, share, export, and any
   other external destination remain disabled unless an explicitly approved
   policy transition exists in the authoritative privacy specification.
   Unknown non-null policy values fail closed.
4. Preserve the existing request/result identity and run correlation. The
   handoff must not persist protected content to a new database or introduce
   another display window, and it must not cause another provider request.

**Required tests:** no compliant route/no sink means zero client creation;
successful delivery reaches the local sink before the caller returns and the
supervisor receives no content; sink/provider failure returns only a fixed
status; emitted events and logs contain no protected canary; protected copy,
share, export, and attachment actions are rejected; a protected and public
result with otherwise identical identity remain distinct; ordinary approved
external results retain their existing behavior.

**Acceptance:** the protected answer is available in the approved local result
surface, while every external path sees at most the fixed status and opaque
reference. This closes only the specialist handoff slice; GC24-03 remains open
until the complete source-to-sink inventory and negative canaries pass.

### 3. Complete durable automatic-memory admission — GC24-05

Durable enqueue-before-cursor/teardown, resumable extract → classify → apply,
atomic shared budget reservation, digest-only shadow metadata, and staged
forget cancellation are implemented in this isolated tree. Preserve those
contracts; do not add another schema, queue, or memory store. Remaining
implementation proof is crash/restart and multi-worker race coverage at every
enqueue, stage, apply, forget, and cursor boundary. Keep provider calls
outside SQLite write transactions; use the committed single-owner claims and
stage compare-and-set in `jarvis/memory_admission.py`.

Before apply, validate the whole classification batch and its evidence against
stored source turns, then recheck source revision, current policy, deletion/
forget state, cancellation and claim/stage identity. Apply rows atomically
through existing revision/provenance mechanisms. Share the existing bounded
daily candidate/call limits with maintenance using persisted atomic budget
reservations. Preserve transient jobs for bounded retry; clean terminal
payloads; forgetting source evidence invalidates staged and in-flight work.
Shadow mode must not alter cursor, live admission, retrieval, or prompts.

Production remains fail-closed while no confidential production model/route
has current verified capability. Do not enable live classification just
because the provider adapter or queue passes tests.

**Required proof:** crash injection before/after enqueue, every durable stage,
apply, and cursor advance; worker/teardown duplicate enqueue; two-worker claim
and shared-budget races; restart/reclaim; provider timeout/failure; correction
and forget races; fabricated/stale/assistant-only evidence; malformed batch
abstains entirely; shadow invariance; voice latency/priority unchanged.

**Acceptance:** cursor cannot pass uncommitted work; each exchange is
resumable and idempotent; no deleted/unsupported fact can be re-admitted;
budgets are atomic across workers. Keep rollout staged pending provider route,
backup, shadow, and daily-driver gates in the memory authority plan.

### 4. Verify each model route and capability — GC24-04

For each model/route separately, verify the exact supported runtime version,
authentication, text/image/structured-output/streaming/tool/cancellation
capabilities, privacy tier and billing evidence. Use provider documentation
current at implementation time. Test CLI/subscription adapters in a clean
task-scoped directory with allowlisted environment, provider-native tools,
hooks/plugins/MCP disabled, bounded I/O, process-group cancellation and
cleanup. Treat malformed/error envelopes as failure even on exit code zero.

Keep provider tools disabled unless runtime isolation **and** the existing
task-scoped Mortimer bridge, action permissions, policy checks, idempotency,
and sandbox execution are proven together. Do not store passwords or OAuth
state in the repo/vault. Do not add API fallback or claim API-cost removal
from login/list price alone. Protected memory probes use synthetic data only.

**Acceptance:** redacted per-model/per-route receipts distinguish capability,
privacy and billing evidence. Unsupported or stale routes remain unavailable.

### 5. Finish Atlas lifecycle and accessibility — GC24-06

Extend the existing store-owned refresh lifecycle only. Prove source-change
triggers, independent partial failure, auth expiry/recovery, stale last-good
cards, retry, cancellation and generation rejection. Verify selection,
groups and pins survive refresh. Presentation moves/tab changes must not
trigger duplicate fetches. Validate keyboard and VoiceOver status/actions,
useful empty/loading/failure states, reduced motion/transparency and existing
graph/frame budgets on the identified candidate.

Investigate and retain the eight recorded headless window-visibility failures;
do not suppress or relabel them as passes. Do not add polling, another data
source, graph service, websocket, or a second fetch owner.

**Acceptance:** focused test receipt plus current-candidate evidence for
recovery, accessibility, performance and zero duplicate fetches.

### 6. Candidate, live journeys and closure gates — GC24-07–10

Build one exact candidate from reconciled source/config. Record source SHA,
artifact/backend identity, configuration digest and effective nonsecret
gates. Run all affected Python, Swift, integration/evaluation, policy/call-site,
performance, package/signature and diff checks with executed/pass/fail/skip
counts. On the same candidate complete only outstanding physical Mac paths:
voice input/output and orb, result placement, sharing/attachment approval,
eight tabs/accessibility, Atlas refresh, supporting display, disconnect/rehome,
and request/window/fetch deduplication. Spaces do not count as multiple
physical monitors.

Run model pilots on synthetic public data first, then explicitly approved
non-voice workloads. Keep quality and latency denominators/thresholds fixed;
record selected route, queue/cold/warm/first-useful/total latency, cancellation,
usage-known state and billing evidence. Run memory shadow/staged pilot only
after backup and verified route; keep its enablement independent. Complete
independent review, feature-disable and executable rollback drills, and the
required stable-candidate observation window. Any relevant source/config
change invalidates the corresponding candidate evidence.

**Acceptance:** a fully traceable candidate with current regressions, physical
journeys, per-route/pilot evidence, independent review, rollback and observation
receipt. Hardware, provider, or observation gaps remain open with owner and
next action; no source-only claim closes them.

## Handoff protocol for the implementing model

1. Read this plan, the matching GC24 section, feature plan, latest receipt,
   current `git status`, and exact source/test files before editing.
2. Take one unblocked work package at a time. Reconcile concurrent file
   ownership first; preserve the dirty tree and do not transplant or reset
   another worker's changes.
3. Add meaningful regression tests for the required failure boundary. Run
   the narrow suite, affected broader suites, applicable audit, and
   `git diff --check`. Preserve all failures and skips in the report.
4. Add a dated receipt with exact source revision, files, commands and
   counts, preserved invariants, limits, and the next unblocked action. Update
   the existing status row; do not create duplicate requirement IDs.
5. Review the diff for secrets, user content, weakened defaults, hidden
   fallback, duplicate architecture, and stale claims. Keep work uncommitted
   and unpushed unless separately requested.
6. Never mark provider, hardware, Mac, merge, deployment, or release gates
   complete from unit tests or an unverified report.

## Immediate next action

First reconcile ownership of the execution-boundary and protected-result
changes already in the dirty worktree; do not overwrite or transplant another
worker's edits. Then complete the remaining GC24-02 production-consumer,
provider/tool-loop terminal, cancellation, late-write, and mutating-tool
reconciliation proof. Continue GC24-03 with the protected specialist handoff
tests above and the full source-to-sink inventory. Keep memory automation and
unverified model routes disabled; GC24-05 source implementation is not live-
accepted.
