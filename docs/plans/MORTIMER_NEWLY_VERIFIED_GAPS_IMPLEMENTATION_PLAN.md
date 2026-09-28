# Mortimer — Newly Verified Gaps: Model-Ready Implementation Plan

**Prepared:** 2026-09-24; refreshed 2026-09-25 after the terminal-completion
crash boundary and full Python regression run.
**Purpose:** give a new model an ordered, bounded plan it can execute without
re-deciding product design, security architecture, provider policy or test
acceptance.
**Working tree:** `codex/isolated-20260924` at base `977f50b`, with the
uncommitted changes listed in the existing GC24-02/03 receipts and the GC24-06
receipt. This is not a clean-tree or release statement.
**Authority:** this plan supplements, and does not loosen, the
[Verified Gap Closure plan](MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md), the
[Model Use plan](MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md), the
[Memory plan](MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md), the
[Command Console and Atlas plan](MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md), and
[`ARCHITECTURE.md`](../ARCHITECTURE.md).

**Current-state authority (2026-09-25):** use this as the model-ready task
sequence, together with the [Current Verified Gaps Implementation
Plan](MORTIMER_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md) for the latest code,
receipt, test-count, and remaining-gap evidence. When these documents differ,
the current verified-gaps plan and named feature acceptance plans control.

## 1. Goal and non-goals

Close the implementation and evidence gaps that remain after the recent code
and plan review. Keep the product that Larry selected. Work only in the
assigned isolated worktree, reconcile incoming changes before touching shared
files, and deliver reviewable increments with tests and dated evidence. Do not
deploy, publish, merge, push, change provider accounts, or access the Mac vault
from this worktree as part of implementation.

This plan does not add another interface, agent orchestrator, memory database,
voice path, model fallback, or roadmap feature. Home automation, surveillance,
investing, Jev, local voice migration, and new product concepts remain outside
this closure scope.

## 2. Binding decisions: no implementer discretion

### Product and interface

- Keep Command Console/layout 2 with compact Conversation as startup; retain
  the eight sidecar tabs, scrollable headers, working font picker, keyboard
  and voice controls, accepted glass/comet/orb design, and explicit rollback
  to the legacy layout.
- Full answers live in the response/results area; conversation shows brief
  live captions. One request owns one result identity; later output appends to
  it. Moving a display or reopening a panel must not start another fetch or
  model call. Keep the existing one-to-four tile supporting-stage limit,
  pins, return locators and single app-owned placement/client/workspace.
- Keep user/Mortimer speaker colors and connected idle animation even while
  the microphone is muted. Voice amplitude reflects measured audio. Do not
  resurrect deleted wave paths/sliders or change Crystal renderer code in
  this work.
- Pointer, keyboard and speech continue to use the same validated action
  registry. No second audio capture tap or competing console.

### Models, security and memory

- Preserve the exact selected model and existing quality floor. Model identity,
  workload and access route are distinct. No silent fallback, paid API fallback,
  privacy downgrade, arbitrary retry or substitution.
- Keep Haiku in its voice-supervisor role and preserve the current STT/TTS and
  voice transport. Do not move the voice loop to subscriptions or SAYGM here.
- Subscription access uses supported first-party authentication. Do not store
  account passwords, copy OAuth material, emulate web login, or move the Mac
  vault into this repository/worktree. Keep API secrets in the existing Mac
  vault.
- A subscription provider gets tools only through the task-scoped Mortimer
  bridge, existing permission checks and existing sandbox/self-edit executor.
  If the pinned provider runtime cannot enforce that boundary, its capability
  remains text-only/unavailable.
- Confidential routing requires verified model/route capability; a key, a
  catalog listing or successful public probe alone does not prove confidential
  compute. Keep protected content local when no compliant route exists.
- SQLite remains the sole memory system of record. Keep provenance, revisions,
  idempotency, budgets, rollback, deletion and quiet operation. Never ask the
  user to label routine memories. Do not replay the already recovered 28
  exchanges or bulk relabel old records.
- Self-edit begins after the spoken preview and remains in its existing
  sandbox; PR approval remains the external change boundary.

## 3. Current verified state

The source audit baseline was main PR #90 (`4acb4dc`); the isolated worktree
has advanced beyond that snapshot. The following is a concise gap map, not
an assertion that the source is merged, deployed, or accepted on the Mac.
Before implementation, reconcile every row against the latest receipt and
current verified-gaps plan. Never infer closure from a prior test count.

| Area | Implemented in the isolated tree | Still open |
| --- | --- | --- |
| Execution contract (GC24-02) | Shared execution primitives and selected caller migrations; delegate terminal lifecycle; SubAgent cancellation suppression; duplicate provider tool-call ID guards in direct SubAgent, self-edit planner, and live Supervisor loops. The voice RTVI transcript streams to the existing result router; focused client-frame (2), stub transport-to-router integration (1), and result-router (7) tests pass. See the [voice stream receipt](../acceptance/verified-gap-closure/GC24-02-existing-voice-response-stream-path-2026-09-25.md) and current dated execution receipts. | No production consumer connects generic shared-execution `ModelExecutionEvent.text_delta` events to the existing result owner; live voice frame-to-pane candidate proof; terminal/tool/artifact ownership over every caller loop; downstream cancellation and late-write suppression; durable unknown-mutation reconciliation; coverage of remaining callers. |
| Policy enforcement (GC24-03) | Static workload floors, sensitive routed SubAgent controls, protected local-result handoff, response-pane copy/share/export blocking, and redaction on covered logs/status paths. | Complete source-to-sink enforcement and negative canaries across provider continuations, tools, memory injection/staging, supervisor/TTS, share/export, telemetry, provider persistence, response/display, and direct-mode paths. |
| Subscription/SAYGM (GC24-04) | First-party CLI and SAYGM foundations/configuration; call-site inventory reports 26/26 covered, zero review-required, and secret-free. | Per-model/per-route capability and billing receipts, runtime isolation, confidential-route evidence, and full task-scoped tool bridge proof. Tool execution remains unavailable through subscription adapters until all gates pass. |
| Automatic memory (GC24-05) | Shared strict classifier adapter; durable extract/classify/apply staging; atomic shared budget reservations; source-turn evidence checks; forget invalidation; digest-only shadow records; claim-timestamp fencing at stage transitions and the apply transaction; child-process tests prove apply and terminal-completion rollback/retry, enqueue/cursor recovery, and extract/classify recovery before commit and after committed transitions; simultaneous independent SQLite worker connections claim a due job exactly once; deterministic forget-during-apply test confirms no forgotten fact remains after transaction serialization. A stale apply-claim regression proves a lease-replaced worker cannot write and the current claim completes once. Latest focused admission/worker/acceptance run passes 74 tests. | Multi-process duplicate-worker proof and cross-process forget/reclaim race coverage; production remains fail-closed without verified confidential route evidence; shadow/benefit and staged Mac acceptance remain. |
| Knowledge Atlas (GC24-06) | Store-owned source refresh, last-good/stale retention, generation guards, retry/recovery/coalescing, and run-history refresh on completed agent runs; focused Atlas suite passes 10 tests. | Live auth recovery, reliable additional source-change events, VoiceOver/keyboard/reduced-motion acceptance, no duplicate fetch on view/display moves, graph/frame performance, and candidate acceptance. Eight headless window-visibility fixture failures remain reported. |
| Candidate and release (GC24-00/07–10) | Historical Mac receipts and current isolated-source receipts exist. | Exact app/backend/config/gate identity; current full candidate regression; physical Mac journeys; model/memory pilots; independent review; executable rollback; and required observation window. |

The isolated directory contains extensive dirty and untracked files, including
concurrent implementation changes. Never infer ownership from a matching
design goal. Before touching code, compare branch, worktree, file diff,
receipts, and exact ownership. Do not reset, overwrite, or transplant work.

**Current verification reference (2026-09-25):** the current isolated tree's
latest complete Python unit/integration run passed **2,908 tests, 4 skipped,
11 warnings, and 2 subtests**. The memory admission/worker/acceptance focused
suite passed **74 tests**. Terminal-completion rollback, stale apply-claim
fencing are now covered: the child exits after the completion update but
before SQLite commit; the transaction rolls back, the apply lease is reclaimed,
and one retry writes one fact and one shadow record; a replaced claim cannot
apply; two simultaneous SQLite connections claim a job only once; forgetting
during apply leaves no fact behind. See the
[apply/enqueue/stage/completion crash receipt](../acceptance/verified-gap-closure/GC24-05-admission-apply-rollback-2026-09-25.md),
[apply claim-fencing receipt](../acceptance/verified-gap-closure/GC24-05-admission-apply-claim-fencing-2026-09-25.md),
the [concurrent claims receipt](../acceptance/verified-gap-closure/GC24-05-admission-concurrent-claims-2026-09-25.md),
and the [forget/apply receipt](../acceptance/verified-gap-closure/GC24-05-admission-forget-apply-race-2026-09-25.md).
These counts describe this dirty snapshot only. Re-run affected suites after
source changes. The 26/26 call-site audit proves inventory coverage, not
end-to-end lifecycle or privacy closure.

## 4. Work sequence and dependency graph

Only implement the next unblocked slice. A later phase can be prepared in
parallel only when it does not modify the same contract/files and cannot
change the earlier phase's decisions.

```text
GC24-00 baseline
  ├── GC24-01 status/source reconciliation (closed in current plan)
  ├── GC24-02 shared execution boundary
  │     └── GC24-03 every transmission/result sink
  │           ├── GC24-04 subscription/SAYGM gates
  │           └── GC24-05 production automatic memory
  ├── GC24-06 Atlas lifecycle (independent; implementation in progress)
  └── GC24-07 exact candidate/regression
        ├── GC24-08 physical Mac journeys
        ├── GC24-09 staged pilots
        └── GC24-10 independent review, rollback, release acceptance
```

Do not enable a feature gate just because its implementation suite passes.
Source implementation, merge, candidate build, deployment, live verification
and user acceptance are separate statuses.

## 5. Task cards

Each task card is a bounded unit. Preserve the named authoritative spec, write
one dated receipt per increment, update the existing status row, and retain
failed/skipped tests in the denominator. Do not close a parent task until its
whole acceptance statement passes.

### A. GC24-00 — Re-establish the exact baseline

**Edit:** dated acceptance receipt and status references only.

1. Record branch, base/current SHA, dirty files, main/remote-main state when
   available, linked worktrees, concurrent Claude work and ownership conflicts.
2. Map each open requirement to current code, tests, receipts and missing
   acceptance. Mark unknowns as unknown.
3. Identify running app executable, backend working tree/revision, process
   starts, effective feature flags and model route using nonsecret fields.
   Never print complete environments, vault contents or authenticated data.
4. Record platform/toolchain/test baseline before a file family is changed.
   Keep pre-existing failures distinct from new regressions.

**Pass:** a dated, reproducible baseline with current runtime identity or
explicitly unverified runtime; no source or shared-tree writes.

### B. GC24-02 — Finish shared execution and lifecycle

**Edit:** `jarvis/model_execution.py`, related routing/usage records, one caller
family at a time, plus focused unit/integration tests. Read the complete GC24-02
contract first; this card is not a replacement for it.

1. Preserve ordered role-aware context and supported attachments; reject
   unsupported payloads before client creation. Keep task model/route/policy
   immutable once admitted.
2. Carry allowlisted Mortimer tool references, output requirements, deadline,
   cancellation and parent request identity. Provider data cannot grant a new
   tool or permission.
3. Normalize queued/start/progress/text/tool/artifact and exactly one terminal
   event. Sequence numbers are monotonic. Cancellation/timeout prevents every
   late text, tool, artifact, UI or DB write. Reconcile mutating tool IDs before
   any retry.
4. Preserve direct adapter prompts, streaming, tool loops and response
   semantics. `execute_chat` remains the compatibility collector. Migrate
   one inventoried caller family and prove parity before the next.
5. Add a process-owned interactive/background admission limit shared by async
   loops and worker threads. Do not create per-loop quotas or throttle voice.

**Required tests:** context order/role; image accept/reject with zero send on
reject; immutable selection; first/terminal ordering; queued and active cancel;
timeout and late completion; exactly one terminal event; tool replay;
interactive capacity while memory work queues; direct API parity; grouping by
parent request; audit covers each migrated caller.

**Pass:** all accepted input is preserved; every migrated caller crosses the
boundary; original direct behavior is covered; no uncaught late side effect.
Do not report event types as streaming-complete until production event
consumers and terminal semantics are tested.

### C. GC24-03 — Close all policy transmission and sink paths

**Edit:** `privacy_policy.py`, routing/preferences, shared execution, relevant
provider/tool/memory/supervisor/speech/sharing/log/export call sites, and
negative tests. Inventory from `scripts/audit_model_call_sites.py`; do not
assume the central helper covers a sink unless its call path proves it.

1. Resolve policy locally from workload plus all input provenance. Combine
   restrictions with strictest-policy. User/provider text cannot lower it.
2. Check every model request, tool continuation/result, memory injection,
   supervisor context, TTS, provider persistence, sharing/export and telemetry
   destination before transmission or persistence.
3. Keep disallowed full results local. Supervisor receives only a fixed status
   and opaque reference when policy requires it. Never leak protected content
   in normal logs, errors, receipts or route-readiness output.
4. Validate route, model capability and availability before activating a
   setting. A workload with no compliant route stays unavailable with a clear
   reason; do not invent local execution or silently use API.
5. Preserve allowed personalization and voice behavior rather than deleting
   context wholesale to make tests pass.

**Required tests:** one synthetic canary through every inventoried path;
assert zero transmissions and zero payload leakage for every forbidden sink;
mixed policy, sensitive mid-task result, unavailable route, configuration
change during task, receipt/log redaction.

**Pass:** complete sink inventory + negative tests + no downgrade. Never claim
the voice conversation is fully local; its accepted external STT/supervisor
route remains.

### D. GC24-04 — Prove model-access capabilities independently

**Edit:** subscription/SAYGM adapters, `config/model_access.yaml`, verifier
scripts and capability tests, following GC24-04 of the authority plan.

1. At implementation time, check official documentation for the pinned
   provider CLI/runtime and record exact version, supported auth, prompt input,
   streaming, image, tool and cancellation capabilities. Unsupported means
   unavailable; do not guess a flag/API.
2. Prove task-scoped process isolation: clean working directory, allowlisted
   environment, no project instructions/hooks/plugins/MCP or provider-native
   tools, no persistent session, safe stdin/file input, process-group cancel,
   bounded cleanup, no child/late output.
3. Parse supported output envelopes and classify auth, allowance, capability,
   timeout, cancellation and provider errors truthfully. Exit code zero alone
   is not success. Separate list-cost estimate from actual account billing.
4. Keep provider tools disabled until a per-task Mortimer bridge uses the
   existing registry, permission checks, sandbox/self-edit path, policy check,
   idempotent receipts and timeout handling; prove all alternative tools off.
5. Verify each model ID and route independently for text/images/tools/JSON and
   privacy. A successful public probe/key/catalog does not prove confidential
   compute. Do not transmit actual memories as a smoke test.

**Pass:** separate route/model/capability/billing/privacy receipts; tools stay
disabled when either bridge or runtime boundary cannot be proven. No API
fallback is introduced.

### E. GC24-05 — Wire automatic classification into real admission

**Edit:** existing memory classifier/extraction worker/watcher, one additive
SQLite migration if the authority plan's table is still absent, policy-bound
model adapter and tests. Reuse existing records and budget ledger.

1. Make production worker and shadow runner call the same strict
   `classify(candidates, *, policy_version)` adapter. Keep deterministic
   heuristics as baseline/rejection checks, not a purported model-success
   fallback.
2. Bound redacted input/output, tools/write authority and retries exactly as
   section B7/GC24-05. Validate the whole batch and verify evidence against
   stored source turns before any write. Assistant quotes are not user proof.
3. Persist an idempotent staged job before advancing the extraction cursor;
   commit each stage, recover after restart, and recheck revision/deletion/
   policy/cancellation before apply. Keep provider calls outside DB write
   transactions. Do not repurpose `memory_extraction_pending`.
4. Reuse persisted daily quotas atomically across workers. Preserve pending
   work on failure. Shadow never alters live retrieval/admission. Forget/delete
   purges staging payloads and invalidates active jobs.
5. Keep maintenance quiet, off voice path, reversible and within the existing
   budget/retry policy. No history replay, bulk relabel, cleanup greeting or
   user memory-classification prompt.

**Required tests:** exact accepted B5/B9 floors; malformed/extra/missing rows;
fabricated or duplicate evidence; concurrent correction/forget; crash at every
stage/cursor boundary; duplicate worker/teardown enqueue; restart and shared
budget races; shadow prompt invariance; provider failure preserves queue and
voice behavior.

**Pass:** real worker and shadow share the tested adapter and durable job
contract; feature remains staged/disabled until GC24-09 pilot evidence.

### F. GC24-06 — Finish Atlas acceptance around implemented refresh lifecycle

**Edit:** `KnowledgeAtlasView.swift`, `AtlasStore.swift`, tests and receipt only
if gaps remain; do not add a new data source or alter the accepted layout.

1. Retain per-source loading/empty/loaded/failure status, last-good stale
   cards, retry, reconnect trigger, cancellation and generation protection.
2. Complete source-change event wiring only for existing reliable events;
   do not add aggressive polling, duplicate websocket or fetch-on-display-move.
3. Add/verify independent partial failure, auth-expiry/recovery, cancellation
   and manual retry tests. Assert selection, groups and pins survive refresh.
4. On a current Mac candidate, check VoiceOver labels, keyboard retry, useful
   context without a research result, freshness truth, performance and no
   duplicated requests when moving Atlas between displays/tabs.

**Pass:** all authority-plan criteria and existing graph/performance gates pass
on the same identified candidate. The ten focused Atlas tests are
implementation evidence only; the eight known headless window-visibility
failures stay visible and are not waived by changing their thresholds.

### G. GC24-07 through GC24-10 — Candidate, journeys, pilots and release

**Edit:** existing launcher/config validation, readiness and acceptance
runbooks/receipts. Use `macos/MortimerHost/scripts/bundle.sh` for the native
candidate. Do not silently enable the console, sharing, model routing or memory
just because layout 2 is selected.

1. Resolve effective runtime gates and candidate identity. Validate each
   independent feature capability and report disabled functions truthfully.
2. Run locked Python/Swift/integration/eval suites, call-site/policy audits,
   memory budget/retry checks, graph/frame budgets, build/sign/package checks.
   Record executed/pass/fail/skip denominators; keep known fixture failures.
3. On hardware availability, finish only missing user journeys: one external
   monitor attach/detach/reconnect, result grouping/return, voice response,
   sharing, accessibility, no duplicate fetch, exact installed app/service
   identity. Do not multiply windows/results during display moves.
4. Run model and memory pilots using synthetic data first and explicitly
   approved routes. Record actual model, auth mode, privacy, billing evidence,
   usage/budgets, quality floor, latency and rollback triggers. Never transmit
   historical memories as an access probe.
5. Independent reviewer checks code, evidence, rollback, all status IDs, exact
   candidate configuration and five-day observation. User deployment or
   external account/hardware steps remain a distinct final action.

**Pass:** candidate matches tested source/config; all applicable gates pass;
failed/skipped hardware/provider items remain open; rollback is demonstrated;
no release claim is inferred from a merge or a source-only test.

## 6. Required handoff for every model turn

Before editing, read this file, the matching GC24 section, authoritative
feature plan, latest receipt, `git status`, and the exact changed source/test
files. Then:

1. State internally the next bounded task, current owner and files shared with
   other work. Do not overwrite concurrent work.
2. Add meaningful tests before claiming implementation. Run the narrow suite,
   then all affected locked suites and audits. Include known failures/skips.
3. Update the task's existing status and add a dated receipt containing branch,
   base/current SHA, dirty-file list, exact commands, counts, key outcomes and
   limitations. Do not claim a deployment that was not inspected.
4. `git diff --check`; validate documentation links and manifests where
   affected. Inspect final diff for secrets, copied vault files, weakened
   defaults, arbitrary model fallback, or unrelated design changes.
5. Leave changes uncommitted/unpushed unless the user separately asks for
   those operations. Never work in Claude's tree or main by default.

## 7. Completion vocabulary

- **Planned:** no implementation evidence.
- **Implemented in isolated tree:** source and focused tests are present; not
  necessarily merged or enabled.
- **Merged:** source exists in the named branch; not proof of local deployment.
- **Candidate verified:** exact artifact/config passes required regression.
- **Live acceptance complete:** user journey on identified deployment/hardware
  has a dated receipt.
- **Released/closed:** all prerequisite gates, rollback and observation
  criteria are met and recorded.

Never replace these distinctions with an overall percentage unless the status
owner has published the requirement denominator and deduplicated aliases.
