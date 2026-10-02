---
date: 2026-09-29
system: claude
rows: [WS-15, WS-16]
prs: []
---

- 2026-09-29 (late, WS-15 PR 2 fix): Claude (Cowork). DEPLOY-MAIN for `05c4a40` stopped in phase A with 3 MortimerHost failures: two assertions of MemoryGraphClosureC3Tests (the new radar tile overlay used the shared URL session; now its own ephemeral session) and the WS-16 protected-window capture test (pre-existing and environment-sensitive, owned by Codex). Production was not changed.
