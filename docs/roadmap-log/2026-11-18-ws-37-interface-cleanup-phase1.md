---
date: 2026-11-18
system: claude
rows: [WS-37]
prs: []
---

# 2026-11-18: WS-37 interface cleanup, Phase 1 (Claude)

- **System:** Claude (Claude Code cloud session). Spec by a Fable 5.2 helper; implementation by a Sonnet helper; reviewed and committed by the Opus 5.5 thread.
- **Larry's words (UTC, Claude Duet channel), 16:13:45:** "Plan it and start PR 1".
- **Plan:** `docs/plans/MORTIMER_INTERFACE_CLEANUP_PLAN_2026-11-18.md` (on `main` via #392), §4.
- **Change (paths under `macos/MortimerHost/Sources/MortimerHost/`):**
  - `OrbFieldView` (the old rail stack: name, state label, captions, six agent chips, clock/weather/memory chips, machine vitals) is deleted from `Console/VoiceWaveView.swift` and unmounted from both orb slots in `Console/AdaptiveStageView.swift`. `AGENT_LAYOUT` stays for the Runs tab; `AmbientStripView.swift` (its `relTime` is used by the Output tab) and `SystemVitalsView.swift` stay in the tree, unmounted.
  - New `Console/OrbStatusLine.swift`: one status line under the orb in all three layouts. Not connected or failed shows Connect; the audio-output notice keeps Reconnect and Dismiss; then needs-your-approval, the speaker-gate and audio-input notices, connecting, and the voice state.
  - The orb's needs-you ring is now passed (`DisplayResultStore.hasPendingDraft`) at the three orb call sites.
  - Rail 200 to 260 pt, rail orb slot 150 to 220 pt (`Console/AdaptiveLayoutMetrics.swift`). Orb glass about 76 to 112 pt. No renderer or shader change.
  - Removed: "Command Console" title (`ConsoleActionBar.swift`), the raw state pill (`TopBarView.swift`), both push-to-talk hints (`MicControlsView.swift`; the mic button gets a "Hold Space to talk" tooltip), the empty tray's "Add content" headline and caption (`AttachmentTrayView.swift`), the carousel "Results" headline (`Display/ResultCarouselView.swift`).
  - Empty conversation: no prompt while not connected; otherwise "Hold Space to talk, or type a request below." (`ConversationThreadView.swift`).
  - Drawer button reads "Inspect" / "Close Inspect", identifier `console.inspect`. T and Escape unchanged; the drawer already starts closed and keeps the user's last choice.
  - Takes over WS-36 C6's open item "the `AdaptiveStageView.swift` orb slots" (rule 14); orb interaction and the shared push-to-talk guard stay for Phase 2.
- **Tests:** `Tests/InterfaceCleanupPhase1Tests.swift` (12 new); `AdaptiveInterfaceClosureC2Tests.swift` (rail 260, slot 220; three `OrbFieldView` tests removed with the view); `CompactConversationTests.swift` (notice now checked in the status line; the retired-layout caption test removed with the view).
- **Not tested here:** no Swift toolchain in the session, so nothing was compiled or run locally; CI's Swift jobs are the first build. The look on the Mac and the larger orb's frame time are unverified.
- **No longer on screen:** the agent chips and their click-through to a filtered Runs tab; the clock, reminder, weather and last-session chips; the machine vitals readout (battery and 85 percent warning). Phase 2 gives these a quieter home.
- **Open:** drawer auto-open on drawer-routed results is unchanged (plan §7 decision 3, needs Larry).
- **Next actor:** Larry: merge, redeploy, then the plan's §4.5 checks.
