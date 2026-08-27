# MortimerHost

The G1(b) harness — proves `JarvisKit` holds a live voice session against
the unchanged bot, with barge-in working. Deliberately ugly: one window,
default system materials, no styling. This is not the T1.3 product app;
see `macos/README.md` for how the packages under `macos/` relate.

## Two settings Xcode must be told (SPM executables have no automatic
## Info.plist / entitlements mechanism — `macos/MortimerShell/Package.swift:14-21`
## documents the same constraint for the existing shell)

1. Open `Package.swift` in Xcode (`open Package.swift`).
2. In the MortimerHost target's **Info** tab, add
   `NSMicrophoneUsageDescription` with the string from
   `templates/Info.plist.template`.
3. In the target's **Signing & Capabilities** tab, add the entitlements
   in `templates/MortimerHost.entitlements.template`:
   `com.apple.security.device.audio-input` and
   `com.apple.security.network.client`, both `true`.

## Build and run (§8 V4)

```
cd macos/MortimerHost
swift build
```

Then open `Package.swift` in Xcode (for the Info.plist/entitlements
settings above to take effect) and Run.

## G1(b) run procedure (§8)

1. `./scripts/mortimer.sh start` — **not** `run_bot.sh`; the latter execs
   the bot on stdout and never creates `logs/bot.log`. Tail with
   `./scripts/mortimer.sh logs`.
2. Make sure no browser tab is open on the console — only one client may
   be connected (`request_handler.py:147-150` refuses a second POST).
3. Launch MortimerHost. If the bot has T2/K1 auth enabled, mint a client
   token and store it via the Debug menu's future token-entry flow, or
   `KeychainStore.setToken(_:for:)` — see the plan's §8 V4b. Without a
   token against an auth-enabled bot, Connect correctly ends in
   `state = .failed("Token required")`; that is not a defect.
4. Click Connect. `state` should show `connected` within 5 s and you
   should hear the greeting.
5. Run the plan's §8 V6–V9 checks (audio-never-stops, the five
   interruption scenarios, wake word, the routing eval) using this app
   as the client.

The **Debug menu**'s one item, "Clear stored token", calls
`KeychainStore.setToken(nil, for: client.config.botURL)` — use it to
isolate a T2 401 to the client half (plan §9's rollback table).
