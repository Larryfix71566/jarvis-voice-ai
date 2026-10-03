# Supporting display transfer: one validated, confirmed route

**Status:** approved scope (Larry, 2026-10-03: new row WS-21; Claude implements, Codex reviews before merge). Design below; not yet implemented.
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
opens until steps 1 and 2 pass.

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
4. **Apply.** `workspace.sendToDisplay(content)`, assign the display window to the
   destination screen (`ScreenPlacement.assignDisplay(to:)`, D2), then
   `placement.openDisplay()`.
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

`DisplayWindowView` reports what it actually renders. On appear, and whenever the
selection changes, it records the supporting-content key it chose (stage panels for a
transport payload, or the supporting stage for a pointer/voice selection) in
`DisplayWindowStore.presented`.

The coordinator then checks the following, every runloop turn for up to 3.5 s (inside
the bot's 5 s wait):

- the display window exists and is visible (`findHostWindow(.display)`);
- the window's frame lies on the destination screen
  (`DisplayPlacementPolicy.screen(for:in:)`);
- `DisplayWindowStore.isWindowOpen` is true;
- `workspace.supportingContent` equals the requested content;
- `DisplayWindowStore.presented` equals the requested content's key.

All five → `applied`. A timeout, a display window closed by the display-lost handler,
or the destination disconnecting during the wait → `error` with the cause. Each of those
also clears the supporting selection, so main does not keep pointing at an absent
window.

The console path stays request/response. `AppMessageRouter` runs the transfer in a
child task and sends the `console/result` when it settles, so other messages are not
held up while it waits.

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

### D5. Detach and move validation

- `panel_detach` with a result UUID that is not a live workspace result is `invalid`,
  and no content record is created. Its `screen_id` (now allowed by both validators) must
  be a connected placement ID.
- `panel_move` rejects an unknown or disconnected `screen_id` before `PanelStore`
  changes.
- `PanelStore.move`/`moveContent` take a validated screen and keep their own non-empty
  guard.

### D6. Inventory

The requested and periodic inventories are built from one function, so they cannot
differ:

- `screens`: placement ID, name, `is_console`, `is_supporting`.
- `supporting_display`: `{content, result_id?, screen_id, presented}`, where `presented`
  is D3's check evaluated now.
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

Codex's six diagnostic tests and two probes are added unchanged as regression tests
once Larry copies them over. They must fail on `63aaeef` and pass on this branch.

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
