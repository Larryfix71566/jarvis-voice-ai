# Mortimer adaptive interface closure plan — close the review gaps, land on `main`, deploy

**Status:** IMPLEMENTATION SPECIFICATION; NOT A CLAIM OF ACCEPTANCE. Supersedes nothing — it extends `docs/plans/MORTIMER_ADAPTIVE_INTERFACE_PLAN.md` (the "interface plan") and sequences `docs/plans/MORTIMER_NATIVE_AUDIO_TRANSPORT_PLAN.md` (the "native-audio plan") ahead of P2.
**Baseline inspected:** candidate `6bf0270` on `feat/adaptive-compact-conversation` in the isolated checkout `~/Documents/Codex/2026-09-09/can/work/active-repo`; installed checkout `~/jarvis-voice-ai-clean` at `2ccf66c` (= `origin/main` on 2026-09-10) with five uncommitted local changes. Gap inventory is `docs/reviews/MORTIMER_ADAPTIVE_INTERFACE_PLAN_REVIEW.md` (2026-09-11). Recheck all three before starting.
**Owner:** Larry. Implementation is assigned to a coding model one phase at a time; Larry runs every merge and every deployment. The implementer never runs `git merge`, `git push --force`, `launchctl`, or `open` against the production host. This document authorizes no application-code change by itself.
**Safety claim:** the interface plan's contracts UI-1 through UI-7 remain in force verbatim. This plan adds no new contract and relaxes none. Anything unmeasured stays open; a status of "done" in this document means positive evidence exists at the named path.

## 1. Locked decisions (Larry, 2026-09-11)

These four answers shape the phase order below and are not reopened by the implementer.

- **L1 — Native audio before P2.** `MORTIMER_NATIVE_AUDIO_TRANSPORT_PLAN.md` is executed in full (its §3 verify-first gate included) before any measured-level work. P2's measured teal/violet levels are taken from the native path's own `AVAudioEngine` taps, not from WebRTC statistics. The candidate's `P2-additive-observation-design.md` (taps inside the pinned WebRTC build) is **retired**: it is kept as a record, not implemented. The WebRTC path stays the remote/T2 transport and shows the honest "Audio level unavailable" fallback.
- **L2 — Candidate `bundle.sh` supersedes the production local patch.** The candidate's `macos/MortimerHost/scripts/bundle.sh` (framework copy at `:14-38`, nested signing and `--verify --deep --strict` at `:65-72`) is committed; the production working-tree patch on that file is discarded at deployment after a diff proves it contains nothing the candidate lacks.
- **L3 — `DrawerModels` hoist is accepted as the separate lifecycle fix.** App-scoped view-model ownership (`MH/Drawer/DrawerModels.swift`, wired at `MH/App/MortimerHostApp.swift:34,57,96`) stays. It lands in its own PR with its own acceptance record, so PR #66 remains the five-file header change.
- **L4 — Deployment target: `main` + installed on the MacBook Air with adaptive layout ON by default.** `mortimer.interface.layoutVersion` defaults to `1` after acceptance; `Debug ▸ Use previous layout` remains for one release; removing the legacy path is a separate later cleanup, not part of this plan.

Path shorthand: `MH/` = `macos/MortimerHost/Sources/MortimerHost/`, `JK/` = `macos/JarvisKit/Sources/JarvisKit/`, `MHT/` = `macos/MortimerHost/Tests/MortimerHostTests/`, `JKT/` = `macos/JarvisKit/Tests/JarvisKitTests/`.

## 2. Gap register

Every row is a finding from the review, the work item that closes it, and the evidence that counts as closure. A row with no evidence path at the end of this plan is not closed.

| ID | Gap (review reference) | Closing item | Evidence of closure |
|---|---|---|---|
| G01 | P1 keyboard navigation absent (`Drawer/` has no focus/key handling) | C1.1 | `MHT/DrawerTabStripKeyboardTests.swift` drives ←/→/Home/End and Tab focus through a real `NSWindow`; selection and reveal asserted |
| G02 | Full `DrawerView` chrome and detached scene untested at 300 pt | C1.2 | `MHT/DrawerViewMinimumWidthTests.swift` at `AppTuning.drawerMinWidth`, docked and `isPoppedOut` |
| G03 | §7 tab label 12 pt became 11 pt, undocumented | C1.3 | Interface plan §7 amended to 11 pt with the rationale; or strip changed to 12 pt — one of the two, recorded |
| G04 | `DrawerModels.scrollOffsets` shared by docked + detached views of one tab | C1.4 | Test mounting two presentations of one tab; offsets keyed by presentation |
| G05 | Wake ripple and agent beams have no compact-rail home (`MH/Console/OrbFieldView.swift:82-108` only) | C2.1 | Rail renders ripple and a compact beam/activity affordance; `P0-preservation-checklist.md` row "OrbFieldView: agent satellites…" checked with screenshot |
| G06 | §4.3 "small AI label during barge-in" computed (`VoicePresentationState.swift:57`) but never rendered | C2.2 | Label rendered in both presentations; `MHT/VoicePresentationStateTests` extended with a rendering assertion |
| G07 | 200 ms layout transition absent | C2.3 | `AppTuning.layoutTransition` used by `AdaptiveStageView`/`WorkspaceView`; Reduce Motion path asserted |
| G08 | §7 literals in views (1180 `ConsoleView.swift:58`, 820 `WorkspaceSourcesView.swift:15,20`, colors `VoiceWaveView.swift:190-192`, attack/release `VoicePresentationState.swift:82`) | C2.4 | All in `AppTuning` (or `AudioPresentationTuning`); tests reference the constants |
| G09 | Large wave shown while a result is active (`AdaptiveStageView.swift:22` vs §4.1) | C2.5 | Either enforce the conjunct or amend §4.1; test asserts the chosen rule |
| G10 | Production pin limit 20 untested (tests use 2); `DisplayWindowPanel.workspaceID` correlation untested | C2.6 | Tests at the production limit and for window-store correlation |
| G11 | P4 frame-time p95 ≤33 ms unmeasured | C3.1 | `MHT/MemoryGraphFrameTimeTests.swift` records per-frame times for pan/zoom on the 500-node fixture; result file under `docs/acceptance/adaptive-interface/P4-frame-time.json` with hardware/scale/dimensions |
| G12 | 2,000-edge fixture is duplicated ring edges; no dense hub | C3.2 | Fixture with one node of degree ≥200 and long labels; layout/culling assertions |
| G13 | Legacy `GraphImageView` still fetches with bare `URLSession.shared` (`MH/Display/GraphImageView.swift:125`) | C3.3 | Routed through `JarvisHTTP.sendTransient`; `DisplayPanelSizingTests` extended; grep shows no `URLSession.shared` outside `JarvisHTTP` |
| G14 | Arrow edge types hardcoded (`MemoryGraphCanvas.swift:34`); `depth=2` always sent; `legend` decoded non-optional | C3.4 | Directionality taken from server legend/edge attrs or verified against `jarvis/graphs/memory_graph.py`; depth omitted when default; `legend` optional; decode test against a captured real response |
| G15 | Truncation literal extended beyond plan wording; `select()` mutates filters | C3.5 | Wording matches §4.5 item 6 exactly; selection no longer un-hides types silently (or the side effect is disclosed in the inspector) |
| G16 | Screen unlock not observed (`ScreenPlacement.swift:56-60` observes wake + session activation only) | C4.1 | Unlock observer added; hardware case §9.4 "lock/unlock" recorded |
| G17 | `PlacementScreen.scale` captured, never used | C4.2 | Used for point/pixel decisions or removed; test |
| G18 | No tests of the AppKit adapter `ScreenPlacement` (debounce, manual detection, persistence decode, reset) | C4.3 | Injectable screen/window/clock seams; `MHT/ScreenPlacementTests.swift` |
| G19 | ≤1 s recovery unmeasured | C4.4 | Measured on hardware in C8 with the clock seam from C4.3 |
| G20 | Independent frozen-profile receipt fails headless on nine `WindowVisibilityTests` (Tart guest has no active desktop) | C5.1 | Graphics-attached verification runner; a passing receipt for a candidate later than `4d188e8` |
| G21 | Sandbox test counts and SHA-256s live outside the tree | C5.2 | Receipts copied under `docs/acceptance/adaptive-interface/receipts/` (hashes and summaries only, no private content) |
| G22 | `WakeWordListener` second capture tap and the 400×300 / 900×600 dual minimum not recorded in P0 | C0.3 | Added to `P0-preservation-checklist.md` "pre-existing" section |
| G23 | P0 baseline screenshots and performance baseline absent | C0.4 / C8 | Baseline captures of the legacy layout on the deployment Mac, before any candidate install |
| G24 | Observation generation is view `@State` (`AdaptiveStageView.swift:13`) — a UI-5 problem once a real adapter exists | C7.2 | Generation owned by the app-scoped audio observer |
| G25 | No ≤30 Hz observation cap anywhere | C7.2 | Cap enforced in the observer; test |
| G26 | Measured user/playout levels absent; §9.3 real-audio matrix not run | C6 + C7 + C8 | Native path levels drive the wave; §9.3 recorded |
| G27 | Preservation checklist 0/22 rows checked | C8.1 | Every row checked with tester, date, viewport, screenshot/log |
| G28 | Rollback never exercised | C8.4 | Rollback record with synthetic state |
| G29 | Five production local patches not reconciled | C0.2 / C10.2 | Per-file decision recorded; working tree clean after deployment |
| G30 | Adaptive layout off by default (L4) | C9.5 | Default flipped in its own PR after C8 |

## 3. Phase order and dependencies

```
C0 prep ─┬─ C1 P1 gaps ──┐
         ├─ C2 P3 gaps ──┤
         ├─ C3 P4 gaps ──┼─ C5 verification runner ─ C6 native audio ─ C7 P2 measured audio ─ C8 acceptance ─ C9 merge ladder ─ C10 deploy ─ C11 post-deploy
         └─ C4 P5 gaps ──┘
```

C1–C4 are independent of each other and of C6; run them in parallel worktrees if wanted. C5 must pass before C8 because the independent native receipt is a P6 gate. C6 precedes C7 by L1. C9 cannot start until C8's automated rows are green; C10 cannot start until Larry authorizes it in writing at the end of C9.

## 4. Phases

### C0 — Preparation (no application-code change)

1. **Rebase check.** Confirm `2ccf66c` is still `origin/main`'s ancestor of the candidate and whether `origin/main` has moved since 2026-09-10 (`git log 2ccf66c..origin/main`). If it has, record every new commit and whether it touches `macos/`, `sandbox/`, or `jarvis/bot/`. A moved `main` changes the rebase in C9 but nothing else.
2. **Production local-patch inventory (G29).** In the installed checkout, save `git diff` for each of the five files to `docs/acceptance/adaptive-interface/production-local-patches/<file>.diff` (redacting nothing — these are code files; if a diff contains a credential, stop and report). For `bundle.sh`, produce a three-way comparison (baseline, production patch, candidate) and confirm the candidate contains every behavior of the patch (L2). For the other four, write one line each: what the patch does and whether it belongs on `main`, in a separate PR, or discarded. **Larry decides per file before C10.**
3. **Pre-existing deviations (G22).** Add a "Pre-existing at baseline" section to `P0-preservation-checklist.md`: `JK/WakeWordListener.swift:162-178` AVAudioEngine tap (runs only while muted; not echo-cancelled); NSWindow minimum 400×300 (`MH/App/MortimerHostApp.swift:239,244`) versus SwiftUI 900×600 (`MH/Console/ConsoleView.swift:96`) — name the SwiftUI value as the preserved contract; `GraphImageView` bare URLSession (closed by C3.3); Edit-draft loss on pop-out (closed by L3).
4. **Baseline captures (G23).** On the deployment Mac, with the currently installed app (baseline `2ccf66c` + local patches), record: screenshots of every tab docked and detached, the console at 900×600 and at the Mac's native size, the display window with two panels, one- and two-screen states if a second display is available; the `logs/mortimerhost-window.log` attach lines; connection time and user-stop-to-first-AI-audio for 20 paired trials (the §7 comparison baseline). Store under `docs/acceptance/adaptive-interface/baseline/` with private memory text blurred.
5. **Retire the WebRTC observation design (L1).** Prepend a status line to `P2-additive-observation-design.md`: "RETIRED 2026-09-11 by MORTIMER_ADAPTIVE_INTERFACE_CLOSURE_PLAN L1; kept as record." No other edit.

Deliverable: the five records above and a C0 note in `docs/acceptance/adaptive-interface/C0-preparation.md`. No PR.

### C1 — Close P1 gaps

Primary files: `MH/Drawer/DrawerTabStrip.swift`, `MH/Drawer/DrawerView.swift`, `MH/Drawer/DrawerModels.swift`, new tests. Do not touch tab bodies.

1. **Keyboard navigation (G01).** Make the strip focusable; ←/→ move selection (which already reveals the tab through `onChange(of: selectedTab)` at `DrawerTabStrip.swift:44-53`), Home/End go to first/last, and the arrows expose `.accessibilityAction`s. Focus ring visible. Test through real key events on an `NSWindow`; no `XCTSkip`.
2. **300 pt chrome and detached (G02).** Fixture hosting the whole `DrawerView` at `AppTuning.drawerMinWidth` in both `isPoppedOut` states; assert Aa, ⧉ and × frames inside the window and the selected label inside the viewport for all eight keys.
3. **§7 typography (G03).** Keep 11 pt (it is what Larry accepted live on 2026-09-11) and amend interface-plan §7 to read "initial 11 pt"; record the change in the plan's status header. Do not change the strip.
4. **Per-presentation scroll offsets (G04).** Key `DrawerModels.scrollOffsets` by (presentation, tab). Test: two mounted presentations of one tab keep independent offsets.

Acceptance: full host suite green in the sandbox; C1 record with test names and a screenshot of keyboard focus. PR: "P1b — header keyboard navigation and minimum-width coverage", stacked on #66 + the L3 hoist PR.

### C2 — Close P3 gaps

Primary files: `MH/Console/OrbFieldView.swift`, `MH/Console/AdaptiveStageView.swift`, `MH/Console/VoiceWaveView.swift`, `MH/App/VoicePresentationState.swift`, `MH/App/AppTuning.swift`, `MH/Display/WorkspaceView.swift`, `MH/Display/WorkspaceSourcesView.swift`, `MH/Stores/WorkspaceStore.swift`, tests.

1. **Rail parity (G05).** Add the wake ripple and a compact agent-activity affordance (lit satellite dot is acceptable in place of beams; the plan's requirement is a *visible home*, not the same drawing) to `compactReadout` (`OrbFieldView.swift:219-246`). Record the mapping in `P0-preservation-checklist.md`.
2. **Barge-in AI label (G06).** Render `assistantSpeaking` as the §4.3 small label in both presentations; keep teal priority.
3. **Transition (G07).** `AppTuning.layoutTransitionSeconds = 0.2`; apply to mode/width transitions; immediate change under Reduce Motion; never during pointer drag, text selection or editing (guard on `NSEvent.pressedMouseButtons` and first-responder text views).
4. **Tuning consolidation (G08).** Move 1180, 820, 200, 480, 300, teal/violet, attack/release into `AppTuning` (audio presentation values may live in a dedicated `AudioPresentationTuning` enum). Tests reference constants, never literals.
5. **Large-wave rule (G09).** Enforce §4.1 literally: conversation presentation with the large wave only when `showsConversation && activeID == nil`; "return to conversation" therefore deselects (results stay in history and pins). If Larry prefers the candidate's behavior, amend §4.1 instead — record either way.
6. **Limits at production values (G10).** Tests at `pinLimit: 20` and for `DisplayWindowPanel.workspaceID` correlation.

Acceptance: full host suite green; rendering fixtures at the five §9.2 sizes re-run; C2 record. PR: "P3b — workspace gap closure".

### C3 — Close P4 gaps

Primary files: `MH/Display/MemoryGraph*.swift`, `MH/Display/GraphImageView.swift`, `JK/MemoryGraphAPI.swift`, tests, one new acceptance JSON.

1. **Frame-time harness (G11).** A test that pans and zooms the 500-node/2,000-edge fixture for 300 frames on the deployment Mac, records per-frame times with `CACurrentMediaTime()`, and writes p50/p95/max plus hardware, dimensions and scale to `docs/acceptance/adaptive-interface/P4-frame-time.json`. Gate: p95 ≤33 ms. If it fails, apply label culling/level-of-detail before any functional cut, and re-measure; do not raise the gate.
2. **Dense-hub fixture (G12).** Add a hub of degree ≥200 with 48-char labels; assert bounded layout and no NaN; include in the frame-time run.
3. **Legacy image fetch (G13).** Route `GraphImageView` through `JarvisHTTP.sendTransient`; keep its debounce and sizing. `DisplayPanelSizingTests` extended; add a grep test (or CI check) that `URLSession.shared` appears only in `JK/JarvisHTTP.swift`.
4. **Server correspondence (G14).** Read `jarvis/graphs/memory_graph.py` (and `render.py` legend output) in the sandbox; derive directional edge types from the server's legend/edge attrs if present, else keep the list but add a decode test against a captured real `/api/graph/memory` response (synthetic memory content) proving `legend` shape and edge-type names. Omit `depth` from the query when the user has not changed it so the server default applies. Make `legend` optional in the decoder.
5. **Wording and selection side effect (G15).** Truncation message exactly "No path in this loaded view"; move "with the current filters" to a second line. `select()` no longer mutates hidden/collapsed types; if the selected node is hidden, show "Selected node is hidden by a filter — Reveal" with an explicit action.

Acceptance: JarvisKit and host suites green; frame-time JSON present; C3 record. PR: "P4b — graph performance evidence and transport parity".

### C4 — Close P5 gaps

Primary files: `MH/Placement/ScreenPlacement.swift`, `MH/Placement/DisplayPlacementPolicy.swift`, new `MHT/ScreenPlacementTests.swift`.

1. **Unlock (G16).** Observe `com.apple.screenIsUnlocked` (distributed notification) and `NSWorkspace.screensDidWakeNotification`; both schedule a topology-changed reposition through the single work item (`ScreenPlacement.swift:71-82`).
2. **Scale (G17).** Either use `PlacementScreen.scale` for the point/pixel clamp of window minimums across mixed-scale displays, or delete the field. Record which.
3. **Adapter seams and tests (G18).** Inject screen provider, window provider and clock into `ScreenPlacement`; test the 250 ms debounce collapses bursts, that `applying` suppresses self-notifications, that manual detection requires pointer/live-resize evidence, that persisted records decode/reject correctly, and that Reset Layout clears only records, placed frames and drawer width.
4. **Recovery timing (G19).** With the clock seam, the hardware run in C8 records time from `didChangeScreenParametersNotification` to the last `setFrame`; gate ≤1 s.

Acceptance: host suite green; C4 record. PR: "P5b — placement adapter tests and unlock reconciliation".

### C5 — Graphics-attached verification runner (G20, G21)

Primary files: `sandbox/verify.py`, `sandbox/profiles.py`, `sandbox/guest/worker.sh`, `sandbox/control.py`, `sandbox/tests/*`. No application code.

1. The Mortimer profile's native checks must run in a guest with an active, unoccluded desktop session. The candidate already provisions the worker identity and auto-login (`P6-interim-checks.md:333-345`); what remains is attaching the desktop before the test process starts. Implement whatever Tart supports for this (a logged-in GUI session via the graphics worker, verified by a probe that asserts `NSWindow.occlusionState.contains(.visible)` before the suite runs). If Tart cannot provide it, the fallback is a second verification stage that runs only `WindowVisibilityTests` on the host Mac under Larry's login, recorded as a separate receipt — never a skip.
2. Receipts (`receipt.json`, log hashes, test counts) are copied into `docs/acceptance/adaptive-interface/receipts/<attempt>.json`. No private content; hashes and counts only.
3. `sandbox/tests` suite green; the 900-second limit unchanged.

Acceptance: one passing independent receipt for a candidate at or after C1–C4. PR: "Sandbox — graphics-attached native verification".

### C6 — Native audio transport (L1)

Execute `MORTIMER_NATIVE_AUDIO_TRANSPORT_PLAN.md` as written, in its own branch cut from the C1–C5 result, with these bindings:

1. Its §3 verify-first gate is a hard stop: pipecat 1.4.0 WebSocket audio transport identity, app-frame carriage, VPIO echo-cancellation quality on AirPods-out + built-in-mic and AirPods-both, latency parity against the C0.4 baseline, and wake-listener independence. Findings are written into that plan before any transport code.
2. Its D4 (`botIsSpeaking` from the player node) is the source of the **playout** channel for C7; its D2 capture tap is the source of the **input** channel. Design `AudioEngineIO` so both expose a latest-value level slot (RMS over the last buffer, with the buffer's host time) that C7 can read without a second tap. This is the one addition to that plan; it is additive and does not change its steps.
3. Its D8 (delete `AudioInputCoordinator` and the input-notice chip) removes one of the eleven OrbField indicators inventoried in the review. Record that removal in `P0-preservation-checklist.md` as intentional, with the plan reference, before C8.
4. Server change (`jarvis/bot/bot.py` WebSocket case) means the backend restarts at deployment (C10.4).

Acceptance: that plan's §7 tests and §8 verification (Larry runs) recorded; `JARVIS_FORCE_WEBRTC=true` rollback proven. PR: per that plan.

### C7 — P2 measured audio on the native path

Primary files: new `JK/AudioActivityObserver.swift`, `JK/AudioActivity.swift`, `MH/Console/AdaptiveStageView.swift`, `MH/App/VoicePresentationState.swift`, `MH/App/MortimerHostApp.swift`, tests. Touch `AudioEngineIO` only to read the level slots from C6.2.

1. **Observer (G24, G25).** An app-scoped `AudioActivityObserver` owns the connection generation (replacing the view `@State` at `AdaptiveStageView.swift:13`), samples the two level slots at ≤30 Hz on a non-audio queue, converts host time to the accumulator's monotonic measurement time, and feeds `AudioActivityAccumulator` (`JK/AudioActivity.swift`). Duplicate-timestamp, stale-generation, mute-eligibility and 300 ms decay rules are already implemented and tested there; do not re-implement them.
2. **Eligibility.** Input level is published only when `micEnabled` is true and the transport is the native path; on the WebRTC path the observer publishes nothing and the wave shows "Audio level unavailable" (already implemented). Muting zeroes input immediately (already tested in `JKT/AudioActivityTests.swift`).
3. **Wire.** `AdaptiveStageView` receives the observer's snapshot instead of `nil`. Nothing else in the presentation changes.
4. **Runtime disable path (§10).** `JARVIS_AUDIO_METER=off` (declared in `JarvisConfig`, tested) makes the observer publish nothing; status stays truthful.
5. **Latency instrumentation.** The observer records, per sample, host time of the audio buffer and the time the presentation consumed it; a debug menu item dumps p50/p95 over the last 60 s to `docs/acceptance/adaptive-interface/P2-latency.json` on demand. Gate: p95 ≤150 ms for both channels on the deployment Mac.

Acceptance: JarvisKit and host suites green; §9.3 matrix run in C8. PR: "P2 — measured dual-speaker voice feedback (native path)".

### C8 — Integrated acceptance on hardware

Run on the deployment MacBook Air with the candidate built from the C1–C7 result and installed **beside** the current app (a differently named `.app`, never over the production bundle). Everything here is recorded under `docs/acceptance/adaptive-interface/C8-*.md` with tester, date, commit, fingerprint, topology.

1. **Preservation matrix (G27).** Every row of `P0-preservation-checklist.md` exercised in legacy and adaptive modes; screenshot or log per row; disposable targets for any write.
2. **§9.2 visual and interaction cases** at the five sizes, Retina and non-Retina if available, every tab docked and detached, long/error payloads, two pins and A/B, graph fixtures at all §7 sizes, Reduce Motion, increased contrast, VoiceOver names and selected state, keyboard traversal (C1.1).
3. **§9.3 real audio** with the C0.4 paired-trial protocol: built-in, headphones, AirPods; muted and PTT; quiet/loud; TV noise; AI-only; interruption; output switch; disconnect/reconnect; sleep/wake; mic denied. Pass criteria as in the interface plan §7 and §9.3; the native-audio plan's §8 checks are folded in here so they are run once.
4. **§9.4 monitors and rollback (G19, G28).** One, two, mirrored, unplug the graph display and the draft display, reconnect with changed order, lock/unlock, sleep/wake, Reset Layout; recovery time from the C4.4 instrumentation. Then exercise rollback on synthetic state: flip `Use previous layout`, confirm drafts/results/pins/graph view survive, flip back.
5. **Independent receipt (G20).** A C5 receipt for the exact C8 commit, fingerprint recorded.

Gate G-C8: every row has positive evidence or is listed by name in `C8-open-items.md` with Larry's written acceptance of it as a known limitation. A row with neither blocks C9.

### C9 — Merge ladder to `main`

Larry runs every merge; the implementer prepares the branches and PR descriptions. Order is fixed; each PR carries its acceptance record and passes the GitHub checks (`validate`, `allowlist`, `policy-tests`, `knowledge-base`, `controller-tests`) plus a C5 receipt where native code changed.

1. PR #65 (test fixture) and PR #66 (P1 header) — already open, merge first.
2. "P1 lifecycle — app-scoped drawer models" (L3): the `DrawerModels` hoist and the mechanical tab-file changes, cut from the candidate.
3. "P3 — central workspace" + C2; "P4 — interactive memory graph" + C3; "P5 — automatic screen adaptation" + C4 — three PRs, rebased from the candidate in that order. Each is the phase's files from the interface plan §8 plus its closure items; the review's boundary notes say which files belong where.
4. "Sandbox — graphics-attached native verification" (C5).
5. Native audio transport (C6), per its own plan.
6. "P2 — measured dual-speaker voice feedback" (C7).
7. "Adaptive layout default" (G30): `layoutVersion` default `1`; `Debug ▸ Use previous layout` retained; interface plan and this plan's status headers updated; `CLAUDE.md` and `docs/REPO_MAP.md` updated for the new files.

If rebasing the cumulative candidate into per-phase PRs proves impractical (conflicts inside single files shared by phases), the fallback is two PRs — "adaptive interface P1–P5 + closure" and "P2 measured audio" — each with the union of records. Record the choice; do not squash native-audio into either.

### C10 — Deployment to the MacBook Air

Authorized only by Larry after C9 completes. Steps, in order, recorded in `docs/acceptance/adaptive-interface/C10-deployment.md`:

1. Keep the current production bundle and its commit as the known-good artifact (copy `macos/MortimerHost/.build/MortimerHost.app` aside with its commit hash and the five local-patch diffs from C0.2).
2. Reconcile the working tree (G29, L2): for each of the five files, apply Larry's C0.2 decision — commit on `main` via PR, or `git checkout -- <file>`. The tree must be clean before pulling.
3. `git pull` `main` into the installed checkout; confirm HEAD equals the C9 final commit.
4. Backend: `uv pip install -r requirements-lock.txt` only if the lock changed (it must not, per UI-7 and the native-audio plan's pins — if it did, stop); restart the bot and admin services through their launchd labels (`com.mortimer.*` from `scripts/launchd_gen.py`); confirm `GET /api/health` on `:7861` (the route `JK/AdminAPI.swift:126-131` preflights) and the bot signalling endpoint on `:7860`.
5. App: `macos/MortimerHost/scripts/bundle.sh` (the L2 version) — it embeds and signs the framework, verifies, and `open`s. Confirm the process stays running for five minutes, `logs/mortimerhost-window.log` shows the attach lines, and a voice round-trip succeeds on the native path with the meter live.
6. First-launch checks in adaptive mode: eight tabs, a result into the workspace, the memory graph interactive, one pop-out and pop-in with a draft, `Use previous layout` and back.
7. Rollback rehearsal on the live machine: `JARVIS_FORCE_WEBRTC=true` session works; `Use previous layout` works; the saved known-good bundle launches.

### C11 — Post-deployment

1. Seven days of normal use before the legacy-layout removal cleanup is planned (separate plan).
2. `docs/plans/MORTIMER_ADAPTIVE_INTERFACE_PLAN.md` status → IMPLEMENTED with the C8/C10 evidence paths; `MORTIMER_NATIVE_AUDIO_TRANSPORT_PLAN.md` status → IMPLEMENTED per its §6 step 8; this plan's status → COMPLETE.

## 5. File boundary

Allowed per phase as listed in §4. Across all phases, never modify: `config/self_edit_allowlist.json`, `config/upgrade_models.yaml`, `config/skills.yaml`, `requirements*.txt`, `macos/**/Package.swift`, `macos/**/Package.resolved` (WebRTC stays at `120.0.0` / `3edaa8f0` for the remote path), `jarvis/selfedit/**`, `jarvis/admin/**`, `.github/**`, `jarvis/skills/registry.py`, `tests/unit/test_agent_isolation.py`, `tests/unit/test_requires_env_snapshot.py`. The only backend code change in this plan is the native-audio plan's `jarvis/bot/bot.py` (and `pipeline.py`/`ws_transport.py` if its §3.1 requires them). Language mode stays `.v5` on every target.

## 6. Verification gates (inherited and added)

All of interface plan §9.1 remains: `swift test` for both packages, full pytest in normal/reverse/seeded order under the 900-second limit, `sandbox/tests` when the controller changes, GitHub required checks. Added: the C5 receipt must be graphics-attached for any PR touching `macos/`; the C3.1 frame-time JSON and C7.5 latency JSON are gates, not reports; the §7 paired-trial comparison uses the C0.4 baseline captured before any candidate touched the machine.

No skip, xfail, relaxed assertion or raised timeout anywhere. Every removed or renamed test is explained in its PR.

## 7. Stop rules for the implementing model

Stop the phase and report when: the native-audio plan's §3 gate fails on any of its five items; VPIO echo cancellation lets the bot transcribe its own TTS in the §9.3 echo-only trials; the frame-time or latency gate fails after culling/level-of-detail; a C8 preservation row cannot be made positive without a change outside §5; `origin/main` has moved in a way that touches `macos/` or `jarvis/bot/`; a production local patch contains something the candidate lacks and Larry has not decided its fate; a receipt cannot be obtained graphics-attached; or a fix would require weakening any test or gate. Continue independent phases where safe. Never merge, deploy, restart, or flip the default as a side effect.

## 8. Completion checklist

- [ ] C0 records present (`C0-preparation.md`, `production-local-patches/`); pending on Larry: fetch origin/main for the rebase check, per-file decisions on the four non-bundle.sh local patches, C0.4 baseline captures.
- [x] C1 keyboard navigation, 300 pt chrome, §7 typography, per-presentation offsets — tests green (`C1-p1-gaps.md`, host-c1.log 130/0).
- [x] C2 rail parity, barge-in label, transition, tuning consolidation, large-wave rule, production-limit tests — green (`C2-p3-gaps.md`, host-c2c.log 138/0).
- [x] C3 frame-time JSON ≤33 ms p95 (13.35 ms on Mac17,4); dense hub; legacy image fetch through JarvisHTTP; server-correspondence decode test; wording fixed. Record: `docs/acceptance/adaptive-interface/C3-p4-gaps.md`.
- [x] C4 unlock observed (`screensDidWake` + distributed `com.apple.screenIsUnlocked`); `PlacementScreen.scale` removed; adapter seams + 5 `ScreenPlacementTests`; recovery timing instrumented (os_log `com.mortimer.host/placement`, hardware reading in C8). Record: `docs/acceptance/adaptive-interface/C4-p5-gaps.md`, host-c4b.log 148/0.
- [x] C5 graphics-attached receipt passing for `6bf0270` (attempt `25d16062…`, 12/12 checks incl. candidate `native-app`; desktop probe bound into the receipt); receipt in `docs/acceptance/adaptive-interface/receipts/`. Record: `C5-verification-runner.md`. Re-run required on the commit that carries C1–C4 (C9).
- [ ] C6 native-audio plan §3 gate recorded; transport implemented; its §7/§8 done; rollback lever proven.
- [ ] C7 measured levels drive teal/violet on the native path; ≤30 Hz cap; app-owned generation; latency JSON ≤150 ms p95; meter disable path.
- [ ] C8 all preservation rows positive or accepted in writing; §9.2–§9.4 recorded; rollback exercised.
- [ ] C9 all PRs merged in order; default flipped in the last PR.
- [ ] C10 deployed; backend healthy; app persistent; working tree clean; known-good artifact retained.
- [ ] C11 plan statuses updated.

## 9. Handoff prompt for the implementing model

Read this plan, the interface plan, the native-audio plan, and `docs/reviews/MORTIMER_ADAPTIVE_INTERFACE_PLAN_REVIEW.md` in full before editing. State which phase (C0–C11) you are implementing and which gap IDs it closes. Inspect the current candidate and `origin/main`; do not assume either is unchanged since 2026-09-11. Work only inside that phase's file list, in an isolated branch and the disposable sandbox. Preserve every contract of the interface plan §3; do not substitute simulated audio, static images, or unmeasured claims for the evidence this plan names. For each gap ID you close, produce the named evidence artifact at the named path. Run the required gates; fix failures without skips or weakened assertions. If a stop rule fires, name the gap ID and the exact blocker and continue only with independent phases. Produce a reviewable PR and updated acceptance records; never merge, deploy, restart, or change the layout default — Larry does those.
