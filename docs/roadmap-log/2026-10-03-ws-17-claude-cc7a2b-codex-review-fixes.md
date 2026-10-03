---
date: 2026-10-03
system: claude
rows: [WS-17]
prs: [169]
---

- 2026-10-03 (WS-17 CC7a.2b Codex review fixes): Claude (Cowork). Codex's review of PR #169 found two P2 routes on d69bf27, both fixed on the branch. (1) Every arrival on the conversation opened, including a background research or plan job finishing during a later conversation. The router now passes answersCurrentRequest (ArrivalIntent): a result opens when its run started after Larry's latest turn, or, with no run, within 120 s of that turn; research_report and plan_ready never open; anything else stays an unread card. (2) With the supporting display open, a window result took the main stage, which then showed only a placeholder; the conversation now stays and the display renders it. Codex's arrival probe is back to its original assertions; CC7a2bArrivalRouteTests drives the router through the requested, background, earlier-run, display-open, display-closed and unattributed routes. Plan 7.2, UI2-23 and the WS-17 scope (AppMessageRouter display arrivals) updated. Remaining: Codex re-review, then merge.
