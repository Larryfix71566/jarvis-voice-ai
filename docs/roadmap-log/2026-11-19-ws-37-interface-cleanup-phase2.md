---
date: 2026-11-19
system: claude
rows: [WS-37]
prs: [397]
---

# 2026-11-19: WS-37 interface cleanup, Phase 2 (Claude)

- **System:** Claude (Claude Code cloud session). Planned and integrated by the Opus 5.5 thread; five slices implemented in parallel by Sonnet helpers.
- **Larry's words (UTC, Claude Duet channel), 2026-11-19 02:10:12:** "continue development, asign to sub-agents anything you can do in parallel".
- **Plan:** `docs/plans/MORTIMER_INTERFACE_CLEANUP_PLAN_2026-11-18.md` (#392), §5. Stacked on Phase 1 (#393); until #393 merges this PR's diff also shows Phase 1's commits.
- **Change (paths under `macos/MortimerHost/Sources/MortimerHost/`):**
  - **One composer pill.** New `Console/ComposerPillView.swift` replaces the tray stack in `Console/CommandConsoleView.swift`: paperclip menu (Paste content, Choose content…), "Type a request", Send, about 44 pt. Staged items open a review panel above it with the same labels and the same explicit-approval rule as before (provider shown, nothing sent until approved and asked). New `Console/AttachmentIntake.swift` is the one drop/paste/import implementation (`AttachmentTrayView` now delegates to it). New `Console/WindowDropOverlay.swift`: `.mortimerWindowDrop()` on the console root accepts a drop anywhere and draws the drop zone only while a drag is over the window.
  - **Mic in the orb.** The orb slots in `Console/AdaptiveStageView.swift` pass `interactive: true` (click toggles, 350 ms hold talks and restores). New `PushToTalkOwnership` (`App/VoicePresentationState.swift`) is the one owner shared by Space and the orb, so they never both own push-to-talk. The bottom mic bar is deleted; `Console/MicControlsView.swift` now holds only the Space monitor as `.pushToTalkKeys()`. New `Console/OrbMicControls.swift`: `OrbMuteButton` under the status line ("Mute"/"Unmute" with symbol, shown only while connected, keyboard reachable). The interactive orb's accessibility label is "Microphone — tap to toggle, hold to talk".
  - **One top capsule.** `Console/TopBarView.swift` now hosts the console's one control row (`ConsoleActionBar(embedded: true)`), the console result line, Glance, ⌘K, Inspect (Phase 1 labels kept) and a "More" menu (Disconnect while connected, Voice when voices exist, Wake word when available, Sounds, Open display, Command menu). No Connect in the capsule: the Connect beside the orb is the only one on the disconnected screen. New `Console/CommandPaletteView.swift`: ⌘K command menu (views, Inspect, Log, display, connect/disconnect, wake word, sounds, expand voice) with type-to-filter, Return runs the first match, Escape closes.
  - **Working line.** New `Console/WorkingLine.swift` maps tool ids (from `mcp_servers/*/server.py`) to current-tense phrases ("Searching your notes", "Reading the repository", …) with agent and generic fallbacks; the activity row in `Console/ConversationThreadView.swift` shows only the phrase (actor stays in the VoiceOver label) and clicking it opens Inspect on the Agents tab.
  - **Error banner folded into the status line.** `Console/ConsoleView.swift` no longer draws the raw red error banner; `Console/OrbStatusLine.swift` shows "Couldn't connect" with Retry, the raw reason only as a tooltip, gone on reconnect.
  - **Glance.** New `Console/GlanceView.swift`: a time button in the capsule with an amber dot only for a battery or 85 percent warning; its popover shows time and date, next reminder, weather and the warning. The last-session/memory text is never shown.
- **Tests (new):** `ComposerPillTests` (5), `ConsoleCapsuleTests` (7), `GlanceTests` (9), `OrbMicTests` (5), `WorkingLineTests` (9). **Changed:** `FullConsoleRenderingTests` (the reachable set is now Connect, the composer pill, More and Inspect instead of the mic bar and tray), `InterfaceCleanupPhase1Tests` (retry on failure, Inspect fixture environment, composer and More instead of tray and wake word), `CompactConversationTests` (orb label), `C7aActivityRowTests` (phrases; `stepName` test removed with the function), `OrbShellFrameTimeTests` (shared push-to-talk owner).
- **Not tested here:** no Swift toolchain in the session, so nothing was compiled or run locally; CI's Swift jobs are the first build. Nothing has been seen on the Mac.
- **Not wired:** clicking the working line opens the Agents tab, not the specific run (no tab takes a run id from outside yet).
- **Unchanged:** drawer auto-open on drawer-routed results (plan §7 decision 3, still Larry's call). The location chip work by another thread is not touched.
- **Next actor:** Larry: merge #393, then this PR; redeploy; the plan's §5.4 checks.
