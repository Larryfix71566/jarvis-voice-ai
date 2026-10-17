# Mortimer evidence-based investigation and development workflow

**Status:** PARKED — documented for future development; implementation is not authorized.
**Roadmap:** WS-22, at the end of `ROADMAP.md`.
**Owner:** Codex for this documentation only; implementation owner unassigned.
**Date:** 2026-10-17.
**Design baseline:** `origin/main` `4e350b466bc6efedde489612fc6232cd5fa15802`.
**Decision:** Larry requires closure of the existing roadmap acceptance gates before new development. This supersedes the earlier proposal to build the isolated core in parallel. No implementation, runtime registration, provider call, activation, deployment, or new service is authorized by this document.

## 1. Purpose and authorization boundary

Provide a repeatable background workflow that investigates a particular software behavior, explains its evidence and uncertainty, writes a behavioral specification, and, only when requested, implements and verifies an adaptation. Investigation must be useful without implementation. A research request does not authorize building, publishing, merging, or deployment.

Example: “Investigate how this application handles background tasks. Show what you can establish, identify useful adaptations for Mortimer, and prepare an implementation proposal.”

The design is model-independent, not a promise that every model is capable. An eligible model must meet the same contracts and acceptance criteria. An incapable or unavailable route reports its limitation rather than simplifying requirements or silently falling back.

### Activation prerequisite

Before claiming implementation, reconcile every pre-existing open acceptance gate in WS-01/02/03/04/05/06/07/09/10/11/13/17/18/20/21 against current evidence. Preserve accepted gates in the other rows. The owning records must show closure and Larry's required outcomes. A blocked, skipped, untested, parked, or hardware-unavailable item is not a pass. A plan-specific written known-limitation acceptance may be used only where that plan allows it; any broader scope change requires Larry's explicit decision. No model may waive a gate to start WS-22.

Some existing gates require unfinished prerequisite code or activation decisions. This document does not authorize that work. Record the prerequisite under its existing owner and obtain the appropriate assignment/decision; do not use WS-22 as a bypass. Once existing acceptance closes, Larry dispatches a fresh implementation claim with owner, branch, scope, and current dependencies.

## 2. Fixed requirements

- **R1 Evidence:** substantive factual claims reference identifiable evidence.
- **R2 Uncertainty:** observations, inferences, unknowns, and contradictions remain distinct.
- **R3 Intent:** requirements and deliberate adaptations are traceable through specification, implementation, and verification.
- **R4 Host authority:** code, not model prose, controls permissions, budgets, identities, lifecycle, and acceptance status.
- **R5 Model independence:** provider-specific behavior stays behind Mortimer's existing model execution boundary.
- **R6 Isolation:** development and target execution use approved isolation; failure never falls back to host execution.
- **R7 Privacy:** collection, persistence, model delivery, display, and export each enforce applicable policy.
- **R8 Honest completion:** tool success, tests passed, deployment, and user acceptance are separate facts.
- **R9 Continuity:** a fresh eligible model can resume from persisted records without the original conversation.
- **R10 Existing architecture:** reuse routing, ownership, run logging, sandbox, notices, and release mechanisms; no parallel production authority.

An implementation violating any R requirement is incomplete even if its demonstration succeeds. The implementation must report each R requirement and AT acceptance case with evidence, a blocker, or an explicit approved disposition.

## 3. Scope and increments

**Increment A: investigation/specification.** Pinned Mortimer repository snapshots; admitted documents/screenshots; evidence collection; claim review; specifications; resumable handoff; background lifecycle; privacy; budgets; result presentation.

**Increment B: implementation/verification.** Genuine Developer dispatch from a frozen specification, isolated changes, independent verification of the actual candidate, and patch/PR delivery through the existing authorized pathway.

**Later optional adapters:** REA, native binary inspection, permitted live third-party application interaction, and bounded web collection. Neither initial increment requires REA. Static inspection is not execution and a local tool does not imply local-only model processing.

Outside scope: automatic deployment, automatic skill activation, unrestricted crawling, self-expanded permissions, replacement model/budget/privacy systems, and repairs to unrelated roadmap workstreams.

## 4. Repository and ownership integration

Proposed new package: `jarvis/investigation/`, containing contracts, persistence adapters, orchestration, evidence, specification validation, and reporting. Confirm paths/interfaces against current main at implementation time; record mappings without changing the requirements.

Reuse:

- `jarvis/admin/server.py` for thin authenticated route registration; keep new logic in the package.
- The supervised MCP registry for thin tools, not a second tool execution system.
- `jarvis/model_routing.py`, `model_execution.py`, `privacy_policy.py`, and existing budget/usage facilities.
- `jarvis/runlog/`, actual Developer runs, source attestations, and the existing sandbox and self-edit boundaries.
- Existing notices, activity, display payloads, result identities, and native interaction contracts.
- Existing SQLite migrations and private runtime storage. Do not invent a second authoritative production database.

A Skill is a reusable instruction package; a Workflow is operational sequence/status. An optional instruction package must not activate itself or replace workflow persistence.

### Future integration boundaries

- WS-05: consume existing model/privacy/source/budget/run-log contracts; no competing policies or ledger.
- WS-03/04: preserve actual Developer identity and server-side owner authentication; do not assume unfinished creator/auth acceptance has passed.
- WS-17/21: preserve stable result IDs, focus, reading state, voice actions, and display placement.
- WS-13: do not alter its mail entries, snapshots, tests, or reserved migration `0035`.
- Reserve all migration identifiers, configuration keys, and shared protocol names through ROADMAP §3 before implementation. No such reservations are made here.

After the acceptance-first hold is lifted, build the isolated core first, integrate one existing subsystem per narrow reviewed slice, and activate the live pilot last. Use explicit interfaces and test substitutes for services; do not ship substitutes as alternative authorities. Confirm actual interface compatibility with integration tests before claiming readiness. Respect the one-active-VM host capacity and other owners' verification windows.

## 5. Persisted contracts

Version every schema. Validate model-produced structured content before acceptance. Host-generated IDs, timestamps, ownership, and receipts must never be accepted as authoritative solely because a model supplied them.

### Request

Required: job ID; authenticated owner; mode (`investigate`, `specify`, or `build_verify`); goal; target references/revision; authorized operations; privacy floor; time/tool/output/evidence/spend ceilings; acceptance criteria; originating conversation/result IDs; idempotency key; schema version.

Modes define the requested stopping point, not a new permission grant. Missing material scope or authority blocks dependent actions. Original user intent remains in the versioned record.

### Evidence

Required: host-assigned evidence ID; source reference; collection method; actual tool invocation or explicit imported provenance; collection time; target revision; managed artifact reference/digest; classification; limitations. Distinguish source text, static code, runtime observations, imported assertions, and test results.

The artifact digest establishes identity/integrity, not truth. References resolve only within managed, owner-authorized storage. An imported document claiming a test passed cannot mint an execution receipt.

### Claim and unknown

A claim contains statement, observation/inference/unknown classification, supporting and contradicting evidence IDs, rationale, alternative explanations, and unresolved questions. Confidence is descriptive, not a calibrated probability unless independently justified. The model proposes claims; the host validates references, lineage, and schema, not semantic truth by schema alone.

An unknown contains question, materiality, status (`open`, `blocked`, `resolved`, or `contradicted`), the smallest useful next probe, and any resolution evidence. Missing search results are not evidence of behavioral absence.

### Specification

Required: immutable revision ID/digest, requirement IDs, purpose, inputs/outputs, state changes, error/cancellation/timeout/recovery behavior, privacy/permission boundaries, relevant timing/resource limits, acceptance examples/edge cases, adaptations from the observed target, assumptions, and blocking unknowns. Every substantive factual premise references evidence.

### Implementation and verification

Implementation attempt: spec digest, pinned source commit, genuine Developer run ID, sandbox identity, patch digest, changed-file inventory, mapped requirements, outcome, and remaining gaps.

Verification receipt: exact candidate identity, spec digest, test ID/definition version, environment identity, expected/actual outcome, diagnostic artifact references, and executor provenance. A reviewer-model opinion is not a host verification receipt.

### Events and storage

Events contain job ID, monotonically ordered sequence, attempt ID, stage, transition, host timestamp, and typed reason. Store metadata in Mortimer's SQLite system with reserved migrations; store evidence in managed private runtime storage outside the repository. Runtime artifacts are not automatically admitted to memory/KB.

Apply owner authorization to every lookup and export. Use atomic transitions, foreign-key/reference validation, and immutable revision/event records. Keep unavailable/deleted evidence references explicit; never silently regenerate evidence under an old ID. Apply the existing retention/deletion policy; define any missing retention rule before activation, not as a model choice.

## 6. Lifecycle

Stages: `preflight → investigate → synthesize → specify → implement → verify → report`.

Statuses: `queued`, `running`, `blocked`, `cancelling`, `succeeded`, `partial`, `failed`, `cancelled`, `interrupted`. Mode determines required stages. Investigation-only can finish with a report and unresolved questions; it cannot label an unbuilt implementation verified.

Enforce transitions in code with expected record version and attempt identity. A worker lease prevents simultaneous execution of one attempt. Start and continue operations are idempotent; the same key with different inputs is a conflict. Reject stale callbacks. Terminal attempt records do not change; retries create linked attempts.

On restart, expired leases become interrupted. Inspect outstanding operations before retrying; never assume they stopped or blindly replay an uncertain side effect. Recheck permissions, target/spec identities, remaining budgets, and resource availability before resume.

Cancellation stops new dispatch and signals active operations. Remain cancelling until termination is confirmed. Cleanup failure records the outstanding operation/resource and blocks reuse; do not claim cancelled successfully. Timeout follows the same termination procedure. A timed-out response is not proof of stopped work. Reporting partial evidence is allowed but cannot disguise an outstanding operation.

## 7. Evidence collection and specification rules

Each adapter declares capability, execution/network effects, required permission, schema, limits, timeout/cancellation behavior, and evidence limitations. Begin with pinned source snapshots and admitted files/images. An adapter receives only its authorized inputs; inspected content cannot choose another tool or scope.

Observation means directly supported by an inspected artifact or recorded execution under stated conditions. Inference means derived explanation with rationale and alternatives. Unknown means insufficient evidence. Contradictions remain visible until reconciled.

Static code establishes what inspected code expresses, not proof of all runtime behavior. Runtime evidence establishes only the recorded inputs/environment/conditions. Neither proves unseen server behavior or untested paths.

Keep observed target behavior separate from desired Mortimer behavior. For example, interrupting on completion in the reference may deliberately become a quiet result card in Mortimer. Record this as an adaptation, not an alleged faithful reproduction.

Material unknowns affecting correctness, permission, or data handling block implementation of affected requirements. Independent research may continue. Changed requirements create a new spec revision and invalidate affected downstream acceptance until reviewed/reverified.

## 8. Model execution and handoff

Every stage receives the same versioned task packet: fixed R requirements, goal/stopping point, allowed actions, schemas, current spec/evidence references, open contradictions/unknowns, existing decisions, remaining budgets, and completion conditions.

Before execution, validate route capabilities (tools/images/context/output/privacy as applicable) through existing routing. Native structured output is optional; text containing schema-conforming JSON is acceptable if host validation is identical. Permit at most one bounded schema-repair attempt per stage attempt, charged against the same budgets. Continued invalid output fails that attempt.

A model switch creates a recorded attempt, rechecks eligibility/privacy, and receives persisted context. It preserves permissions, decisions, remaining budgets, and provenance. It does not imply paid fallback, broader context disclosure, or a reset budget. If the packet exceeds context limits, use authorized bounded evidence retrieval and explicit omissions; never silently truncate mandatory requirements.

A fresh eligible session must be able to identify what is established, unresolved, authorized next, and why. Exports contain schemas/version, intent, decisions, spec/requirement mappings, authorized evidence or resolvable protected references, attempts, outcomes, and remaining blockers. Export never copies credentials or bypasses owner/privacy controls.

## 9. Build and verify

Developer input is the frozen spec, acceptance examples, approved project context, and required access. Where independent implementation is required, separate original target implementation material from the implementation packet. This mechanism alone does not establish a formal clean-room process.

Build from pinned source in the existing isolated pathway with actual Developer/run and sandbox identities. Preserve the spec digest, produce a reviewable patch, and list unimplemented requirements. Do not synthesize a Developer ID from a request/job ID. Do not publish or merge without the existing authorization.

Verify the exact resulting candidate against requirement IDs: normal behavior, boundaries/malformed inputs, failure/recovery, cancellation/timeouts, privacy/permission rejection, and relevant regressions. Expected results must come from the frozen spec/evidence, not be rewritten to match the implementation.

For critical checks, use a controlled wrong output or disposable mutated candidate and establish that the check detects it. Keep independent holdout cases where appropriate. A second model may review reasoning; agreement does not replace execution evidence. Changes to candidate/spec/environment require an affected-evidence review and reruns as needed.

## 10. APIs, UI, and operational limits

Proposed authenticated operations: start; read status/paginated events; retrieve authorized evidence/results; continue a specific spec revision; cancel; export an authorized handoff. Host identities are never accepted from model arguments. Continuation binds expected state version and spec digest. Thin routes validate and dispatch; long work remains outside the voice turn.

Show plain stage/status, findings/evidence links, inferences/unknowns, spec/candidate identity, verification outcomes, and time/cost. Update the existing result identity; preserve reading focus. Use the existing durable notice outbox with stable IDs and client deduplication, not an exactly-once transport promise.

Host configuration caps deadline, tool calls, attempts/output, evidence count/bytes, external requests, spending, concurrency, and sandbox use. Models cannot raise limits. Paid execution without required financial authority is blocked. Unknown usage/cost is unknown, not zero. Reuse actual usage accounting; avoid duplicate ledger entries.

Initial pilot: one active investigation and existing sandbox capacity. Record production limit values, disabled-by-default activation key, and failure behavior before activation through the owning roadmap reservation process. No values or flags are activated by this plan.

## 11. Privacy and untrusted content

Files, web content, screenshots, tool results, and embedded prompts are data, never authorization. They cannot change instructions, routes, permissions, or request credentials. Enforce policy before collection, persistence, model delivery, display, and export. Preserve stricter classifications when combining evidence.

Redacted derivatives retain protected provenance. Credentials never enter evidence, prompts, patches, exports, or ordinary diagnostics. Reuse credential scoping, source attestations, and protected-result handling. Local inspection does not imply local model processing. Exports enumerate contents and obey existing sharing controls. Deletion/expiry is explicit and cannot upgrade claim confidence.

## 12. Implementation sequence — only after the hold is lifted

1. **Ownership and contract freeze:** fresh row/branch/scope claim; resolve dependencies and shared paths; reserve identifiers/keys; record limits. Exit: owner and concrete contract for every dependency.
2. **Schemas/persistence/lifecycle:** validated records, migrations, transitions, leases, idempotency, recovery, budget adapters, cancellation. Exit: offline deterministic tests without provider/service access.
3. **Evidence/investigation:** initial adapters, evidence admission, references, unknowns, privacy. Exit: traceable synthetic investigation; fabricated/unauthorized references rejected.
4. **Specification/handoff:** validated generation, immutable revisions, requirement mapping, model-switch continuation. Exit: fresh session resumes without original conversation.
5. **Mortimer integration:** narrow reviewed API/MCP/background/activity/result/notice slices. Exit: start/status/cancel/reconnect/results preserve conversation and focus. Keep disabled until prerequisites pass.
6. **Developer/verifier:** real run/sandbox association, candidate patches, independent receipts. Exit: exact candidate/spec verification and rejection of stale/mismatched receipts.
7. **Pilot/release:** tests below; required reviews; existing merge/deploy/rollback/live acceptance. Exit: separately evidenced implemented, verified, deployed, accepted states.

## 13. Acceptance cases

- **AT-01:** duplicate start key creates one job; changed inputs conflict.
- **AT-02:** another owner cannot inspect, continue, cancel, or export.
- **AT-03:** embedded instructions cannot change permissions or dispatch.
- **AT-04:** nonexistent/mismatched evidence references are rejected.
- **AT-05:** static inspection is not labeled runtime verification.
- **AT-06:** material unknowns block unsupported implementation claims.
- **AT-07:** invalid output receives only the permitted bounded repair.
- **AT-08:** ineligible routes refuse without silent fallback.
- **AT-09:** model switch preserves intent, evidence, permissions, decisions, and budgets.
- **AT-10:** budget exhaustion stops dispatch and records the reason.
- **AT-11:** cancellation/timeout/cleanup failures report actual execution state.
- **AT-12:** restart/retry does not duplicate outstanding work or replay uncertain effects blindly.
- **AT-13:** spec/candidate changes invalidate incompatible receipts.
- **AT-14:** controlled incorrect behavior fails relevant acceptance checks.
- **AT-15:** sensitive content stays protected in activity, results, and exports.
- **AT-16:** reconnect/delivery retries do not duplicate visible completion notices.
- **AT-17:** missing Developer or sandbox identity cannot be fabricated.
- **AT-18:** passing tests cannot mark deployed or user-accepted status.

Start with deterministic fixtures; then exercise portability through two independently configured eligible model routes using the same task packet and fixed rubric. Provider calls require existing source/budget authority. Report unsupported/skipped cases explicitly; no denominator reduction to manufacture a pass.

## 14. Pilot

First use synthetic background tasks in the new workflow harness: completion, failure, timeout, pre-start/in-flight cancellation, late completion after cancel, duplicate delivery, disconnect/reconnect, protected content, and restart during execution.

Inspect existing Mortimer cancellation/notification behavior read-only if useful. Route discovered existing defects to their owning workstream; do not silently repair conversation/notification systems within WS-22. A requested repair needs its appropriate scope/claim.

Deliver evidence, behavioral specification, discrepancy report, and verification results. Build only if requested. Pass requires traceable conclusions, visible uncertainty, and successful fresh-model continuation without changing approved behavior or reconstructing missing decisions.

## 15. Handoff instructions and deviations

Implement all R and AT requirements. Refresh current repository ownership/interfaces first. Do not remove requirements, substitute mocks for live acceptance, expand permissions, or weaken design for model limitations. Identify blocked requirement IDs and continue independent authorized work.

Record each proposed deviation with reason, alternatives, impact, and affected tests. Changes to intent, permissions, privacy, evidence semantics, or acceptance need an explicit decision before implementation. File/interface mapping changes preserving the contract are recorded ordinary implementation decisions.

The final handoff includes exact commits/spec/patch identities, requirement coverage, tests and failures/skips, evidence references, model/runtime identities, known limitations, remaining prerequisites, and the next actor. Never claim completion while mandatory requirements remain unresolved.

## Progress

- **2026-10-17 — Codex:** Preserved the chat design and parallel-development boundaries as this canonical deferred plan. Larry's acceptance-first decision overrides the earlier parallel-start recommendation. WS-22 is documentation-only and parked; no runtime work or acceptance is claimed.
