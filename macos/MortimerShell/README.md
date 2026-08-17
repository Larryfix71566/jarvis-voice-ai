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
