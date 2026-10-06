# Implementation and acceptance status

Updated 2026-09-28 during integration of main `2e6f769` into
`codex/isolated-20260924`. [ROADMAP](../../ROADMAP.md) owns workstream status
and assignments. Plans specify requirements; receipts prove only their recorded
candidate, environment and scope. All merge conflicts are resolved locally; release acceptance remains open. Nothing in this update claims deployment or activation.

## Work still open

- **WS-01 — verified gap closure:** execution, privacy, memory admission and
  Atlas work is implemented in part on the isolated branch. All 31 merge
  conflicts are resolved. The approved memory ordering and live streaming
  flags are integrated; acceptance and human-only protections remain open. See
  [canonical plan](../plans/MORTIMER_VERIFIED_GAP_CLOSURE_PLAN.md).
- **WS-02 — subscription isolation:** offline adapter/status checks pass on the
  merged files (56 tests). Live route, cancellation, capability and confinement
  gates remain open; a login or text probe does not close them. See the
  [isolation plan](../plans/MORTIMER_SUBSCRIPTION_RUNTIME_ISOLATION_PLAN_2026-09-25.md).
- **WS-03 — Skills Workspace:** catalog, intended process, truthful activity,
  real Developer creator dispatch and late validation ownership exist on the
  branch. Skills and Workflows must remain distinct views. Navigation placement
  is approved; Swift integration is complete locally; native suites pass with environment-dependent skips. Provider
  evaluation, blinded review, accessibility, voice, physical displays,
  activation/rollback and frozen-candidate release gates are not accepted. The
  frozen authoring fixtures still need their human deny-list commit. See
  [Skills status](skills-workspace/STATUS.md) for SW-A through SW-L.
- **WS-04 — remote access:** approved dormant-merge fixes are in progress.
  Explicit `true` enables auth; otherwise bind is loopback-only. Synthetic
  authenticated health/caller tests pass, but the health script's human-only
  deny-list gate remains open. Whole-app route coverage and native suites pass; live
  acceptance remains open. Enabling remote access and token onboarding
  remain Larry's separate decisions. See
  [Remote Access Addendum R1](../plans/MORTIMER_REMOTE_ACCESS_PLAN.md).
- **WS-05 — model use:** Codex owns the active `codex/ws05-execution-20261005`
  candidate in draft PR #177. Route, execution, privacy/source, budget and saved-control
  foundations are implemented; real workload, account and deployed rollout acceptance
  remain open. Subscription access does not prove image, tool, streaming, cost-bound
  or confidential capability. See [model-use status](model-use-enhancements/STATUS.md).
- **WS-06/07 — main's self-service access, registry and voice workflows:**
  source is landed on main; Codex is preserving it in the merge. Mac checks
  remain open per ROADMAP. Source integration does not certify a running build.
- **WS-08 — orb:** source is landed; placement, Reduce Motion and rollback
  observations remain open. Do not replace the renderer in gap closure.
- **WS-09/11 — console, Atlas and adaptive-interface acceptance:** remaining
  voice/display/provider sharing, accessibility, rollback and observation
  journeys need the exact frozen Mac candidate. Follow
  [Command Center status](command-console/STATUS.md),
  [adaptive release readiness](adaptive-interface/RELEASE_READINESS.md) and
  [acceptance runbook](ACCEPTANCE_RUNBOOK.md).
- **WS-10 — automated memory enablement:** CX-07 ordering is approved; merged-pipeline implementation and acceptance remain open. Earlier sandbox
  classification/retrieval/maintenance and synthetic shadow evidence does not
  prove the merged admission-plus-settlement pipeline or a production benefit
  and cost observation period. See [memory status](memory-automation/STATUS.md).

## Automated memory management

Mac staged enablement and benefit/cost observation remain open. Offline
classification, provenance, retrieval and maintenance checks from earlier
candidates remain historical evidence; merged-pipeline acceptance must follow
CX-07 before enabling the new behavior.

## Command Center and Knowledge Atlas

Supporting-display voice-triggered repeat and provider/fetch evidence remain
open for the frozen merged candidate. Sharing needs a live picker/provider journey; accessibility and measured audio need target-Mac observations.
Five-day daily-driver acceptance, rollback and independent release verification
remain open. Earlier monitor observations do not automatically transfer to
this new build.

## Latest scoped evidence

These checks are independent and may overlap; do not sum them into an overall
completion percentage. They do not replace a full merged-tree verification.

- DB migration tests: 20 passed, including upgrade from main's schema with
  notices preserved and repeated migration application remaining idempotent.
  Codex IDs are now reserved 0028–0034 and 0036; 0035 stays reserved for mail.
- Workflows, key health and Skills validation activity: 475 passed.
- Registry and supervision: 57 passed, including content-free shutdown/status
  failure diagnostics on the actual owner-task lifecycle.
- Auth, bind and service-token checks: 79 passed.
- Subscription adapter/status probes: 56 passed, with synthetic providers.
- Web-tool tests: 70 passed. Native packaging tests: 10 passed, 2 subtests.
- Deployment health/internal caller/token tests: 14 passed with a temporary
  loopback stub. A separate required human-only tier test fails until
  W1-REMOTE-HEALTH is applied; no production deployment was run.
- The earlier historical verifier completed 11/12 stages. Candidate checks
  passed; its old baseline failed an exact floating-point assertion. The
  aggregate receipt remains **failed**, and predates current integration.
- The subsequent IPv4/IPv6 canary passed all eight positive-control and
  provisioning/offline containment observations. This closes the network
  subcheck, not all creator lifecycle/VM isolation acceptance. Evidence:
  [verified network receipts](skills-workspace/receipts/ipv6-verified-2026-09-28/).

Runtime identity and final-release evidence remain missing for
the merged candidate. Earlier Python/Swift counts are historical results and
must not be presented as current pass counts.

## Preserved history

CX-08 reconciles the competing status copies without discarding either:

- [Main snapshot at 2e6f769](../archive/IMPLEMENTATION_STATUS_MAIN_2e6f769.md)
  retains the September 18/22 receipt counts and release matrix.
- [Codex snapshot before reconciliation](../archive/IMPLEMENTATION_STATUS_CODEX_2026-09-28.md)
  retains the dated implementation details and earlier handoffs.

Both archives are historical, not alternate current trackers. Use ROADMAP for
ownership, the canonical per-workstream plan for remaining requirements, and
the linked receipt for any completion claim.

The two human-only allow-list additions are prepared as a
[reviewable patch](skills-workspace/human-allowlist-proposal.patch). `git apply
--check` passes; a temporary copy verifies both paths become denied. The actual
allow-list remains unchanged. Apply through the human-commit process in
[ALLOWLIST_SEQUENCE](../plans/ALLOWLIST_SEQUENCE.md), after merge resolution.

## 2026-09-28 merged verification update

[Integration receipts](skills-workspace/receipts/main-integration-2026-09-28/)
record the broad Python run (4,851 passed; two expected failures for the pending
human deny-list changes; four skipped), JarvisKit (219 tests, zero failures),
and MortimerHost (372 executed, seven skipped, zero failures). These supersede
the earlier scoped evidence for integration, not for live acceptance.

A subsequent fixture-provenance audit restored main's historical registry
snapshots unchanged: the rename merge had carried Codex's three streaming
flags into the old YAML fixture. The live profile flags remain, as approved,
and a separate regression checks only that intended overlay against the
historical snapshot. All 59 registry tests pass with three historical byte-
snapshot tests appropriately skipped after the deliberate live-pool change.
