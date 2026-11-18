---
date: 2026-11-18
system: claude
rows: [WS-34]
prs: []
---

# 2026-11-18: merge `main` into `next`

- **System:** Claude (Claude Code cloud session), at the coordinator's request after Larry merged #383 (main `fd9a156`).
- **What:** a no-rebase merge of `origin/main` (`fd9a156`) into `origin/next` (`fec254e`), so `next`, the enhanced build acceptance now runs on, carries the 2026-11-18 non-production rules (#383) and the merged docs #379 and #381. The merge brings docs only: `ROADMAP.md`, `AGENTS.md`, `CLAUDE.md`, the release closure plan and four roadmap-log files. No source, test or configuration file changes.
- **Conflicts:** `ROADMAP.md` and `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md`. Both files are maintained on `main` by the daily batch (§0 rule 16), and `next`'s edits to them since the merge base `c23dda5` were stale text carried in by feature-branch merges (rule 16 removed, the C8 boxes back to their pre-C8 wording, the batch progress lines removed, row statuses back to 11-11). The resolution takes `main`'s version of both files, plus one genuine `next` correction: the plan's §6 assumption that B1 runs on `macos-26-intel` (the `macos-15-intel` runner cannot run the macOS 26 packages).
- **Checks:** `python scripts/check_roadmap.py` on the merge result, below in the PR.
