# Acceptance — right-side tabbed drawer (MORTIMER_SIDE_DRAWER_PLAN.md §7)

Manual checklist. Not run by pytest; `web/` has no JS test runner and the
plan explicitly does not add one (§7 note). Automated verification for this
phase is `cd web && npm run build`, `cd web && npm run lint`, and the
unchanged Python suite.

Run the stack with `./scripts/mortimer.sh` (the admin sidecar on `:7861`
must be up, or every panel correctly reports "admin sidecar offline").

## Drawer basics

- [ ] Open each of the five tabs; confirm exactly one body is visible and no
      two panels ever overlap (the §1.1 defect this plan removes).
- [ ] Click the active tab's topbar button; confirm the drawer closes and
      reopens to the same tab.
- [ ] With the drawer open, confirm the orb, satellites, and mic controls are
      all visible and clickable — nothing is covered.
- [ ] Click the `×` close button inside the drawer's tab strip (D27); confirm
      it closes the drawer, same as re-clicking the active topbar button.

## Resize and persistence

- [ ] Drag the left edge; confirm the stage re-centers live and the
      satellites follow, with no visible stutter.
- [ ] Drag to both extremes; confirm the width clamps and the stage never
      disappears.
- [ ] Reload; confirm width, open state, and active tab are restored.
- [ ] Tab to the resize handle and use Left/Right arrows; confirm the width
      changes (D20).

## Status cards and layout interaction

- [ ] Trigger a delegation to a non-Developer agent with the drawer open;
      confirm its anchored card stays fully left of the drawer and never
      slides underneath (D14).
- [ ] Narrow the window below 860px; confirm the drawer overlays full-width
      and status cards fall back to the stacked column.
- [ ] Shrink the window below 860px with a custom width saved; confirm the
      drawer goes full-width and the handle disappears. Widen it again;
      confirm the saved custom width returns unchanged (D16).
- [ ] Narrow the window below 860px with the drawer CLOSED; confirm the app
      is fully usable (orb, buttons, mic all reachable) — a closed drawer
      must not paint as a full-screen block in overlay mode (D16/D23).

## Developer tab

- [ ] Start a self-edit run with the drawer CLOSED; confirm the Developer
      topbar button shows the live indicator (D7), then open the tab and
      confirm the run's progress is intact, not restarted or missing (D10).
- [ ] Let a self-edit run finish, wait 15s, then open the Developer tab;
      confirm the completed run is still listed (D8).
- [ ] Run two Developer delegations back to back; confirm BOTH appear in the
      Developer tab and the second did not erase the first (D8a — the
      highest-risk regression in this plan).

## Existing card behavior, re-tested after the D10 state move

- [ ] A successful non-Developer run's card still fades out after ~8s.
- [ ] A failed run's card still stays until dismissed, showing the reason.
- [ ] A new run for the same non-Developer agent still replaces its previous
      card (replacement rule unchanged for non-Developer runs).
- [ ] Tool chips appear exactly once per tool call (a duplicate would mean a
      second RTVI listener was registered — D10's single-listener rule).

## Keyboard and mutual exclusion

- [ ] Open the transcript drawer while the side drawer is open; confirm one
      closes the other (D17).
- [ ] Press `Escape` with the drawer open; confirm it closes.
- [ ] Press `Escape` while the cursor is in a panel's text input; confirm it
      does NOT close (D20's `isTypingTarget` guard).

## Mount/unmount behavior (D23)

- [ ] Open a panel, close the drawer, reopen it; confirm the panel refetches
      and shows current data rather than a stale snapshot.
- [ ] Watch the network tab with the drawer closed for 30s; confirm no panel
      is polling behind it.

## Output tab (D28–D35)

- [ ] With the drawer CLOSED, ask for something that produces a
      drawer-routed display payload (e.g. "what are the working tree
      changes" → `git_diff_summary`). Confirm the drawer auto-opens to the
      Output tab with the result expanded (D31), and that nothing floats
      over the stage.
- [ ] With the drawer OPEN on the Memory tab, trigger another drawer-routed
      payload. Confirm the tab does NOT switch, and the `📄 Output` topbar
      button and Output tab both show a live dot (D31). Click Output;
      confirm the dot clears.
- [ ] Trigger three drawer-routed payloads in a row. Confirm all three are
      listed newest-first, the newest is expanded, and the older two are
      collapsed (D32).
- [ ] Expand an older item; confirm the previously-expanded one collapses
      (one at a time).
- [ ] Dismiss one item with its `×`, then use "Clear"; confirm both work
      and the empty state renders (D32).
- [ ] Confirm each item's relative time is sane ("12s ago", not "56y
      ago") — a 1970-ish timestamp means `payload.ts` was used instead of
      `receivedAt` (D34).
- [ ] Confirm the topbar row does not wrap at ~900px with seven controls
      present (D35's noted risk); if it does, the fix is to drop the emoji
      from the topbar labels, not remove a tab.

## Informational window and pop-out (D36–D43)

- [ ] Ask for weather and then for a web search. Confirm each opens the
      floating window (unchanged drag/resize/`×` behavior) and that
      **neither touches the drawer** — no auto-open, no Output dot,
      nothing added to the Output tab (D28/D31).
- [ ] Ask for the working tree changes. Confirm it goes to the Output tab
      and does **not** open the floating window (D36 routing both ways).
- [ ] Click `⧉` in the window header. Confirm a real browser window opens,
      and that the in-page window disappears while it is open (D41).
- [ ] Drag the popup to a second monitor (if available). Ask for weather.
      Confirm the result appears on that monitor and the console screen is
      untouched.
- [ ] Close the popup, then ask for weather again. Confirm the result is
      NOT lost — either the popup reopens or the in-page window comes back
      with the `⧉` button (D41's mandatory fallback). A blocked popup that
      swallows the payload is a failure.
- [ ] Reload the console with the popup preference on; confirm it is
      remembered (D41).
- [ ] Open the popup, then ask for weather, then close and immediately
      reopen the popup. Confirm the current result is shown rather than a
      blank window (D40's hello/replay handshake).
- [ ] Ask for a weather radar with the popup open; confirm the 3×3 seamless
      tile grid renders there correctly (D43 — shared rendering, not a
      copy).
- [ ] Confirm the popup never prompts for microphone access and the
      console's voice session is unaffected while it is open (D39 — no
      `jarvisClient` in the popup's module graph).
- [ ] `cd web && npm run build`; confirm the output lists BOTH
      `index.html` and `display.html` (D39/§7) — a missing entry fails
      silently at build time and only surfaces as a 404 when the popup is
      opened from a production build.
