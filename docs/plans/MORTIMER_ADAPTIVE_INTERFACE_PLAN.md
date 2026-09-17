# Mortimer adaptive interface implementation plan

**Status:** IMPLEMENTATION IN PROGRESS; NO RELEASE ACCEPTANCE. See `docs/acceptance/adaptive-interface/` for measured progress and open gates.

**2026-09-17:** the adaptive layout is now the DEFAULT (`layoutVersion` 1, closure item C9.5 / gap G30). `Debug ▸ Use previous layout` is retained for one release. C8 acceptance is still unrun — its unexercised rows are accepted as known limitations in `docs/acceptance/adaptive-interface/C8-open-items.md` under Gate G-C8's written-acceptance route, which is not the same as acceptance having been performed.
**Current application candidate:** `6264fdf` on `feat/adaptive-compact-conversation`; adaptive
source phases and sandbox runner corrections are present, but release acceptance
is intentionally not claimed.
**Latest manual evidence:** Larry confirmed the sidecar font picker works after
`6264fdf`. Larry's subsequent screenshot shows the connected candidate using its
previous-layout presentation with floating graph images inside the main console.
Adaptive graph activation and acceptance remain open. Desktop automation had
selected the older MortimerShell retry screen; see the correction and screenshot
analysis in P6-interim-checks.md. A candidate connection failure or graph-routing
defect was not established by those earlier captures.
**Scope:** Native MortimerHost interface, dual-speaker Silo feedback, central results, interactive memory graph, preserved sidecar, automatic monitor adaptation.
**Baseline inspected:** repository commit `2ccf66cd7e00b82cf9136d2cd00f42e9bddb90af` (PR #63), 2026-09-10. Recheck the actual starting commit before implementation.
**Owner:** Larry. Implementation may be assigned to a coding model one phase at a time. This document authorizes no application-code change by itself.
**Safety claim:** This plan reduces regression risk through explicit contracts, independent verification, staged rollout and rollback. It does not promise zero regressions. An unmeasured or untested requirement remains open.

## 1. Agreed outcome and decision precedence

The primary screen becomes a useful working surface. The Silo wave retains Mortimer's identity, moving into a compact left column when results are displayed. During conversation with no result open, it can use the larger central presentation. It does not take the center back while Larry is reading.

Decisions, in precedence order:

1. **Preserve every existing sidecar tab and its contents.** Larry's final clarification supersedes any earlier suggestion to replace the sidecar with a contextual inspector.
2. **Fix the sidecar header:** horizontally scrollable labels at readable natural widths, overflow arrows, selected-tab visibility, and an unmistakable active state. Never squeeze, wrap, or shrink labels to fit.
3. **One Silo wave, two speaker colors:** teal for Larry's microphone input; violet for Mortimer's spoken output. Status text supplements color. The waveform must indicate actual activity, not invented confirmation of understanding.
4. **Remove the decorative central M.O.R.T.I.M.E.R. lettering.** Keep a small Mortimer name near the wave or top bar. Do not invent an acronym.
5. **Central results:** research, text, sources, images, documents, maps and memory exploration use the main area. Results remain available after speech ends. Support explicit comparison and pinning.
6. **Contextual details complement the sidecar.** They show sources or selected graph items without replacing, closing, or switching the existing sidecar.
7. **Automatic one-/multi-monitor adaptation:** useful on one screen; optional results/details on extra screens; recover all content when a screen disappears; restore prior arrangements without overruling manual placement.
8. **Interactive memory graph:** adopt the reference image's spacious network and selection/inspection structure. Do not copy its branding, unrelated controls, categories, person image, or implied capabilities.

Initial release uses a readable 2D graph. A 3D graph, new AI memory inference, transport replacement, provider/model changes, a web-client redesign, and broader product roadmap tracks are not part of this plan. These exclusions must not be used to omit any of decisions 1–8.

## 2. Verified starting points and important risks

Repository paths beginning with `macos/`, `jarvis/`, `sandbox/`, `tests/` or `docs/` are relative to the repository root. Short native paths beginning with `App/`, `Console/`, `Drawer/`, `Display/` or `Placement/` resolve under `macos/MortimerHost/Sources/MortimerHost/`; paths beginning with `JarvisKit/` resolve under `macos/JarvisKit/Sources/`. Proposed types and acceptance files are explicitly identified as new.

- `macos/MortimerHost/Sources/MortimerHost/Console/ConsoleView.swift` places a full-window wave behind the stage, overlays result panels, and docks the drawer on the right.
- `Console/VoiceWaveView.swift` retains Silo's layered sine shape, but its speaking amplitude is explicitly simulated. A speaking flag is not an audio level. Recoloring that simulation does not satisfy this plan.
- `Console/OrbFieldView.swift` contains the central lettering **and functional indicators**: agent activity, thinking, wake/speaker/audio notices and captions. Remove only the decorative lettering; map every functional indicator to a surviving home before changing the view.
- `App/VoiceState.swift` currently derives offline/connecting/listening/speaking from connection and bot speaking state. `macos/JarvisKit/Sources/JarvisKit/JarvisClient.swift` also exposes thinking, microphone state, wake pulses and transcript. User transcript handling currently appends final frames; do not claim interim transcription is already available in the UI.
- `JarvisKit/AudioInputCoordinator.swift` documents the AirPods capture/playout clock workaround. WebRTC owns the duplex audio path. Adding another microphone engine or changing the input format for a meter could degrade voice quality.
- `Drawer/DrawerView.swift` owns tab view-models and renders all labels in one HStack. Existing polling, drafts, attention dots, authentication errors and pop-out behavior are load-bearing.
- `App/UICommandRouter.swift` owns stable tab keys and existing voice-command behavior. The exact current sequence is `repo`, `edit`, `memory`, `runs`, `agents`, `output`, `transcript`, `costs`. Visible labels are **Repo, Edit, Memory, Runs, Agents, Output, Log, Costs**. Agents includes the council roster.
- `App/AppMessageRouter.swift` currently routes `.window` payloads to `DisplayWindowStore`, and drawer payloads to `DisplayResultStore`/Output. Preserve that contract and its auto-open/attention behavior while adding the central presentation.
- `Display/DisplayContentView.swift` renders body text, images/basemaps, links, command blocks and clipboard payloads. All remain supported.
- `JarvisKit/AppMessage.swift::DisplayPayload` has no stable server result ID; the existing stores assign client IDs. Unknown/absent surface defaults to drawer. Its clipboard `content` explicitly **must never be persisted**.
- `Display/GraphImageView.swift` renders server-generated graph images. The existing `/api/graph/memory` JSON route is in `jarvis/admin/server.py`; `jarvis/graphs/model.py` defines nodes, edges, legend, focus and truncation metadata. An interactive client should use this route rather than infer connections from pixels.
- `Placement/ScreenPlacement.swift` already observes monitor changes and protects manually adjusted windows. Its no-external-screen path currently leaves placement alone. Some file-header comments are historical; inspect executable call sites in `App/MortimerHostApp.swift` and `Placement/WindowPlacement.swift` before changing behavior.

**Deployment baseline:** The live Mac has five preserved local changes in `jarvis/admin/server.py`, `jarvis/bot/progress_watcher.py`, `jarvis/prompts.py`, `macos/MortimerHost/scripts/bundle.sh`, and `scripts/launchd/com.mortimer.template.plist`. They are not all represented by the base Git commit. Inventory them again; do not overwrite or silently absorb them. The last app deployment also required refreshing the local ad-hoc signature of the app and its bundled framework. A successful build alone is not a successful app launch.

## 3. Non-regression contracts (must remain true in every phase)

### UI-1 — Existing functions survive

All eight sidecar keys, labels, tab order, contents, commands, data operations, loading/empty/error states, authentication handling and keyboard behavior remain. Preserve editor drafts, selected records, scroll positions, active tab, width, attention dots, council roster, clear controls and pop-out/pop-in controls. Header scrolling must not recreate the active tab or duplicate polling subscriptions. Merely hiding a feature behind an inaccessible control is a regression.

Inventory the existing stage's captions, agent indicators, degradation notices, output-device reconnect action, speaker-rejection notice, wake state, connection errors and microphone controls. Assign each a visible destination in the new layout. Do not delete the functional OrbField content with its lettering. Retain top-bar weather/time/system information and existing audio-output behavior.

### UI-2 — Voice quality and control are independent of visualization

Do not change models, prompts, voice selection, audio gain, sample rate, VAD/speaker thresholds, mute/PTT semantics, wake-word rules, barge-in cancellation or speaker-gate policy to make the display look convincing. Metering is observation only. A failed or unavailable meter must not interrupt audio or prevent a conversation. Layout transitions must not reconnect WebRTC or create another audio session.

Do not open a second microphone capture engine, pause user capture during AI speech, or disable echo cancellation. Muting must stop user visualization immediately while permitting AI playback visualization. Raw audio is not recorded or sent to another service for this feature.

### UI-3 — Results and sidecar are preserved

The central view is an additional presentation of existing results, not a replacement for Output, Log, Memory or another tab. Existing surface routing and auto-open/attention semantics remain until separately approved; deduplicate presentations by shared result identity. Never route a result away from Output merely because it is also shown centrally.

A new result cannot discard a pinned result, replace a comparison pane, reset scrolling, or steal keyboard focus. Closing a central tab removes its presentation, not the underlying Output history or saved artifact. A failure in a new renderer retains the original readable result/fallback.

### UI-4 — No privilege or data-model expansion

Keep existing permissions, authentication and graph limits. No new MCP server, port, financial capability, background AI call, secret forwarding, memory write or database migration is justified by layout work. Do not bypass the sandbox or weaken test/allowlist policies. Never expose a secret in telemetry, graph fixtures, screenshots or failure reports.

Graph edges come from the existing graph API. Spatial proximity is not an additional relationship. Missing evidence is displayed as missing, not generated by the model. Existing graph endpoints and image/tool consumers continue to work.

### UI-5 — State has one owner

Connection, conversation, result, drawer, graph and placement state outlive view/window reconstruction. One owner assigns identities and one subscriber applies each incoming event. Reparenting views between monitors must not duplicate tool calls, polling loops, notices, speech, results or active jobs. Async responses must be rejected when their request generation, graph focus, result ID or connection generation is stale.

### UI-6 — Display changes do not lose work

The most recent user placement wins while its display remains reachable. A removed display overrides this protection only enough to bring inaccessible windows/content back into view. Never minimize a required control off-screen or silently close content on unplug. Distinguish user movement from OS movement during display reconfiguration.

### UI-7 — Passing remains meaningful

No reduced suite, new skip/xfail, relaxed assertion or raised timeout to hide a regression. Preserve the 900-second full-unit gate. Isolate order failures and fix the polluter. Preserve existing Swift language modes and deployment targets. Do not upgrade WebRTC or rewrite the transport within a UI phase.

## 4. Target layout and interaction

### 4.1 Main window

Three logical regions:

- **Voice region:** Silo, small Mortimer name, speaker/status label, current caption and microphone controls. Agent progress and important notices remain accessible here or in the preserved top bar.
- **Workspace:** active result with recent-result tabs, pin, compare, fit and explicit return-to-conversation controls. The empty state offers a quiet prompt and current-session recent results, not the old central lettering.
- **Existing sidecar:** same contents and resize/pop-out behavior. Its header alone receives the requested scrolling fix.

A contextual inspector belongs to the workspace. On a wide screen it may be a resizable subpane; on a narrow screen it opens as a sheet/overlay without changing the sidecar's selected tab or destroying the workspace state. Do not create a permanently crowded fourth column.

Conversation presentation uses a large wave only when the user has returned to conversation (amended 2026-09-12 by MORTIMER_ADAPTIVE_INTERFACE_CLOSURE_PLAN C2.5: returning to conversation keeps the active result selected in history so "Return to workspace" resumes where the user was; the large wave means no result is *presented*, not that none is selected). The first eligible result may enter workspace presentation. Once there, remain there until an explicit user action changes it. New results arriving while the user is reading are added to history with an indicator; they do not replace the current selection. No focus stealing when Mortimer begins speaking.

At compact widths, use a shallow bottom wave instead of a left rail if necessary to preserve a readable center. This is the responsive form of the same feature, not an alternate app. User can choose to keep the compact voice region even during conversation. Optional comparison uses two panes on wide windows and switchable A/B tabs when space is insufficient.

### 4.2 Sidecar header

Only the tab strip scrolls horizontally. Pop-out, close and overflow arrows occupy fixed header positions and cannot scroll out of reach. Labels have intrinsic width, one line and no text scaling/truncation. Trackpad, wheel and keyboard navigation work; arrow controls appear only when overflow exists and are disabled at their respective ends.

Selecting a tab by click, keyboard, restored preference or voice command brings the whole tab into view. Scrolling alone never selects a different tab. Preserve the current active-tab border and attention dots, with accessible selected/unread labels. Large text increases strip overflow rather than collapsing names. Verify both docked and detached drawers at the existing minimum width.

### 4.3 Voice state and color

Retain one recognizable Silo silhouette. Teal identifies user input; violet identifies Mortimer output. Labels, icons and actual transcript provide meaning independent of color. Exact palette values are proposed in §7 and require contrast verification.

Connection and microphone status are orthogonal to speaker activity:

- Offline/failed: static or very quiet neutral trace; Standby/Disconnected plus existing error/action.
- Connecting: neutral connecting animation, not a speech envelope.
- Connected, mic enabled, no activity: Listening; quiet neutral trace.
- User input activity: teal, driven by measured eligible microphone level. Label **Hearing you**. This means audio detected, not transcription accepted or identity verified.
- AI playback activity: violet, driven by measured output audio aligned with actual playout. Label **Mortimer speaking**.
- Simultaneous speech/barge-in: teal gets visual priority immediately while AI activity remains indicated by a small label until the actual interrupted/stopped event arrives. The visualizer does not trigger or suppress interruption itself.
- Thinking: a gentle violet pulse only while the existing thinking/work state says processing is active and neither voice is active. Silence alone must never trigger Thinking. Background specialist work retains its own progress indicator.
- Mic muted: user envelope is zero and Muted stays visible; AI speech can still animate violet. Wake-word armed status remains distinct from ordinary capture.

If metering is unavailable, use an honest static speaking/listening indicator with **Audio level unavailable** in its accessible detail. Never relabel the old random envelope as measured audio. This fallback is for runtime resilience; it does not count as implementing dual-speaker metering.

A short caption shows the latest recognized user text and assistant output using existing transcript ownership. If interim user frames can be consumed safely, show provisional text distinctly and replace it on finalization; never append duplicate conversation entries. If only final frames are available, show them when received. Do not fabricate an interim transcript. Speaker-gate rejection must retain its explicit notice: a teal wave is not permission to treat rejected audio as a valid request.

### 4.4 Results, sources and comparison

All current DisplayPayload fields remain supported: body, images, radar basemaps, links, commands/expected output, clipboard content and truncation notice. Unknown result kinds render with the current fallback. Do not treat commands as executable UI actions.

One app-owned workspace store provides: stable session result identity, ordered open tabs, active ID, pinned IDs, optional A/B comparison selection, inspector selection, and per-result viewport state. IDs are assigned once at message ingestion, never regenerated when a view moves. For existing stores without shared IDs, introduce an adapter/identity envelope at the router; do not maintain two independent event subscriptions.

The result modes are Summary, Sources and Connections where the underlying data supports them, plus explicit Compare selection. These are views of supplied evidence, not permission to invoke an LLM to create missing material. Opening a source is explicit. Sources retain supplied titles/URLs; excerpts, dates or citations appear only when available. Unsupported content remains a readable original result with an explanation.

Pins and open-result content are session-only in the first release. Layout preferences and result view metadata may persist without content. Explicit Save/Export is user initiated, respects existing destination/confirmation rules and reports success only after writing succeeds. Clipboard payload content is never auto-saved or persisted, including through crash/session restoration. A malformed preference record must fall back to a usable layout without losing the underlying Output history.

### 4.5 Interactive memory graph

Use the existing authenticated AdminAPI transport to GET `/api/graph/memory` with supported `focus`, `depth`, `edge_types`, and `since` parameters. Do not create an unauthenticated URLSession path. Decode the current JSON shape: node `id/type/label/attrs`; edge `from/to/type/attrs`; graph/focus/depth/legend/counts/truncated/truncated_reason. Preserve the server's default depth 2, maximum depth 4 and configured node limit (default 500); the UI may impose smaller performance limits but must disclose them and offer focused expansion.

Provide:

1. Deterministic initial layout, pan, zoom, fit, reset, stable node selection and keyboard-accessible node list.
2. Type/relationship legend and filters derived from actual graph metadata. Unknown types get a neutral style and readable label.
3. Search within loaded nodes, explicitly labeled **Search this view**, plus a separate server-focus action for broader exploration. Do not present local search as searching all memory.
4. Focus/expand neighbors and Back navigation with saved view state. Expanded nodes do not cause all existing nodes to jump or erase user placement.
5. Node/edge inspector showing available content, attributes and provenance. No fictional creation dates, confidence or causal explanation. Abbreviated graph labels are not a substitute for full details; fetch details only through an existing authorized read API when the ID maps safely, otherwise state that full detail is unavailable.
6. Two-node path tracing using the graph's existing undirected traversal semantics. Preserve directional arrows where edge data warrants them. If the loaded graph is truncated, say **No path in this loaded view**, not **These memories are unrelated**. Explain edge types, not speculative causation.
7. Collapsible display groups using actual type/prefix structure; grouping changes presentation only. Cluster counts disclose the loaded subset. Do not add graph edges or memory records.
8. Clear empty/error/disabled/truncated states, cancellable loading, explicit retry, and existing image fallback with a visible limited-interaction notice. A fallback image alone is not completion.
9. Saved view metadata (focus, filters, camera and selected IDs), validated against current graph data on restore. Never persist node text simply to remember a view.

Use a native bounded 2D renderer and off-main-thread bounded layout computation. Reuse the existing graph schema and builder; no graph database migration or third-party graph dependency is assumed. Optional 3D and continuously moving force simulations are deferred. Keep execution/capability/deliberation graph behavior intact; upgrading those interactively requires an explicit later scope.

## 5. Automatic monitor behavior

Implement one placement policy, shared by UI buttons, voice commands, restoration and screen-change handling. Use stable available display identifiers plus a validated fallback, not array index as permanent identity. Use visible work areas and backing scale; handle negative coordinates, portrait screens, mirroring, resolution/scaling changes and dock/menu-bar insets.

- **One screen:** one integrated workspace by default. Existing explicit pop-outs still work as visible, reachable windows on that screen. Do not confiscate manual pop-out capability.
- **Two screens:** default primary retains Silo, active work and the sidecar; the extra screen may present a pinned supporting result, graph or comparison. Never create an empty full-screen window just because a monitor appears. A manual drawer pop-out uses the existing controls; preserve its placement unless the screen becomes unreachable.
- **Three or more:** optional assigned roles for supporting results and existing sidecar; unused screens remain unused. Mirrored displays count as one usable area.
- **Unplug:** return all affected content to the primary workspace (or clamp explicit floating windows into its visible area). Preserve IDs, selections, drafts, scroll/zoom, graph coordinates and comparison assignment. Recovery must work even for a manually positioned window.
- **Reconnect:** restore saved roles/frames when still valid, unless the user moved/docked that content after unplugging. Newer manual intent wins. Do not launch a second renderer/subscriber for the same result merely to restore a window.
- **Lock/unlock and sleep/wake:** reconcile placement once the display topology settles; do not reset conversation or restart audio. Permission/connection errors remain visible.

The old 60/40 auxiliary split becomes the fallback for an explicitly detached display and drawer sharing one external screen, not an unconditional rule for every new topology. Persist legacy drawer width/tab preferences unchanged; new placement preferences have their own versioned key. A Reset Layout control resets only layout, never memories, results history, credentials, connection settings or model choices.

## 6. State ownership and proposed interfaces

These are planned contracts, not claims that the types already exist. Put UI presentation types in MortimerHost; transport observations in JarvisKit. Final filenames may vary only with a documented equivalent mapping.

- `AudioActivitySnapshot`: connection generation, local timestamp, normalized user/output levels, validity/availability, mic eligibility and speaking evidence. Never contains PCM, transcript or secrets. Data arriving from a prior connection is ignored; smoothing belongs to presentation, not capture.
- `VoicePresentationState`: connection/mic labels, dominant speaker, thinking, two level values and reduced-motion state. It consumes existing client truth and activity observations. It does not write back to transport state.
- `WorkspacePresentationStore`: result identity envelope and selection/viewport state from §4.4. Lifetime is app/session scope. A renderer subscribes to this store; opening a window does not subscribe to incoming RTVI again.
- `MemoryGraphStore`: typed graph response, focus/filter generation, selected node/edge, camera, pinned layout positions and request cancellation. A stale response cannot replace a newer focus.
- `AdaptiveLayoutState`: conversation/workspace mode, compact/wide layout, inspector visibility and explicit comparison mode. New results may request a mode transition; they cannot force selection away from an already open result.
- `DisplayPlacementPolicy`: pure topology/intent-to-placement decision plus a separate AppKit application step. Record whether a change is automatic or manual; prevent screen-notification loops.

No server protocol change is assumed for central results or graph rendering. If phase 0 proves an audio event extension necessary, first specify an additive, bounded, authenticated envelope and compatibility fixtures. Old clients ignore unknown events; new clients tolerate absence. Do not add a new mandatory environment variable or change required credentials.

## 7. Initial tuning values and performance gates

These are proposed design defaults/acceptance targets, **not measured baseline results**. Keep one source of truth in AppTuning or a dedicated audio-presentation tuning type. Validate with phase 0 measurements; if a target is infeasible, report the measured conflict and revise this plan explicitly. Do not silently loosen a gate.

- User teal `#2DD4BF`, AI violet `#A78BFA`; verify text contrast on the actual theme and supply labels/icons. Do not recolor existing warning/error semantics.
- Wide layout starts at 1,180 logical points; below it use compact voice placement. Initial left rail 200 points; minimum usable results width 480 points. Preserve the existing 900×600 app minimum; any smaller supported size is an additional tested case.
- Inspector initial width 300 points only when it fits; otherwise overlay. Existing drawer width limits/preferences remain authoritative.
- Tab label text initial 11 points (amended 2026-09-12 by MORTIMER_ADAPTIVE_INTERFACE_CLOSURE_PLAN C1.3: 11 pt is the Standard size Larry accepted live on 2026-09-11 with the Aa menu offering 16 and 22 pt; the baseline was 10 pt), minimum control height 32 points. Accessibility text scaling must scroll, not shrink. Existing labels remain intact.
- Layout transition 200 ms; Reduce Motion uses an immediate change or non-moving fade. No forced transition during pointer drag, text selection or keyboard editing.
- Audio observation publishes at most 30 Hz; rendering targets 60 Hz when visible and active, at most 15 Hz when idle. Suspend animation/layout work when not visible. Stale audio observations decay to zero within 300 ms. Proposed attack 40 ms, release 180 ms, using elapsed time rather than frame count. Input activation uses the existing processed speech signal plus a calibrated noise floor; no hardcoded universal microphone threshold.
- User-audio-to-visible-feedback target: p95 ≤150 ms on the deployment Mac, measured from eligible captured/processed audio to displayed change. Measure AI playout alignment too; target p95 ≤150 ms. Do not substitute server transcription completion for microphone response.
- No statistically clear >10% degradation in measured connection time, user-stop-to-first-AI-audio, or interruption-stop latency against the same-build baseline: at least 20 paired trials, same devices/network/provider settings, report distribution and variability. If provider noise makes inference inconclusive, report inconclusive and repeat under controlled conditions; do not claim a pass.
- UI fixtures: 50, 200 and 500 graph nodes, including a 500-node/2,000-edge stress case, long labels and a dense hub. Target p95 frame time ≤33 ms during graph pan/zoom and sidecar scrolling. Record hardware, dimensions and scale. Apply edge-label culling/level-of-detail before reducing functional scope; display any limit explicitly.
- No unbounded queues or caches. Respect current result-history limits; a pin-count limit of 20 avoids bypassing history bounds. Refuse a new pin with an explanation rather than evicting an existing pin. Keep pin references valid if the underlying bounded history evicts an unpinned record.
- Multi-monitor recovery target: affected controls/results reachable within 1 second after a stable topology notification, excluding OS display negotiation. The policy debounce is initially 250 ms; one timer owner only.

## 8. Phased execution and file boundaries

Each phase is a separate reviewable PR, based on the accepted preceding phase. A phase is not complete when it merely compiles. Include requirement IDs, before/after evidence, tests, remaining limits and rollback instructions in its PR. Never merge or deploy automatically.

### P0 — Baseline and audio feasibility (no production behavior change)

Inspect current source and live local customizations. Inventory all visible functions from UI-1 and record screenshots of every tab, current dialogs, the console, existing display panels and one-/multi-screen states where available. Capture current performance and voice acceptance with the same hardware/settings used for comparison.

Inspect the pinned WebRTC build's actual API/headers and existing stats callback in `DirectWebRTCTransport.swift`. Prove access to user and actual-playout activity without a competing audio engine, altered device selection or echo-cancellation change. Prefer supported existing transport observations. Stats must be measured for freshness and correspondence to the active track; an arbitrary `audioLevel` field is not proof.

A disposable prototype may establish the signal path, but is not shipped. Test speakers, built-in mic, headphones/AirPods and interruptions. If the pinned transport cannot supply safe timely levels, block **P2 only**, write the exact missing capability and a separately reviewed additive observation design. Continue independent header/results phases; never mark the full plan complete with a fake wave. Do not roll a transport rewrite into this plan.

Deliver baseline manifest, function inventory, fixture manifest, feasibility findings and measured performance record. Use synthetic/redacted data in the repository. Manual checks that require Larry remain marked pending.

### P1 — Sidecar header only

Primary files: `Drawer/DrawerView.swift`, existing `App/UICommandRouter.swift` only if visibility notifications need a narrow addition, and MortimerHost tests. Keep tab bodies and models untouched unless a proven lifecycle bug requires a separate fix.

Implement §4.2 in docked/detached states. Verify all eight tabs and voice aliases, overflow in both directions, large text, selection restoration, attention dots, fixed controls and draft/polling preservation. This phase can ship independently; it must not depend on a redesigned workspace.

### P2 — Honest dual-speaker voice feedback

Primary files: `JarvisKit/JarvisClient.swift`, the proven narrow observation seam in `DirectWebRTCTransport.swift`, `Console/VoiceWaveView.swift`, `App/VoiceState.swift`, `App/AppTuning.swift`, client and host tests. Add small observer/presentation types where needed. Touch audio coordinator/output monitor only to consume existing notifications, not redesign routing.

Implement the approved P0 signal path and §4.3. Preserve the existing Silo geometry, wake flash and device notices. Add provisional captions only with verified event support and duplicate-free transcript handling. Exercise silence, background sound, echo-only playback, quiet/loud speech, mute/PTT, AI-only speech, overlap, rapid interruption, missing/out-of-order events and reconnect. Gate on UI-2 and §7 measurements before enabling by default.

### P3 — Central workspace and restrained adaptation

Primary files: `Console/ConsoleView.swift`, `Console/OrbFieldView.swift`, `Console/TopBarView.swift`, `App/MortimerHostApp.swift`, `App/AppMessageRouter.swift`, existing display stores/renderers, and new app-owned presentation types.

Add the left voice region, compact bottom variant, persistent central selection, result tabs, pinning, contextual inspector, explicit return-to-conversation and comparison. Remove only the central decorative readout. Preserve all functionality in the P0 inventory and all existing payload types/surface behavior.

Do not introduce duplicate result stores or new tool invocation. Verify arrival during reading, older-result revisit, pin limits, explicit close/clear semantics, clipboard non-persistence, unknown payloads, resize and draft state. Verify console/window transitions while speaking do not create a new audio connection.

### P4 — Interactive memory graph

Primary files: `JarvisKit/AdminAPI.swift`, additive typed graph models, new native graph view/store under `Display/`, and existing graph/display tests. Use `GraphImageView.swift` as fallback. Prefer no backend change; any missing authorized detail read must be proposed and tested separately without changing graph-building meaning or privacy boundaries.

Implement all nine §4.5 capabilities. Tests include schema decoding, unknown node types, request cancellation, deterministic placement, partial/truncated graphs, absent provenance, keyboard selection, search scope, path semantics, focus/back restoration, grouping and realistic performance. Refresh preserves valid selection/positions; deleted IDs are removed gracefully. No image-only completion claim.

### P5 — Automatic screen adaptation

Primary files: `Placement/ScreenPlacement.swift`, `Placement/WindowPlacement.swift`, `App/MortimerHostApp.swift`, workspace/display stores and host placement tests.

Implement §5 using app-owned state and pure placement-policy tests. Preserve existing manual-placement protection on reachable screens and explicitly override it for off-screen recovery. Verify no duplicate subscription, state reset, window activation loop or hidden control. One-screen mode is first-class, not an emergency fallback. Add a manual Reset Layout action with the restricted semantics in §5.

### P6 — Integrated acceptance, release and rollback

Run the complete automated and manual matrix in §9, compare against P0, review every preservation requirement, and exercise rollback on synthetic state. Rebuild the app bundle, verify its framework resources and signature, launch it, confirm it remains running and verify backend health. A successful `open` return code is insufficient.

Keep the prior known-good app artifact and record release commit, local patches, dependency versions and layout preference version. Deployment requires explicit authorization separate from implementation. Mark code, automated checks, hardware checks and deployment as separate statuses. Update this plan with actual evidence and remaining items.

## 9. Verification and acceptance matrix

### 9.1 Automated gates

Run application code/tests in the existing disposable sandbox, using the installed profile and its prepared dependencies. Do not run candidate development against the production databases/vault or add arbitrary host test fallbacks. The trusted host controller tests remain host-side as designed. Commands below describe required checks, not permission to bypass that execution boundary.

- `swift test --package-path macos/JarvisKit`
- `swift test --package-path macos/MortimerHost`
- Full `pytest tests/unit tests/integration -q -p no:randomly`; repeat in reverse and deterministic seeded order at final integration and after any lifecycle/global-state fix.
- Full unit candidate **and trusted-baseline** gates remain within `sandbox/verify.py`'s 900-second limits. Preserve the profile's existing additional checks: backend imports, scripted evaluations, latency, knowledge base, frozen web build and native baseline/candidate checks.
- `python -m unittest discover -s sandbox/tests -v` when controller/profile/adapter code changes; do not change these merely to accommodate UI code.
- Backend-facing changes also require the existing graph API/model tests, full sidecar suite and skill validation. All GitHub-required checks must pass on the final submitted commit.
- Add focused pure tests for voice-state precedence/stale generations, tab visibility/layout, result identity/lifecycle, graph decode/layout/navigation, placement/manual-override/off-screen recovery and preference migration. Tests must assert observable behavior and preservation, not just mirror implementation formulas.

Capture the existing test list before editing. For every removed or renamed test, explain the preserved contract and replacement. No blanket replacement of suites with new assertions that only describe the new UI.

Native GUI tests are not assumed to exist: P0 must identify a supported UI-test harness or provide deterministic repeatable manual cases with recorded evidence. Pixel snapshots alone cannot prove tab navigation, draft preservation, voice quality or monitor recovery.

### 9.2 Required visual and interaction cases

Record screenshots and interaction outcomes for:

- Conversation and results layouts at 900×600, 1,280×800, 1,440×900, an ultrawide work area and a portrait external screen; Retina and non-Retina scaling when hardware supports them.
- Every sidecar tab docked and detached, both overflow ends, keyboard/voice selection, large text, attention dots and an unsaved Edit draft surviving tab/monitor changes.
- Long research text, multiple sources, images/radar, clipboard block, command output, failed/unknown payload, two pinned results and A/B comparison. A new result during reading leaves position/selection intact.
- Graph fixtures at all §7 sizes; search/focus/back, node/edge details, path tracing, truncation, filtered-out selection, unsupported schema, offline retry and fallback. Verify accessible navigation without color or pointer gestures.
- Reduce Motion, increased contrast/text size, keyboard traversal, visible focus and VoiceOver names/selected state. Do not announce every audio sample or continuously changing amplitude to assistive technology.

### 9.3 Real audio acceptance (cannot be replaced by mocks)

With the same setup before and after: built-in speakers/mic, headphones, AirPods, available alternate input/output devices; muted and PTT; quiet/loud speech; TV/background noise; AI-only playback; user interruption while AI speaks; output-device switch; disconnect/reconnect; sleep/wake; mic permission denial.

Pass requires measured timely teal/violet responses, no AI echo falsely presented as user speech in controlled echo-only trials, unchanged pitch/speed and intelligibility, preserved wake/mute/PTT and interruption behavior, no duplicate audio session and no new lost requests. User voice activation must still work during AI playback; suppressing all input while the AI speaks is a failure. Record perceived quality and timing results separately. Unavailable devices produce a pending hardware row, not a green check.

### 9.4 Real monitor acceptance

One screen; two screens; three if available; mirrored mode; manual move/resize; dock/undock; unplug the display hosting an active graph and the one hosting a draft; reconnect with changed resolution/order; close/reopen an auxiliary window; sleep/wake; reset layout.

All content remains reachable, no drafts/results/graph state vanish, no window snaps back over newer manual intent, and no conversation restarts. Simulated topology tests prove policy decisions; they do not substitute for real AppKit/hardware acceptance.

### 9.5 Evidence format and final review

Add phase evidence under `docs/acceptance/adaptive-interface/` (new, plan-specific directory). Each record names: requirement IDs, baseline/candidate commit and source fingerprint, fixture identity, hardware/OS/display topology, command or manual steps, expected/actual outcomes, timing distributions, screenshot/log references, reviewer and unresolved items. Screenshots are sanitized; no private memory text, voice recordings or credentials are committed.

Keep a one-page preservation checklist with a row for each UI-1 function from P0. Completion requires positive evidence for each row. A new screen looking attractive does not compensate for lost sidecar behavior or worse speech quality.

## 10. Rollout, rollback and stop rules

Use a versioned local preference `mortimer.interface.layoutVersion` and a developer-accessible **Use previous layout** control while the redesign is being accepted. Missing/invalid preference selects the old layout until P6 acceptance. Both presentations share the same authoritative stores; reverting layout cannot resurrect stale data or reset a draft. Audio metering must have a separate runtime-disable path that retains truthful non-metered status and working audio. Do not add environment flags unless the existing configuration pattern requires one and it is declared/tested.

Preserve existing `mortimer.drawer.*` keys. New layout metadata is additive and schema-versioned. Rollback ignores newer optional metadata, restores reachable window positions, and retains underlying data. Keep old renderer paths until the replacement has passed P6; do not leave a permanently untested duplicate UI after acceptance. Removing the temporary fallback is a separate reviewed cleanup.

Stop the affected phase and report evidence when:

- a safe audio-level source is unavailable, measured speech quality/latency regresses, or a second capture path would be needed;
- any sidecar function, draft, result or monitor recovery cannot be preserved;
- a required graph detail is absent and would otherwise be invented;
- a fix would need relaxed security/tests, new credentials, a model change, a transport rewrite or a database migration;
- the working tree contains unexplained edits or the current source no longer matches the documented contracts.

Continue independent phases when safe. Do not claim the whole plan complete while an affected phase or required hardware acceptance remains open. Do not deploy, merge, enable speaker recognition, or modify model tiers as a side effect of implementing this interface plan.

## 11. Completion checklist

- [ ] P0 baseline, live customization inventory and safe audio feasibility recorded.
- [ ] P1 all sidecar contents preserved; scrollable readable header accepted.
- [ ] P2 real user/AI audio feedback, distinct colors, truthful labels/captions and unchanged voice behavior verified.
- [ ] P3 central workspace, compact/large Silo transitions, result history/pins/comparison and additive inspector accepted.
- [ ] Central lettering removed; every functional stage indicator preserved.
- [ ] P4 fully interactive, truthful and bounded memory graph accepted.
- [ ] P5 automatic one-/multi-monitor behavior and manual placement recovery accepted.
- [ ] P6 full automated gates, accessibility, performance and real hardware matrix completed with evidence.
- [ ] Rollback exercised; no unaccounted source changes, weakened checks or undeclared limitations.
- [ ] Larry authorizes deployment; installed app/backend health and persistent app launch verified.

## 12. Handoff prompt for the implementing model

Read this entire plan and the current repository instructions before editing. Restate the phase you are implementing and the preservation contracts it touches. Inspect current code; do not trust historical comments or assume the baseline is unchanged. Work only on that phase in an isolated branch and the existing disposable sandbox. Preserve all eight sidecar tabs and their behaviors, the current audio path, result routing, memory semantics, permissions and manual window ownership. Do not substitute simulated audio for measured user/AI feedback, a static graph for the interactive requirements, or a visual mockup for working behavior. Do not rewrite unrelated architecture. Run the required baseline/candidate checks and record evidence for every acceptance item you claim complete. Fix failures without skips or weakened gates. If a required signal, capability or hardware check is unavailable, name the exact blocked requirement and continue only independent safe work. Produce a reviewable PR and updated acceptance record; do not merge or deploy without Larry's separate instruction.
