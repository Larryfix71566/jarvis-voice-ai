# Mortimer shell

MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md Part B. A SwiftUI app
hosting the console, display, and drawer as native windows around the
same three Vite entries the browser already serves — see `CLAUDE.md`'s
"Mac shell" paragraph for the full design writeup.

This scaffold was written and reviewed without access to Xcode or a Mac
(no sandbox available to build/run it) — see the plan's own note that
Part B needs Larry's machine to build and verify. **Nothing here has been
compiled.** Treat every file as a first draft to get right on your first
real build, not as tested code.

## First open in Xcode

1. `open Package.swift` (or File > Open... on this folder in Xcode).
   Xcode opens SPM packages as first-class projects — no `.xcodeproj` to
   hand-author or go stale.
2. Select the MortimerShell scheme, then the target's **Info** tab:
   add `NSMicrophoneUsageDescription` with the string in
   `templates/Info.plist.template`.
3. Target's **Signing & Capabilities** tab: add **App Sandbox**, check
   **Audio Input** (Hardware) and **Outgoing Connections — Client**
   (Network). See `templates/MortimerShell.entitlements.template` for
   the exact keys Xcode should produce.
4. Run `./scripts/mortimer.sh` from the repo root first (the shell
   loads `http://127.0.0.1:5173` and shows a native retry screen if
   nothing is listening there — B4).
5. Build and run (⌘R).

### 2026-08-18 — pop-in close path + device location (needs rebuild + 2 settings)

Two things landed after the S1–S3 fixes above, both needing another
Xcode build:

1. **Close path.** The native close works, but SwiftUI keeps a closed
   `Window` scene's WKWebView and its JS timers alive, so `pagehide`
   never fires and the popup's heartbeat kept the console believing it
   was still popped (the drawer flickered in-page then popped back).
   `ShellBridge` now handles `{cmd:"closeWindow"}` ->
   `ShellController.closeWindow(named:)` (refuses `console`), and the
   web side confirms the document actually went hidden before going
   silent.
2. **Device location.** `ShellLocation.swift` runs a `CLLocationManager`
   and POSTs coordinates straight to the sidecar's `POST /api/location`
   — never through the web layer — so the ambient weather chip is right
   for where you actually are. Macs have no GPS receiver; CoreLocation
   resolves from surrounding WiFi, accurate to roughly a city block
   versus IP geolocation's tens of miles (which put Larry in Forestbrook
   SC, ~350 miles off).

**Two settings must be applied by hand in Xcode** (see `templates/`,
both updated):

- Info tab -> add `Privacy - Location When In Use Usage Description` ->
  "Mortimer uses your location to show current local weather."
- Signing & Capabilities -> App Sandbox -> check **Location** under App
  Data.

Without them CoreLocation reports `.denied`, `ShellLocation` logs the
reason (subsystem `com.mortimer.shell`, category `location`) and stays
silent — the sidecar keeps using IP geolocation, so a build missing the
entitlement degrades rather than breaks.

`WindowLookup.swift` and `ShellLocation.swift` are both NEW files and
have been added to `Mortimer.xcodeproj/project.pbxproj` directly; if
Xcode still reports "cannot find … in scope", close and reopen the
project (it caches the parsed pbxproj).

## B0 spike — record the verdict here before trusting Part B proper

Two go/no-go questions, both with a predecided fallback if they fail
(see the plan's B0 section and this scaffold's own comments —
`ShellController.micCaptureAssumedWorking`,
`ShellWebView.useBroadcastRelayFallback`):

- [ ] **Mic/WebRTC capture inside WKWebView.** PASS = a full live voice
      turn (connect, speak, hear TTS) inside the console window.
      Verdict: _____________________________________________
- [ ] **BroadcastChannel across two WKWebViews.** PASS = opening the
      display window from the console shows it going "live" in the
      console's own presence tracking (same heartbeat mechanism as the
      browser — check the topbar's Display button state). Open the
      drawer too and confirm both stay live simultaneously.
      Verdict: _____________________________________________

If question 1 FAILS: flip `micCaptureAssumedWorking` to `false` in
`Sources/MortimerShell/ShellController.swift` and stop loading `/` in the
console window — the shell then hosts Display + Drawer only, and the
console (mic) stays in a plain browser tab. Multi-screen placement for
Display/Drawer still works; native audio capture becomes a future plan.

If question 2 FAILS: flip `ShellWebView.useBroadcastRelayFallback` to
`true` and implement `broadcastRelayFallbackScript`'s actual relay logic
(currently an inactive placeholder) plus a matching
`WKScriptMessageHandler` on the native side that rebroadcasts a message
from one webview's document into every other webview's document.
`popoutWindow.ts` needs zero changes either way — it's written against
the standard `BroadcastChannel` API, and the shim would sit underneath
it.

## What's NOT in this scaffold (B6 scope guard)

Menu-bar extra, global hotkeys, dock badges, login item, auto-start of
the Python stack, packaging/notarization, bundled static assets. Each is
a separate future decision, not an oversight.

## Building headlessly

`../../scripts/build_shell.sh` wraps `swift build` for a quick compile
check (macOS only). It does NOT produce a signed, entitled, runnable app
— open in Xcode for that (step 1 above), since mic access needs the
sandbox entitlement Xcode's UI applies, which `swift build` alone
cannot express for an SPM executable target.

## Naming (B7)

The app is "Mortimer" (shell implied). In code and docs this component
is "the shell" — never "sidecar" (that's the admin `:7861` Python
process) and never "drawer" (that's the tabbed panel it hosts, one of
the three windows).
