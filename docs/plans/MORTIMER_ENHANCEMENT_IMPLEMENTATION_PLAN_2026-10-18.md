# Mortimer enhancement implementation plan

**Date:** 2026-10-18 · **Roadmap authority:** [WS-27](../../ROADMAP.md#ws-27)
**State:** documentation only; proposed implementation and all benchmarks parked.
**Source baseline:** main `28420af29191716945e55f6aeec1f0fd125ea931`; refreshed
to documentation-only main `9ea27c7` after #218/#219 merged during publication.
**Planning preference:** GPT-6.1 Sol, high effort, as requested by Larry; this is
not a claim about independently observed model telemetry.

This plan turns the discussion into staged, reviewable work after the current
release and acceptance campaign. Its technical appendices are the
[sandbox voice evaluation protocol](MORTIMER_VOICE_EVALUATION_PROTOCOL_2026-10-18.md)
and [private local-model runbook](MORTIMER_PRIVATE_LOCAL_MODEL_RUNBOOK_2026-10-18.md).
They are parts of this one plan, not additional workstream claims. No model has
been installed or benchmarked for this plan; all result cells remain unmeasured.

## 1. Authority, baseline and dependencies

The Git [master roadmap](../../ROADMAP.md) remains the shared record for Codex,
Claude and Larry. Existing acceptance gates retain priority. A plan review is
not permission to implement, enable a provider, spend money, grant credentials,
change security settings, merge, deploy, send messages or ingest private data.
Before each later slice: fetch main, reconcile claims and PRs, dispatch a named
owner/branch/scope, reserve any new identifiers, and preserve existing owners.

| Evidence inspected on 2026-10-18 | Consequence for this plan |
|---|---|
| Main `28420af`, merged #216; draft [#218](https://github.com/Larryfix71566/jarvis-voice-ai/pull/218) head `7da4a91` | Source repair is distinct from installed build, deployment and live acceptance. #218 merged as `0b49706`; its WS-17 status update is incorporated without changing release gates. |
| Later merged [#219](https://github.com/Larryfix71566/jarvis-voice-ai/pull/219) head `40c357d` | It merged as `9ea27c7` during publication. The intake, four parked cards and WS-22 dependency note are preserved; do not create competing verification/task/commitment/event systems. |
| [WS-22 evidence workflow](MORTIMER_EVIDENCE_WORKFLOW_IMPLEMENTATION_PLAN.md) | Reuse investigation, requirement/evidence and handoff contracts; reconcile schemas with proposed WS-24 before code. |
| [WS-05 model access](MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md), [access config](../../config/model_access.yaml), [route clients](../../jarvis/model_routing.py) | Existing policy/execution boundaries are the integration authority. `local_runtime` is declared but both sync/async clients explicitly refuse with “local model runtime is not configured.” A localhost URL alone does not implement the private route. |
| [Pipeline](../../jarvis/bot/pipeline.py), [observer](../../jarvis/bot/transcript_log.py), [prior voice bench](MORTIMER_VOICE_MODEL_BENCH_PLAN.md) | Current source separates Deepgram Flux `flux-general-en`, conversational LLM and ElevenLabs Flash TTS. Source supports native Google, native Anthropic (conditional on `native_enabled`) and OpenAI-compatible service paths. Effective installed model/adapter/settings must be observed later. The existing observer measures backend speaking-stop → outbound audio frame, not acoustic end → actual client playback. Preserve historical bench results and locked backend targets; do not treat them as new playback results. |
| [WS-13 canonical revised mail plan](MORTIMER_MAIL_CALENDAR_BRIEF_PLAN.md), [architecture](../ARCHITECTURE.md) | Local bounded IMAP header reader and deterministic protected brief P1–P3 precede optional private model-written P4 and interactive P5. Larry already has mail in his daily report; the actual deployed report path remains unverified. Extend verified gaps only. |
| [#210 findings](../roadmap-log/2026-10-17-ws-20-codex-three-pr-review.md), [later claim evidence](../roadmap-log/2026-10-17-ws-17-codex-ui2-24-25-repair-claim.md) | #210 merged as `34e5d55` despite the stale deletion-plan race and omitted cleanup runner fingerprint. Diff of its head `8842503` to inspected main for `sandbox/prune.py`/`sandbox/verify.py` is empty. No prune/reclaim or normal clone path that invokes it until independently repaired/reviewed. |

Only #218 and #219 were open at initial preparation; both merged during
publication. Main `9ea27c7` is incorporated with both documentation intents
preserved; only draft #220 remained open at refresh. Active runtime locks remain
untouched. The source inventory links retain their original commit for stability. No pending Codex
conflict grants scope here, including WS-04 onboarding (CX-11). Resolve owning
rows' blockers there; this documentation does not start feature work.

## 2. Scope, roles and routing contract

Preserve the Supervisor and the six specialist roles in
[agents.yaml](../../config/agents.yaml): Scheduler, Librarian, Analyst, Systems,
Developer and App Builder. Do not add a general autonomous “acceptance agent.”
Proposed role labels below describe responsibilities, not assignments to Claude,
Codex, running agents or other sessions.

| Work package | Proposed responsible role after dispatch | Dependencies and boundary |
|---|---|---|
| Host routing/state and evaluation harness | Assigned runtime engineer + independent reviewer | WS-05/06/07 and current locks; harness separate from live pipeline |
| Verification checklist | Systems constrained verifier | Proposed WS-23; evidence only, no repair/release authority |
| Durable tasks/checkpoints | Assigned lifecycle engineer | Proposed WS-24 + WS-22; select existing authority first |
| Commitments and relevant events | Scheduler + Librarian responsibilities | Proposed WS-25/26; host timing, source/privacy rules and WS-24 |
| Private model/provider and retrieval | Assigned local/privacy engineer | WS-05/10, T3/T4 and WS-13; synthetic proof before records |
| Mail/report extensions | Existing WS-13 owner, after fresh claim | No reassignment; read-only isolated mail tools |
| Product decisions, listening and releases | Larry | Explicit gates; no proposal below delegates his authority |

### 2.1 Workflow first, then agent and tools

Host resolution order: **target + existing task ID → workflow → eligible
agent/model → permitted tool subset**. Resolve a known task before classifying
its wording as new work. Preserve deterministic UI/status/weather shortcuts;
material ambiguity gets one focused clarification rather than a guessed target.
Reuse current durable self-edit/app-build/planning authority and UUIDs.

| Initial workflow | Target and allowed behavior | Must not do |
|---|---|---|
| Mortimer repair | Own repository, exact source/revision, inspect → propose → separately authorized execute through existing self-edit service | Supervisor edits code itself; new job for an existing task; bypass sandbox/review/deploy |
| Separate-app change | Explicit external application/workspace ID, App Builder workspace seam and existing job/approval | Route an unspecified app into Mortimer self-edit or broaden source access |
| Existing-task status | Authoritative task/run ID and evidence, read-only status or clarification | Start/retry/commit/publish because a status question mentions those words |

Resolve Supervisor/Developer/App Builder conflicts by making this contract
common to prompts, host dispatch, schemas and UI. Supervisor may retain bounded
direct chrome/status/weather tools; Developer handles Mortimer investigation and
repair, App Builder a separate app. A repository plan uses the existing planning
pathway. Requests such as “commit these changes” must either perform the exact
already-authorized direct action through its host gate or obtain the material
missing authority, rather than merely say it can. An eval passes only when the
expected allowed call graph and final state occur. Existing routing floor ≥90%
remains; the newer evaluation protocol proposes stricter targets for review.

### 2.2 Enforce capabilities outside prompts

Define host-owned modes, with tool inventories filtered **and invocation checked**:

- **Inspect:** admitted source/status/read tools only; no mutating calls or tool
  side effects through nested delegation.
- **Propose:** inspect plus bounded draft/artifact creation in the task workspace;
  no execution, publication or live settings changes.
- **Execute:** only authorized workflow operations with exact target, approval
  scope, expiry, privacy label, idempotency key and retained task authority.

Approval, tool/argument/source validation, money limits, model floor and
cancellation are host checks. A confident model, a verifier pass, retrieved
instructions or another agent's handoff cannot enlarge them. Benchmark token,
iteration, timeout and concurrency budgets on real workload classes in the
sandbox before proposing changes; preserve current caps until separately decided.

### 2.3 Librarian selection and communication

Select the store by user intent and retention/privacy, not tool availability:
short durable personal facts/corrections → existing memory admission/review;
explicit authored note → notes; long source-backed knowledge → KB retrieval and
its existing digest path. `mcp_kb` is read-only today; do not expose its internal
write/delete functions as a shortcut. Resolve contradictions with provenance and
existing WS-10 staged approval. No new fourth general memory store.

Private finance/email and derived facts must not enter ordinary memory/notes/KB,
cloud embeddings, session extraction or a general conversation replay. Preserve
labels through retrieval, tool returns, drafts, errors and background jobs.
Speech may be brief (“The task is queued; I’ll report the result”) while the
protected/full artifact retains complete requirements, reasoning evidence,
failures and next steps. Spoken brevity must not truncate stored work or imply
completion before evidence exists.

## 3. Phases and exit criteria

Every phase is proposed. Existing acceptance closure and a fresh scoped dispatch
are prerequisites to new development; offline document review can happen now.
The sandbox evaluation sequence below is agreed in direction, not authority to
build the harness, install assets, record audio or make billable calls.

| Phase | Implementation tasks after authorization | Acceptance/tests and exit gate |
|---|---|---|
| P0 — Reconcile and freeze | Record source, installed artifact/hash, backend PID/config and effective Haiku endpoint/adapter/settings separately; inventory deployed daily report and existing task/run/outbox stores; refresh current main/PRs and cleanup blockers | Exact-source evidence map; no false gate closures. Larry resolves existing acceptance and assigns bounded work. Missing deployed identity stays unknown. |
| P1 — Sandbox voice measurement and optimization | Standalone harness, isolated test client/config/ports/storage, immutable incumbent baseline. Add acoustic/end/transcript/LLM/tool/TTS/render timing. Optimize shared turn detection, streaming and buffers by one-factor ablations; retest incumbent | Full [protocol](MORTIMER_VOICE_EVALUATION_PROTOCOL_2026-10-18.md): production untouched, attribution proven, pause/correction/barge-in/cancel/duplicate regressions pass. Freeze optimized shared cascade before comparison. |
| P2 — Newer models and architecture decision | Track A fixed STT/TTS conversational models; bounded per-model dev tuning; held-out comparisons. Separately Track B baseline/winning cascade versus Live/Realtime frontends with same backend; optional fully local Track C | Quality/privacy hard gates, real playback p50/p95, costs and listening preference with uncertainty. Publish no-winner if inconclusive; Larry chooses direction. Jev remains ON HOLD until this resolves. No automatic production switch. |
| P3 — Agent/workflow contract | Implement §2 in fresh scopes: target/task resolution, host inspect/propose/execute, store selection, truthful states and expected-action routing evals | Stubbed end-to-end allowed/forbidden call graphs; identical user request cannot create duplicate workflow. Unauthorized tools refuse even when directly invoked. Full artifacts survive brief speech. No timeout/concurrency increase without measured budget decision. |
| P4 — Durable lifecycle and verification | Under proposed WS-24 and WS-23, inventory/reuse authority, add missing checkpoints/fencing and constrained evidence verifier; integrate WS-22 rather than new stores | Restart/kill/network/cancel race tests and seeded bad evidence. One task identity, fenced stale workers, idempotent outbox, correct failed/blocked/untested verdicts; missing physical evidence never passes. |
| P5 — Local private route and synthetic retrieval | Implement missing local provider boundary under WS-05 after runbook proof. Host labels, before-recording mode selection, private sinks, protected local retrieval, deterministic financial arithmetic and encrypted user-presence tier | [Runbook matrix](MORTIMER_PRIVATE_LOCAL_MODEL_RUNBOOK_2026-10-18.md#6-test-matrix-and-release-gates) passes including runtime unavailable/no fallback, synthetic leakage, injection, lock/expiry, arithmetic and combined-load tests. Hardware/quality gate + Larry's private-data pilot approval; no real records before then. |
| P6 — Mail Q&A, commitments and events | Extend existing daily report only for verified missing P4/P5 behavior under WS-13; proposed WS-25 commitments and WS-26 relevant events reuse WS-24/outbox/reminders | Source-cited bounded read-only mail answers, explicit incomplete retrieval, no duplicate brief. Corrections/cancel/completion suppress stale reminders; no inferred commitment becomes authorization. |
| P7 — Optional pilots and release | If P2 decision supports it, separate scoped production integration of selected cascade/frontend. Jev decision-only experiment may be considered later. Canary/rollback under existing release owners | Independent exact-build verification, Larry listening/live acceptance, content-free diagnostics and approved rollback; separate merge/deploy decisions. No optional work is implicitly scheduled. |

### 3.1 Voice optimization details

P1 must compare Flux semantic end-of-turn against the existing Silero fallback
without blindly reducing the present `stop_secs=2.5` pause tolerance. Trace which
end event the installed aggregator actually uses. Measure pause retention,
corrections (“Boston—actually Atlanta”), background speech and false barge-in.
Test TTS chunk size/first useful phrase, stream flush and playback/jitter queues
individually; record tradeoffs in intelligibility and interruption stop time.
Keep the unchanged snapshot and ablation receipts. Improvements belong only to
the sandbox variant until the separate production decision.

Speculative preparation, if separately approved, may only perform bounded
read-only preparation with no externally visible side effect. Cancel and discard
it when speech resumes. No tool execution, reminder, edit, message, commitment or
other action may originate from provisional transcripts. Speech interruption
stops speech; it does not cancel durable work unless the user asks to cancel it.
Late results must bind to the original task and be suppressed or delivered
according to that task's current state, privacy and notification policy.

### 3.2 Optional voice frontend versus existing cascade

Evaluate both improving the existing pipeline and a separate full-duplex voice
frontend over Mortimer orchestration. Do not assume migration is necessary.
The primary comparison fixes backend model, prompt, tool fixtures, delays,
authority and task IDs. Compare native frontend tool-calling modes separately
so a changed backend does not masquerade as better audio latency. Specify
asynchronous result correlation, reconnect/session expiry, interruption versus
cancellation, long-running work, context transfer, idle session billing and
private-mode boundaries. Cloud frontend audio is ineligible for private finance
or mail by default even when the backend is local.

### 3.3 Jev — ON HOLD

Do not integrate, acquire credentials or benchmark Jev until voice optimization
and newer-version comparison are resolved and Larry makes a fresh decision.
Only then consider one typed bounded public/synthetic decision pilot (e.g.
select a workflow from a closed list with abstention). It must **replace** a
slower decision and demonstrate net end-to-end benefit, not add a serial model
hop. No text/audio generation, private content, permission authority or automatic
execution. Host checks still decide whether an option is allowed.

[TypeSafe models](https://docs.typesafe.ai/models) documents versioned Jev IDs
and moving aliases; pin a version and record the returned version if a later
pilot is approved. [Confidence](https://docs.typesafe.ai/confidence) is derived
from answer distributions, not a permission or correctness guarantee.
[Legal](https://docs.typesafe.ai/legal) describes default retention and enterprise
ZDR: verify the exact account/endpoint terms before any pilot. No such account
configuration is established here. Official documentation checked 2026-10-18.

## 4. Durable task, evidence and proactive follow-through contract

The proposed WS-24 record is the overall-task authority; agent runs, attempts,
results and notifications are related identities, not interchangeable IDs.
Select/reuse existing SQLite job/task/run storage and outbox/reminders before
proposing a schema. Reconcile WS-22's lifecycle with that choice. No migration
or new daemon is reserved by this document.

Persist goal/source request, owner, workflow/target, requirement/stopping
condition, approval/privacy scope, dependencies/blocker, next check, attempts,
checkpoint, evidence and pending result delivery. Host transitions distinguish
**queued, running, refused, failed, cancelled and complete**; blocked/waiting
conditions must also be explicit. Map legacy states without inventing a success.
Accepted/enqueued is not running; successful tool transport is not task complete;
a refused preflight is not a failed execution; stopping audio is not cancellation.
Use exclusive claims, lease/version fencing and compare-and-set transitions.
An uncertain write after crash is reconciled before retry, never blindly repeated.

A constrained Systems Acceptance Verifier (proposed WS-23) reads only admitted
build/source identity, criteria, diagnostics and receipts. It returns passed,
failed, blocked or untested per criterion. It cannot edit code, weaken tests,
change acceptance requirements, repair evidence or authorize release. Independent
VM results do not prove physical-Mac behavior. Verification must bind the exact
artifact; changed source/settings invalidate affected evidence.

WS-22 handoff carries source/build hashes, requirement/evidence mapping,
observations versus inferences, decisions, contradictions, unknowns, checkpoint,
remaining authority and next action. Test a fresh eligible model resuming from
that packet without recovering an entire private chat. A model swap must not
lose commitments or revive cancelled work.

Proposed WS-25 extends Scheduler/Librarian: distinguish Larry's explicit
commitments from tentative plans, assistant suggestions and third-party mail
requests; support date corrections, completion and cancellation with provenance.
Review suggestions before creating new commitments or writing calendar entries.
Proposed WS-26 consumes relevant build completion, deadline change or blocker
resolution events through existing outbox/watchers. Deduplicate out-of-order
updates, recover after downtime, expire stale events and respect quiet times.
Generic notices disclose no private payload; protected results carry details.
No autonomous outreach or automatic calendar writes are included.

## 5. Privacy, finance and the existing mail report

Cloud services remain suitable for permitted public research, weather and app
building. Finance and private email content, attachments, subjects/metadata and
derived summaries are **local by default**. Reading from the original mail
provider or obtaining public market prices is distinct from sending private
material to a cloud AI. No real financial/email records are accessed in this work.

Select local private mode **before recording**, unless every initial STT path
is local. Cloud STT receives raw audio before text redaction. A private answer
requires local TTS or text-only output (default for finance). Isolate recall,
background extraction, logs, notifications, tool outputs, prompt/response caches,
crash reports, backups and conversation history as well as storage. No silent
cloud fallback on overload, timeout, unsupported schema or model unavailability.

**Explicit reconciliation:** [platform roadmap T3.4/R7 and T4b](MORTIMER_PLATFORM_ROADMAP.md)
previously retain ElevenLabs and describe private spoken output as an accepted
residual. Larry's latest requirement supersedes that allowance for this proposed
private scope: private financial/email speech may not go to ElevenLabs by
default. Public voice can keep ElevenLabs. Before implementation, the existing
T3/T4 owner must reconcile those canonical sections with this decision; until
then use text-only private output and do not rely on the older residual to send
private data. The user-presence-unlocked encrypted finance tier and read-only
analysis remain prerequisites; no trading, transfers or account mutation.
The verified Air is a prototype target, not automatic satisfaction of the older
mini/G3 financial activation gate. Larry must explicitly reconcile that hardware
gate after local evidence; no ordinary-memory substitution for the encrypted tier.

Use deterministic Decimal or integer-cents calculations with typed currencies,
rounding/date rules, source rows and reproducible formulas. The LLM extracts or
explains; generated prose does not calculate authoritative balances/tax/returns.
Abstain on missing, stale, conflicting or unreconciled records. Local models
still need device protection, least privilege and prompt-injection defenses.

### 5.1 Mail enhancement boundary

First identify the actual deployed daily-report trigger, reader, source limits,
protected result and generic notification without fetching real mail in this
planning task. Preserve the WS-13 revised §R.1 P1–P3 design: bounded isolated
header reader, deterministic host-produced brief, no LLM mail content, fixed
generic spoken notification. Header-only source evidence cannot establish body
or attachment Q&A support. P4 optional model-written prose and P5 interactive
retrieval require an eligible private route and their own authorization.

Later read-only Q&A can locate an appointment message, summarize a selected
thread, explain a report item and propose commitments. Each answer cites message
identity/source, selection/window and completeness; “not found” cannot imply an
exhaustive mailbox search when limits/partial errors apply. Treat hostile mail as
data, never instructions to use network/tools, reveal other mail or create events.
Preserve the mail worker's process isolation and restricted tool surface; do not
add general shell/screen/web tools or route mail through cloud Librarian defaults.
Mail sending, marking/moving messages, calendar writes and automatic commitment
creation are separate features/authorizations, absent from this plan's read scope.

### 5.2 Optional cloud exception — default off, per request

This is a proposed mitigation path, **not approved sharing**. The local host
prepares a preview of the **exact selected excerpt**, destination provider,
model, endpoint, purpose and retention profile. Larry approves that specific
payload for one request; changed content, derived summary, destination, retry
policy or purpose needs a new decision. A refusal or missing policy fails closed.
Never automatically send full records, private audio, attachments or histories.

Before enabling such an exception, verify the exact account/feature's no-training
configuration, storage settings, retention/abuse-monitoring rules and eligibility.
Use ZDR only when supported **and actually enabled** for that endpoint/features;
no-training alone is not ZDR. [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data)
and [Anthropic API retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention)
were checked 2026-10-18; refresh them at approval. ZDR does not remove remote
processing, account, legal or implementation risk. Local redaction/minimization,
restricted network destinations/tools, payload-bound approval and content-free
audits are still required. Test synthetic secret markers through logs, retries,
cache/history replay, tools and background jobs. No cloud exception is required
for useful local finance or mail analysis.

## 6. Rollout, rollback and decisions

Each dispatched increment needs focused offline unit/contract and integration
checks for its actual behavior, the sandbox protocol where voice changes, and
existing required repository/independent verification. Run no live API suite as
part of documentation validation. Record exact tested revisions/settings and
which evidence is simulated versus physical. Existing acceptance requirements
are never replaced by the proposed targets in the appendix.

Roll out later as: synthetic/offline → isolated approved sandbox → reviewed
exact-source candidate → separately authorized narrow pilot → existing release
verification → Larry's merge/deployment/live acceptance. Gate each optional
feature independently; do not activate unrelated memory/mail stages together.

Rollback must restore the last approved model/adapter/config and app artifact
with the existing deploy/rollback mechanism, stop new candidate admission, drain
or fence owned workers, preserve task/result IDs and privacy labels, and reconcile
pending outbox/cancelled actions before resuming. A failed local private route
stays unavailable; rollback never routes private work to cloud. Disable a pilot
without deleting user records, commitments or audit receipts. New schema changes
must document reversible migration or compatible forward recovery before claim.

| Decision still needed | Evidence required before deciding |
|---|---|
| Existing release/acceptance closure after #218/#219 integration | Owning rows' exact-build outcomes; cleanup race/fingerprint repair/review; no gate waiver here |
| Harness implementer, isolated environment, setup/microphone permission and paid-run scope | Non-destructive sandbox isolation receipt, fixture-only tools, explicit provider access and total/per-session spend cap |
| Playback/quality targets and candidate promotion rule | Calibrated unchanged baseline and instrumentation uncertainty; approve proposed thresholds before held-out runs |
| Optimized cascade versus optional Live/Realtime architecture | Paired reliability, useful-audio p50/p95, full cost and blinded preference; retain baseline if inconclusive |
| Local model/runtime revision and private pilot; Air versus mini/G3 | Pinned manifest, quality/resource/coexistence tests and production isolation; explicit canonical hardware-gate reconciliation |
| Private input/output, sink isolation and encrypted tier | No-egress synthetic proof, user-presence unlock/expiry and text-only/local voice decision |
| Any cloud excerpt exception | Exact content/destination/purpose preview and enabled endpoint-specific retention profile; default stays off |
| Mail P4/P5, commitments/events and Jev reconsideration | Verified report gap, private routing/lifecycle prerequisites; Jev only after voice decision and net-benefit replacement design |

## 7. Dated progress

2026-10-18: Saved this plan and both appendices as documentation in WS-27.
Current main/PRs, prior bench, routing/local-runtime refusal and mail/finance
constraints inspected; official source checks are linked. No runtime changes,
models installed, private records read, paid benchmarks, merge or deployment.
