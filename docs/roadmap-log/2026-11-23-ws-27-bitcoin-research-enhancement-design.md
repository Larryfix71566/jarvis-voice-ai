---
date: 2026-11-23
system: codex
rows: [WS-27]
prs: [408]
---

# WS-27 Bitcoin research enhancement design

- **Change:** Add the Bitcoin research skill and chart-first card, a separately
  gated Daily Brief recommendation, and the later native Mac workspace to the
  existing canonical WS-27 plan. No new plan, runtime work or status-line edits.
- **Evidence:** Compared the canonical plan on `main` and `next` (same plan
  blob) with Larry's November 23 Bitcoin implementation plan, including its
  Daily Brief revision. Checked open PR scopes before editing; the C9 claim
  touches only `ROADMAP.md`. `git diff --check` and the roadmap checker pass.
- **Left / next actor:** Larry reviews and merges the design. Implementation
  needs fresh scope dispatches and the documented gates. Nothing has been
  built, enabled, accepted, or deployed for this enhancement.
