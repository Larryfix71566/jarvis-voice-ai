---
date: 2026-09-29
system: codex
rows: [WS-16]
prs: []
---

- 2026-09-29: Larry's DEPLOY-MAIN for `2ed1986` stopped in phase A; the protected-window capture test timed out waiting for `occlusionState.visible` before taking a screenshot. Production remained at `adeffc1`. Codex's WS-16 follow-up removes only that prerequisite and adds a third real capture to prove the local body rendered; four focused actual-capture runs and the full MortimerHost suite (383 tests, six unrelated skips, zero failures) passed in this worktree. Merge and a fresh DEPLOY-MAIN run remain open.
