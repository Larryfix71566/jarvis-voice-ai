---
date: 2026-10-17
system: codex
rows: [WS-20, WS-17, WS-18, WS-09, WS-11]
prs: [208, 209]
---

# 2026-10-17 — Existing acceptance campaign

- **System:** Codex; session `01a14bae-5269-78b0-abe8-6611e9c357dc`.
- **Workstream:** WS-20 acceptance coordination; existing WS-17/18/09/11 evidence.
- **Branch:** `codex/acceptance-campaign-20261017`.
- **Authorization:** Larry requested execution of existing acceptance testing,
  offering human intervention. WS-22 remains parked; no runtime changes,
  deployment, provider activation or other system workspace changes.
- **Change:** reconcile current conversation-first runbook; record installed
  identity, automated results, bounded live passes and reproducible failures;
  close only Larry's fully evidenced WS-18 physical-switch criterion.
- **Evidence:** [dated campaign receipt](../acceptance/command-console/receipts/acceptance-campaign-2026-10-17.md).
- **Remaining:** preserve failed Recents/reuse and test/preflight findings;
  complete scoped repairs/review/release before retesting affected gates.
  Required hardware, activation decisions and frozen observation periods
  remain open. No parent acceptance is inferred from a subset.

## Final results follow-up

Initial evidence PR #208 merged as `f363444` during verification. The final
receipt follows on `codex/acceptance-campaign-results-20261017` with the same
scope. Independent verification: all twelve checks pass, source unchanged,
receipt hashes validated, both VMs stopped. Quiet-host performance and the
single deadline case pass, but two Vision OCR errors reproduce in a focused
retry; the final host suite is not clean. Live Recents/reuse and synthetic mail
preflight failures remain open. The receipt records final runtime observations
and the remaining hardware, activation, release and observation prerequisites.
