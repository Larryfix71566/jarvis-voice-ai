---
date: 2026-10-03
system: claude
rows: [WS-17]
prs: [169]
---

- 2026-10-03 (WS-17 CC7a.2b Codex re-review fix): Claude (Cowork). Codex's re-review of ba52a25 found one P2 route: a newer run of the same agent replaces the older run's card in AgentRunStore, so the older run's result had no start time, fell back to the 120 s direct-result window and could open over the newer conversation. The router now dates runs from its own record of agent working messages (ArrivalRunClock, latest 64 runs), and ArrivalIntent treats a payload whose run ID has no recorded start as a card; only a payload with no run ID uses the 120 s window. Router tests cover a replaced run (card) followed by the newer run (opens) and a run ID the app never saw start (card). Remaining: Codex re-review, then merge.
