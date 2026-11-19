---
date: 2026-11-19
system: claude
rows: [WS-37]
prs: [401]
---

# 2026-11-19: WS-37 drawer never opens itself; results light the Inspect dot (Claude)

- **System:** Claude (Claude Code cloud session, Opus 5.5 thread). Small enough that the planning thread wrote it directly rather than handing it to a Sonnet helper.
- **Larry's words (UTC, Claude Duet channel), 2026-11-19 03:11:35**, answering the plan's open decision 3 ("should it keep opening itself when a result arrives, or light a dot on Inspect instead?"): "1 light a dot".
- **Plan:** `docs/plans/MORTIMER_INTERFACE_CLEANUP_PLAN_2026-11-18.md` (on `main`), §7 open decision 3.
- **Change (paths under `macos/MortimerHost/Sources/MortimerHost/`):**
  - `App/AppMessageRouter.swift`: a drawer-routed result no longer opens the drawer or switches it to Output (D31's auto-open is gone). New `drawerResultNeedsDot(_:)`: unless the Output tab is already on screen (docked or popped out), the result sets `outputDot`, which lights the dot on the Inspect button and on the Output tab.
  - `App/UICommandRouter.swift` (`DrawerState`): with the auto-open gone, every remaining way the drawer opens is the user's (Inspect click, Escape/T keys, command menu, voice `drawer_open`, which the prompt allows only when the user asks, pop-in, the working line), so saving every change now saves only the user's choice. A one-time reset (`mortimer.drawer.openResetWS37`) discards an open state saved before this build, since it may have come from the old auto-open: the first launch of this build starts closed.
  - `Console/TopBarView.swift`: the Inspect button's accessibility value says "New output", "Needs attention" or "Agent working" while its dot shows, so the dot is spoken too.
- **Tests:** new `InspectDotTests` (6): closed drawer stays closed with the dot lit and saved state "false"; open on another tab keeps its tab and lights the dot; Output already showing (docked or popped out) gets no dot; viewing Output clears it; the one-time reset; the Inspect button's spoken dot. **Changed:** `CC7a2ReviewRegressionTests` (lines 78-80 asserted the old auto-open; now assert the drawer's open state and tab are unchanged and the dot follows `drawerResultNeedsDot`).
- **Not tested here:** no Swift toolchain in the session; CI's Swift jobs are the first build. Nothing seen on the Mac.
- **Not changed:** opening Inspect while the dot is lit opens on whatever tab was last used, not on Output; the dot then sits on the Output tab.
- **Next actor:** Larry: merge, then the planned redeploy with Phase 2.
