# Mortimer — Model-Neutral Gap Implementation Plan

> **Archived 2026-09-28 — superseded as an execution index.** The canonical plan is [MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md](../plans/MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md). This archive preserves the original requirements and evidence for history; it does not mark any gate complete.


**Prepared:** 2026-09-25  
**Purpose:** provide a bounded, decision-safe implementation handoff for the gaps confirmed in the latest source and plan review. Any capable coding model should be able to execute the open work without changing the accepted product, architecture, privacy policy, or acceptance thresholds.  
**Target tree:** `/Users/larryfix/Documents/Codex/2026-09-09/can/work/codex-isolated-20260924`, branch `codex/isolated-20260924`, base `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`. This is a dirty, shared isolated worktree.  
**Status:** handoff prepared; implementation and acceptance remain open. This document is not evidence of merge, deployment, live-provider, Mac, or release acceptance.

## Authority and precedence

This document is an execution index, not a replacement for detailed contracts. Follow the [Verified Gap Closure Plan](../plans/MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md), [Current Review Gaps Plan](../plans/MORTIMER_CURRENT_REVIEW_GAPS_IMPLEMENTATION_PLAN_2026-09-25.md), [Fresh Review Plan](../plans/MORTIMER_FRESH_REVIEW_IMPLEMENTATION_PLAN_2026-09-25.md), [GC24-03 residual diagnostic plan](../plans/MORTIMER_GC24-03_REMAINING_EXCEPTION_LOG_REDACTION_PLAN_2026-09-25.md), [Model Use Enhancements Plan](../plans/MORTIMER_MODEL_USE_ENHANCEMENTS_PLAN.md), [Automatic Memory Plan](../plans/MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md), [Command Console and Atlas Plan](../plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md), and [Implementation Status](../acceptance/IMPLEMENTATION_STATUS.md). The linked specifications own product behavior, thresholds, and feature-specific acceptance. If this handoff conflicts with one of them, stop that slice and preserve the stricter authoritative contract; do not resolve the conflict by inventing behavior.

At plan creation, the consolidated review plan recorded **3,053 passed, 4 skipped, 11 warnings, and 2 subtests**. Re-run checks after changes and record the exact snapshot. Treat hardware, provider, account, candidate, and production evidence as unknown unless a dated receipt demonstrates it.

## Locked design and safety constraints

- Work only in the designated isolated worktree. Before touching a file, inspect branch, HEAD/base, dirty and untracked state, sibling worktrees when available, the latest receipt, and file ownership. Preserve concurrent changes. Do not reset, clean, overwrite, commit, push, merge, publish, deploy, or access the Mac vault from this work.
- Preserve Command Console with compact Conversation startup, all eight sidecar tabs, accepted orb and speaker colors, existing voice transport, keyboard/speech action registry, and response/results pane. Full responses belong in the response/results area; Conversation carries brief live captions. One request keeps one result identity across streaming, retry, cancellation, panel changes, and display moves.
- Retain existing execution, action registry, permission, tool, sandbox/self-edit, display-placement, result, and SQLite memory owners. Do not add parallel orchestrators, queues, buses, result stores, tool executors, or memory databases.
- Keep exact model identity, workload, access route, capability, privacy eligibility, authentication, and billing as separate facts. Preserve quality floors. No silent route fallback/substitution, privacy downgrade, arbitrary retry, or unknown-as-zero accounting.
- Keep Haiku in its accepted supervisor role and preserve the current voice path. Subscription authentication does not prove process isolation, tool capability, privacy eligibility, or zero marginal billing. Provider-native tools remain unavailable until the task-scoped Mortimer bridge is proven end to end.
- Keep automatic memory quiet, strict, bounded, provenance-aware, reversible, and fail-closed; SQLite remains the system of record. Do not ask users to classify routine memories, replay the recovered 28 exchanges, or bulk-relabel old data.
- Keep self-edit inside its existing sandbox. It begins after the spoken preview; PR approval remains the external change boundary.
- Implementation, source merge, candidate build, deployment, production enablement, and user acceptance are distinct states. Mark only what the evidence proves.

## Confirmed gaps and execution order

| Order | Workstream | Verified partial state | Open gate |
|---|---|---|---|
| 0 | Snapshot and ownership | Isolated worktree and multiple dated receipts exist. | Reconcile current dirty state and concurrent file owners before every slice. |
| 1 | GC24-03 privacy source-to-sink closure | Policy floors, protected local-result handoff, scoped diagnostic-redaction receipts (including F14–F17), mid-task tool-result stop behavior, protected-result copy/save/share guards, and a body-only protected renderer are evidenced. Same-session Supervisor history retention is accepted for T4a; protected-context handling is deferred to T4b. | Complete source-to-sink enforcement and negative canaries over continuations, persistence, result/display, sharing/export, logs/telemetry, and error/cancellation paths. Keep the history continuation gate under T4b and preserve conversation continuity. |
| 2 | GC24-02 lifecycle and mutation identity | Existing voice transcript-to-result path, selected terminal/cancellation fixes, tool-call replay guards, run-scoped claims for selected actions, and app-build submission claim/status have receipts. | Complete action-family lifecycle and unknown-outcome recovery. `app_create` lacks stable durable approval identity; direct `app_register` lacks a claim. |
| 3 | GC24-04 model access | Claude/Codex subscription and SAYGM foundations exist; call-site inventory reports 26/26 coverage. | Prove every enabled model/route/workload capability, isolation, privacy eligibility, cancellation/error behavior, tool bridge, and billing semantics. |
| 4 | GC24-05 automatic memory | SQLite staging, strict classification, provenance/budgets, forget invalidation, claim fencing, crash/retry and selected concurrency evidence exist. | Prove eligible confidential route; complete approved shadow benefit/quality/cost evidence; then staged Mac acceptance and rollback. |
| 5 | GC24-06 Knowledge Atlas | Refresh/recovery/last-good lifecycle and selected accessibility/fetch-identity receipts exist. | Live auth recovery/source change, mounted keyboard/VoiceOver, no duplicate fetch on presentation changes, visible graph performance, unlock delivery, physical display and candidate acceptance. |
| 6 | GC24-07–10 candidate/release | Historical receipts exist. | Freeze exact candidate, run exact-artifact regression, finish required physical/provider/memory journeys, independent review, rollback drill, observation period, and status reconciliation. |

## Work packages

### WP0 — Establish the current baseline (read-only)

Before each implementation slice, record branch, base/HEAD, modified and untracked paths, known concurrent owners, runtime identity if verifiable, toolchain, and the relevant test baseline. Never print secrets, complete process environments, prompts, results, or private records. Compare the current source with the cited receipt; a receipt from an earlier snapshot is not proof of current behavior.

**Deliverable:** dated, secret-free baseline note with unknowns explicitly labeled. **Pass:** every selected task has one owner, an authoritative contract, exact source/test scope, and a bounded next action; no existing edit is overwritten.

### WP1 — Complete GC24-03 privacy source-to-sink closure

Use the model call-site inventory as a starting index, not as proof of complete privacy coverage. Build a source → provenance/policy → transformation/continuation → sink matrix. Include direct and routed model calls; provider tool rounds and MCP tools; memory reads, writes, and staging; supervisor context; STT/TTS; provider/session persistence; results and display; clipboard/copy/share/export; logs, exceptions, telemetry, receipts; retries, cancellation, and direct-mode branches. Include the residual F1–F25 diagnostic rows and verify each receipt against current source.

At each existing boundary, enforce the strictest inherited policy before processing, transmission, or persistence. Keep disallowed full results local; where allowed, external coordination may receive only the approved fixed status and opaque reference. If no compliant route or sink exists, fail closed and explain the unavailable capability without leaking protected values. Do not remove all context or benign diagnostics as a shortcut. The [Security Hardening Plan](../plans/MORTIMER_SECURITY_HARDENING_PLAN.md) explicitly accepts same-session Supervisor history retention during T4a to preserve continuity and assigns protected-context handling to T4b (R-H7). Do not try to close that sink with lossy history deletion or placeholder substitution; track it as a T4b-dependent gate.

**Required evidence:** unique synthetic-secret canaries at every applicable source-to-sink path; assert forbidden sinks receive zero payload in success, provider continuation, error, retry, cancellation, and direct-mode cases. Re-scan interpolated fields, traceback formatting, serialization, and wrappers. Every inventory row ends with a passing canary or a documented, contract-approved disposition.

### WP2 — Finish GC24-02 lifecycle and mutation reconciliation

Start with a read-only inventory of every production caller from admission through provider rounds, tool dispatch, cancellation, terminal event, artifact/result routing, UI, notifications, memory, and durable writes. Follow [GC24-02 execution contract](../plans/MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md) and existing caller receipts. Migrate or repair one caller family at a time, preserving its existing prompt, model, route, tool permissions, streaming semantics, and result owner.

For every mutation, identify stable action identity across regenerated provider-call IDs, request retry, fresh run, restart, and recovery. Use existing run/action ledgers where their identity matches the operation. Persist bounded `unknown`/reconciliation-needed state after ambiguous dispatch and prohibit automatic replay until action-specific evidence resolves it. Cancellation must suppress later provider/tool/UI/database effects; document that it cannot undo a mutation already committed externally. Preserve the existing RTVI response stream. Add generic event streaming only where a traced production consumer requires it.

**Unresolved contract; do not guess:** decide how `app_create` obtains a stable approval/action ID that binds preview to confirm, and whether `app_register` remains directly callable or must use a confirmed action. Until that contract is supplied, keep these operations fail-closed and continue independent lifecycle work. Do not manufacture IDs from mutable descriptions or silently change user-visible confirmation semantics.

**Required evidence:** repeated/new IDs, fresh-run retry, restart recovery, claim-store failure, pre/post-dispatch cancellation, non-cooperative provider/tool, late write, exactly-one terminal/result, and unknown-outcome reconciliation for each inventoried mutation family. Exact-candidate proof must show one spoken request reaches one result pane.

### WP3 — Prove GC24-04 model access per exact route

For every configured model × workload × access route, record exact model/runtime version, authentication source, supported text/image/stream/tool/structured-output capabilities, cancellation, privacy eligibility, isolation, limits, failure modes, and usage/billing basis. Check the provider's official documentation for the exact pinned runtime when capability is not already established; never infer support from a successful login or public probe.

Exercise subscription and API routes independently in task-scoped processes with allowlisted environments, bounded process-group cancellation/cleanup, no persistent session, no late child output, and no project instructions/hooks/plugins/MCP/provider tools unless that specific capability is under test. Parse success and error envelopes; exit code zero alone is insufficient. Keep unknown usage unknown. Provider tools stay disabled unless their task-scoped Mortimer bridge passes through the existing registry, policy, permissions, sandbox/self-edit execution and durable result handling.

**Pass:** each supported combination has a secret-free capability/isolation/privacy/cancellation/billing receipt. Every unsupported or unproven combination remains unavailable with no fallback or route substitution.

### WP4 — Finish GC24-05 automatic-memory shadow and staged acceptance

Preserve SQLite ownership, approved classifier behavior, provenance/evidence, budgets, idempotency, forgetting, rollback and quiet UX. Review durability/concurrency coverage against the memory plan and add tests only for uncovered crash or race boundaries. First prove the selected classification route is eligible for confidential content using WP2 and WP3 evidence. Then run the approved shadow evaluator and report denominators, quality, measured user value, latency, cost, failures, backlog and decision against the already approved thresholds.

Only after privacy, route and shadow gates pass, follow the existing staged Mac rollout, observation period and rollback runbook. Do not enable production processing or recover/replay historical exchanges under this plan.

**Pass:** deterministic persistence/race requirements pass; route/privacy proof is accepted; shadow metrics meet existing thresholds; staged rollout and rollback each have dated receipts. Otherwise leave production disabled/fail-closed.

### WP5 — Complete GC24-06 live Knowledge Atlas acceptance

On the exact candidate, test authentication expiry/recovery and source mutations for every supported source; stale last-good display; partial failure/retry/reconnect; actual unlock delivery; and source refresh identity. On a mounted app, verify keyboard-only and VoiceOver navigation, focus, labels, values and announcements. Prove changing tab, size, panel, or display does not duplicate a fetch. Measure graph responsiveness/resource use on the approved fixture. Separate truly headless fixture limitations from product failures; do not silently waive skips.

**Pass:** source lifecycle, accessibility, fetch identity, performance, unlock and physical-display receipts satisfy the existing Atlas plan on the exact candidate.

### WP6 — Freeze and accept a single candidate (GC24-07–10)

After source prerequisites pass, freeze source SHA, app bundle identity, backend revision, non-secret effective configuration, and feature gates. Run regression against that exact artifact. Complete the required physical journeys: compact startup; voice/mute/orb; one response identity; monitor connect/disconnect/reconnect/rehome; Atlas; text/image sharing; privacy boundaries; memory disabled and then eligible staged route; and sandboxed self-edit from spoken preview through PR approval. Obtain independent review, demonstrate rollback, observe for the already required period, and reconcile all checklist rows to dated receipts.

**Pass:** all source, route, privacy, memory, Atlas, physical-device, independent-review, rollback and observation gates are evidenced for the frozen candidate. If any gate is unavailable, label it open; do not claim release readiness.

## Per-slice model handoff protocol

1. Read this plan, the named authoritative contract, current status, latest relevant receipt, and repository instructions.
2. Reconcile worktree and ownership. State the invariant and one bounded slice before editing.
3. Inspect the live call/data path; do not infer behavior from filenames or prior summaries.
4. Implement only the slice; preserve existing owners and public behavior. Add a regression test that would fail on the identified gap.
5. Run focused tests and relevant lint/build checks. Broaden to full suites when a shared boundary changed. Preserve failures, skips, warnings, and subtest counts.
6. Review the diff for unrelated edits, privacy leaks, duplicate owners, fallback, and stale documentation.
7. Write a dated receipt with exact snapshot, commands, results, and remaining gates; update status only to what the receipt proves. Leave changes uncommitted and unpushed.

If hardware, a provider, an account, an explicit contract decision, or the exact candidate is unavailable, finish independent deterministic work and record that external gate as open. Stop only the dependent slice when ownership or contract is genuinely unresolved; do not block independent work. Never report a test, capability, or user acceptance that was not observed.

## Completion definition

This plan is complete only when every work package has current source evidence, required regression coverage, linked dated receipts, and reconciled status. Release remains incomplete until the frozen-candidate gates in WP6 pass. A green unit suite, a merged PR, or a working local screen alone cannot close those gates.
