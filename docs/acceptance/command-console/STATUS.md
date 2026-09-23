# Command Console / Knowledge Atlas acceptance

Consolidated requirement matrix: [`../IMPLEMENTATION_STATUS.md`](../IMPLEMENTATION_STATUS.md).
Remaining Mac procedures: [`../ACCEPTANCE_RUNBOOK.md`](../ACCEPTANCE_RUNBOOK.md).

Updated 2026-09-18. The implementation is present in the release-review
worktree and ships with Command Console layout version 2 as the default;
legacy layouts remain selectable through the Debug menu. Native unit evidence:
JarvisKit 190 tests pass. MortimerHost builds and its focused
  console/Atlas, attachment, panel, graph, and command-console startup tests
  pass; the latest complete host run in the current sandbox (2026-09-18)
  executed 244 tests (3 display-dependent skips; 0 failures); focused console,
  sharing and placement suites remain green, including value-addressed
  detachable-panel coordinator coverage.
  Reconnect, sharing picker, VoiceOver, and five-day daily-driver
  evidence require a Mac acceptance session and remain open.

Reconciled 2026-09-22 against main `88b206f`. Swift figures in this file are
the counts recorded at the time of each receipt, not current pass counts.
Static `func test` counts at `88b206f`: JarvisKit 195, MortimerHost 250,
`ScreenPlacementTests` 9, `SupportingDisplayAcceptanceTests` 4,
`NativeAudioTransportTests` 26, `KnowledgeAtlasTests` 4. No committed receipt
records a run at those counts. Physical *display* reconnect restoration now
has a committed receipt (see Open Mac evidence); voice/socket reconnect is
still open.

## Automated evidence

- Full Mortimer answers now use one streaming result per user request in layout 2,
  with brief live captions and supporting-display ownership. Two-screen synthetic
rendering and return-to-main tests pass. Live voice and reconnect acceptance
remain open; see [response-routing receipt](receipts/response-routing-2026-09-18/README.md).

- Python console, session, shared-content, vision, memory and plan-manifest
  acceptance tests run with the project virtualenv; the latest full suite is
  2,611 passed / 4
  skipped.
- `tests/unit/test_plan_manifests.py` verifies the listed Command Console
  implementation, fixture, test and acceptance artifacts; it records the
  landed `FullConsoleRenderingTests.swift` name as the plan's rendering-suite
  equivalent.
- Swift `ConsoleProtocolTests`, `SharedContentTransferTests`,
  `MessagePrivacyTests`, `ConsoleActionRegistryTests`, `KnowledgeAtlasTests`,
  `AttachmentNormalizerTests`, `ShareCoordinatorTests`, and `PanelStoreTests`
  pass.
- The complete JarvisKit suite passed 190 tests on 2026-09-18 after adding
  typed voice approval-offer and memory metadata decoders. The native Memory
  tab renders the same inspection metadata returned by the admin API.
- The approved inbound transfer path is wired in the sandbox: the server
  issues a distinct `input/accept` transfer ID, native sends one bounded chunk
  at a time after `input/ack`, and manifest/chunk/commit/analyze messages feed
  the bounded ephemeral transfer session with digest, ordering, quota,
  approval, session-lifetime memory latch and cleanup checks.
  Provider delivery and physical-Mac acceptance remain separate gates.
- Native publishes a bounded, revisioned `console/inventory` snapshot after
  handshake, display arrival and console mutations. The backend validates the
  negotiated identity and uses the latest snapshot for target resolution and
  stale-selection rejection; the snapshot contains IDs and labels only.
- Layout-2 navigation, result selection/comparison, sharing controls, Atlas
  selection and primary graph controls now call the same app-scoped
  `ConsoleActionCoordinator` used by voice requests; legacy layouts retain
  their existing fallback path when no coordinator is injected.
- Native request handling now repeats the closed action/argument checks and
  rejects a revision that no longer matches the live workspace before any
  store mutation. The response is `stale_selection`, and the regression suite
  covers stale revisions, unknown fields and non-finite numbers.
- Graph node moves use the same bounded store owner as pointer drags: the
  requested coordinates must be finite and within the persisted ±1,000,000
  point layout bound. Invalid voice requests return `invalid` without changing
  the saved node position; the regression suite covers both rejection and
  boundary acceptance.
- Knowledge Atlas voice placement supports either a relation to another card
  or an exact one-based row/column (1…100), rejects occupied cells and invalid
  groups, and preserves stable card identity. Graph focus accepts a bounded
  depth (1…4), and scoped paragraph sharing uses deterministic one-based
  sections from the frozen result snapshot.
- The Python request boundary now enforces the same required-target,
  secondary-target, identity-length, array, and scalar-type rules as the native
  registry; `view_set` accepts its locked `mode` argument without a target, and
  `compare_set`, `atlas_move`, and `graph_path` require a secondary identity on
  both boundaries. The focused Python contract/action set passes 13 tests and
  includes direct Swift-enum, target-set and argument-field parity assertions;
  the native registry parity suite passes 4 tests.
- Persisted layout values are closed to `0|1|2`; unknown values resolve to the
  adaptive layout. Fresh installs and one-time migrated installs use Command
  Console layout 2, while the Debug menu retains rollback to older layouts.
- Focused native verification on 2026-09-18 passed 42 tests covering the
  coordinator, action registry, attachment bounds, startup conversation view,
  and virtual-screen placement/recovery. This is implementation evidence for
  UI2-03/UI2-06, not physical-monitor or full voice acceptance. (Reconciled
  2026-09-22: this 42-test run is not recorded in a committed receipt; treat
  the count as unverified.)
- The fresh candidate bundle now launches without the prior `PanelStore`
  environment crash. Native transport startup opens the WebSocket before
  CoreAudio and starts CoreAudio outside the socket callback queue; the
  focused `NativeAudioTransportTests` pass 21/21, including the main-actor
  CoreAudio-start regression. The exact candidate reached
  HTTP 101 on `ws://127.0.0.1:7860/ws-client`, established a bot session, and
  was inspected in the logged-in Mac UI at `READY VOICE` with the compact
  Conversation view as the default. Output-speech and complete two-channel
  active-audio evidence remain separate open gates.
  (Reconciled 2026-09-22: the 21/21 run has no committed log. The committed
  `receipts/monitor-ownership-2026-09-18/audio-start-deadline-tests.log`
  records `NativeAudioTransportTests` 22/22 after the 30-second audio-start
  deadline was added; the file now has 26 static tests. `READY VOICE` is
  recorded in `receipts/candidate-live-response-display-2026-09-18.md`.)
- The `ScreenPlacementTests` (eight at the time of this entry; nine static
  tests at `88b206f`, 9/9 in `receipts/full-verification-2026-09-18.md`)
  include synthetic virtual-screen clamping,
  manual-frame preservation, mirrored-screen handling, disconnect/reconnect
  recovery, and a live two-display topology check. That check passed on the
  connected Mac on 2026-09-18. A direct `NSScreen` probe on 2026-09-17
  reported one screen (`1710x1107`, visible origin `y=57`, scale `2.0`); the
  later 2026-09-18 probe records two system-recognized displays. A read-only
  probe is now available
  at `scripts/run_display_topology_probe.sh` for the logged-in Aqua session;
  headless shells may correctly report zero screens and do not count as a
  multi-display receipt. The current two-screen receipt is
  `receipts/display-topology-2026-09-18-current.json`; it records the external
  `C34H89x` as the current main display and leaves content-role/reconnect
  acceptance open.
- The connected candidate has a separate role receipt showing the console on
  `C34H89x` and the supporting display on the built-in panel:
  `receipts/candidate-two-screen-roles-2026-09-18.md`. This does not close the
  content-governance or reconnect gates.
- A focused candidate inspection then showed the main console retaining an
  `On the supporting display — Return here` locator while `Mortimer Display`
  contained exactly one bounded research card and no sidecar, console, or
  transient-window fan-out. The evidence is recorded in
  `receipts/candidate-two-screen-content-2026-09-18.md`; repeated-request,
  explicit-pin, fetch/subscription, reconnect, and one/three-display gates
  remain open.
- The rebuilt candidate's pointer-driven graph exercise is recorded in
  `receipts/candidate-supporting-stage-live-2026-09-18.md`: the supporting
  window now visibly contains one bounded graph stage with its header and no
  nested window fan-out. Closing it returned the graph to the main surface,
  but the client reported a socket error during the same exercise; reconnect
  after display close therefore remains an explicit open gate.
- The architecture contract is inspectable from both sides: the self-edit
  author receives a bounded `docs/ARCHITECTURE.md` context suffix, while the
  admin sidecar's read-only `/api/architecture` route feeds the native Repo
  sidecar's expandable full-document view and digest. The source remains the
  repository file; this adds no mutable architecture store.
- The layout-2 attachment tray is available before staging and accepts paste,
  file choose and bounded native drop input through one normalizer; approval
  and provider disclosure remain required before transfer. Clear increments a
  staging generation, so late file-provider callbacks cannot repopulate the
  tray; the guard is covered by `AttachmentStoreTests`.
- Voice `input/offer` messages now decode through JarvisKit, are rejected when
  their session/generation is stale, and appear in the same tray with explicit
  “Send these items” / “Cancel these items” controls. Approval reuses the
  existing manifest/chunk state machine, and unattended offers expire after
  120 seconds. Hands-free spoken consent and the provider journey still
  require Mac acceptance evidence.
- The hands-free path is now wired in the final-transcription observer: only
  the exact normalized phrases “Send these items” and “Cancel these items”
  consume a pending offer, emit one typed `input/consent`, and reuse the same
  native approval state machine. Non-matching speech remains an ordinary turn.
- Existing graph p95 gate remains 33 ms; the latest clean measured p95 was
  9.908 ms (2026-09-18 native run; max 13.147 ms), recorded in the committed
  [`receipts/response-routing-2026-09-18/P4-frame-time.json`](receipts/response-routing-2026-09-18/P4-frame-time.json).
  (Reconciled 2026-09-22: this entry previously cited the uncommitted build
  output `macos/MortimerHost/.build/interface-fixtures/P4-frame-time.json`.
  The later full-verification receipt records p95 9.627 ms, max 12.743 ms,
  but no JSON for that run is committed.)
- Verification rerun on 2026-09-18 after the supporting-stage handoff fix:
  `PresentationLevelMappingTests|VoiceWaveRenderingTests` passed 13/13,
  `SupportingDisplayAcceptanceTests` passed 2/2 (including the four-result
  visible-grid regression), and the focused Python
  memory/console/manifest acceptance set passed 230 tests. These are current
  sandbox evidence; they do not close the physical display, provider, picker,
  accessibility, rollback or daily-driver gates below.
  (Reconciled 2026-09-22: this rerun has no committed log. The committed
  `receipts/response-routing-2026-09-18/render-tests.log` records
  `SupportingDisplayAcceptanceTests` 4/4, which matches the four static tests
  now in that file.)
- The durable automated-run receipt is
[`sandbox-verification-2026-09-18.md`](receipts/sandbox-verification-2026-09-18.md).
  It records the complete Python, JarvisKit, MortimerHost, plan-manifest and
  formatting checks plus the latest graph timing numbers.
- The current focused native rerun is recorded in
  [`current-focused-native-2026-09-18.md`](receipts/current-focused-native-2026-09-18.md):
  ScreenPlacementTests 8/8 and the Command Center/rendering/ownership filter
  39/39 passed. These are receipt-time counts. The later full-verification
  receipt records ScreenPlacementTests 9/9.

## Open Mac evidence

Graph-image follow-up (September 18): `GraphImageView` now includes the source
URL and backing scale in its debounced task identity. Previously a different
graph at the same viewport size could retain the old bitmap indefinitely.
The unmeasured-viewport fallback also accepts a changed source URL. This is a
source correction; it does not close the cross-view duplicate-fetch or live
provider acceptance gates. `MemoryGraphImageStore` retains its separate tested
same-query reuse and stale-reply rejection behavior.

`AdminAPI.graphImageData` now coalesces identical in-flight URLs through its
session-local `GraphImageRequests` owner after validating the configured
origin. It retains no completed response cache. Five concurrency tests cover
one-fetch sharing, independent URL/owner isolation, cancelling one versus all
waiters, fresh subsequent reads and retry after failure. The full JarvisKit
suite passes 195/195 (reconciled 2026-09-22: no committed receipt records this
run. The committed JarvisKit logs record 190/190. 195 is the static test
count at `88b206f`, including the five `GraphImageRequestsTests`). This closes the legacy path's concurrent-request
implementation gap; cross-surface/provider instrumentation and repeated live
voice requests remain acceptance work.

September 18 monitor follow-up: mixed pointer/transport ownership is corrected
and rendering on both attached screens is covered by the new native test.
The [ownership receipt](receipts/monitor-ownership-2026-09-18/README.md)
records the 52-test focused pass, three rendering passes, images, rebuilt
executable hash and live graph/locator handoff. Physical display recovery is
now covered by the candidate monitor receipts. The atom voice display is
implemented and accepted in the adaptive-interface receipt; live two-channel
audio and visual acceptance remain open.

System share picker delivery, inbound provider journey, full accessibility
matrix,
independent receipt, rollback exercise, deployment hash, and the separate
five-day daily-driver period are not established by unit tests.
The current two-screen inspection also found Mortimer disconnected from its
backend stack; the readiness failure is recorded in
`receipts/live-app-connection-2026-09-18.md` and must be cleared before any
content-placement observation can count.
The rebuilt exact candidate was subsequently connected in a single-screen
inspection and reached `READY VOICE`; this clears startup readiness for that
session only. It does not replace the two-screen role, reconnect, or content
placement receipts above.
The fresh external-graph exercise is recorded in
[`candidate-memory-graph-external-2026-09-18.md`](receipts/candidate-memory-graph-external-2026-09-18.md):
the graph rendered on the supporting display with its controls and 404/37
summary, and the corrected bounded multi-result stage emitted no negative
geometry errors. The long-lived native socket later ended with `Socket is not
connected`, so voice/socket reconnect recovery remains open; the physical
display reconnect path is covered separately below.
The latest connected-monitor observation is recorded in
[`candidate-external-stage-current-2026-09-18.md`](receipts/candidate-external-stage-current-2026-09-18.md):
the exact candidate exposed one `Mortimer Display` supporting-stage window with
the memory graph and no nested or transient-window fan-out; closing and
reopening returned the graph between the display scene and the main console.
The candidate was in `ERROR VOICE` during this observation, so voice-triggered
repeat and provider acceptance remain open; the physical reconnect path is
covered by the later monitor receipts.
The final exact-candidate unplug run is recorded in
[`candidate-monitor-auto-rehome-2026-09-18.md`](receipts/candidate-monitor-auto-rehome-2026-09-18.md):
with the graph on `Mortimer Display`, unplugging the external monitor without
using “Return here” removed the supporting window and left the graph usable in
the main console. The physical unplug/rehome and reconnect-restoration gates
are closed; voice-triggered repeat and provider/fetch instrumentation remain
open.

Reconciled 2026-09-22 against main `88b206f`. The three committed monitor
receipts show the following:

- [`candidate-monitor-unplug-2026-09-18.md`](receipts/candidate-monitor-unplug-2026-09-18.md):
  after unplug the probe reported one display. The graph and response moved
  to the main workspace when the user chose **Return here** (a manual
  return). No duplicate window was created. The candidate was in
  `ERROR VOICE` / `Socket is not connected`.
- [`candidate-monitor-reconnect-2026-09-18.md`](receipts/candidate-monitor-reconnect-2026-09-18.md):
  after replugging, the probe reported two screens. Reopening the display
  restored one stage with the same two results. The receipt says it closes
  "display topology and bounded-stage restoration only". The candidate was
  still in `ERROR VOICE`.
- [`candidate-monitor-auto-rehome-2026-09-18.md`](receipts/candidate-monitor-auto-rehome-2026-09-18.md):
  unplugging without **Return here** removed the `Mortimer Display` window and
  left the graph in the console. The receipt says this closes "the physical
  unplug/rehome gate for the candidate".

In summary, physical display unplug/rehome and display reconnect restoration
are recorded as passing for this candidate on one external monitor. These
are prose observation records. None of them includes a committed
screenshot or accessibility capture, visible tile IDs, or duplicate-fetch
instrumentation, all of which runbook §2 requires. Mirrored and three-display
runs were not performed. Voice/socket reconnect failed in both the unplug and
reconnect runs, so it remains open. The paragraph below about the manual
reconnect describes only
[`candidate-live-response-display-2026-09-18.md`](receipts/candidate-live-response-display-2026-09-18.md),
which covers neither unplug nor reconnect. Its remark that physical
unplug/reconnect was not closed means that receipt does not close it. The
monitor receipts above cover it.
The latest locked-session native rerun is recorded in
[`native-rerun-locked-2026-09-18.md`](receipts/native-rerun-locked-2026-09-18.md):
JarvisKit remained green, while the eight MortimerHost failures are the
visibility fixture's expected inability to obtain an unoccluded window while
the Mac is locked. This is an environment blocker, not a test waiver.
The follow-up service-health and reconnect attempt is recorded in
[`candidate-reconnect-attempt-2026-09-18.md`](receipts/candidate-reconnect-attempt-2026-09-18.md):
the local services answered their health checks, but the exact candidate did
not produce a settled `READY VOICE` state during that attempt.

That observation was superseded by a later manual reconnect: the same
candidate reached `READY VOICE`, moved the memory graph to the supporting
window, and verified the main-console `Memory graph is on the supporting
display` / `Return here` locator. Closing the supporting window returned the
graph to the main surface without opening another window. This improves the
startup and ownership evidence, but does not close physical unplug/reconnect,
active two-channel audio, or live spoken-response gates.

- [ ] **UI2-19 — Multi-window content policy and duplicate suppression.** The
  2026-09-18 two-screen exercise showed memory-graph content on the external
  display while the same graph remained rendered in the main work surface,
  and repeated display requests accumulated several low-value graph panels.
  Before UI2-06/UI2-09 can close, define and implement one authoritative
  renderer for each exact graph/result identity: an external assignment must
  leave a compact “On [display] — Return here” locator in the main surface,
  repeated requests must focus/reuse the existing panel, and only explicitly
  pinned additional panels may coexist. When no supporting display is
  available, the same content must remain usable in the main surface. Verify
  this by voice and pointer on one and two displays, including return-to-main,
  repeated “show the memory graph” requests, bounded panel count, and no
  duplicate fetch/subscription work.
  The latest candidate log also recorded the console and display settling on
  the external `3440x1410` screen, so placement stabilization and content
  ownership must be verified together.
  Sandbox implementation now reuses an exact payload identity, focuses the
  existing panel, exposes a separate explicit pin/duplicate path, and routes
  pointer-selected legacy `WorkspaceStore.supportingContent` through the same
  single supporting stage as modern panels. The main surface keeps an
  `On the supporting display — Return here` locator. Focused supporting-display
  acceptance is 1/1 (receipt-time count, no committed log. The committed
  `response-routing-2026-09-18/render-tests.log` later records 4/4. Reconciled
  2026-09-22). The router now reuses the existing workspace owner for
  an exact repeated window payload, while distinct sections from one
  Developer run still receive separate history rows;
physical two-screen and return-locator behavior is now recorded in the
  candidate monitor unplug/reconnect receipts; provider/fetch instrumentation
  acceptance remains open.
- [ ] **UI2-20 — External-display content governance and presentation budget.**
  The recent two-screen logs show the external display receiving the memory
  graph while the same graph remained in the main surface, and the display
  window being re-added multiple times during one attach cycle. Define the
  external screen as one curated presentation stage: one result fills it,
  two results share it in a split, and three or four results use a bounded
  adaptive grid. The console, sidecar, transient status panels and duplicate
  graph windows stay on the primary surface unless the user explicitly moves
  or pins them. Repeated requests must replace or focus the active identity,
  never open a nested information window or fan out more windows. Verify the
  bounded tile count, stable console/display roles, explicit pin as the only
  way to add overflow, and clean unplug/reconnect recovery on one, two and
  three displays. This is a release gate in addition to UI2-19's identity and
  fetch/subscription checks. The sandbox store and supporting-stage view now
  enforce the four-result unpinned budget and preserve explicit pins;
  physical role, reconnect and bounded multi-result behavior are now recorded
  for this session; three-display/mirrored-output behavior, provider/fetch
  instrumentation and voice-triggered repeat evidence remain open.
- [ ] **UI2-21 — Developer-run result grouping and Liquid Glass consistency.**
  (ID collision, noted 2026-09-22: `adaptive-interface/RELEASE_READINESS.md`
  uses UI2-21 for a different, ticked item, "Atom-style compact voice display
  (implementation)". The two UI2-21 entries are separate requirements. Cite
  them by title until one is renumbered.)
  A single self-edit request may read several files and emit several
  window-routed results. The client must group those same-`run_id` Developer
  payloads into one outer result window with appended sections; separate runs,
  ordinary research/weather/graph results, and explicit pinned copies remain
  independent. All supporting-stage tiles, including the single-result stage
  and legacy in-window fallback, must use the shared `.mortimerGlass` modifier
  and respond together to the Liquid Glass setting. Sandbox implementation and
  focused tests are complete; physical grouped-run and glass-on/off evidence
  remain open.
- [x] **UI2-22 — Atlas source coverage (implementation).** `KnowledgeAtlasView`
  now retains the existing `WorkspaceStore.results` cards and adds a bounded,
  read-only context projection from the authenticated AdminAPI: memory
  overview/facts, the architecture reference and digest, current plan status,
  recent run lineage, and the shared memory-graph summary. `AtlasStore` uses
  stable namespaced identities and merges context refreshes without resetting
  result selection, manual placement, or groups. `AtlasCardView` labels each
  source kind and uses the shared Liquid Glass card treatment. The focused
  `KnowledgeAtlasTests` suite passes 4/4. Physical Atlas refresh/error,
  VoiceOver, and multi-display evidence remain part of the open Mac gates.
- [ ] **Stray duplicate source file (housekeeping, noted 2026-09-22 against
  main `88b206f`).** `macos/MortimerHost/Placement/ContentWindowRegistry.swift`
  sits outside the package's `Sources/` tree. It is an older, different
  version of the real
  `macos/MortimerHost/Sources/MortimerHost/Placement/ContentWindowRegistry.swift`,
  which is the file the plan manifest checks. Remove it or explain it in a
  separate code change. This status update does not touch code.
