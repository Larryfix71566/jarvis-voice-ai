# Drawer pop-out — acceptance checklist

MORTIMER_DRAWER_POPOUT_PLAN.md. Manual, run against a live stack
(`./scripts/mortimer.sh`), ideally with a second monitor attached (some
items are Chrome-only via the Window Management API — Safari/Firefox
items are called out separately). Not run by pytest, except where an item
names a specific automated test/command. Copied from the plan's §4
Verification list.

- [ ] `⧉` in the drawer's own tab strip (right end, beside the close ×)
      pops a window; in Chrome it lands on the extra screen; with the
      display window also open, display takes the left 60% and the
      drawer takes the right 40% of that screen.
- [ ] Every tab works in the popped window: Repo/Edit/Memory/Runs (HTTP,
      fetch the admin sidecar directly, no relay) — Dev + Output
      (relayed stores) — Log (`conversationFeed.ts`) — including a
      window opened MID-SESSION showing existing runs/output/transcript
      (the replay handshake on the popped window's `hello`).
- [ ] While popped: the in-page drawer body is hidden (not just
      visually — `SideDrawer`'s `open` prop is forced false), the topbar
      Panels button shows `◪ Panels ⧉` with the "Panels are on the
      display screen" title, and "show me the runs" by voice switches
      the POPPED window's tab (not the hidden in-page one).
- [ ] Console reload while popped: still popped (heartbeat presence
      survives losing the console's window ref, same mechanism as the
      display window), no double drawer, Panels click refocuses/re-places
      rather than opening a second window.
- [ ] "Bring the panels back" (voice, `drawer_popin`) and closing the
      popped window's own OS close box both return the in-page drawer
      with its PRIOR open/tab state — not reset to defaults.
- [ ] The drawer window never prompts for mic access — open its DevTools
      console and confirm no `getUserMedia` call, no `PipecatClient`
      construction (D39-equivalent for the drawer, verified by
      `drawerMain.tsx`'s import graph never reaching `jarvisClient.ts`).
- [ ] Two windows, one extra screen (DP8): opening the drawer while the
      display window is already open (or vice versa) repositions BOTH —
      display left 60%, drawer right 40%. Closing one lets the other
      reclaim full width ("fill") on its next open/re-place. (Requires
      the Window Management API — Chrome/Edge; not exercisable
      headlessly, so this is a manual/code-review item, not automated.)
- [ ] Three or more screens: display takes the first non-console screen,
      drawer takes the second if one exists (each gets the FULL screen,
      no split) — falls back to the two-screen split only when a single
      extra screen is shared.
- [ ] Safari / Firefox (no Window Management API): both windows open
      unplaced and are dragged by hand once; no console errors from the
      feature-detected fallback.
- [ ] `mortimer.drawerwin.popout` persistence (DP9): pop the drawer out,
      then quit the browser entirely (not just close the popped window)
      so the window dies without ever sending `bye`/being explicitly
      popped in; reload the console — the drawer stays in-page until the
      FIRST click anywhere, then reopens the popped window automatically
      (matching browser popup-blocker rules, which require a user
      gesture).
- [ ] `pytest tests/unit/test_ui_control.py -q` covers `drawer_popout`/
      `drawer_popin` resolution (message shape, `"ok"` reply, tab
      ignored) alongside the existing action tests.
- [ ] `cd web && npx tsc -b && npx oxlint` both clean, including the new
      `popoutWindow.ts`, `conversationFeed.ts`, `drawerRelay.ts`,
      `drawerMain.tsx`, `DrawerWindowApp.tsx`.
- [ ] Full `pytest tests/unit tests/integration` clean (aside from the
      pre-existing sandbox-network `test_mcp_web_server` failure, which
      predates this plan).
- [ ] `RUN_LIVE=1 python -m tests.evals.routing_eval` scores >= 90%
      including the two new `ui_control` cases ("send the panels to the
      display screen", "bring the panels back") — not run by this
      implementation pass; needs real API keys.
