---
date: 2026-11-03
system: claude
rows: [WS-28]
prs: [222, 294]
---

# WS-28 — prune operator-report fix, Claude, 2026-11-03

System: Claude (Claude Code cloud session `session_01EHREEWWT9PPGKDzg678o9r`). Planned by Claude Opus 5.5; implemented by a Claude Sonnet subagent from that plan, then reviewed and checked by Claude Opus 5.5.
Branch: `claude/ws28-prune-report-20261103`. Claim: #294 (Larry-authorized 2026-11-03).

Closes the change Claude's [2026-10-22 cross-review](2026-10-22-ws-28-claude-cleanup-cross-review.md) required before any real prune. `sandbox.prune main()` now separates would-delete or deleted VMs, retained VMs and malformed records, and exits 1 on a failed deletion, 3 when any record is malformed, otherwise 0. `Pruner.run()` adds a `retained` list to the report.

Evidence (this session): `python3 -m unittest discover -s sandbox/tests` passes 164 tests (160 before, plus four `main()` regressions covering dry run, real run, a clean pass and JSON output). No real prune, reclaim, clone or production change was run.
