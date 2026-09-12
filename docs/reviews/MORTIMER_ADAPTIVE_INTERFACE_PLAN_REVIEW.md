# Review — Mortimer adaptive interface implementation plan, item-by-item status

**Candidate reviewed:** `~/Documents/Codex/2026-09-09/can/work/active-repo`, branch `feat/adaptive-compact-conversation`, HEAD `6bf0270` (2026-09-11 15:54 ET). 56 commits on top of the plan baseline `2ccf66c`, which is a true ancestor; 98 files changed, +8,111/−307. Backend (`jarvis/`) untouched except one test-fixture fix (`tests/unit/test_admin_selfedit.py`, isolated as draft PR #65).
**Correction to yesterday's review:** that review inspected `~/jarvis-voice-ai-clean` (the installed checkout) and concluded nothing was implemented. The implementation lives in the isolated checkout above, exactly as the plan's D1/§8 prescribe. Yesterday's baseline findings (dual window minimums, second capture engine in `WakeWordListener`, Edit-draft loss on pop-out, bare `URLSession` in `GraphImageView`) remain true of the baseline and are referenced below where the candidate addresses them.
**Method:** every changed Swift/Python file and every acceptance record was read. Five independent read-only audits (one per phase P1–P5) were run against the files and cross-checked; their file:line citations are the evidence below. Nothing was executed — no `swift test`, no app launch — so every "N tests passed / SHA-256" claim in the records is **unverifiable from the tree** and is reported as the implementer's claim. Paths are relative to the candidate root; `MH/` = `macos/MortimerHost/Sources/MortimerHost/`, `JK/` = `macos/JarvisKit/Sources/JarvisKit/`.
**Date:** 2026-09-11

## 1. Bottom line

The candidate is a serious, largely honest implementation of P1, P3, P4 and P5, with P2 correctly recorded as **blocked at the audio-signal seam** and P0's feasibility work actually done. Adaptive layout is **off by default** (`mortimer.interface.layoutVersion` defaults to 0, `MH/App/MortimerHostApp.swift:27`); the shipped default path is still the old console, which is what §10 asks for until P6 acceptance. The plan's own status header in the candidate says "IMPLEMENTATION IN PROGRESS; NO RELEASE ACCEPTANCE", and that is the right reading.

What is done, partial, and missing, in one line each:

- **P0** — automated baseline captured (JarvisKit 96 / MortimerHost 39 tests), preservation checklist written but **zero rows checked**, audio feasibility genuinely probed (media-source `audioLevel` present at ≈9 Hz held-peak; inbound `audioLevel` absent; 50 ms stats cache), no screenshots of the baseline, no performance baseline, no UI-test harness beyond offscreen `NSHostingView` fixtures.
- **P1** — scrollable header done and well tested; keyboard navigation **absent**; §7's 12 pt became 11 pt undocumented; §8's "keep tab bodies and models untouched" **not respected** (models hoisted to app scope — which fixes the Edit-draft-on-pop-out bug — plus a Runs-tab rewrite).
- **P2** — presentation layer, colors, timing, "Audio level unavailable" fallback and the wave's adaptive branch are built and tested with synthetic levels; **no live audio signal is wired** and the records say so plainly; the §4.3 "small AI label during barge-in" is computed but never rendered.
- **P3** — workspace store, single-subscription identity adapter, pins (cap 20 refuses), A/B compare, inspector, sources, export, lettering removal, `layoutVersion` gate: done. 200 ms transition **absent**; §7 literals hardcoded outside `AppTuning`.
- **P4** — all nine §4.5 capabilities present, authenticated transient transport, stale-generation rejection, 50/200/500 fixtures. Frame-time p95 **unmeasured**; the pre-existing unauthenticated `GraphImageView` fetch remains on the legacy path.
- **P5** — pure `DisplayPlacementPolicy` with stable display IDs, unplug recovery, manual-intent revisions, 250 ms single debounce, Reset Layout: done and tested at policy level. Screen **unlock** not observed; backing scale captured but unused; no `ScreenPlacement` (AppKit adapter) tests.
- **P6** — full backend suite green in normal/reverse/seeded order (after the #65 fixture fix); independent frozen-profile receipt passed once (`4d188e8`) and **fails at later candidates** on nine `WindowVisibilityTests` because the Tart guest has no active desktop space; bundle now embeds and signs WebRTC and refuses to launch without it; Larry's Xcode smoke test passed. Hardware audio/monitor matrix, VoiceOver, rollback exercise, deployment: **open**.

Three things that need your decision before anyone continues:

1. **P2's unblock.** The candidate's `P2-additive-observation-design.md` proposes tapping the processed-capture and device-render seams inside the pinned WebRTC build. That is a transport change the plan forbids inside P2 ("do not roll a transport rewrite into this plan"), and it competes with `MORTIMER_NATIVE_AUDIO_TRANSPORT_PLAN.md`. Pick one: approve the additive observation design as its own reviewed plan, or park P2 behind the native-audio plan. Neither is authorized today.
2. **`bundle.sh` absorbed one of the five production local patches.** The candidate's `macos/MortimerHost/scripts/bundle.sh:14-38, 65-72` now copies the resolved WebRTC framework, signs it, and `codesign --verify --deep --strict` — the record says this "explicitly incorporates" the production checkout's uncommitted patch. The plan says "do not overwrite or silently absorb them". It is disclosed, not silent, but merging this branch will collide with the production working-tree diff on that file. Decide whether the candidate version supersedes the local patch.
3. **Model ownership moved out of `DrawerView` (P1 boundary).** This is a real improvement — it is what makes UI-1's "draft survives pop-out" true (`MH/Drawer/DrawerModels.swift:11`, `MH/App/MortimerHostApp.swift:34,57,96`) — but §8 P1 says tab bodies/models stay untouched unless a proven lifecycle bug is fixed separately. The bug was real (baseline `DrawerView.swift:18-24` @State models, two `DrawerView` instances). Accept it as the "separate lifecycle fix", or ask for it to be split out of PR #66.

## 2. §1 decisions

| # | Decision | Status | Evidence |
|---|---|---|---|
| 1 | Preserve every sidecar tab and contents | Done in code, **unaccepted** | All eight keys/labels/order from unchanged `DrawerState.tabKeys` (`MH/Drawer/DrawerTabStrip.swift:24,68,91`); `DrawerView.swift:139-158` switch covers all eight. Bodies changed mechanically (API refresh, cancel guards, scroll restore) — `P0-preservation-checklist.md` has 0 of 22 rows checked |
| 2 | Fix sidecar header (scroll, arrows, active state, no squeeze) | Done except keyboard | `DrawerTabStrip.swift:19-35,56-58,70-73,109`; `TabStripViewport.swift:10-14`; no `focusable`/`onKeyPress` anywhere in `Drawer/` |
| 3 | One Silo wave, teal user / violet Mortimer, measured activity | **Partial — presentation only** | Colors `MH/Console/VoiceWaveView.swift:190-192` (#2DD4BF / #A78BFA); adaptive branch never calls `simLevel` (`:169-176`); production snapshot is `nil` (`MH/Console/AdaptiveStageView.swift:13-18`) so no measured activity drives it |
| 4 | Remove decorative lettering, keep small name | Done in adaptive path only | `MH/Console/OrbFieldView.swift:285-301` gated by `hidesLettering` (declared `:37`), set true at `AdaptiveStageView.swift:25,39,51`; legacy path (default) keeps lettering |
| 5 | Central results with comparison and pinning | Done | `MH/Stores/WorkspaceStore.swift:29-42,56-82,126-132`; `MH/Display/WorkspaceView.swift:57-72` |
| 6 | Contextual details complement sidecar | Done | `MH/Display/WorkspaceSourcesView.swift:15-22` (≥820 pt subpane at 300 pt, else sheet); never touches `DrawerState.activeTab` |
| 7 | Automatic one-/multi-monitor adaptation | Done at policy level, hardware untested | `MH/Placement/DisplayPlacementPolicy.swift:75-165`; `MH/Placement/ScreenPlacement.swift:45-156` |
| 8 | Interactive memory graph, no branding copy | Done, performance unmeasured | `MH/Display/MemoryGraph*.swift`; `JK/MemoryGraphAPI.swift` |

## 3. Non-regression contracts

| Contract | Status | Notes with evidence |
|---|---|---|
| UI-1 Existing functions survive | **Code-level yes; acceptance open** | Every OrbField functional indicator has a home in both full and compact presentations except **wake ripple and agent beams**, which exist only in the full stage (`OrbFieldView.swift:82-108`; `compactReadout` `:219-246` has neither). The rail substitutes the wave flash for the ripple. Plan says every indicator must be mapped — this is an undisclosed omission (`P3-progress.md:26-30` also omits them). Edit draft now survives pop-out by construction (models app-scoped). `OutputTab`'s baseline first-mount auto-expand (`OutputTab.swift:45-58` baseline) was replaced by ingestion-time expansion in the store (`MH/Stores/DisplayResultStore.swift:40`) — same rule, different moment; checklist row still unchecked |
| UI-2 Voice path untouched | **Done** | Grep over all changed sources for `AVAudioEngine`, `RTCAudioSource`, `setMicEnabled`, `wakeListener`, echo/device selection: zero hits outside `docs/acceptance/.../probes/`. `JarvisClient`, `DirectWebRTCTransport`, `AudioSession`, `MicControlsView` unchanged |
| UI-3 Results and sidecar preserved | **Done** | Router surface split + auto-open/dot rules byte-identical (`MH/App/AppMessageRouter.swift:90-105`); `WorkspaceStore.close():151-160` never touches `DisplayResultStore`; pin cap refuses (`:126-132`); `trimHistory():172-178` protects pins/panes; renderer fallback `MH/Display/WorkspaceResultPane.swift:36-40` |
| UI-4 No privilege/data expansion | **Done** | No `jarvis/` change; graph edges only from decoded `edges` (`MH/Display/MemoryGraphCanvas.swift:21-47`); only new persistence is the graph view record (`mortimer.interface.memoryGraph.view`, node IDs but no text, `MH/Display/MemoryGraphStore.swift:5-27`) and placement record (`mortimer.interface.placement.v1`) |
| UI-5 One owner | **Done, one latent issue** | One `messageStream()` loop feeds workspace + both legacy stores with a shared `workspaceID` (`AppMessageRouter.swift:80-93`); one graph store per owner, `loadIfNeeded` guarded (`MemoryGraphStore.swift:106-109`); one screen observer, one debounce work item. Latent: the audio observation generation is view `@State` (`AdaptiveStageView.swift:13`) — harmless while the snapshot is nil, wrong once an adapter exists. `DrawerModels.scrollOffsets` is one dictionary keyed by tab (`DrawerModels.swift:16`); docked + detached showing the same tab would fight — untested |
| UI-6 Display changes don't lose work | **Done at policy level** | Manual intent detected by pointer/live-resize evidence (`ScreenPlacement.swift:49-51,89-100`), suppressed during topology change (`:139-141`); recovery record + clamp (`DisplayPlacementPolicy.swift:128-144`); `manualRevision` ordering (`:62-73`) |
| UI-7 Passing remains meaningful | **Done** | No `XCTSkip`/`expectedFailure`/relaxed assertions in any new test; 900 s gate intact (`sandbox/verify.py:20`); language mode `.v5`, WebRTC 120.0.0 unchanged (`Package.swift`/`Package.resolved` not in diff). The seeded-order failure was fixed by correcting the polluting fixture, not by skipping (PR #65). The nine `WindowVisibilityTests` failures in headless verification were **retained as failed evidence**, not skipped |

## 4. Phase-by-phase item status

### P0 — Baseline and audio feasibility

| Deliverable | Status | Evidence |
|---|---|---|
| Baseline manifest (commit, tests) | Done | `P0-P1-progress.md:5-18`: `30850f9` = `2ccf66c` + plan; JarvisKit 96 / MortimerHost 39 green (claimed) |
| Function inventory with screenshots of every tab/dialog/console/panel/screen state | **Partial** | Inventory exists as the 22-row `P0-preservation-checklist.md`; no baseline screenshots are in the tree; every row unchecked |
| Fixture manifest | Partial | Graph fixtures in `MemoryGraphTests.swift:14-71` and `probes/GraphFixtureServer.py` (50 nodes/80 edges); no audio or monitor fixture manifest |
| Audio feasibility finding | **Done — finding is "not yet feasible on M120 stats alone"** | `P2-audio-feasibility.md:52-116` two disposable probes (sources in `probes/`), `:192-222` pinned upstream trace (`audio_level.cc` held peak ≈9.09 Hz; `rtc_stats_collector.h` 50 ms cache); `P2-upstream-source-manifest.json` pins commit `b0cc68e6` with hashes |
| Measured performance record | **Absent** | No frame-time, latency or connection-time measurements anywhere; `MemoryGraphTests.swift:69` prints layout seconds and says so |
| UI-test harness identified | Partial | Offscreen `NSHostingView` + AX-tree fixtures work (`P0-P1-progress.md:51-65`), and Computer Use in a GUI VM was used for interaction; no XCUITest; headless verification cannot run visibility tests |
| Live local customization inventory | Done | `P6-interim-checks.md:212-217` re-confirms the five files and base commit |
| Pre-existing deviations recorded (from yesterday's list) | Partial | `GraphImageView` bare `URLSession` disclosed (`P4-progress.md:82,169-170`); Edit-draft-on-pop-out fixed rather than recorded; `WakeWordListener` second capture engine and the 400×300 vs 900×600 dual minimum are **not** recorded anywhere |

### P1 — Sidecar header

| §4.2 / §8 item | Status | Evidence |
|---|---|---|
| Only strip scrolls; chrome fixed | Done | `DrawerTabStrip.swift:22-35`; chrome in `DrawerView.swift:58-95` outside the `ScrollView` |
| Intrinsic width, one line, no truncation | Done | `DrawerTabStrip.swift:70-73` (`lineLimit(1)`, `fixedSize`) |
| Trackpad/wheel | Done (untested) | inherent to `ScrollView` |
| **Keyboard navigation** | **Absent** | no focus/key handling in `Drawer/` |
| Arrows only on overflow, disabled at ends | Done | `DrawerTabStrip.swift:19,56,109`; `TabStripViewport.swift:10-14`; test `DrawerTabStripRenderingTests.swift:174-192` presses until disabled |
| Selection by click/restored pref/voice reveals whole tab | Done | `DrawerTabStrip.swift:44-53` `onChange(of: selectedTab, initial: true)`; voice path via unchanged `UICommandRouter.setTab` |
| Scrolling never selects | Done | `DrawerTabStrip.swift:96-112` arrow handler only `scrollTo`; asserted `:187` |
| Active border + dots + accessible selected/unread | Done | `DrawerTabStrip.swift:74-93` |
| Large text increases overflow | Done via app menu, not system | "Aa" menu 11/16/22 pt, key `mortimer.interface.sidecarTabTextSize` (`DrawerView.swift:20,64-66,100-121`); macOS ignores Dynamic Type (documented at `P0-P1-progress.md:144-149`) |
| Docked and detached at 300 pt | Partial | Strip alone tested at 300 pt; full `DrawerView` chrome at 300 pt and the detached scene are untested by assertion (Computer Use observed detached at ~420–690 pt) |
| No tab recreation / duplicate polling | Done structurally | `DrawerModels.swift:33-46` leases; `alreadyVisible` guard; tests assert `visibleCount`, not HTTP counts |
| §7 label 12 pt / control ≥32 pt | 11 pt (undocumented); 32 pt done | `DrawerTabStrip.swift:9-11` |
| §8 boundary "tab bodies and models untouched" | **Not respected** | 12 drawer files + `MortimerHostApp.swift` + `DisplayResultStore.swift` changed; `RunsTab.swift` gained generation tokens and a "Retry details" button (`RunsTab.swift:245-249`) — new behavior, not preservation |
| Isolated PR | Done | Draft PR #66 (`fdf1b89`), five-file version, CI green (claimed); does not include the typography work |

### P2 — Honest dual-speaker voice feedback

| §4.3 / §6 / §7 item | Status | Evidence |
|---|---|---|
| Measured user level → teal | **Absent (disclosed)** | `AdaptiveStageView.swift:13-18` passes `snapshot: nil`; `AudioActivityAccumulator` used only in tests |
| Measured playout level → violet | **Absent (disclosed)** | same |
| State labels Standby/Connecting/Listening/Hearing you/Mortimer speaking/Thinking/Muted | Done | `MH/App/VoicePresentationState.swift:15-24` |
| Overlap: user priority immediately, AI activity kept as small label | **Partial** | priority `:59-60`; `assistantSpeaking` computed `:57,64` but **no view renders it** |
| Thinking only with thinking flag, never silence | Done | `:61`; test `VoicePresentationStateTests.swift:30-43` |
| Muted orthogonal to output; wake-armed distinct | Done | `:62`; rail `OrbFieldView.swift:223-224` |
| "Audio level unavailable" honest fallback; no simLevel in adaptive | Done | `VoicePresentationState.swift:26-31`; `VoiceWaveView.swift:78,144,174` |
| Attack 40 ms / release 180 ms elapsed-time | Done | `VoicePresentationState.swift:82-83`; 30/60 Hz equivalence test `:66-76` |
| 300 ms stale decay; duplicate timestamps; generation check | Done | `JK/AudioActivity.swift:20,54-65,74`; re-checked at render `VoicePresentationState.swift:45-56` |
| ≤30 Hz observation cap | **Absent** | no such cap in `macos/`; deferred to the unbuilt adapter |
| 60 Hz active / 15 Hz idle; suspend when not visible; Reduce Motion | Done | `VoiceWaveView.swift:40-47,58-67,152-158`; `MH/Console/WindowVisibilityReader.swift:62-63` |
| Captions final-only, no duplicates; speaker-gate chip kept | Done | `OrbFieldView.swift:351-361,133-144,226` |
| Tuning values in one place (AppTuning) | **Not done** | colors and attack/release hardcoded in views |
| Contrast verification of teal/violet | Untested | no record |
| P0 signal path "approved" and wired; §9.3 real audio matrix | **Blocked / not run** | `P2-audio-feasibility.md` throughout; `P2-additive-observation-design.md` is a proposal "for separate review; not implemented" |

### P3 — Central workspace

| §4.1 / §4.4 / §6 / §7 / §10 item | Status | Evidence |
|---|---|---|
| Voice region / workspace / sidecar; inspector subpane or sheet; no 4th column | Done | `MH/Console/ConsoleView.swift:57-58,86-90`; `AdaptiveStageView.swift:34-53`; `WorkspaceSourcesView.swift:15-22` |
| Large wave only on return-to-conversation **and no result active** | Partial | gate is `showsConversation && !compactConversation` (`AdaptiveStageView.swift:22`); `returnToConversation()` leaves `activeID` set (`WorkspaceStore.swift:84-87`) |
| First result enters workspace; selection sticky; unread indicator | Done | `WorkspaceStore.swift:56-82`; `WorkspaceView.swift:34`; tests `WorkspaceStoreTests.swift:27-71` |
| No focus steal when Mortimer speaks | Done by construction, untested | no `@FocusState`/first-responder calls in workspace views |
| Compact → bottom wave; user can keep compact | Done | `AdaptiveStageView.swift:7,44-53,60-61` (`mortimer.interface.compactConversation`) |
| Comparison: two panes wide / A-B narrow | Done | `WorkspaceView.swift:57-72` |
| All DisplayPayload fields rendered; commands not executable | Done | `MH/Display/DisplayContentView.swift:28-52,101-129` |
| One store; IDs at ingestion; one subscription; IDs correlate across stores | Done | `AppMessageRouter.swift:80-93`; `DisplayResultStore.swift:11,37`; `DisplayWindowStore.swift:11,45-49` (window-store correlation untested by assertion) |
| Modes Summary/Sources/Connections; explicit source open; no LLM | Done | `WorkspaceResultDetails.swift:5-17`; `WorkspaceResultPane.swift:48-56`; `WorkspaceSourcesView.swift:30,42-43,76-81` |
| Pins session-only; export reports success after write; clipboard never persisted/exported | Done | no persistence on `WorkspaceResult`; `WorkspaceExportCoordinator.swift:15-52`; `WorkspaceResultDetails.swift:36`; test `WorkspaceResultDetailsTests.swift:31-63` |
| Pin limit 20 refuses; pin refs survive history eviction | Done (tested with limit 2, not 20) | `WorkspaceStore.swift:48,126-132,172-178` |
| §7: 1180 / 200 / 480 / 300 / 900×600 | Done, literals not centralized | `ConsoleView.swift:58,96`; `AdaptiveLayoutMetrics.swift:7,9`; `WorkspaceSourcesView.swift:17` |
| §7: 200 ms layout transition | **Absent** | no `withAnimation` in stage/workspace/console |
| `mortimer.interface.layoutVersion`; invalid → old layout; "Use previous layout"; adaptive off by default | Done | `MortimerHostApp.swift:27,135-137` |
| Both presentations share stores; `mortimer.drawer.*` untouched | Done | `MortimerHostApp.swift:50-58,72-76`; `UICommandRouter.swift` unchanged |
| Lettering removed (adaptive) / retained (legacy) | Done | `OrbFieldView.swift:37,285-301` |

### P4 — Interactive memory graph

| §4.5 item | Status | Evidence |
|---|---|---|
| GET `/api/graph/memory` via JarvisHTTP with focus/depth/edge_types/since; Bearer | Done | `JK/MemoryGraphAPI.swift:111-124`; `JK/JarvisHTTP.swift:26-43,53-55` (`sendTransient`: ephemeral, no shared cache) |
| Decode full shape; default depth 2 / max 4 / 500 nodes; UI limits disclosed with focused expansion | Done, two quirks | `MemoryGraphAPI.swift:17-35,63-107`; always sends `depth=2` (ignores server `JARVIS_GRAPH_DEPTH` override); `since` has no UI control; `legend` decoded as non-optional `[String:String]` — untested against real server output |
| 1 Deterministic layout, pan/zoom/fit/reset, stable selection, keyboard list | Done | `MH/Display/MemoryGraphLayout.swift:7-78`; `MemoryGraphCanvas.swift:104-122`; `MemoryGraphView.swift:90-93,150-185` |
| 2 Legend/filters from metadata; unknown types neutral | Done | `MemoryGraphStore.swift:82-83`; `MemoryGraphView.swift:250-253` |
| 3 "Search this view" + separate server focus | Done | `MemoryGraphView.swift:152-153,18-20,244-247` |
| 4 Focus/expand + Back; positions preserved | Done | `MemoryGraphStore.swift:115-119,145-151,173-182` |
| 5 Inspector; no fabrication; detail only via existing read API | Done | `MemoryGraphView.swift:187-242`; `MemoryGraphStore.swift:269-273` (`fact:` ids → `api/memory`; all else "Full detail is unavailable through the current read API") |
| 6 Undirected path; arrows where warranted; "No path in this loaded view" | Partial | BFS `MemoryGraphLayout.swift:82-103`; literal extended to "…with the current filters." (`MemoryGraphView.swift:50`); arrow edge-type list hardcoded (`MemoryGraphCanvas.swift:34`) — untested against the builder's actual edge types |
| 7 Collapsible groups; counts disclose subset | Done | `MemoryGraphStore.swift:87-96,217-221`; `MemoryGraphView.swift:39,128-131` |
| 8 States, cancel, retry, image fallback with notice | Done | `MemoryGraphView.swift:27-43,102-122,144-147`; `MemoryGraphImageStore.swift:52` |
| 9 Saved view metadata validated; no node text | Done (IDs persisted, text not) | `MemoryGraphStore.swift:5-27,71-72,290-304`; key `mortimer.interface.memoryGraph.view` |
| Native bounded 2D; off-main layout; no deps; no continuous sim | Done | `MemoryGraphCanvas.swift:20-93`; `MemoryGraphStore.swift:131-136,254-259`; no `Package.swift` change |
| Stale response rejection by generation | Done | `MemoryGraphStore.swift:125,137,157,166,278,284` |
| §7 fixtures 50/200/500 + 500/2,000 stress, long labels, dense hub | Partial | `MemoryGraphTests.swift:62-71`; 2,000-edge case is 4× duplicated ring edges, max degree 8 — no dense hub |
| p95 frame ≤33 ms during pan/zoom | **Unmeasured** | no instrumentation |
| Pre-existing bare `URLSession` in `GraphImageView` | Unchanged | still reached from `DisplayContentView.swift:86` for the original-result path; disclosed |
| §8 boundary | Mostly | `JarvisHTTP.swift` addition documented; `DisplayContentView` hunk is P3 scroll work |

### P5 — Automatic screen adaptation

| §5 / §6 / §7 / §10 item | Status | Evidence |
|---|---|---|
| One policy for buttons/voice/restoration/screen change | Done | `DisplayPlacementPolicy.swift:75`; `ScreenPlacement.swift:45-62,130-156`; `WindowPlacement.swift:19-47` |
| Stable display IDs + validated fallback; visible areas; negative/portrait; rescale | Done, scale unused | `ScreenPlacement.swift:27-36,102-112`; `DisplayPlacementPolicy.swift:29-33,88,120-127`; `PlacementScreen.scale` captured, never read |
| One screen first-class; pop-outs reachable | Done | `DisplayPlacementPolicy.swift:137-156` |
| Two screens: no empty window on monitor appearance; manual preserved | Done | policy cannot open windows (`:23-24`); supporting content opt-in from `WorkspaceView.swift:110-126` |
| Three+: roles optional; mirrored = one | Done | `:79-80,92-101` |
| Unplug recovery incl. manual windows; state preserved | Done (policy), live untested | `:128-144`; test `DisplayPlacementPolicyTests.swift:10-20` |
| Reconnect restore unless newer manual intent; no second renderer | Done | `:62-73,106-113`; `WorkspaceResultPane.swift:5,18-23` yields to supporting window |
| Lock/unlock, sleep/wake reconcile | **Partial** | `didWakeNotification` + `sessionDidBecomeActive` observed (`ScreenPlacement.swift:56-60`); screen **unlock** not observed |
| 60/40 only as detached display+drawer fallback | Done | `DisplayPlacementPolicy.swift:159-165` |
| New versioned pref key; legacy keys untouched; Reset Layout scope | Done | `mortimer.interface.placement.v1` (`ScreenPlacement.swift:10-14,28`); `MortimerHostApp.swift:128-133` |
| 250 ms single debounce; loop prevention; auto-vs-manual recorded | Done | `ScreenPlacement.swift:20,71-82,90,146-153`; `DisplayPlacementPolicy.swift:18` |
| Recovery ≤1 s measured | Untested | no clock seam; `P5-progress.md:50-52` concedes |
| Policy pure and separate from AppKit step | Done | `DisplayPlacementPolicy.swift:1,25` Foundation-only |
| Tests of the AppKit adapter | **Absent** | no test references `ScreenPlacement` |
| §9.4 hardware matrix | Not run | — |

### P6 — Integrated acceptance

| §8 P6 / §9 item | Status | Evidence (claims in `P6-interim-checks.md`) |
|---|---|---|
| Full pytest normal / reverse / seeded within 900 s | Done (claimed) | 2,458 passed ×3 after fixture fix `:77-88`; seeded failure root-caused to a class-attribute leak and fixed in PR #65, not skipped `:52-75` |
| `sandbox/tests` controller suite | Done (claimed) | 109 tests `:321-323` |
| Independent frozen-profile receipt | **Passed once, failing since** | pass at `4d188e8` `:156-184`; nine `WindowVisibilityTests` failures at `55767c0`, `2fb6a9f`, `bae4aa5` because the Tart guest has no active desktop space `:296-354`; retained as failed evidence |
| Bundle rebuilt, framework + signature verified, app stays running | Done in VM | `bundle.sh:14-38,65-72`; observed running as PID 2272 `:234-238`; `tests/unit/test_native_bundle.py` (5 tests) |
| §9.2 visual cases at 900×600 / 1280×800 / 1440×900 / ultrawide / portrait | Partial | offscreen fixtures at all five (`FullConsoleRenderingTests.swift:9-80`); Retina/non-Retina, every tab docked+detached, long/error payloads: not covered |
| §9.2 accessibility (Reduce Motion, VoiceOver names, keyboard traversal) | Partial | Reduce Motion rendering tested; VoiceOver and keyboard traversal not |
| §9.3 real audio acceptance | **Not run** (blocked on P2) | — |
| §9.4 real monitor acceptance | **Not run** | — |
| Compare against P0 baseline; rollback exercised on synthetic state | **Absent** | no rollback exercise recorded |
| Larry smoke test | Done | Xcode run: eight tabs, startup response, weather request `:356-380` |
| Deployment authorization | Not requested | correct |

## 5. §11 completion checklist, as it stands

- [ ] P0 — baseline tests captured; inventory written; audio feasibility recorded as **not feasible on M120 stats alone**; screenshots/performance baseline missing.
- [ ] P1 — header accepted by you for the font picker only; keyboard navigation absent; preservation matrix unchecked.
- [ ] P2 — presentation built; **no measured audio**; blocked pending your decision (§1 item 1).
- [ ] P3 — built and unit/rendering tested; 200 ms transition absent; adaptive is off by default so nothing here is "accepted".
- [ ] Lettering removed / indicators preserved — removed in adaptive path; wake ripple and beams have no compact home.
- [ ] P4 — built and tested; frame-time unmeasured.
- [ ] P5 — policy built and tested; adapter untested; hardware untested.
- [ ] P6 — backend gates green; native independent gate blocked by headless-VM visibility; hardware matrix, rollback, accessibility open.
- [ ] Rollback exercised — no.
- [ ] Deployment authorized — no, and none occurred.

## 6. Record claims the code does not support

1. `P0-P1-progress.md:22-24,125-126` — "models remain in DrawerView" / "five-file phase preserves view-model ownership": true of PR #66 only; the candidate tree hoisted models to `DrawerModels.swift` and changed twelve drawer files.
2. `P2-audio-feasibility.md:171-172` and `P3-progress.md:26-30` — "preserves existing captions and notices": true for content; wake ripple and agent beams are absent from the compact rail.
3. `P4-progress.md:30-32` — "screenshots prompted fixes for overlapping text": the rendering test asserts only non-zero pixel dimensions; overlap is not measured.
4. §7 "one source of truth in AppTuning": colors, attack/release, 1180 and 820 are literals in views.
5. Every test count and SHA-256 in the records is unverifiable here — logs live in the sandbox task directories, not the tree. Not a defect, but P6's final receipt must reference committed evidence.

## 7. Plan corrections still worth making

Carried from yesterday and still valid: name the native-audio plan as P2's sanctioned unblock (now sharpened by the candidate's own observation design); record the `WakeWordListener` capture tap and the dual window minimum in P0; drop or justify the 12 pt tab label; say where the Swift suites actually run (they ran in a Tart VM, and the native visibility gate cannot pass headless — §9.1 should say a graphics-attached verification runner is a P6 prerequisite). New: §4.1 should either enforce "no result active" for the large wave or drop the conjunct; §4.3 should say where the AI "small label" during barge-in lives, since the candidate computes it but never renders it.
