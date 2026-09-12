import Foundation
import SwiftUI
import AppKit

/// APP plan §6 — every number, one place. Constants marked "web parity"
/// carry their measured source; the UserDefaults-overridable ones read
/// the key on access so a `defaults write` takes effect on relaunch.
enum AppTuning {
    private static func seconds(_ key: String, _ fallback: Double) -> Double {
        let v = UserDefaults.standard.double(forKey: key)
        return v > 0 ? v : fallback
    }

    /// Edit tab active-run poll (EditModePanel.tsx setInterval(...,3000)).
    static var editRunPollSeconds: Double { seconds("JARVIS_EDIT_POLL_SECONDS", 3.0) }
    /// Repo tab poll (GitPanel.tsx setInterval(refresh,15000) — F5, NOT 3s).
    static var repoPollSeconds: Double { seconds("JARVIS_REPO_POLL_SECONDS", 15.0) }
    /// Memory tab poll (MemoryPanel.tsx setInterval(refresh,15000) — F5).
    static var memoryPollSeconds: Double { seconds("JARVIS_MEMORY_POLL_SECONDS", 15.0) }
    /// Runs tab poll — NEW behavior, not web parity (RunsPanel has no
    /// periodic poll today; F5). Live feel at a slower cadence than Edit.
    static var runsPollSeconds: Double { seconds("JARVIS_RUNS_POLL_SECONDS", 5.0) }
    /// Costs tab poll (MORTIMER_OPTIMIZATION_PLAN.md Phase 0 step 9) — NEW,
    /// no web parity to match (no such panel exists there). Spend changes
    /// only as fast as LLM calls happen, so this is deliberately the
    /// slowest poll in the drawer rather than matching Runs' 5s.
    static var costsPollSeconds: Double { seconds("JARVIS_COSTS_POLL_SECONDS", 30.0) }
    /// Council roster poll, under the Agents tab (MORTIMER_OPTIMIZATION_
    /// PLAN.md's Interface Task) — NEW, no web parity. A council round
    /// takes minutes and only five have ever run to completion, so this
    /// is the slowest poll in the drawer: the panel is a record to read,
    /// not a live meter.
    static var councilPollSeconds: Double { seconds("JARVIS_COUNCIL_POLL_SECONDS", 60.0) }

    /// agentRuns.ts:79 MAX_AGENT_RUNS
    static let maxAgentRuns = 20
    /// agentRuns.ts:61 MAX_ACTIVITY
    static let maxActivity = 50
    /// agentRuns.ts:54 MAX_TOOLS
    static let maxTools = 10
    /// agentRuns.ts:53 DONE_FADE_MS (seconds here)
    static let doneFadeSeconds = 8.0
    /// displayResults.ts MAX_DISPLAY_RESULTS (F4 — Output tab cap)
    static let maxDisplayResults = 20
    /// displayWindow.ts MAX_OPEN_DISPLAY_PANELS (F4 — display window cap)
    static let maxDisplayWindowPanels = 15
    /// conversationFeed.ts:36 MAX_CONVERSATION_ENTRIES
    static let maxConversationEntries = 200
    /// SideDrawer.tsx DRAWER_DEFAULT_WIDTH_PX
    static var drawerDefaultWidth: Double { seconds("JARVIS_DRAWER_WIDTH", 400) }
    /// SideDrawer.tsx DRAWER_MIN_WIDTH_PX
    static let drawerMinWidth: Double = 300
    /// SideDrawer.tsx drawerMaxWidthPx() = min(720, 60vw)
    static let drawerMaxWidthCap: Double = 720
    static let drawerMaxWidthFraction: Double = 0.6
    /// 2026-09-05 (drawer-handle fix): the docked drawer's resize grip IS
    /// the gap between the stage and the drawer's glass edge — DrawerView
    /// drops its leading padding when docked so the grip sits on the
    /// panel edge, not 8pt into the background. 10pt is the hit target;
    /// the visible hairline lives on its trailing edge.
    static let drawerHandleWidth: Double = 10
    /// DP8 two-panel extended-screen split (CORE §1.4)
    static let displaySplitLeftFraction = 0.60

    // --- display panels (2026-09-05, "graph window sizable without limitation") ---
    /// SingleDisplayPanel's outer inset inside the display window / stage
    /// (was a literal 20 in DisplayWindowView).
    static let displayPanelInset: Double = 20
    /// The corner resize grip's hit target (the SF symbol alone was ~10pt).
    static let displayPanelGripSize: Double = 22
    /// A graph image is re-requested from the sidecar at the panel's new
    /// pixel size this long after the size stops changing — one render
    /// per resize, not one per mouse event (each render is a networkx
    /// layout + Pillow encode on the Python side).
    static let graphImageReloadDebounceSeconds: Double = 0.3
    /// Mirror of jarvis/graphs/config.py GRAPH_IMAGE_MIN_PX / MAX_PX — the
    /// sidecar clamps too; this just avoids asking for a size it will
    /// refuse or shrink.
    static let graphImageMinPx = 400
    static let graphImageMaxPx = 3000

    // --- parity sweep 2026-08-30 -----------------------------------------
    /// OrbField.tsx MIN_WORKING_MS — a satellite's working glow holds at
    /// least this long even when the run finishes sooner (the done SOUND
    /// still plays immediately; the visual lingers).
    static let minWorkingSeconds = 2.5
    /// AmbientStrip.tsx sidecar poll (60s) and clock tick (10s).
    static let ambientPollSeconds = 60.0
    static let ambientClockTickSeconds = 10.0
    /// AmbientStrip.tsx REMINDER_EXPIRY_GRACE_MS
    static let reminderExpiryGraceSeconds = 60.0
    /// SystemVitals.tsx POLL_MS + LOW_BATTERY / BATTERY_ALWAYS
    static let vitalsPollSeconds = 60.0
    static let lowBatteryPercent = 20.0
    static let batteryAlways = true
    /// OrbField.tsx CAPTION_MAX_USER / CAPTION_MAX_BOT
    static let captionMaxUser = 160
    static let captionMaxBot = 600
    /// App.tsx transient-notice auto-dismiss (speaker gate, popout errors)
    static let noticeFadeSeconds = 4.0

    // --- adaptive interface (closure plan C2.3 / C2.4; interface plan §7) ---
    /// §7: layout/mode transitions take 200 ms; Reduce Motion, a held
    /// pointer button or keyboard editing suppress the animation entirely
    /// (see AdaptiveTransition).
    static let layoutTransitionSeconds: Double = 0.2
    /// §7: the wide layout (left voice rail + workspace) starts here; below
    /// it the compact bottom-wave placement is used.
    static let wideLayoutMinWidth: Double = 1180
    /// §7: the sources inspector is a 300 pt subpane only when the results
    /// pane is at least this wide; otherwise it opens as a sheet.
    static let inspectorSubpaneMinWidth: Double = 820
    static let inspectorWidth: Double = 300
}

/// Interface plan §7 audio-presentation values, one place (closure C2.4).
/// Colors are the plan's teal #2DD4BF (user) and violet #A78BFA (Mortimer);
/// contrast verification against the actual theme is a C8 row.
enum AudioPresentationTuning {
    static let userRGB: (Double, Double, Double) = (45, 212, 191)        // #2DD4BF
    static let assistantRGB: (Double, Double, Double) = (167, 139, 250)  // #A78BFA
    static let neutralRGB: (Double, Double, Double) = (95, 130, 150)
    static var userColor: Color { Color(red: userRGB.0 / 255, green: userRGB.1 / 255, blue: userRGB.2 / 255) }
    static var assistantColor: Color { Color(red: assistantRGB.0 / 255, green: assistantRGB.1 / 255, blue: assistantRGB.2 / 255) }
    /// VoiceEnvelope smoothing, elapsed-time exponential (§7: attack 40 ms, release 180 ms).
    static let attackSeconds: Double = 0.040
    static let releaseSeconds: Double = 0.180
}

/// The one decision for §7's layout transition: animate for 200 ms, or not
/// at all. No transition under Reduce Motion, while a pointer button is
/// held (a drag or resize in progress), or while a text view has keyboard
/// focus (selection/editing must not be disturbed).
@MainActor
enum AdaptiveTransition {
    static func animation(reduceMotion: Bool) -> Animation? {
        if reduceMotion { return nil }
        if NSEvent.pressedMouseButtons != 0 { return nil }
        if NSApplication.shared.keyWindow?.firstResponder is NSTextView { return nil }
        return .easeInOut(duration: AppTuning.layoutTransitionSeconds)
    }
}
