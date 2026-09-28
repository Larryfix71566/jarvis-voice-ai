# Mortimer — Current Review Gaps Implementation Plan

**Prepared:** 2026-09-25  
**Purpose:** give any implementation model a concrete, dependency-ordered handoff for the gaps confirmed by the latest code and plan review, without reopening accepted product or architecture decisions.  
**Target:** dirty isolated worktree `codex/isolated-20260924`, based on `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`.  
**State:** planning and implementation remain in progress. This plan is not evidence of candidate, Mac, provider, privacy, or release acceptance.

## Authority and scope

This is the current execution index for the gaps below. It supplements, and does not replace, the detailed contracts in the [Verified Gap Closure Plan](MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md), [Fresh Review Implementation Plan](MORTIMER_FRESH_REVIEW_IMPLEMENTATION_PLAN_2026-09-25.md), [GC24-03 residual diagnostic plan](MORTIMER_GC24-03_REMAINING_EXCEPTION_LOG_REDACTION_PLAN_2026-09-25.md), [Model Use plan](MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md), [Automatic Memory plan](MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md), [Command Console and Atlas plan](MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md), and [Implementation Status](../acceptance/IMPLEMENTATION_STATUS.md). Those documents own detailed policy and acceptance thresholds. If evidence conflicts, pause that slice and preserve the stricter existing contract; do not invent a new architecture to reconcile it.

This plan covers remaining execution-lifecycle, privacy, model-route, automatic-memory, Knowledge Atlas, and frozen-candidate evidence gaps. Roadmap additions and new interface/product concepts are out of scope.

## Decisions that every implementer must preserve

- Work only in the designated isolated worktree. Reconcile branch, base, HEAD, dirty and untracked files, sibling worktrees, and concurrent file ownership before editing. Preserve all existing user and concurrent changes; do not clean, reset, or overwrite the tree.
- Keep the accepted Command Console, compact Conversation startup, eight sidecar tabs, speaker-aware orb, existing voice transport, keyboard/speech action registry, and response/results pane. Full answers remain in the response/results area; Conversation carries brief captions. One request owns one result identity across streaming, reconnect, cancellation, panel changes, and display moves.
- Retain existing result, display-placement, permissions, action-registry, tool-execution, sandbox/self-edit, and SQLite memory owners. Do not add parallel queues, orchestrators, event buses, result stores, tool executors, or memory databases.
- Preserve exact model identity and quality floors. Identity, workload, access route, capability, privacy eligibility, authentication, and billing evidence remain distinct. No silent fallback, route substitution, privacy downgrade, arbitrary retry, or unknown-as-zero billing.
- Keep Haiku in its accepted supervisor role and preserve the current voice path. Subscription authentication does not itself prove isolation, capability, privacy eligibility, or free usage. Provider tools remain disabled until their permission-checked bridge is proven end to end.
- Keep automated memory strict, quiet, bounded, provenance-aware, reversible, and fail-closed. SQLite stays the system of record. Do not prompt users for routine classifications, replay the 28 historical exchanges, or bulk-relabel existing memories.
- Do not merge, push, publish, deploy, change account settings, enable production memory, or claim release acceptance as part of this implementation plan.

## Verified status at plan creation

| Area | Evidence already in the isolated tree | Remaining work |
|---|---|---|
| Baseline and ownership | Isolated branch and multiple source/test receipts exist. | Reconcile live dirty state and owners before each increment; re-run checks on the exact edited snapshot. |
| GC24-02 execution | Existing voice transcript-to-result path, selected cancellation and terminal-owner fixes, run-scoped claims for selected actions (including the app-build PR submission session claim), provider tool-call replay guards, and unknown-outcome visibility have receipts. A source audit found `app_create` and direct `app_register` lack stable durable approval IDs. | Resolve an explicit preview/action identity contract for `app_create` and whether `app_register` remains directly callable, then add claims and recovery. Finish other action-family reconciliation across caller/run/provider IDs; prove one terminal/result/artifact owner and downstream cancellation/late-write suppression; obtain exact-candidate voice-to-pane evidence. Add generic shared streaming only for an inventoried production caller that needs it. |
| GC24-03 privacy | Protected local-result handoff, policy floors, fail-closed behavior for covered paths, and scoped log-redaction receipts exist. F14–F17 have focused canary receipts against the current source. The security-hardening plan explicitly accepts same-session Supervisor history retention in T4a and assigns private-context handling to T4b. | Complete the end-to-end source-to-sink inventory and negative canaries across every continuation and destination. Do not clear or redact same-session history as a T4a workaround; resolve this continuation sink under the accepted T4b contract. |
| GC24-04 model access | Claude/Codex subscription and SAYGM foundations exist; the call-site inventory reports 26/26. | Prove each supported model/route/workload capability, isolation, privacy eligibility, cancellation/failure semantics, tool bridge, and usage/billing behavior. Disable unsupported combinations. |
| GC24-05 automatic memory | Strict shared classifier, SQLite staging, budgets, provenance/evidence, forget invalidation, claim fencing, crash/retry and multi-process race receipts exist. | Establish an eligible confidential classification route; collect the approved shadow quality/benefit/cost evidence; only then execute staged Mac acceptance and rollback evidence. Production stays disabled/fail-closed until these gates pass. |
| GC24-06 Knowledge Atlas | Refresh lifecycle, last-good state, retries/reconnect, generation checks, run-history refresh, accessibility content, and headless-fixture classification have receipts. | Verify live auth expiry/recovery and source mutations, mounted keyboard/VoiceOver journeys, no duplicate fetch on presentation changes, graph performance on-screen, real unlock delivery, physical display behavior, and current-candidate acceptance. |
| GC24-07–10 candidate/release | Historical interface, monitor, and release receipts exist. | Freeze one exact candidate; run its regression; complete missing physical/provider/memory journeys; independent review; rollback drill; observation window; reconcile every status row to evidence. |

The most recent recorded full Python unit/integration run is **3,054 passed, 4 skipped, 11 warnings, 2 subtests** after the GC24-04 explicit-environment credential guard. See the [dated receipt](../acceptance/verified-gap-closure/GC24-04-explicit-environment-credential-isolation-2026-09-25.md). Treat this strictly as a dirty-tree snapshot result; rerun relevant and full checks after changes. The current macOS test counts and skips are also snapshot-specific. Hardware-, provider-, account-, and candidate-dependent evidence remains unverified unless a new receipt says otherwise.

**2026-09-25 progress — GC24-03 residual log rows F14–F17:** current-source canaries verify self-edit staging fallback without logging staging IDs, override refusal without logging profile/reason, sidecar startup without repository root, and council too-small logging without round/provider details while preserving returned and persisted results. The four focused suites passed **168** with **1 existing Starlette deprecation warning**; Ruff `F`/`I`, compileall, and `git diff --check` passed. See the [F14](../acceptance/verified-gap-closure/GC24-03-selfedit-staging-log-redaction-2026-09-25.md), [F15](../acceptance/verified-gap-closure/GC24-03-model-override-refusal-log-redaction-2026-09-25.md), [F16](../acceptance/verified-gap-closure/GC24-03-sidecar-root-log-redaction-2026-09-25.md), and [F17](../acceptance/verified-gap-closure/GC24-03-council-small-round-log-redaction-2026-09-25.md) receipts. This closes only those diagnostic fields; full privacy source-to-sink coverage remains open.

**2026-09-25 progress — app-build PR submission replay guard:** the existing sandbox session ID now owns a separate durable submission claim. The endpoint preserves validation-before-dispatch, blocks duplicate/ambiguous replay, recovers a saved PR URL, and fails closed when the claim store is unavailable. Focused admin/MCP app-build tests passed **70**, with **1 existing Starlette deprecation warning**; Ruff `F`/`I`, compileall, and `git diff --check` passed. See the [GC24-02 app-build submission receipt](../acceptance/verified-gap-closure/GC24-02-appbuild-submit-session-claim-2026-09-25.md). This does not close other mutation families or live publication acceptance.

**2026-09-25 progress — app-build submission reconciliation and tool status:** submission responses now expose a session-scoped `submission_id`; `app_build_status` can query that exact action. A recovered `publishing`/`publication_pending` session without an old claim remains unknown and is not redispatched, while a persisted PR URL can prove completion. The MCP layer reports unknown honestly and distinguishes an existing PR from a newly started submission. Focused admin/MCP/integration tests passed **76**, with **1 existing warning**. Ruff `F`/`I`, compileall, and `git diff --check` passed; the final full Python unit/integration suite passed **3,053**, with **4 skipped**, **11 warnings**, and **2 subtests**. See the [app-build submission receipt](../acceptance/verified-gap-closure/GC24-02-appbuild-submit-session-claim-2026-09-25.md).

**2026-09-25 progress — app-tool mutation identity audit:** source review confirmed `app_build_start` and the new app-build submit claim are tied to stable run/session identities. `app_create` still replays its confirm from mutable name/template/description without a durable approval ID; direct `app_register` writes the registry with no approval/action claim. The audit records the exact source and contract gap in [GC24-02 mutating caller identity audit](../acceptance/verified-gap-closure/GC24-02-mutating-caller-identity-audit-2026-09-25.md). No identity scheme was guessed and no live GitHub action was performed.

**2026-09-25 validation refresh:** after the app-build submission guard and a timing-robust wait in the self-edit authoring tests, `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` passed **3,053**, with **4 skipped**, **11 warnings**, and **2 subtests**. The authoring API remains asynchronous; the test now accepts and polls its documented `starting` state rather than requiring sandbox setup to finish within the short synchronous response window. This is a dirty isolated-tree result, not a release or live-provider result.

**2026-09-25 design reconciliation — Supervisor history:** source review found that the Security Hardening Plan explicitly accepts same-session Supervisor history retention during T4a because clearing it breaks conversational continuity, and assigns protected context handling to T4b. A candidate deletion change was reverted before delivery because it would violate that accepted behavior. Treat history continuation as an open T4b-dependent privacy sink; do not close it with lossy history deletion or placeholder substitution.

**2026-09-25 progress — protected-result share actions:** added a console-action canary proving a protected result referenced by an image preview cannot reach copy, save, or the system share picker; the existing text-preview and export guards remain covered. `swift test --package-path macos/MortimerHost --filter ConsoleActionCoordinatorTests` passed **16 tests, 0 failures**. See the [GC24-03 share-actions receipt](../acceptance/verified-gap-closure/GC24-03-protected-result-share-actions-2026-09-25.md). This closes only these native result-action sinks; the full GC24-03 inventory remains open.

**2026-09-25 progress — protected renderer boundary:** protected payloads now render only their non-selectable local body. Ancillary image, link, command, and clipboard fields are suppressed, and protected results cannot switch to Sources/Connections views. The rendered-pixel canary plus normal-command accessibility check passed (**2 tests**); the protected share-action suite passed **16 tests**. See the [GC24-03 renderer receipt](../acceptance/verified-gap-closure/GC24-03-protected-display-rendering-2026-09-25.md). This closes only the native renderer and action boundaries; provider, TTS, persistence, other displays, and complete source-to-sink coverage remain open.

**2026-09-25 progress — explicit model-route environment isolation:** checked SAYGM resolution no longer falls back to the process environment when its caller supplies an explicit empty credential mapping. It refuses before catalog access if the configured credential is absent. The routing, route-client, SAYGM, memory-model, and model-execution suites passed **66**; Ruff `F`/`I`, compileall, and `git diff --check` passed. See the [GC24-04 receipt](../acceptance/verified-gap-closure/GC24-04-explicit-environment-credential-isolation-2026-09-25.md). This closes only catalog-credential selection for explicit environments; model capability, runtime isolation, confidentiality, tools, cancellation, and billing remain open.

**2026-09-25 progress — T4a offline V1 security tests:** on the current
Darwin host, the sensitive-detector, child-environment, `requires_env`
snapshot, and agent-isolation suites passed **152**. This is offline unit
evidence only; live process-environment inspection, spoken sensitive-turn,
memory, and paid routing evaluation remain open. See the [T4a receipt](../acceptance/verified-gap-closure/GC24-03-T4a-offline-security-tests-2026-09-25.md).


## Dependency-ordered implementation sequence

### 0. Reconcile source and ownership

Record the current branch, HEAD and base; changed and untracked paths; sibling worktrees and known owners; runtime/toolchain; and the exact test baseline. Inspect the latest status and receipts for every selected row. Do not expose secrets, raw prompts/results, full environments, or private user data in logs or receipts.

**Pass:** each work item has one owner, authoritative contract, exact source/test scope, current evidence, and a bounded next action. No concurrent edits are overwritten.

### 1. GC24-03 F14–F17 focused verification — complete

The latest source review found these rows already changed in the dirty tree. Current-source tests and receipts now verify these bounded diagnostic fields; do not reapply an edit just to match this plan.

The verified source/test pairs are `jarvis/admin/server.py` and `tests/unit/test_admin_selfedit.py` (F14), `jarvis/agents/base.py` and `tests/unit/test_subagent.py` (F15), `jarvis/admin/server.py` and `tests/unit/test_admin_api.py` (F16), and `jarvis/council/council.py` and `tests/unit/test_council_gather.py` (F17).

F14 preserves the single-live-stage fallback while omitting requested and selected IDs; F15 preserves the caller-visible refusal while omitting profile/reason and preventing provider fallback; F16 preserves bounded host/port startup metadata while omitting the repository root; F17 preserves returned and durable council values while omitting round/provider details from logs. Focused canaries and dated receipts are recorded for each row.

**Evidence:** the four focused suites passed 168 tests with one existing Starlette deprecation warning; Ruff `F`/`I`, compileall, and `git diff --check` passed. See the F14–F17 receipts linked above. This does not close full privacy source-to-sink coverage.

### 2. Complete privacy source-to-sink enforcement — GC24-03

Use the existing 26/26 model-call inventory as an input, then map provenance and policy from each source through every continuation to each sink. Include direct and routed model calls, provider tool continuations, MCP/tools, memory read/write/staging, supervisor context, STT/TTS, provider/session persistence, result/display, copy/share/export, logs/telemetry, cancellation/retry, and error paths.

At every existing boundary, enforce the strictest inherited policy before processing or persistence. Keep protected full results local. Where policy permits external coordination, expose only the approved fixed status and opaque reference. Fail closed when there is no eligible route or sink. Add unique synthetic-secret negative canaries at each applicable boundary and assert prohibited sinks receive no secret, including failure, retry, cancellation, and direct-mode branches. Preserve allowed product behavior and existing owners.

Re-scan traceback, exception formatting, interpolated log/print fields, serialization, and wrappers after the F1–F25 rows are verified. Disposition every remaining sink with evidence; do not remove benign diagnostics mechanically.

**Pass:** a complete source-to-sink matrix is checked into the evidence trail; all prohibited paths have negative tests; all remaining sensitive sinks have a documented disposition; and status distinguishes scoped logging work from full privacy closure.

### 3. Complete action lifecycle and mutation reconciliation — GC24-02

Inventory every production caller from admission through provider rounds, tool dispatch, artifacts/results, UI updates, notifications, memory, and durable writes. For each mutating action family, show how stable action identity survives new provider-call IDs, request retries, fresh runs, process restart, and recovery. Use the existing ledger/owners where applicable; do not add a parallel action queue or result store.

Propagate cancellation through provider/tool/UI/durable-write boundaries and suppress all late output after terminal state. For a possibly dispatched mutation with unknown completion, persist a bounded `unknown`/reconciliation-needed state and prohibit automatic replay until action-specific reconciliation proves the outcome. State accurately that cancellation cannot undo an already committed external mutation. Add generic shared text streaming only if a traced production caller needs it; preserve the existing RTVI response stream.

Acceptance must cover duplicate/replayed/new IDs, fresh-run retries, process recovery, claim-store failure, cancellation before and after dispatch, non-cooperative providers/tools, late writes, exactly-one terminal event/result, and unknown-outcome recovery for every inventoried mutation family.

**Pass:** every production caller has an identified lifecycle/result owner; no unresolved mutation can be automatically replayed; no post-terminal side effect or duplicate result occurs; and the exact candidate demonstrates one spoken request reaching one response pane.

### 4. Prove model access by exact route and workload — GC24-04

For each configured model/workload/access route, record exact identity, runtime/version, authentication source, supported text/image/stream/tool capabilities, cancellation, privacy eligibility, isolation, limits, failure behavior, and usage/billing basis. Test subscription and API routes independently in a task-scoped, isolated process with an allowlisted environment, no project instructions/hooks/plugins/MCP/provider tools unless that capability is the explicit subject of the test, no persistent session, bounded process-group cleanup, and no late child output.

Parse success and error envelopes; process exit alone is insufficient. Keep unknown usage unknown. Provider tools stay unavailable until the existing Mortimer permission-checked bridge is proven end to end. Do not infer confidential processing from a login, key, catalog record, or successful public probe.

**Pass:** each supported route has secret-free evidence for identity, individual capabilities, isolation, privacy eligibility, cancellation, and billing semantics; every unsupported or unproved combination is unavailable without fallback.

### 5. Finish automatic-memory shadow and staged acceptance — GC24-05

Keep current SQLite ownership, classifier, provenance, evidence rules, budgets, idempotency, forgetting, and fail-closed controls. Complete deterministic durability tests for any uncovered crash boundary, then establish that the selected classification route is eligible for confidential content using GC24-03/04 evidence. Run the existing shadow evaluator and record denominators, quality, user value, latency, cost, errors, backlog, and decisions against the already approved thresholds.

Only after the route/privacy and shadow gates pass, follow the existing staged Mac rollout, observation period, and rollback runbook. Never replay the historical 28 exchanges as part of this plan.

**Pass:** deterministic durability and concurrency tests pass; route/privacy proof passes; shadow metrics meet existing thresholds; staged rollout and rollback have dated receipts. Otherwise production remains disabled/fail-closed.

### 6. Complete live Knowledge Atlas acceptance — GC24-06

On the exact candidate, exercise source authentication expiry/recovery, source mutation, stale last-good data, partial failure, retries, and reconnect for every supported source. Verify keyboard-only and VoiceOver navigation, focus, labels, values, and announcements. Prove presentation/tab/display/size changes do not duplicate fetches. Measure on-screen graph responsiveness/resource use on the approved fixture. Verify actual unlock delivery and physical display journeys; keep headless fixture skips limited to tests that truly require a visible display.

**Pass:** source lifecycle, accessibility, fetch identity, performance, unlock, and physical display receipts meet the existing Atlas acceptance plan on the candidate.

### 7. Freeze and accept one candidate — GC24-07–10

After source and route prerequisites pass, freeze the exact source SHA, app bundle identity, backend revision, non-secret effective configuration and feature gates. Run regression against that exact artifact. Complete the missing physical Mac journeys: compact startup, voice/mute/orb, one response identity, monitor connect/disconnect/reconnect/rehome, Atlas, text/image sharing, privacy boundaries, memory disabled then eligible staged route, and sandboxed self-edit through spoken preview and PR approval. Obtain independent review, demonstrate rollback, observe for the already required period, then reconcile every checklist/status row to a dated receipt.

**Pass:** every required source, provider, privacy, memory, Atlas, physical-device, review, rollback, and observation gate is evidenced against the frozen candidate. Implementation, merge, deployment, production enablement, and release remain distinct decisions.

## Handoff requirements for any model

Before each slice, read this plan, its authoritative feature contract, the latest relevant receipt, and repository instructions; inspect current source and dirty state; choose one bounded change and state its invariant. After each slice, run focused tests and applicable lint/build checks, broaden tests when the changed boundary warrants it, review the diff for unrelated changes and privacy regressions, and write a dated receipt with exact commands, counts, failures/skips, snapshot identity, and remaining gates. Update status only to the level the receipt proves. Leave work uncommitted and unpushed.

If a required secret, interactive display, live provider, physical Mac journey, or exact candidate is unavailable, complete independent deterministic work and record the hardware/provider gate as open. Never label unavailable evidence as a pass. Stop only the affected slice when contracts conflict, ownership is unclear, or a privacy/cancellation invariant cannot be preserved; document the exact unresolved decision while continuing independent work.
