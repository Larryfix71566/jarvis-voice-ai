---
date: 2026-10-03
system: claude
rows: [WS-21]
prs: [171]
---

- 2026-10-03 (WS-21 supporting display transfer implemented): Claude (Cowork). One validated, confirmed route to the supporting display: SupportingDisplayCoordinator checks the content (a live, non-protected result, or the memory graph, Skills or workflows) and the destination (a connected placement screen that is not the console's) before anything opens, assigns the display to that screen, opens it, and reports success only once the display is presenting that content on that screen (3.5 s, inside the bot's 5 s wait); a timeout or disconnect returns the content to main and closes a window it opened. Voice display_show (new console action) and skill_display_transfer reply from it; the menus use it too. display_popout no longer claims to move content and, with nothing to show, says so instead of opening an empty window. Inventory: one builder for the requested and published inventory, screens by placement ID with names, supporting_display ownership and placement, panel destinations. panel_detach and panel_move reject unknown results and screens; screen_id is accepted on detach by both validators. Remaining: Codex review, Codex's diagnostics as regression tests, Mac external-display acceptance.
