---
date: 2026-10-02
system: claude
rows: [WS-17]
prs: [164]
---

- 2026-10-02 (WS-17 CC7a.2 Codex review fixes): Claude (Cowork). Codex's review of PR #164 found two P2 regressions on 5b1b91f, both fixed on the branch. (1) On a layout switch the departing stage's onDisappear ran after its replacement's onAppear and turned quiet arrivals off with the thread showing; stages now report per identity (WorkspaceStore.setQuietArrivals(_:owner:) and releaseQuietArrivals(owner:)). (2) The New count was positional: a reply inserted before a tool-first card was missed, and closing the last card counted rows as new; ConversationThread.newTurns now counts identities not seen before. Codex's probes are kept unchanged as CC7a2ReviewRegressionTests, with Claude's unit tests for both. Remaining: Codex re-review, then merge.
