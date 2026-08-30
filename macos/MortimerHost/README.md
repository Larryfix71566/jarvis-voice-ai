# MortimerHost

**As of T1.3 (`MORTIMER_NATIVE_CLIENT_APP_PLAN.md`) this is the real
native Mortimer app** — the three-window SwiftUI view port over
`JarvisKit`: the console (voice wave, orb field, mic controls, topbar),
the display window (`surface == "window"` payloads, parked on a second
monitor), and the drawer with the seven tabs (Repo, Edit, Memory, Runs,
Agents, Output, Log). The original G1(b) debug harness view lives on
under **Debug ▸ Show message log**.

## Xcode settings (unchanged from the harness)

SPM executables have no automatic Info.plist/entitlements mechanism.
For a debug run straight from Xcode nothing is required — the app runs
unsandboxed and macOS prompts for the mic on first use. For a bundled
build, apply `templates/Info.plist.template`
(`NSMicrophoneUsageDescription`) and
`templates/MortimerHost.entitlements.template` (audio-input +
network-client) in the target's Info / Signing & Capabilities tabs.

## Build and test

```
cd macos/MortimerHost
swift build
swift test     # AgentRunStore reducer, UICommandRouter dispatch, TabState mapping
```

Run from Xcode (`open Package.swift`). Verification is the APP plan's
§8 V(-1)–V9 — including V0 (capture the decode fixtures into
`../JarvisKit/Tests/JarvisKitTests/admin-fixtures/`, see the README there)
and V9, the five-day daily-driver period that gates T1.4's deletion of
`web/`.

## Structure

- `Sources/MortimerHost/App/` — app scenes, theme/glass/tuning, the two
  message routers (one store feeder, one UI-command dispatcher)
- `Sources/MortimerHost/Stores/` — AgentRunStore (the agentRuns.ts
  reducer, ported verbatim), DisplayResultStore, ConversationStore
- `Sources/MortimerHost/Console|Display|Drawer/` — the views
- `Sources/MortimerHost/Placement/` — the ported DP8 ScreenPlacement +
  window lookup (CORE N15), consumed unchanged

Rollback: `defaults write <bundle-id> JARVIS_GLASS_ENABLED -bool false`
makes every glass surface opaque; the web console and MortimerShell are
untouched by this plan and still run (T1.4 owns their deletion, after
G1(e)).
