---
date: 2026-10-17
system: codex
rows: [WS-20, WS-22, WS-23, WS-24, WS-25, WS-26]
prs: [211]
---

# Consolidated enhancement intake

Larry supplied eight planning inputs and requested roadmap additions. Preserve
all eight in the shared intake, map baseline/acceptance and Mail Reader to
existing ownership, and reuse the WS-22 canonical plan for evidence/handoffs.
Four new parked entries record verification, durable tasks, commitment review
and event follow-through. Each has requirements, dependencies, future acceptance
checks and an unassigned implementation owner. Item 8 is a cross-cutting rollout
contract, not another agent. No new implementation plan or runtime code is
created; future design must reconcile existing components and claim ownership.

The supplied statement about daily-report mail is preserved as user-reported
baseline behavior to verify/protect, not independently verified full-report
coverage. Current P1 source evidence alone cannot prove calendar/reminder/summary
behavior. Interactive mail remains a missing-capability audit under WS-13 P5,
with P4 prose and outbound/write scopes separate. No Claude-owned plan changed.

Shared task/run/result/notification identity and host authority are explicit;
WS-22 now points to proposed WS-24 for lifecycle reconciliation. Existing
checklists remain unchanged; new boxes are future requirements, not acceptance
results. Sequence and parked state retain Larry’s acceptance-first priority.


### 2026-10-18 — Restore parked enhancement intake after #211 merge (Codex)

The 10-17 `fc9c958` candidate added the eight-item intake and four parked WS-23–26 cards after PR #211’s merged head `98ad864`. The merge therefore did not contain those later additions, although the old right-pane preview showed them. Rebased the exact documentation additions on current main `28420af`, preserving the separate three-PR review note and all intervening WS-17/13/20 source. The restoration creates no implementation claim, deployment or acceptance.
