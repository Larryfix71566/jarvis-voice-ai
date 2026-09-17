# C8 open items — accepted as known limitations

**Gate G-C8** requires every row of `P0-preservation-checklist.md` to carry
positive evidence *or* be named here with Larry's written acceptance. C8 has
not been run. This file takes the second route, on Larry's instruction of
2026-09-17: *"lets push layoutVersion default to 1 and clear that item."*

Accepted by: Larry. Date: 2026-09-17. Commit: the C9.5 flip.
Recorded by: Claude (Opus 5), session `011UrBECfDiC8HvQDAdWM4Xi`.

## What is actually being accepted

`mortimer.interface.layoutVersion` now defaults to `1`, so a fresh install
gets the adaptive layout without touching the Debug menu.
`Debug ▸ Use previous layout` is retained (L4: "remains for one release"),
so the rollback is one menu press and needs no rebuild.

**C8's five requirements are all unrun** — the preservation matrix in both
modes (G27), the §9.2 visual cases at five sizes, §9.3 real audio on the
C0.4 paired-trial protocol, §9.4 monitors and rollback (G19/G28), and the
independent C5 receipt (G20). None of the 24 preservation rows has recorded
evidence.

## The rows, grouped by whether the flag can reach them

This grouping is the substance of the acceptance. It was established by
reading `ConsoleView.swift` rather than by inspection of the UI:
`DrawerView()` is instantiated at `ConsoleView.swift:88`, **outside** the
`layoutVersion` branch. What the flag switches is the full-window
`VoiceWaveView` background (`:43`), `AdaptiveStageView` in place of
`OrbFieldView` + the in-page display panels (`:57–60`), the drawer's *width*
computation and drag behaviour (`:37`, `:174`), and one additional branch in
`DisplayWindowView` (`:18`).

### A — Structurally outside the flag: the flag cannot change these (13 rows)

The eight drawer tabs and the shared tab behaviours render from the same
`DrawerView` in both modes. A defect in any of them would be a defect in
both, so flipping the default neither introduces nor conceals one.

- DrawerView/DrawerTabStrip: tab keys and order.
- Common: loading, empty, failure, 401/403, reconnect.
- Common: active tab, scroll, selected records, drafts, in-flight actions.
- RepoTab, EditTab, MemoryTab, RunsTab, AgentsTab, OutputTab, LogTab,
  CostsTab: their own controls and states.

**Still owed, but as T1.3 §8 V3–V8 rather than as a gate on this flip.**

### B — Inside the flag, with incidental evidence from live use (6 rows)

Exercised repeatedly between 2026-09-14 and 2026-09-17 while the adaptive
layout was on via the Debug toggle, in sessions recorded in
`closure-checks/logs/bot-c6.log*` and the C6/C7 acceptance records. Not
row-by-row evidence with screenshots, which is what C8 asks for — but not
unknown either.

- TopBarView: Connect/Disconnect, connection state and errors — every
  session.
- MicControlsView: microphone toggle, SPACE press-to-talk — wake-while-muted
  verified in the native-audio plan's §8.
- OrbFieldView: listening/speaking/thinking, muted/wake labels — the C7
  measured-audio and item 10 amplitude work is precisely this surface.
- OrbFieldView: agent satellites, working/completion indications — the
  librarian and developer cards on 2026-09-16 11:44 and 12:51.
- App menus: Full Screen, Reset Layout, layout preview/rollback, clear
  stored token — the layout toggle itself, used daily.
- DisplayContentView: body text, image layering — `memory_graph_view`
  rendered to the display window on 2026-09-17 12:51
  (`display_payload … kind=image`).

### C — Inside the flag and genuinely unexercised: the accepted risk (5 rows)

**This is the list that matters.** Each is reachable only in adaptive mode,
or behaves differently there, and none has been exercised.

1. **Drawer width and drag.** `AdaptiveLayoutMetrics.drawerWidth(...)`
   replaces the stored width, and the drag path branches on the flag
   (`ConsoleView.swift:37`, `:174`). Failure mode: a drawer that opens at a
   wrong width, or resists resizing. Visible immediately, recoverable by
   `Reset Layout`.
2. **Display-panel routing.** Adaptive mode routes window-surface results
   through `AdaptiveStageView`'s workspace instead of the in-page
   `SingleDisplayPanel` stack. Rows: `SingleDisplayPanel/DisplayWindowView`
   existing panels, and `AppMessageRouter`/stores surface routing, attention
   and auto-open. Failure mode: a result that arrives but is not shown.
3. **Workspace additions** — persistent reading/selection, pins, A/B
   comparison. Adaptive-only surfaces with no legacy equivalent, so there is
   nothing to compare against and nothing has been tried.
4. **The OrbFieldView notices in a compact region** — pending draft,
   input-device, output-device (`OrbFieldView.swift:184`, `:244`). They
   render in both modes, but in `.rail` and `.bottom` the region is 150 px
   tall or 140 px wide. Failure mode: a notice clipped or unreadable, which
   matters most for the *pending draft* notice, since missing it means not
   knowing a write is awaiting confirmation.
5. **`DisplayWindowView`'s supporting-content branch**
   (`DisplayWindowView.swift:18`) — a view that exists only when the flag is
   on, including the "Original display panels" escape button. Never
   exercised.

Plus, not a preservation row but in the same blast radius: **multi-display
(DP8)** behaviour under the adaptive layout, unwalked in both T1.3 §8 and
here.

## Why accepting this is reasonable, and what makes it recoverable

- The flag has been ON in daily use since 2026-09-15 via the Debug toggle.
  The flip changes the default for a *fresh* install; it does not put Larry
  somewhere he has not already been.
- `Debug ▸ Use previous layout` is retained and needs no rebuild, so the
  rollback cost is one menu press.
- Group A cannot regress from this change, which is 13 of the 24 rows.
- Group C's failure modes are all *visible* — a wrong width, a result that
  does not appear, a clipped notice — rather than silent. The one worth
  watching is the pending-draft notice, because its failure mode is not
  noticing that something wants confirming.

## What this does not do

It does not close C8. C8 remains unrun and the preservation matrix remains
unexercised; `P0-preservation-checklist.md` still has no ticked rows. This
file is the gate's escape hatch, not a substitute for the work, and the
five C8 requirements stay on the open list.
