---
date: 2026-11-17
system: codex
rows: [WS-35]
prs: [378]
---

# C10: external measurement feasibility remains unverified

**None of the three metrics has been demonstrated measurable on the unmodified freeze. No app change has been proved necessary either.** The exact freeze builds locally, but the proposed external driver's macOS permissions prevent an input-driven dry run. These results are preflight evidence, not a negative experiment proving that Instruments cannot measure the app. C10 section 3 step 5 still applies: **unmeasured, instrumentation required**. Do not convert that status into a claim that the instrumentation must be in the app.

System: Codex. Session: parent thread `6afac5ab-3210-8191-a87a-f40521cd30ce`. Claim [#377](https://github.com/Larryfix71566/jarvis-voice-ai/pull/377) merged into main as `5f178bb071fa497b62916756f2ab0cc60e183178`, verified by fetch and GitHub on 2026-11-17. Owner is Codex; this follow-up branch is `codex/ws35-c10-measurement-harness-20261117`, targeting `next`. No reservation is needed. Independent review remains Kimi or Claude; Larry alone merges.

## Metric decisions and candidate boundaries

| Metric | Present decision | Candidate start → end, still requiring a freeze-app experiment |
| --- | --- | --- |
| Selection, ≥100 samples | Unmeasured; unmodified feasibility undetermined | The injected click's observed HID event → first presented frame containing the newly selected result's body. A selected-tab AX attribute or first unrelated frame is insufficient. Unique synthetic result bodies must establish which frame actually contains the target content. |
| Navigation acknowledgement, ≥100 samples | Unmeasured; unmodified feasibility undetermined | Observed HID event → first presented frame showing the specific navigation acknowledgement. Define the action and visible acknowledgement in advance, separately from content completion. AX action return, state mutation and layout completion are not presentation. |
| Graph pan/zoom, ≥300 frames | Unmeasured; unmodified feasibility undetermined | Each relevant pan/zoom HID input → the presented frame reflecting its camera update. Preserve event/frame associations, coalesced inputs and dropped frames; do not manufacture one sample per input if several inputs share a frame. |

An out-of-process driver can potentially find results by their unique title plus button role and window position. Frozen `Display/WorkspaceView.swift:42–56` exposes result buttons and selection traits; `MemoryGraphView.swift:103–104` labels Zoom out/in; `MemoryGraphCanvas.swift:170` labels its canvas. These are source observations, not a captured AX tree or validated selector script. There are no result/graph accessibility identifiers. XCUITest-style discovery is another candidate, not a tested fallback for this driver permission failure.

An external driver signpost should identify the action sequence and record its own clock immediately around event submission. That timestamps submission, not delivery. It needs validation against the observed HID event in the trace and a common clock with frame presentation. Record both endpoints, action ID, target PID/window, event/frame identifiers and any uncertainty. A nearest subsequent frame join alone cannot establish that selected content or acknowledgement appeared. AX press is an accessibility action request; it must not silently replace an HID-start metric.

Instruments 27.2 lists **Animation Hitches**, but no template named **Core Animation**. Apple describes User Events, Commits, Renders, GPU and Frame Lifetimes tracks in its [responsiveness documentation](https://developer.apple.com/documentation/xcode/improving-app-responsiveness). The installed Core Animation schema has `coreanimation-lifetime-interval` fields including `hid-latency`, `frame-seed`, `swap-id` and `display-id`. Neither the documentation nor installed schema proves these fields are populated, causally usable or exportable for this app on this Mac. `--show-recording-options` succeeds but is not a trace. A real recording and export table inspection must settle this before implementing the parser. Apple's [AX action documentation](https://developer.apple.com/documentation/applicationservices/1462091-axuielementperformaction) likewise supplies no frame-presentation completion guarantee.

For a validated trace only: retain raw endpoint timestamps and latency samples; sort valid samples and use rank `ceil(p*n)`, one-based, for both p50 and p95. Require n≥100/100/300 for selection/acknowledgement/graph and report failures and exclusions separately. At those minimum counts p95 is sample 95/95/285; p50 is 50/50/150. Empty data has no percentile. No parser, action script or numerical baseline is delivered against a guessed trace schema.

## Observed blockers

1. The diagnostic executable calls only `AXIsProcessTrusted`, `CGPreflightPostEventAccess`, `CGPreflightListenEventAccess` and `CGPreflightScreenCaptureAccess`; it never requests permissions or injects/captures anything. In the command sandbox all four return false. Outside that sandbox, Accessibility, event posting and event listening still return false; Screen Recording returns true. Both probes exit 0: that is successful status reporting, not a permission pass. Thus the proposed CGEvent/AX driver cannot perform this session's intended run. This says nothing about permissions of another process or an untested XCTest runner. No privacy setting was changed.
2. No offline fixture-loading entry point was found in the reviewed freeze app startup, debug menu, environment/argument handlers or workspace. `WorkspaceStore.swift:53` starts with an empty in-memory results array; incoming display messages reach it in `AppMessageRouter.swift:299–433`. `MemoryGraphView.swift:88` loads its graph through AdminAPI. The production native transport starts audio (`NativeAudioTransport.swift:349–366`). Starting a voice connection to populate a synthetic scene is outside this task. A separate hosting test that sets stores directly would measure a component, not the deployed app. The six-result/two-pin/graph scene therefore has not been prepared. An offline external replay transport might avoid app changes, but its feasibility and audio isolation have not been established or run.

## Isolation requirement before any GUI trial

Larry's follow-up requires isolation verification before any separately arranged experiment. A separate worktree or debug executable establishes neither a disposable preference domain nor synthetic routing. **Whether this debug executable shares the installed app's preference domain is unestablished.** No app was launched to investigate it.

Read-only inspection at `7e8adc9` confirms the concrete risks:

- `WorkspaceStore.swift:86` supplies persistence key `mortimer.interface.memoryGraph.view`; `MemoryGraphStore.swift:68–76` reads it using `UserDefaults.standard` by default, and `persist()` at lines 411–413 writes graph metadata back. Panning, zooming and leaving the graph can therefore affect persisted state.
- `MortimerHostApp.swift:25–33` reads and can write `mortimer.interface.layoutVersion` and `mortimer.interface.commandConsoleDefaultMigrated` during initialization. Startup itself is not a read-only check of settings.
- `JarvisConfig.swift:40–72` resolves each service URL from process environment, then standard defaults, then its compiled loopback endpoint. An unset or unparseable override can fall through; loopback alone does not mean synthetic. Changing only the admin URL leaves bot, wake-word and costs routing independently configured.
- With client auth enabled, config initialization can query `KeychainStore`. Its service is `com.mortimer.jarviskit` and account derives from the bot URL (`KeychainStore.swift:17–36`), rather than the executable's checkout path. `JarvisHTTP` attaches a configured bearer token to requests. A different executable or admin URL therefore does not prove credential isolation. No Keychain item or production preference was read during this source review.
- Read-only inspection of `scripts/bundle.sh:85` shows the packaged identifier `com.mortimer.host`; the script was not executed. This does not establish the bare debug executable's effective defaults domain or Keychain access.

Before execution, the experiment must have evidence of a disposable user/VM preference and credential environment, the exact executable/bundle identity and effective defaults-domain arrangement, and explicit synthetic routing for every reachable service with no fallback to production. Do not use a first launch on Larry's desktop to discover which settings it changes. Verify isolation with configuration/source evidence and non-app checks first; any later app-side confirmation must occur inside that established isolated environment. Never export production tokens or clone a production Keychain into it.

Preserve comparison meaning by recording an explicit non-sensitive configuration manifest: layout/thread choice, glass/accessibility settings, window geometry, display scaling/refresh, and initial graph camera/filter/layout state. Populate only those agreed settings inside the disposable environment and record before/after state there. A VM changes rendering/GPU/display conditions: it can establish functional feasibility, but its timings are not the deployed physical-Mac baseline. An eventual physical-Mac baseline still requires its own verified isolation/routing arrangement and configuration comparison before execution. Endpoint or identity changes must be documented as experimental configuration, not silently treated as an identical deployed setup.

These are unfulfilled prerequisites, not verified isolation. This follow-up changes documentation only; no launch, preference write, credential access, endpoint connection, server execution or permissions change occurred. The independent graph fixture lead does not remove these requirements, and its disposable-VM/loopback restrictions remain intact.

## What ran

The raw text evidence and exact build command/flags are in [the preflight evidence directory](../acceptance/ws35-c10-preflight-20261117/). Original local evidence is retained at `/Users/larryfix/Documents/Codex/2026-11-16/task/ws35-c10-evidence/`. `SHA256.json` records original filenames, byte sizes and hashes; the diagnostic C source is preserved as `driver-preflight.c.txt` rather than an executable source artifact in the repository.

| Check | Exit/result |
| --- | --- |
| `git fetch origin`; verify #377 merged | 0; main `5f178bb0`, claim present |
| `git worktree add --detach ../ws35-c10-freeze 7e8adc9` | 0; isolated exact freeze, clean tracked tree before and after build |
| Swift signpost search at `7e8adc9` | 1, no matches; identifier search finds console/thread/skills identifiers, not result/graph IDs |
| `git diff --exit-code c23dda5 7e8adc9 -- . ':!docs' ':!ROADMAP.md'` | 0; non-documentation tree identical |
| Initial offline `swift build --product MortimerHost` with isolated cache flags | 1; manifest compilation attempted the protected default Clang cache and selected the CommandLineTools SDK |
| Same build with explicit Xcode SDKROOT and isolated CLANG_MODULE_CACHE_PATH / SWIFTPM_MODULECACHE_OVERRIDE | **0**, build complete, 16.54 s; existing warnings retained in raw log |
| `xcrun clang driver-preflight.c -framework ApplicationServices -o driver-preflight`; run diagnostic | 0 / 0; permission results above |
| `xcrun xctrace list templates` | Initial sandbox attempt 134 (Instruments cache access); outside sandbox 0, retained template listing |
| `xcrun xctrace record --template 'Animation Hitches' --show-recording-options` | 0; options only, no recording |

Toolchain: Xcode 27.2 (`27B52`), Swift 6.4.2 (`swiftlang-6.4.2.1.9`), arm64 macOS; explicit SDK `MacOSX27.2.sdk`. Existing WebRTC 120.0.0 dependency checkout/artifacts were copied read-only from the production build cache into the isolated freeze `.build`; local workspace-state paths were rewritten. `--disable-automatic-resolution --skip-update` were used; no dependency was fetched. `--disable-sandbox` disabled SwiftPM's nested manifest sandbox only; the build still ran inside the command sandbox. No tracked freeze file was edited.

Local executable: `ws35-c10-freeze/macos/MortimerHost/.build/debug/MortimerHost`; SHA-256 `b54b296e88cd810dd910542cc7026c9ffec7ed71c8c9b721b7ecc91c3d5967a3`. This is a locally compiled debug executable, **not** an identity assertion about the deployed executable. Successful build log SHA-256: `89c76dfeace888e70aaeeb742d68b98a8d93a8895f31b6d8938f0b06743e8237`; exact successful build command receipt: `08f2e6fb31c8a6cbff4b477e91452842784e90fb89ca82d157f8fd3d1ca8551c`.

**App execution: not run. Trace paths/hashes: none. Selection n=0, acknowledgement n=0, graph n=0. p50/p95: undefined.** No app launch, input injection, backend start, live voice/model/external workload call, deployment, bundle/start script, production write or acceptance closure occurred. No component benchmark was substituted.

## Decision and next actor

Larry can arrange the required input permissions for an agreed external driver and approve an offline scene-preparation route that demonstrably avoids voice and production services. After the isolation requirements above are verified, Codex would capture a bounded trial against local `7e8adc9`, inspect actual exported event/presentation associations, and only after successful attribution deliver the fixed action script and parser. These are prerequisites, not a request to change the freeze or a claim that permissions alone solve the measurement.

If Larry instead elects a first instrumented-build baseline, the concrete proposed changes are an explicit disconnected synthetic fixture entry point, stable result/acknowledgement/graph target identities, and action/revision correlation markers for selection, navigation and camera updates tied to verified presented frames. A marker after a method returns, SwiftUI `onAppear`, a Core Animation transaction completion or a display-link tick alone is not a demonstrated presentation boundary. Instrumented end boundaries still need validation. No such changes are made or declared necessary by this preflight. That option abandons these metrics as a freeze baseline and requires Larry's explicit acceptance decision.

Remaining: Kimi or Claude review of this note and evidence; Larry's choice of the blocked experiment prerequisites or a different baseline build. All three full-scene metrics remain open.
