# Mortimer interface cleanup plan, 2026-11-18

**Status:** approved by Larry. This plan lives on `main` so every system can read it; Phase 1 is built as PR 1 into `next` on `claude/interface-cleanup-phase1-20261118`. Row: `ROADMAP.md` WS-37.
**Mortimer is a non-production application** (`ROADMAP.md` section 0, rule 15), so this plan asks for checks on the Mac, not for production-grade gates.

## 1. Purpose and approval

Two reviewers looked at the Mac command console on 2026-11-18 and reached the same conclusion from different directions: the orb, the composed answers and the result carousel are worth keeping, and almost everything around them is left over from the old cockpit and says the same things several times. This plan removes the leftovers in three steps so that the conversation owns the window and the operator console is one click away.

**Approval.** Larry, 2026-11-18 16:13:45 UTC, in his Claude Duet channel: "Plan it and start PR 1". He was answering the coordinator's comparison of the Fable and Astra reviews, which proposed the three phases below.

Nothing in this plan has been rendered or compiled yet. Section 9 lists what is not verified.

## 2. Sources

- `docs/reviews/2026-11-18-fable-visual-review.md`: Fable 5.2's review, with file and line pointers into the source at `8d3be6df`. The Swift sources on `next` at `510b989` are identical to that commit (`git diff 8d3be6df 510b989 -- macos/MortimerHost/Sources` is empty), so those pointers are still exact.
- `docs/reviews/2026-11-18-astra-visual-review.md`: Astra's independent review of the live window ("one room, two levels of detail").
- `docs/interface-research/orb-plasma/ORB_SPEC.md`: the approved direction (composed answers, result carousel, the orb), the approved palette and the orb spec. This plan keeps all of it.
- The code itself, read on `next` at `510b989`. Paths below are under `macos/MortimerHost/Sources/MortimerHost/` unless they start with `Tests/`, which means `macos/MortimerHost/Tests/MortimerHostTests/`.
- The exact Phase 1 edits, with current code and line numbers, are in the implementation spec handed to the implementing engineer. This document is the plan; the spec is the worksheet.

## 3. Principles

1. **Front room: the conversation.** One calm window: the orb, one line of honest status, the thread and its answer, one place to type. Nothing else is on screen unless it is needed now.
2. **Back room: Inspect.** Agents, runs, council rounds, costs, logs and history stay as deep as they are today, behind a labelled Inspect button. Existing keyboard access stays (T opens the Log, Escape closes). A person who likes the console open can leave it open and it stays open.
3. **Keep what works.** The glass orb, the composed answers and the result carousel are kept. This is a change of emphasis, not a removal of expert tools.
4. **Say each thing once.** A state, a hint or a destination appears in one place.
5. **Never prompt for something that cannot work.** No invitation to speak while the microphone cannot be used; the action that fixes it sits beside the explanation.
6. **Palette and orb spec are kept.** No new colours. Rust for Mortimer, teal for the speaker, yellow for approval, and the offline behaviour, all as in `ORB_SPEC.md`. Phase 1 does not touch the orb renderer or any shader.
7. **Layout first, visual tuning last.** Size and position change before glass, glow or motion are tuned.
8. **Nothing useful is lost silently.** Where a removed surface carried a real notice or action, this plan says where it goes.

## 4. Phase 1 (PR 1): clear the rail, delete duplicates, bigger orb by size only

Small, mostly deletions. One new small view, one relabelled button.

### 4.1 What changes on screen

**The rail under the orb is cleared.** Today the rail still mounts the old status stack (`Console/AdaptiveStageView.swift:79` and `:94`, the view at `Console/VoiceWaveView.swift:484`), although a code comment says it was retired (`Console/VoiceWaveView.swift:482-483`). Removed from the screen:

- the name "Mortimer", the state label with its dot, and the captions "Wake word armed", "Microphone muted" and "Audio level unavailable";
- the six agent chips (Developer, Analyst, Systems, App Builder, Librarian, Scheduler);
- the clock and date, and the reminder, weather and last-session chips;
- the machine vitals readout.

**One line of status takes its place.** Directly under the orb, in natural case, in the existing dim text colour (existing amber when it needs attention). It shows exactly one thing, highest priority first:

| Situation | The line | Action beside it |
|---|---|---|
| Not connected | "Not connected" | **Connect** |
| Connection failed | "Couldn't connect" | **Connect** |
| Audio output moved to another device mid-session | the existing notice text | **Reconnect**, **Dismiss** (as today) |
| Something needs your approval | "Needs your approval" | none (the approval card is in the thread or the tray) |
| Voice not recognised by the speaker gate | the existing notice text | none |
| Microphone input was switched at connect | the existing notice text | none |
| Connecting | "Connecting" | none |
| Otherwise | "Listening", "Hearing you", "Mortimer speaking", "Thinking" or "Muted" | none |

Why these survive: the three notices are shown nowhere else in the app. Only the old stack reads them (`Console/VoiceWaveView.swift:551-562`; they are raised at `App/AppMessageRouter.swift:75`, `:83` and `:458`). Losing the Reconnect action would be a real regression, so it moves to the line.

Why the rest can go:

| Removed | Where it still is, or why it is fine |
|---|---|
| "Microphone muted", "Wake word armed" | The mic bar already shows Mic on/off and Wake word on/off (`Console/MicControlsView.swift:36`, `:59`). |
| "Confirmation needed in Output" (amber sentence) | Replaced by the line "Needs your approval" plus the orb's yellow ring (below). The signal is the same one (`Stores/DisplayResultStore.swift:36`). |
| Wake ripple in the rail | The orb draws its own wake flash (`Console/VoiceWaveView.swift:129`, `:469-472`). |
| "Audio level unavailable" | Still in the orb's accessibility value, and the orb draws a static trace when levels are missing (`Console/VoiceWaveView.swift:22-23`, `:61-66`). |
| Agent chips | A working agent already shows as the activity row in the thread (`Console/ConversationThreadView.swift:299`, `:345-347`). The chips' click-through to a filtered Runs tab goes; the Runs tab keeps its own agent filter (`Drawer/RunsTab.swift:136-144`), and the agent identity list it uses is kept (`Console/VoiceWaveView.swift:5-17`). |
| Clock, reminder, weather, last-session chips; machine vitals | Not shown anywhere else after this PR. This is the approved removal (Fable's change C). Their code stays in the tree, unmounted, so Phase 2 can give them a quieter home (a glance popover or Inspect). Note that the vitals readout was the on-screen battery and 85 percent warning (`Console/SystemVitalsView.swift:4-14`). |

**The yellow needs-you ring is switched on.** The orb already knows how to draw the approved yellow ring (`Console/CometOrbRenderer.swift:54-57`), and the view already has the parameter (`Console/VoiceWaveView.swift:31`), but nothing passed it. Phase 1 passes it from the existing signal. This is three call sites and is included because it lets the amber sentence go without losing the message; the line "Needs your approval" carries the words so the colour is not the only cue.

**Bigger orb, by size only.** The voice rail goes from 200 to 260 pt wide and the orb's slot from 150 to 220 pt tall. The orb's glass is drawn at 0.51 of the smaller slot side (`Console/CometOrbRenderer.swift:32-35`), so it grows from about 76 pt to about 112 pt across. That is about one and a half times, not double. Doubling it means changing the glass factor in the renderer, which is the deferred tuning in open decision 2. No shader or renderer file is edited.

**Disconnected state.** One honest line ("Not connected") and an enabled Connect button beside the orb. The empty conversation no longer says "Use the microphone controls to start a conversation" (`Console/ConversationThreadView.swift:305-306`); while not connected it says nothing. Once connected, the empty conversation shows "Ready" and one sentence, "Hold Space to talk, or type a request below." That sentence is now the only place the Space hint appears.

**Inspect.** The drawer button in the top bar reads "Inspect" when closed and "Close Inspect" when open (today "Panels" and "Close" with box glyphs, `Console/TopBarView.swift:189`). Same button, same attention dot, same T and Escape keys (`Console/ConsoleView.swift:180-206`). The drawer is already closed on a fresh install and comes back open only if it was open when last used (`App/UICommandRouter.swift:29`, `:31`, `:65`), so no change is needed for "closed by default; if you open it, it stays open". See open decision 3 for the one case where it opens itself.

**Duplicates deleted.**

| Deleted | Where |
|---|---|
| "Command Console" title and its icon | `Console/ConsoleActionBar.swift:97-102` |
| The raw state pill beside Connect (DISCONNECTED, READY, ERROR) | `Console/TopBarView.swift:73-80` |
| "Hold SPACE to talk" chip | `Console/MicControlsView.swift:41-53` |
| "SPACE TALK · T TRANSCRIPT" hint | `Console/MicControlsView.swift:77-81` |
| "Add content" headline and the caption sentence under it | `Console/AttachmentTrayView.swift:18`, `:25-29` |
| "Results" headline above the carousel | `Display/ResultCarouselView.swift:35` |

The mic button gains a tooltip, "Hold Space to talk", so the shortcut is still discoverable there. The drop zone stays until Phase 2 replaces the tray: it is the only visible hint that dropping works and most of the drop target. When content is staged, the tray keeps its "Staged content" heading and the provider line, because those are information.

**Knowledge Atlas and Memory graph shown twice.** Astra saw them in two successive rows. In the source on `next` the main console draws them once, inside the Knowledge menu (`Console/ConsoleActionBar.swift:292-308`). The second set lives in `Display/WorkspaceView.swift:152-193` and is switched off for the console (`Console/AdaptiveStageView.swift:151`); only detached panels draw it. An existing test already asserts this (`Tests/ConsoleActionBarTests.swift:145-162`). So Phase 1 changes no code here; it adds a whole-console test and an on-Mac check after the redeploy. If the duplicate is still visible on the Mac, that is a finding to chase, not something this plan can explain from source.

### 4.2 Files touched

Edited:
- `Console/AdaptiveStageView.swift`: unmount the old stack in both places, mount the status line in all three layouts, pass the needs-you signal to the orb, rail slot height, tell the thread when not connected.
- `Console/AdaptiveLayoutMetrics.swift`: rail width 260; new constant for the 220 pt slot.
- `Console/VoiceWaveView.swift`: delete the old stack and its three private helpers (lines 482 to the end). Lines 1 to 480 are untouched.
- `Console/ConversationThreadView.swift`: empty-state wording; a not-connected flag.
- `Console/ConsoleActionBar.swift`: title removed.
- `Console/TopBarView.swift`: state pill removed; Inspect label.
- `Console/MicControlsView.swift`: two hints removed; tooltip.
- `Console/AttachmentTrayView.swift`: headline and caption removed for the empty tray.
- `Display/ResultCarouselView.swift`: headline removed.
- `App/AppMessageRouter.swift`: one comment.

New:
- `Console/OrbStatusLine.swift`: the status rule as a small pure function, and the one-line view.

Left in the tree, no longer mounted: `Console/AmbientStripView.swift` (it also holds a time-formatting helper the Output tab uses, `Drawer/OutputTab.swift:96`, so it cannot simply be deleted) and `Console/SystemVitalsView.swift`.

Not touched: `Console/CometOrbRenderer.swift`, `Console/CrystalGlassRig.swift`, `App/AppTheme.swift`, `Display/WorkspaceView.swift`, the drawer.

### 4.3 Layout numbers

The rail layout needs a window at least 1180 pt wide (`App/AppTuning.swift:114`, unchanged) and enough stage for the rail plus a readable result. That minimum follows the rail width: 480 + 32 + 260 + 1 = 773 pt (was 713).

| Window | Drawer | Stage | Before | After |
|---|---|---|---|---|
| 1180 | closed | 1180 | rail | rail |
| 1280 (the default size) | closed | 1280 | rail | rail |
| 1280 | open at 400 (the default) | 870 | rail | rail |
| 1440 | open at 400 | 1030 | rail | rail |
| 1180 | open at 400 | 770 | rail | orb moves to the bottom band |
| 1280 | open at 500 or wider | 770 or less | rail down to 713 | orb moves to the bottom band |
| under 1180 | any | | bottom band | bottom band |

With the drawer closed nothing changes. The only new case is a docked-open drawer that leaves between 713 and 772 pt of stage. At 1180 with the drawer closed, the area beside the rail is 919 pt (was 979), still above the 900 pt point where the thread and the carousel sit side by side (`Console/AdaptiveStageView.swift:124`).

### 4.4 Tests

Changed:
- `Tests/AdaptiveInterfaceClosureC2Tests.swift:23`: rail width 200 becomes 260.
- `Tests/AdaptiveInterfaceClosureC2Tests.swift:161-261`: three tests that render the old stack (agent chip in the rail, the same with Reduce Motion, clock pinned above the chips) and their helper are deleted with the view.
- `Tests/CompactConversationTests.swift:48-125`: rewritten to check that an audio notice is visible in the new status line and that the Log still holds the transcript.
- `Tests/CompactConversationTests.swift:127-166`: deleted; it guarded the old stack.

New, in `Tests/InterfaceCleanupPhase1Tests.swift`:
- rail 260, orb slot 220, minimum rail stage 773;
- which layout is chosen at 900, 1180, 1280 and 1440 with the drawer closed and open;
- the status rule: not connected always wins and offers Connect; the priority order of notices; muted; barge-in;
- rendered status line: an enabled Connect button that calls its action; Reconnect and Dismiss still present for the audio-output notice;
- the empty conversation gives no prompt while not connected, and the offline stage shows "Not connected" and Connect with none of the old captions or agent chips;
- the drawer is closed with no saved state and comes back open when it was left open;
- the top bar has a button labelled Inspect that opens the drawer and then reads "Close Inspect"; the state pill and the old "Panels" label are gone;
- the whole console shows none of the removed strings, exactly one Knowledge entry and no bare "Knowledge Atlas" or "Memory graph" button;
- the carousel has no "Results" headline but keeps its spoken label and "Show all results".

Expected to pass unchanged: `Tests/FullConsoleRenderingTests.swift` (every label it requires is kept), `Tests/ConsoleActionBarTests.swift`, `Tests/AdaptiveLayoutMetricsTests.swift`, `Tests/OrbShellFrameTimeTests.swift`.

Frame time: `OrbShellFrameTimeTests` renders the orb on a 1440 x 220 canvas (`Tests/OrbShellFrameTimeTests.swift:60`). The orb's radius depends on the smaller side, so that probe already draws an orb the same size as the new rail slot. No probe is added. The Mac run is still the evidence.

The compile and test check for this PR is CI (`swift test --package-path macos/MortimerHost`); there is no Swift toolchain where the plan was written.

### 4.5 Acceptance checks on the Mac

After deploying the PR build, with the app at its default window size:

1. **Disconnected.** Quit and reopen without connecting. Under the orb there is one line, "Not connected", and a Connect button. The middle of the window does not tell you to use the microphone. Press that Connect button: it connects.
2. **Rail.** Connected, drawer closed. Under the orb there is one line and nothing else: no name, no agent chips, no clock, no weather or memory chip. The orb is visibly larger than before (about 112 pt across).
3. **Status follows the voice.** Speak, let Mortimer answer, mute. The line reads "Hearing you", "Mortimer speaking", "Muted" in turn. The orb's colours still follow the approved palette.
4. **Needs you.** Trigger something that asks for approval (an agent action that needs your yes). A yellow ring appears around the orb and the line reads "Needs your approval". Both clear when you approve or decline.
5. **Audio moved.** With a session live, switch the Mac's output device (for example connect AirPods). The line shows the notice with Reconnect and Dismiss; both work.
6. **Top bar.** No DISCONNECTED / READY / ERROR pill beside the Connect button. The drawer button reads "Inspect"; click it, the drawer opens and the button reads "Close Inspect". Escape closes it. T opens the Log.
7. **Stays as you left it.** Leave Inspect open, quit, reopen: it is open. Close it, quit, reopen: it is closed.
8. **Console row.** No "Command Console" title. Knowledge Atlas and Memory graph appear once, inside Knowledge, and not in a second row below. If you still see a second row, note which view was showing.
9. **Bottom of the window.** No "Add content" headline or caption; Paste, Choose and the drop zone are still there and a dropped file is still staged. The mic bar has no "Hold SPACE to talk" chip and no "SPACE TALK · T TRANSCRIPT"; holding Space still talks; the mic button's tooltip says "Hold Space to talk".
10. **Carousel.** Ask for something that produces a result. No "Results" headline above the card; "Show all results" and Previous/Next still work.
11. **Narrow and wide.** Drag the window under 1180 pt wide: the orb and its line move to the bottom band. Open Inspect and widen it past about 500 pt at the default window size: the same happens. Close it: the rail returns.
12. **Frame time.** Run `OrbShellFrameTimeTests` on the Mac as usual; crystal p95 stays within one 60 Hz frame.

## 5. Phase 2: one composer, mic in the orb, one top capsule

### 5.1 What changes on screen

- **One composer pill.** The typed field, a paperclip menu (Paste, Choose) and Send in one row of about 44 pt, replacing the tray stack. Dropping works anywhere on the window, and the drop zone is drawn only while something is being dragged. Staged items still need explicit approval before anything is sent, and the preview shows what will be shared and with which provider.
- **The mic folds into the orb.** The orb becomes the microphone control: click to toggle, hold to talk, as `ORB_SPEC.md` item 7 describes and as the code already supports when switched on (`Console/VoiceWaveView.swift:33`, `:43-46`, `:71-87`; the hold guard is `App/VoicePresentationState.swift:99`). A visible mute control stays beside it; mute must never depend on colour or animation alone. Wake word and sounds move into a menu. The bottom mic bar goes.
- **One top capsule.** The top bar and the console row merge into one floating capsule with about four items, a workspace switcher (Conversation, Results, Knowledge Atlas, Memory graph, Skills, Workflows) and an overflow menu (Connect or Disconnect, Voice, Display, Inspect). The second Connect button introduced beside the orb in Phase 1 becomes the only one on the disconnected screen. Disabled voice preferences are hidden until they can work.
- **A current-tense working line.** Under the request in the thread: "Searching your notes", "Reading the repository". It builds on the existing activity row (`Console/ConversationThreadView.swift:186-193`, which today prints the raw tool name) and is clickable to open Inspect on that run.
- **Error banner.** One plain line and Retry, gone on reconnect, folded into the status line (Fable's change 4), so the raw system error is no longer the headline (`Console/ConsoleView.swift:92-103`).
- **A quieter home for what Phase 1 unmounted.** Clock, next reminder, weather and the battery warning return as a glance popover or inside Inspect, never as raw memory-note text.

### 5.2 Files touched

`Console/AttachmentTrayView.swift`, `Console/TypedComposerRow.swift`, `Console/TypedComposerModel.swift`, `Console/CommandConsoleView.swift`, `Console/MicControlsView.swift`, `Console/VoiceWaveView.swift` and `Console/AdaptiveStageView.swift` (the orb slots opt in to interaction), `App/VoicePresentationState.swift` (shared push-to-talk guard), `Console/TopBarView.swift`, `Console/ConsoleActionBar.swift`, `Console/ConsoleView.swift`, `Console/ConversationThreadView.swift`, `Console/OrbStatusLine.swift`, `Console/AmbientStripView.swift`, `Console/SystemVitalsView.swift`. Possibly `App/Glass.swift` for the capsule shape. No palette change.

### 5.3 Tests

- Composer: paste, choose and drop each stage an item without sending it; Send is disabled until there is text or an approved item; the drop zone is absent at rest and present during a drag; whole-window drop reaches the store.
- Orb as mic: click toggles; a 350 ms hold talks and restores the previous mic state; Space and the orb never both own push-to-talk (extends `Tests/OrbShellFrameTimeTests.swift:237` and `Tests/C7aActivityRowTests.swift:120-145`); the orb exposes a button role and label; the mute control is reachable by keyboard.
- Top capsule: every destination reachable; one Connect; nothing clipped at 900, 1280, 1440 and 2560 wide (`Tests/FullConsoleRenderingTests.swift` updated, since it looks up the mic bar and tray labels that move).
- Working line: wording for each known tool family, a sensible fallback for unknown tools, and that clicking it opens Inspect on the active run.
- `Tests/ConsoleActionBarTests.swift` and `Tests/CompactConversationTests.swift` are rewritten around the capsule.

### 5.4 Acceptance checks on the Mac

1. The bottom of the window is one pill. Type and send; paste an image; choose a file; none of them sends before you approve.
2. Drag a file over the window: a drop zone appears; let go: the item is staged, not sent. Nothing is drawn when nothing is dragged.
3. Click the orb: the mic toggles. Hold it: you can talk, and on release the mic returns to how it was. Hold Space: same. The mute control is visible and works without the mouse.
4. The top is one capsule. Reach Atlas, Memory graph, Skills and Workflows from the switcher; Connect, Voice, Display and Inspect from the overflow.
5. Ask for something that takes a few seconds: a plain current-tense line appears under your request; clicking it opens Inspect on that run.
6. Force a failed connection: one plain line with Retry, which disappears on reconnect.
7. Repeat at a narrow and a wide window, and with Reduce Motion on.

## 6. Phase 3: the orb owns the empty stage; Inspect opens to the current run

### 6.1 What changes on screen

- **At rest** the orb is large and centred on an empty stage with its one line. No thread chrome until there is a thread.
- **When an answer lands** the orb moves aside to the margin and the answer takes the centre. When Mortimer needs permission, the movement stops and the action is readable. With Reduce Motion the same sequence is a direct cut with the text label.
- **Inspect opens to the current run** from its working line; older sessions sit behind a History control instead of being the first thing in the drawer.
- Transcript readability (Fable's changes A and B: a reading width of about 680 pt, speaker label once per run, timestamps on hover) fits here or late in Phase 2, whichever lands first.
- Only after this layout is right: visual tuning. That is where the orb's glass factor, the static stripes, refraction and the type and shape tokens are revisited, each behind `OrbShellFrameTimeTests` and each needing Larry's OK where `ORB_SPEC.md` says so.

### 6.2 Files touched

`Console/AdaptiveStageView.swift` (the at-rest and answering layouts and the transition), `Console/AdaptiveLayoutMetrics.swift`, `Console/VoiceWaveView.swift`, `Console/ConversationThreadView.swift`, `Drawer/DrawerView.swift`, `Drawer/AgentsTab.swift`, `Drawer/CouncilRosterView.swift`, `Drawer/RunsTab.swift`, `App/UICommandRouter.swift` (which tab Inspect opens on), `App/AppTuning.swift` (transition timing). Visual tuning, if approved later: `Console/CometOrbRenderer.swift`, `App/Glass.swift`, `App/AppTheme.swift`.

### 6.3 Tests

- Layout rule as a pure function: empty thread gives the centred orb; first turn or first result gives the margin orb; the rule is the same at narrow and wide widths.
- Transition is nil under Reduce Motion (extends `Tests/AdaptiveInterfaceClosureC2Tests.swift:45-52`).
- Focus and scroll position are kept when the orb moves and when other work finishes.
- Inspect opens on the active run when there is one; History lists older sessions; nothing opens by itself.
- Frame time with the large centred orb, same-session comparison as `ORB_SPEC.md` "Measure first".

### 6.4 Acceptance checks on the Mac

1. Open the app and connect: a large orb, one line, a composer, nothing else.
2. Ask a question: the orb moves to the margin and the answer takes the centre. Clear or start over: it returns.
3. Turn on Reduce Motion and repeat: the change is a cut, with the label.
4. Start a longer task and click its working line: Inspect opens on that run. History shows earlier sessions.
5. Astra's five-second test: show someone a still of disconnected, working and needs-approval. Can they name the state and their next action without coaching?

## 7. Open decisions

1. **Carousel: one card in focus, or neighbours peeking.** Astra: one selected result, with "1 of N" or "Show all" only when there is more than one. Fable: neighbours hinted at the edges, which today needs 720 pt of carousel width (`Display/ResultCarouselView.swift:60`). The coordinator recommends Astra's single card, with the count shown only when there is more than one. Recheck after the carousel has been seen on screen following today's redeploy. Phase 1 removes only the "Results" headline and leaves the pager as it is.
2. **Orb size.** Phase 1 makes the orb bigger by layout alone (about 76 pt to about 112 pt), which squares Fable's "double it" with Astra's "layout first, visuals last". Any change to the glass factor or shaders to go further waits until the layout has been seen, and stays behind `OrbShellFrameTimeTests`.
3. **Should the drawer ever open itself?** Found while planning; not part of the approved list. Today any result routed to the drawer opens it on the Output tab (`App/AppMessageRouter.swift:439-450`), and because the open state is saved on every change (`App/UICommandRouter.swift:29-34`), the next launch then starts with it open. That undercuts "closed by default" and Astra's "do not silently reopen it". The proposed change is small: never open, raise the existing dot on the Inspect button and the Output tab instead. It reverses a rule a test asserts (`Tests/CC7a2ReviewRegressionTests.swift:78-80`), so it needs Larry's yes. Until then Phase 1 leaves it alone.

## 8. Lane and overlap note

- `ROADMAP.md` WS-36 (Kimi) lists C6's open item "the `AdaptiveStageView.swift` orb slots" and names `TopBarView.swift`, `ConsoleActionBar.swift`, `MicControlsView.swift` and `ConversationThreadView.swift` in its scope. Under section 0 rule 14 a lane is a guide, not a lock, and any system not engaged may pick up work after updating the row's Owner and Where. There are no open PRs on these files.
- **PR 1 takes over the orb-slot item:** it passes the needs-you signal into the slots and resizes the rail slot. It does not switch on orb interaction (`interactive`) or share Space's push-to-talk guard; those remain C6's other open item and are Phase 2 here.
- The claim is the new WS-37 block in `ROADMAP.md`, added with this plan on `main`. PR 1 into `next` records its status only in its own file under `docs/roadmap-log/`.
- WS-17's rule that the console has one row of controls (`Console/ConsoleActionBar.swift:4-5`) is respected: no view or result control is added below the row. The Connect button beside the orb is the approved exception, in the place where Reconnect and Dismiss already were.
- `ORB_SPEC.md` is not edited.

## 9. What is not verified

- Nothing here has been compiled or rendered. There was no Swift toolchain where this was written; CI on the PR is the first compile.
- Whether the build Astra inspected matched this source. The duplicate Knowledge Atlas and Memory graph row cannot be found in the main console's source on `next`.
- How the 260 pt rail, the 112 pt orb and the single line look on the Mac, and whether the line wraps well for the longer notice sentences.
- Frame time of the larger orb in the real rail. The existing probe already uses the same orb radius, so no regression is expected.
- The listening, approval and carousel states have still not been seen on screen by either reviewer.
- Whether the accessibility walk used by the new tests can see every piece of text it checks for absence. The absence checks are backed by direct tests of the rules.
- Phases 2 and 3 are outlines. Their file lists come from reading the code, not from a design that has been drawn.

## 10. Progress log

(Empty. Status reaches this section only through the daily batch.)
