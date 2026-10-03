# Supporting display transfer: one validated, confirmed route

**Status:** PR #171; Codex requested changes on `43f3d5b` (2026-10-03, four defects), repaired on `ws21/display-transfer`, awaiting Codex's re-review; Mac acceptance open. Approved scope: Larry, 2026-10-03, new row WS-21; Claude implements, Codex reviews before merge.
**Row:** `ROADMAP.md` WS-21.
**Baseline:** `origin/main` `63aaeef` (deployed 2026-10-03).

## 1. Why

On the deployed build `63aaeef`, Larry asked Mortimer to put the weather radar on the
external monitor. The bot log shows two `display_popout` calls (about 13:56 and 13:57).
Both returned `ok`, and Mortimer said the radar was on the external monitor. Each time
the supporting display opened empty.

Codex's audit (2026-10-03, six temporary native diagnostic tests and two Python probes
against source identical to production) found five defects. Claude confirmed each
against `63aaeef`:

| # | Defect | Where |
|---|---|---|
| F1 | `display_popout` opens the display window and assigns no content. Weather is main-window only (WS-15) and voice never sets the supporting selection, so the window shows "Nothing on display". The tool description promises to move weather or research. | `UICommandRouter.swift` `display_popout` → `placement.openDisplay()`; `ui_control.py` description |
| F2 | Success is reported before the app confirms anything: `ui_control` returns `"ok"` once the message is queued. | `ui_control.py` `resolve_ui_command`/handler |
| F3 | `panel_detach` with an unknown result UUID still creates a content-panel record and returns `.applied`. | `ConsoleActionCoordinator.swift` panel branch; `PanelStore.openContent` |
| F4 | Screen identities disagree. The inventory names screens by `localizedName`; placement matches the hardware display UUID. `PanelStore.move`/`moveContent` accept any non-empty string, so a move to a screen that does not exist succeeds. | `WorkspaceStore.swift` inventory; `ScreenPlacement.liveScreens`; `PanelStore` |
| F5 | The contract and inventory are incomplete. Detach reads `screen_id`, but both validators allow it only on `panel_move`. The requested inventory omits panel and screen details. The periodic inventory reports fixed-panel destinations as null and lacks the supporting-display selection. | `console_protocol.py` `ACTION_ARG_FIELDS`; `ConsoleActionRegistry.swift`; inventory builders |

The pointer menus already use the right route (`workspace.sendToDisplay(content)` and
then `openDisplay()`), and the bot's `console_action` tool already waits up to 5 s for
the app's `console/result`. The repair reuses both and adds no second display path.

## 2. Requirements (Codex review, Larry)

1. Voice and pointer transfers go through one validated coordinator into the existing
   shared supporting-display stage.
2. Content is resolved by result UUID (or a named non-result view); the destination is
   resolved by the same stable screen identity placement uses.
3. Missing results, protected content and disconnected destinations are rejected
   before anything opens.
4. The requested and published inventories report the same content ownership and the
   actual placement.
5. Tool descriptions and argument contracts match what the app does.
6. Completion is reported only after the app confirms that the intended content is
   presented on the intended display. Failures are reported truthfully.
7. Unchanged: weather's default main-window placement, the conversation (it stays on
   the main screen), shared result tiles, pins, reading position and radar controls.
   Repeated transfer requests reuse the presentation.

## 3. Design

### D1. `SupportingDisplayCoordinator` (native, new)

One `@MainActor` object owns every transfer to the supporting display. Its callers are
the voice action (D4), the Results, Knowledge and Tools menus (`ConsoleActionBar`), the
results view's Display menu (`WorkspaceView`), and `skill_display_transfer`.

`transfer(content, screenID?) async -> TransferOutcome` runs in this order. Nothing
opens until steps 1 and 2 pass, and steps 1–3 change nothing, so a refused or
repeated request leaves a transfer that is still confirming alone (Codex review
of #171).

1. **Content.** `.result(UUID)` must be a live workspace result that is not
   protected-local. A missing, closed or protected result is rejected with a named reason.
   `.memoryGraph`, `.skills`, `.workflows` and `.skillDetail(id)` keep their existing
   checks.
2. **Destination.** It is resolved with `ScreenPlacement.liveScreens()` IDs (D2). With
   no `screen_id`, the destination is the connected screen the console is not on: the
   last supporting screen if it is still connected, otherwise the first non-console
   screen. With only one screen, or a `screen_id` that is not connected, the transfer is
   rejected with a reason.
3. **Reuse.** If the display window is already presenting this content on this screen,
   the result is `noop` ("already showing") and nothing reopens.
4. **Accept and apply.** `workspace.sendToDisplay(content)`, assign the display window
   to the destination screen (`ScreenPlacement.assignDisplay(to:)`, D2), then
   `placement.openDisplay()`. Only an accepted transfer takes over from one still
   confirming. It inherits what that chain of transfers started from (the earlier
   selection, and whether the window was already open), and with it the cleanup.
5. **Confirm (D3)** and return `applied` with a summary naming the content and screen,
   or a failure with the reason.

### D2. One screen identity

`PlacementScreen` gains a `name` (the screen's `localizedName`). Its `id` stays the
`CGDisplayCreateUUIDFromDisplayID` string, as it is today. The same values feed:

- the console inventory's `screens` list (`id` = placement ID, `label` = name, plus
  `is_console` and `is_supporting`);
- `panel_move`/`panel_detach` validation (an unknown ID is rejected, not stored);
- the coordinator's destination.

`ScreenPlacement.assignDisplay(to screenID:)` records the display window's target
screen for the next reposition, so the policy places the window on that screen rather
than on its last automatic choice.

### D3. Confirmation that the content is presented

"Presented" uses the rule the main surface already uses to decide that a
result is on the supporting display: `DisplayWindowStore.isPresented(content,
selection:layoutVersion:)`. It is true only while the display scene is on
screen (`isWindowOpen` is set by the scene's own `onAppear`/`onDisappear`) and
the stage renders that content: a stage panel for a transport payload, or the
supporting stage for a pointer or voice selection. The coordinator also checks
that the display window's frame lies on the destination screen
(`ScreenPlacement.screenID(of: .display)`).

It checks both every 50 ms for up to 3.5 s, inside the bot's 5 s wait. Both
true → `applied`. A timeout, or the destination disconnecting, → `error` with
the cause. Either way the chain's earlier selection is put back (or cleared if
there was none), and a window the chain opened is closed, so main does not
point at an absent window and no empty window is left. A newer accepted
transfer supersedes an older one still waiting; the older one returns
`superseded` and undoes nothing, so it can never undo a newer success or a
display that was open before.

The console path stays request/response. `AppMessageRouter` runs a transfer in
its own task and sends the `console/result` when it settles, so other
messages are not held while it waits.

### D4. Voice contract

- New console action `display_show`. `target` is a result UUID from the inventory, or
  one of `memory_graph`, `skills`, `workflows`. Its optional arg is `screen_id`, a
  placement ID from the inventory. It is added to `ALLOWED_ACTIONS`,
  `REQUIRED_TARGET_ACTIONS`, `ACTION_ARG_FIELDS` (Python) and `ConsoleActionRegistry`
  (Swift). The result summary names the content and the screen on success, or the
  failure reason.
- `ui_control` `display_popout` no longer claims to move content. Its description
  becomes "open the supporting display window as it is", and it points to
  `console_action` `display_show` for putting a result there. `UI_CONTROL_ADDENDUM`
  gains one sentence: putting a result on the other screen is `display_show` with the
  result's UUID from the inventory, and success is spoken only from its result.
- `display_close` keeps working; with nothing else on the display it is the existing
  "return it here".
- `display_popout` with nothing for the display to show sends a `ui/noop`
  ("Nothing is on the other display yet…"), which the bot speaks, instead of
  opening an empty window.

### D5. Detach and move validation

- `panel_detach` with a result UUID that is not a live workspace result is `invalid`,
  and no content record is created. Its `screen_id` (now allowed by both validators) must
  be a connected placement ID. That check runs once, before any change, for every
  detach form: a content target, an open content panel's UUID, and a fixed panel.
  Each then lands on the named screen (a fixed panel records it in
  `PanelStore.screenByPanel`; an open content panel moves).
- `panel_move` rejects an unknown or disconnected `screen_id` before `PanelStore`
  changes.
- `PanelStore.move`/`moveContent` take a validated screen and keep their own non-empty
  guard.

### D6. Inventory

The requested and periodic inventories are built from one function, so they cannot
differ:

- `screens`: placement ID, name, `is_console`, `is_supporting`.
- `supporting_display`: `{open, content, result_id, result_ids, tiles, screen_id,
  presented}`, read from what the window renders
  (`DisplayWindowStore.visibleStage`: the selection alone in layout 1; otherwise the
  supplemental tile, the bounded stage panels, then pinned panels). `content` and
  `result_id` name the first tile, `result_ids` lists up to six results across all
  tiles, and `presented` is true while the window is open and the stage is not
  empty. An ordinary `surface: window` result has no selection and is still listed
  (Codex review of #171). `isPresented` reads the same stage. A protected result's
  ID is never listed.
- `panels`: fixed panels and content panels with their actual screen ID, read from
  placement for an open window and from the record otherwise; null only when the
  panel is not detached.

### D7. Preserved behaviour

Weather still arrives in the main window and is moved only on request. The conversation
stays on the main screen while a result is on the supporting display (CC7a.2b). Result
tiles, pins, reading position, radar controls and the shared stage are unchanged; the
coordinator only changes how content reaches the stage. CC7a.2b's arrival routing
(`AppMessageRouter` display arrivals) is not changed.

## 4. Tests

Native (MortimerHost):

- weather and radar transfer by voice and by pointer → the display presents that result
  on the requested screen; the conversation stays in main;
- a repeated request → `noop`, same presentation;
- a stale or closed result ID, and a protected result → rejected, no window opened;
- one screen only, and an unknown or disconnected `screen_id` → rejected, no window
  opened;
- the destination disconnecting during confirmation → error, selection cleared;
- confirmation timeout → error;
- `panel_detach` of an unknown UUID → `invalid`, no record; `panel_move` to an unknown
  screen → `invalid`;
- the requested and periodic inventories are equal, with placement screen IDs.

Codex's six diagnostic tests are characterization tests: they assert the defects and
passed on `63aaeef`, so they cannot run unchanged as regressions (corrected 2026-10-03,
Codex review of #171). The originals, the two Python probes (which print observations
and were never pass/fail tests) and the review evidence are archived unchanged in
`docs/acceptance/supporting-display/codex-audit-2026-10-03/`. Each of the six has a
regression twin with the repaired expectation in `VoiceDisplayAuditRegressionTests`.
Codex's four review probes are in `SupportingDisplayTransferTests` unchanged, with
further cases for a successor that succeeds, a failure that restores an already-open
display, a refused request during a transfer that later fails, detach of an open
content panel, and an inventory of several tiles.

Python: `display_show` validation (targets, `screen_id`), `screen_id` accepted on
`panel_detach`, the console tool returning failure text when the app reports an error,
and the `ui_control` description no longer promising a transfer.

## 5. Acceptance (Mac, after merge and deploy)

Codex reviews the repair against:

- weather/radar transfer;
- repeated requests;
- stale result IDs;
- missing monitors;
- disconnect during transfer;
- the conversation remaining on the main screen.

External-display acceptance stays open until Larry runs these on the Mac.

## 6. Out of scope

New display layouts; changes to weather's default placement; CC7a.3 (Recents, voice
result actions by number and subject), which stays in WS-17.

## 7. Progress

- 2026-10-03: row and plan claimed (Larry chose a new row). Defects F1–F5 confirmed
  against `63aaeef`.
- 2026-10-03: D1–D7 implemented on `ws21/display-transfer`.
  - `SupportingDisplayCoordinator` (new) is the one route; `display_show`
    and `skill_display_transfer` reply from `executeTransfer` after D3's
    confirmation, and the results, Knowledge and Tools menus call it through
    `DrawerState.supportingDisplayRef`.
  - `ScreenPlacement` gained `currentScreens`, `screenID(of:)`,
    `consoleScreenID`, `preferredSupportingScreenID` and `assignDisplay(to:)`,
    and `PlacementScreen` gained `name`.
  - `ConsoleActionCoordinator.inventoryJSON()` is the one inventory, and the
    `inventory` action's result now carries it as `data`.
  - Panel detach and move reject unknown results and screens.
  - Native tests are in `SupportingDisplayTransferTests`; existing panel
    tests now name connected placement screens. Python tests cover the
    `display_show` contract, `screen_id` on detach, failure relay and the
    `display_popout` description.
  - Codex's six diagnostic tests and two probes are still to be added once
    copied over.
- 2026-10-03: Codex reviewed `43f3d5b` (request changes) and reproduced four defects
  with independent probes: a refused request superseded a valid transfer still
  confirming; a failed replacement left the window its predecessor opened open and
  empty; fixed-panel detach ignored `screen_id`; the inventory reported nothing
  presented while a transport result was on the stage. Repaired as D1, D3, D5 and D6
  now describe. Codex's audit tests and probes are archived and their regression
  twins added (§4).
