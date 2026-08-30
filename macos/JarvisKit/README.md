# JarvisKit

A platform-neutral Swift Package (macOS 26 / iOS 26) that is the single
client-side implementation of the RTVI voice session, the admin sidecar
API, and the wake-word path — shared by `MortimerHost` (this plan's debug
harness) and, later, the T1.3 native app.

This package was written entirely without a Swift toolchain (`macos/JarvisKit/PROBE.md`
explains why, and what to run to verify) — see
`docs/plans/MORTIMER_NATIVE_CLIENT_CORE_PLAN.md` for the full design record.
Every file traces to a step in that plan's §5, and every numeric constant
lives in `Sources/JarvisKit/JarvisConfig.swift`'s `JarvisTuning` enum (§6).

## Two possible transports

`RTVITransport` is a protocol with exactly one implementation compiled into
the package at a time:

- **Branch A** — `PipecatSDKTransport.swift`, a thin wrapper over Pipecat's
  official `pipecat-client-ios-small-webrtc` SDK. Only exists if the plan's
  §5 step 2 probe passed on real hardware.
- **Branch B** (the default shipped here) — `DirectWebRTCTransport.swift`,
  a hand-written signalling + WebRTC implementation over `stasel/WebRTC`
  (SPM binary distribution of Google's `WebRTC.xcframework`).

`PROBE.md` in this directory records which branch is active and why. As
shipped, **Branch B is active** — the probe could not be run in either of
the implementer's execution environments (no Swift toolchain in either the
cloud sandbox or the connected-Mac bridge shell). See `PROBE.md` for the
exact commands to run the real probe and switch to Branch A per plan §5
step 6, if it turns out to qualify.

## Running the tests

```
cd macos/JarvisKit
swift build      # §8 V1 — also proves stasel/WebRTC resolves on Branch B
swift test       # §8 V2 — all of plan §7 should pass; record the count
```

Both require Xcode / a Swift toolchain, which is not available in either
of the environments this package was written in. Larry runs both on his
Mac per the plan's §8.

## T1.3 additions (the F12 deliverable)

`AdminAPI.swift` now also carries the concrete per-tab response structs
CORE deferred (`GitStatus`, `GitDraft`/`GitActionResult`,
`SelfEditModels`/`SelfEditStatus`, `MemoryOverview`/`MemoryReviews`/
`KnowledgeOverview` and their leaves, `RunsList`/`RunSummary`,
`RunDetail`/`RunEvent`) plus additive methods: typed reads
(`gitStatusTyped`, `selfeditModelsTyped`/`selfeditStatusTyped`,
`memoryOverview`/`memoryReviewsTyped`/`knowledgeTyped`,
`runsTyped`/`runTyped`) and the draft→confirm writes (`prepareCommit`/
`commit`, `preparePush`/`push`, `selfeditValidate`/`Submit`/`Revert`).
This is `MORTIMER_NATIVE_CLIENT_APP_PLAN.md`'s F12 deliverable —
ADDITIVE to K8; CORE's seventeen read routes are unchanged. Decode
fixtures live in `Tests/JarvisKitTests/admin-fixtures/` (captured per that
plan's §8 V0, see the README there).

## What this package deliberately does NOT do

- No client-side VAD, no half-duplex, no muting the outbound track while
  the bot speaks (§3 N9 — these are the barge-in obligations).
- No reconnect policy — `connect()`/`disconnect()` are one-shot; auto-retry
  is a decision for the app that hosts `JarvisClient` (T1.3), not this
  package.
- No per-tab `AdminAPI` response structs — those are typed inside
  `AdminAPI` by whichever plan renders that tab (§3 N14); this package
  returns `JSONValue` for admin **responses** only (requests are typed).
- No openWakeWord port — the wake listener streams PCM to the existing
  `ws://127.0.0.1:7862/ws` sidecar exactly as the web client does (§3 N10).
