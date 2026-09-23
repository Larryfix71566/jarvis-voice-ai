# Adaptive interface release readiness

Updated 2026-09-18 after the architecture-reference audit and full sandbox
verification. The
deployed release is main revision `94a56412f065d7808ca5ad87825fbdd38df9ad36`
with candidate fingerprint
`b57cd348b0d0c30359a6713f919732fe3fabef373a8ffe8be208c75fdc382fe8`.
This checklist distinguishes implementation, merge, verification, deployment
and user acceptance. A pass in one category never implies the others.

Scope augmented 2026-09-17 with the Command Console / Knowledge Atlas
implementation closure gates below. The release identity above is the existing
deployment record, not a claim that the proposed redesign is deployed. All 12
previously open items and all 14 completed items retain their status.

The redesign now has sandbox implementation evidence: the Command Console
composition (shipped as the default layout), Atlas/store primitives, bounded shared-content contracts, memory automation policy and native regression suites are present.
UI2 rows remain open because they close only with exact-candidate acceptance,
physical display/audio/accessibility exercises, provider journeys, deployment
receipts and daily-driver evidence. Implementation presence does not close
those release gates.

Latest sandbox verification (2026-09-18): Python 2,611 passed / 4 skipped;
JarvisKit 190 passed; MortimerHost 244 tests executed (3 display-dependent
skips; 0 failures). See the current full-verification
receipt in the Command Center acceptance directory.
The live content-window registry
and value-addressed panel scenes are wired into the console, display and drawer
surfaces. Physical multi-monitor, sharing, accessibility and daily-driver gates
remain open. Targeted host coverage for the approval-offer, layout-default,
catalog scalar-type, secondary-target, and bounded content-panel changes passed 42 tests.

The exact release-review candidate also reached `READY VOICE` in the logged-in
Mac UI with the compact Conversation view as its startup state. The measured
input path was previously observed through `HEARING YOU` and a visible compact
lobe; output-speech verification and the complete two-channel audio receipt
remain open.

## TODO — remaining items

- [x] **ARCH-01 — Current architecture and operations reference.** Closed
  2026-09-18: [architecture reference](../../ARCHITECTURE.md) is linked from
  the README, documentation index and repository map, and its source/runtime
  audit plus explicit model-route dry-run passed. The reference now records
  Haiku as Supervisor/orchestrator-only and keeps registry routes explicit for
  agents, planning/research, vision, memory and background maintenance.
  Existing September 4 snapshot remains historical evidence. The live memory
  provider receipt and native physical acceptance gates remain separately open.
- [ ] Publish a fresh status reconciliation to the repository after the
  remaining hardware and acceptance gates are recorded.
- [ ] Obtain a fresh full-profile independent receipt for the deployed release
  revision; the current deployment receipt is operational evidence, not the
  complete preservation receipt.
- [x] Resolve or characterize reported graphical timing/focus variability
  without disabling checks or relaxing the 33 ms frame-time gate. The latest
  complete current-host run has 0 failures across 244 executed tests (3
  display-dependent skips); the latest P4
  p95 is 9.678 ms (max 11.401 ms) in the current native receipt (the live run remains under
  the 33 ms gate).
- [ ] Earbud-removal rebuild-churn investigation.
- [ ] Echo benches: AirPods both ways; AirPods output + built-in input.
- [ ] Complete C8's five requirements and all P0 preservation rows. Existing
  known-limitations acceptance enabled the default flip; it did not run C8.
- [ ] Complete T1.3 V3–V8: tabs/workflows, output/log, display/multi-display
  and visual/accessibility acceptance. Record test case and evidence.
- [ ] Complete T1.3 V9's five-day daily-driver period begun September 15.
- [ ] Settle model-registry split decisions before implementation (#71 is
  a merged plan, not delivered code).
- [ ] Speaker-gate labeled effectiveness protocol; keep gate off until met.
- [ ] Security V2–V6 acceptance; V7 deny entries are already on main.
- [ ] Routing/evaluation floors and current denominator reconciliation.

C8 needs legacy/adaptive preservation, five viewport sizes, compact notices,
workspace pins/comparison/reading state, graph interactions, keyboard and
accessibility behavior, physical audio/device scenarios, monitor recovery,
synthetic-state rollback and an exact-candidate independent receipt. Unit
fixtures do not by themselves establish physical-device behavior.

## TODO — Command Console / Knowledge Atlas implementation closure

Specification: [Command Console / Knowledge Atlas plan](../../plans/MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md).
UI2 identifiers below are stable checklist IDs; CC0–CC8 refer to the plan's
implementation increments. The implementation increments have partial
sandbox evidence; all additions remain open as release-acceptance gates.

- [x] **UI2-01 — Resolve imported-content memory behavior before CC6.** The
  release decision is session-only temporary-content mode: staging is local and
  does not pause ordinary memory; an approved manifest arms the latch until
  reconnect, imported content and derived answers remain ephemeral, and the
  user sees the pause notice. `test_staging_does_not_pause_memory_but_approved_manifest_does`
  plus the sensitive-transcript tests cover the boundary.
- [ ] **UI2-02 — Freeze baseline and preservation coverage (CC0).** Record
  source revision, existing local changes and baseline verification. Map all
  24 P0 preservation rows and the existing open C8/T1.3 requirements to the
  redesigned candidate's acceptance evidence; omit none.
- [ ] **UI2-03 — Shared ownership and action contracts (CC1).** Verify one
  owner for audio, results, graph state and placement; matching Swift/Python
  schemas; capability negotiation; default-off gates; truthful acknowledgements;
  stale-target rejection; cancellation and duplicate-request handling.
- [ ] **UI2-04 — Command Console and complete sidecar (CC2).** Deliver the
  selected composition with measured user/AI waveform feedback, captions and
  existing controls. Preserve all eight tabs, readable scrolling headers,
  font preferences, attention states and unsent drafts. Keep old layouts usable.
- [x] **UI2-04a — Measured-wave visibility correction (implementation).** The
  adaptive wave now applies documented channel-specific measured-audio gains
  (`0.55` input / `0.42` playout) after the dB window, lifting the recorded
  quiet-input median into visible compact-rail travel while preserving the
  no-level-is-no-speech rule. The adaptive renderer now adds a bounded
  measured-audio depth ribbon with a Mortimer-only depth lift and no synthetic
  depth when output is unavailable. The focused mapping/render suite passes
  13/13.
  The latest hardware receipt records 403 input arrivals and 84 playout
  arrivals; input is observed, but the two-channel P2 floor is not yet met,
  so this is not a complete physical C7 pass.
- [ ] **UI2-05 — Atlas and memory graph (CC3).** Verify cards/groups, selection,
  sources, comparison, pins and reading state; legible graph selection, search,
  filters, paths, provenance, camera and original fallback. Preserve actual
  graph semantics and show missing/truncated data honestly.
- [x] **UI2-21 — Atom-style compact voice display (implementation).**
  Requested September 18 from the supplied 12-second video. Replace the
  compact voice visualization with a luminous central nucleus and tilted
  elliptical orbits, keeping the compact Conversation view as the startup
  default. Distinguish user and Mortimer with separate colors and orbit planes;
  use measured microphone and playout levels independently, including overlap.
  Proposed palette: cyan/teal user and amber/orange Mortimer. Verify visible
  response for both speakers, truthful idle/mute/offline/unavailable states,
  reduced motion, contrast, existing tuning controls and bounded rendering cost.
  Preserve voice controls, captions, sidecar contents and result space. The
  sandbox implementation and rendering acceptance are recorded in
  `receipts/candidate-atom-wave-2026-09-18.md`. Live two-channel audio,
  accessibility and final candidate visual acceptance remain release gates.
- [ ] **UI2-06 — Detachable content and physical monitor recovery (CC4).**
  Verify supported panels on one, two and three displays, including mirrored
  outputs, manual positions, unplug/reconnect, return-all and panel limits.
  Preserve content, drafts and selection without duplicate work or hidden
  windows. The logged-in Mac now provides two system-recognized displays and
  the live placement topology check passes; panel exercise, three-display,
  and mirrored-output evidence remain open. The latest exact candidate run
  proves automatic unplug/rehome and reconnect restoration: the supporting
  window closes without manual recovery and the graph remains usable in the
  main console. See
  `command-console/receipts/candidate-monitor-auto-rehome-2026-09-18.md`.
  The earlier socket errors corresponded to a logged five-minute backend idle
  timeout; native sampling separately found audio startup blocked in CoreAudio.
  Startup now times out with a usable Connect control, but successful live
  audio remains open. Unavailable physical
  hardware leaves that scenario open.
- [ ] **UI2-19 — Multi-window content policy and duplicate suppression (CC4/CC7).**
  The two-screen exercise showed the memory graph in both the main work
  surface and the external display, while repeated display requests created
  several low-value graph panels. Define one authoritative renderer per exact
  graph/result identity, show a compact return locator at the source surface,
  focus/reuse repeated requests, and allow additional panels only after an
  explicit pin action. Verify one/two-display fallback, repeated voice and
  pointer requests, return-to-main, bounded visible panel count, and no
  duplicate fetch or subscription work.
  The sandbox renderer reserves a stage tile for pointer-selected content
  and derives main-surface locators from actual visible ownership. The
  September 18 response-routing update also places full Mortimer answers in
  results, updating one card per user request across streamed/tool subturns.
  Brief live captions remain beside the voice visualization; the full Log
  remains available. Replies join the bounded supporting grid when open and
  return to the main results area when it closes. Two-screen native rendering
  tests verify these paths with synthetic text; live provider/voice and
  duplicate-fetch evidence remain open. The physical unplug/rehome path is
  covered by the candidate monitor receipt. See
  `docs/acceptance/command-console/receipts/response-routing-2026-09-18/README.md`.
- [ ] **UI2-20 — External-display content governance and presentation budget
  (CC4/CC7).** The recent two-screen logs show the memory graph rendered in
  both the main work surface and the external display, while the display
  window was re-added several times during one attach cycle. Treat the
  external screen as one curated outer presentation stage: one result fills
  it, two results split it, and three or four results use a bounded adaptive
  grid. Console, sidecar, transient status panels and duplicate graph windows
  remain on the primary surface unless explicitly moved or pinned. Repeated
  requests replace or focus the active identity, never open a nested
  information window. Verify bounded tile count, stable console/display roles,
  explicit pin as the only additional-panel path, and unplug/reconnect
  recovery across one, two and three displays. The sandbox store and view now
  enforce the four-result unpinned stage budget and preserve explicit pins;
  real two-screen synthetic rendering now verifies multi-result layout and
  no extra floating tile. Three-display/mirrored-output behavior and live
  provider/voice acceptance remain open; automatic unplug/rehome and
  reconnect restoration are covered by the candidate monitor receipts.
- [ ] **UI2-07 — Outward text/image sharing (CC5).** Verify explicit selection,
  immutable preview, text/PNG copy, save/reopen, export-folder access, cancel
  and system sharing in another app. No adjacent private UI is exported;
  opening a picker is never reported as recipient delivery.
- [ ] **UI2-08 — Inward text/image analysis (CC6; depends on UI2-01).** Verify
  paste/drop/choose, exact previews, bounded normalization, explicit approved
  batches, configured provider disclosure, upload progress, failure/cancel,
  reconnect and ephemeral-result cleanup across every UI history. No automatic
  upload or replay and no hidden screen/clipboard capture.
- [ ] **UI2-09 — Complete voice parity (CC7).** Exercise every new
  Mortimer-owned action through the shared voice and pointer/keyboard path,
  including sharing and moving content. Verify ambiguous references, duplicate
  titles, late results, unavailable displays and honest failure feedback.
  Retain mic/PTT/wake behavior; document the boundary at OS-owned dialogs.
- [ ] **UI2-10 — Sharing security and memory-isolation acceptance.** Extend
  existing Security V2–V6 coverage for the final UI2-01 decision, imported
  instructions, malformed/oversize inputs, stale sessions, unauthorized batches,
  diagnostics, persistence sinks and cleanup. Prove ordinary memory behavior
  is preserved as specified. Existing security gaps remain separately open.
- [ ] **UI2-11 — Routing/evaluation and compatibility.** Update tool-menu and
  prompt parity, coverage denominator and voice fixtures for the new tools;
  meet existing evaluation floors without relaxing budgets. Test old clients,
  disabled features and both native/WebRTC application-message paths. This
  does not settle the separate model-registry split decision.
- [ ] **UI2-12 — Combined performance and audio regression gate.** Exercise
  graph plus six panels plus maximum accepted attachment load during voice.
  Retain the 33 ms graph gate and current audio limits; verify focus/timing,
  cancellation and bounded memory. Carry forward the earbud, echo and
  speaker-gate obligations; UI work is not evidence those issues are fixed.
- [ ] **UI2-13 — Candidate visual/accessibility and user acceptance.** Complete
  C8/P0 and T1.3 V3–V8 coverage for the redesigned candidate, including required
  viewport/font combinations, keyboard/VoiceOver, contrast/reduced motion,
  notices and all tab workflows. Record Larry's acceptance of the actual
  running design, identified by artifact receipt, not a concept image.
- [ ] **UI2-14 — Exact-candidate independent verification (CC7–CC8).** Obtain
  the full-profile sandbox/independent-verifier receipt, required Swift/backend
  suites and repository CI for the frozen candidate. Historical receipts and
  verification of the earlier deployed release do not satisfy this gate.
- [ ] **UI2-15 — Demonstrate rollback (CC8).** Verify feature switches,
  return to layout 1, panel recovery, pending-transfer cancellation and
  restoration of the known-good app/server artifacts. Preserve drafts,
  existing preferences and user-saved files; do not falsely claim provider
  context is erased. Record the rollback exercise and recovery result.
- [ ] **UI2-16 — Candidate deployment and loaded-version evidence (CC8).**
  After required approval/gates, record coordinated app/server deployment,
  artifact hashes, actual process paths, health and a successful end-to-end
  voice/content-sharing journey. Do not overwrite the only known-good build.
- [ ] **UI2-17 — New candidate's five-day daily-driver acceptance.** Begin a
  separate dated period after the redesign candidate is frozen and installed.
  Record interruptions, failures and fixes; a material fix requires a fresh
  candidate record and a new period. Preserve September 15's earlier-version
  record without presenting it as evidence for the redesign.
- [ ] **UI2-18 — Final reconciliation and closure record.** Publish the final
  source/merge/verification/deployment/acceptance status with evidence for each
  UI2 item and every original gap. Move only evidenced completions below; list
  unresolved hardware or design requirements explicitly. Keep web retirement
  and unrelated roadmap gates dependent on their original acceptance rules.

### Coverage and counting rules

The current file contains 30 unchecked and 19 checked checklist entries. The
older 31-open / 15-complete narrative is retained only in historical receipts;
these are differently sized obligations, not a weighted estimate of project
effort or completion.

Several additions extend existing gates to a new candidate rather than create
independent defects. Cross-link shared evidence instead of duplicating tests:
UI2-02/UI2-13 extend C8/P0 and T1.3 V3–V8; UI2-06 extends display acceptance;
UI2-10 extends security; UI2-11 extends routing/evaluation; UI2-12 extends
timing/audio; UI2-14 requires the new candidate's independent receipt.
Check each covered row only if its exact scenario and version are evidenced.
Earlier-version obligations keep their own status; explicitly supersede a
version-specific gate with a recorded scope decision rather than silently
marking it passed. UI2-17 is distinct from the earlier daily-driver record.

An accepted limitation remains an open gap with a recorded release exception;
it is not a test pass. Do not relabel implementation as physical acceptance,
change a denominator to hide untested actions, or close a parent requirement
from a passing subset. The separate automated-memory roadmap is not completed
by Atlas visualization, historical replay or the UI2-01 design decision.

## Completed items

- [x] Main identified as `94a56412f065d7808ca5ad87825fbdd38df9ad36`.
- [x] PRs #65–79 merged; native audio and adaptive foundation are present.
- [x] PR #76's waveform, delegation, interruption and extraction changes were
  reviewed, consolidated and deployed.
- [x] Existing receipt `a56c192c20704ab5a7d59366a9e52d43` passes all 12 checks
  and desktop probe at `8c1fb5a`, with unchanged source. This is historical.
- [x] Prepared image dependencies match `5faa2e6`; controller doctor passes;
  no other VM was running before this release task started.
- [x] Adaptive workspace, sidecar header, graph and placement code exists.
- [x] Native capture/playout observation drives distinct user/AI feedback.
- [x] Native audio live conversation, output switching, muted wake word and
  WebRTC rollback have recorded evidence (C6/C7).
- [x] Audio-report minimum sample floor and explicit coverage field are in the
  deployed release.
- [x] The pre-deployment mixed topology was inspected and the five local
  patches were preserved during reconciliation.
- [x] A version-identifiable signed bundle was built from the release source.
- [x] Coordinated bot/admin/app/extractor deployment completed; intended DB
  path, rollback backup and health checks are recorded in the deployment
  receipt.
- [x] Actual process paths, working directories, PIDs and source metadata were
  recorded after restart.
- [x] Replayed the 28 verified failed extraction exchanges after deployment;
  28/28 completed with zero errors, producing 24 facts and 12 observations.
  The live cursor remained at 3219. Receipt:
  `work/release-memory-replay-result.json`.

Remote access, local models/Mac mini, financial-data handling, mail/calendar
and advanced skill authoring retain their own roadmap gates. Web retirement
waits for native acceptance and daily-driver completion. Native WebRTC is
still needed for remote/rollback operation after web-console retirement.

**Future roadmap additions, 2026-09-17:** T7 home automation integration,
T8 home surveillance interactions/automation, and T4c investing assistance
automation under the existing financial track are queued in the
[platform roadmap](../../plans/MORTIMER_PLATFORM_ROADMAP.md). Their open
decisions O8–O10 and future gates G7/G8/G4c remain there until detailed plans
define implementation closure lists. They are not part of UI2, do not block
  completion of this interface release, and are excluded from the 31-open /
  15-complete release checklist count. T4c retains the G3/G4 prerequisites.

**Memory automation additions, 2026-09-17 (reconciled 2026-09-18):** the
automated classification and maintenance phase is specified in
[MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md](../../plans/MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md).
The sandbox policy, offline B5 corpus, provider-backed shadow, and executable
staged-rollout gate (including limits and first-20-decision review) now pass;
gradual Mac enablement and redacted live benefit/cost monitoring remain open
and are tracked separately from UI2 and the original release count. Historical
28-exchange replay does not satisfy these gates.

## Evidence rules

For each newly checked item record date, source commit or candidate digest,
scenario, result, and evidence path. Keep historical failures. A source fix
is not a test result; accepted risk is not a pass; a listener is not a live
conversation; an old receipt is not current-head verification.
