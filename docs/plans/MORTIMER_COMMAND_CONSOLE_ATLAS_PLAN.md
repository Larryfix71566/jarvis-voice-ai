# Mortimer — Command Console, Knowledge Atlas, and voice-first sharing

**Status:** SANDBOX IMPLEMENTATION COMPLETE; RELEASE ACCEPTANCE IN PROGRESS,
2026-09-18. Core protocol, stores,
Atlas composition, attachment bounds, approved inbound transfer state (including
server-issued accept, one-chunk acknowledgement pacing, session-lifetime
temporary-content memory latch and cancellation) and
feature-gated Command Console are present and sandbox-verified. Revisioned
native inventory snapshots are now exchanged after handshake and mutations,
so voice targets resolve against current IDs rather than a static placeholder.
Value-addressed detachable panels now use the shared placement owner for
virtual-screen disconnect/reconnect recovery, with synthetic topology coverage.
The native coordinator now repeats the closed action/argument validation and
rejects stale inventory revisions before touching app state; this preserves
the wire contract when a delayed or hand-built request bypasses the Python
decoder.
Voice `input/offer` messages now have a typed native decoder and tray approval
surface; exact final-transcription consent phrases emit a typed `input/consent`,
and the approval path feeds the same manifest/chunk state machine as the pointer
path. Layout version 2 is the user-directed native default; server/provider
feature gates and physical acceptance remain separate.
Native share
picker/provider journeys, physical display recovery, full voice parity and
release acceptance remain open; no completion claim is made until those gates
have evidence. (Reconciled 2026-09-22 against main `88b206f`: physical
display unplug/rehome and display reconnect restoration on one external
monitor are recorded in the committed `candidate-monitor-*-2026-09-18.md`
receipts. Still open are mirrored and three-display runs, the runbook §2
capture/tile-ID/duplicate-fetch evidence, and voice/socket reconnect. See
`docs/acceptance/command-console/STATUS.md`.)

**Architecture visibility amendment, 2026-09-18:** `docs/ARCHITECTURE.md` is
now a read-only shared reference for both sides of the product. The self-edit
author receives a bounded copy alongside `docs/REPO_MAP.md`; the admin sidecar
serves the source through `GET /api/architecture`, and the native Repo tab
renders it with its source path and digest. This is a view of the repository
document, not a second state owner, and it does not alter self-edit authority
or approval gates.
**Implementer:** Luna, using the sandbox and independent verification workflow.
**Direction:** Command Console composition, Knowledge Atlas exploration, full preservation of current functions, voice parity, and easy text/image exchange.

## 0. Scope, precedence, and verified baseline

Larry's direction is Command Console with Knowledge Atlas enhancements,
retaining voice control and adding easy text/image sharing. Luna implements
the decisions here. It must not choose another architecture, state owner,
transport, graph engine, storage system, provider or placement policy.

Sharing scope: both directions—add text/images for Mortimer to analyze and
copy/save/share selected results outward. This is the stated default following
the optional scope question. If Larry narrows it, amend before execution.
No external recipient or automatic sending is authorized by this plan.

**Closure tracking amendment, 2026-09-17:** the authoritative closure list is
[RELEASE_READINESS.md](../acceptance/adaptive-interface/RELEASE_READINESS.md)
and the consolidated
[`IMPLEMENTATION_STATUS.md`](../acceptance/IMPLEMENTATION_STATUS.md),
with the remaining physical and provider checks sequenced in
[`ACCEPTANCE_RUNBOOK.md`](../acceptance/ACCEPTANCE_RUNBOOK.md),
including new UI2-01–UI2-20 gates and all previous open requirements. UI2-01
holds CC6 inbound analysis pending a decision on the conflict between §6.4's
conversation-wide memory pause and seamless automated memory. The pause below
is a draft proposal, not an accepted locked decision; amend the affected
contracts, privacy text and tests together before CC6. Luna must not choose an
alternative. Unaffected CC0–CC5 work can proceed under the existing sequence.
This specific hold takes precedence over later statements that all privacy
decisions are fixed. Adding these gates closes no existing requirement.

**Reconciled 2026-09-22 against main `88b206f`:**

- **UI2-01 hold is resolved.** The paragraph above is kept for history, but
  the hold no longer applies. `RELEASE_READINESS.md` ticks UI2-01 with a
  release decision of session-only temporary-content mode:
  - staging is local and does not pause ordinary memory;
  - an approved manifest arms the latch until reconnect;
  - imported content and derived answers stay ephemeral;
  - the user sees the pause notice.

  The boundary is covered by
  `tests/unit/test_shared_content.py::test_staging_does_not_pause_memory_but_approved_manifest_does`.
  §6.4's pause is therefore the accepted behaviour, limited to approved
  manifests, and not a draft proposal.
- **Gate range.** The gates now run beyond UI2-20. UI2-21 and UI2-22 are
  tracked in `docs/acceptance/command-console/STATUS.md`. UI2-21 is used for
  two different items: Developer-run grouping in the Command Console status,
  and the atom-style voice display in `RELEASE_READINESS.md`. Cite each by
  title.

This extends MORTIMER_ADAPTIVE_INTERFACE_PLAN.md and its closure plan. For
layout version 2 it supersedes the left voice rail, large central conversation
wave and single supporting-content slot. Versions 0 and 1 remain available.
Existing C8, audio, security, daily-driver and automated-memory gates stay open
until separately evidenced. Historical memory recovery does not implement Atlas.

Source inspected: release-review tree, Git b224c84 (a release-branch commit,
not on `main`; its content is on `main` in `88b206f`), September 17. Pre-existing
edits to C6-remaining.md and the adaptive-interface plan must be preserved.
The deployment receipt names main 94a5641 and candidate fingerprint
b57cd348b0d0c30359a6713f919732fe3fabef373a8ffe8be208c75fdc382fe8.
The installed checkout still reports Git HEAD 2ccf66c despite deployed file
changes. Do not infer loaded code from its HEAD. This is a source-based design,
not a new runtime audit. Freeze actual source before beginning; a changed seam
requires a plan amendment, not an implementer workaround.

Verified anchors (repository-relative, line numbers from the inspected tree):

- macos/MortimerHost/Sources/MortimerHost/App/MortimerHostApp.swift:32 owns
  layoutVersion and app-scoped stores; :89 declares the fixed display scene.
- Stores/WorkspaceStore.swift:7 defines stable session result UUIDs; :28 owns
  results, pins, active/comparison selection and graph stores; :56 preserves
  reading on incoming results; :19 supports one result or graph on the display.
- App/AppMessageRouter.swift:83 assigns result identity once and feeds existing
  Output/display histories. There must not be a second ingestion listener.
- Console/AdaptiveStageView.swift:37 chooses conversation/rail/bottom; :73 is
  the existing compact bottom presentation, not the proposed console.
- App/UICommandRouter.swift owns DrawerState and legacy dispatch;
  jarvis/bot/ui_control.py:25 only enumerates the older console controls.
- macos/JarvisKit/Sources/JarvisKit/AppMessage.swift:194 decodes action/tab;
  ClientMessage.swift only supports voice/set and ui/noop outbound messages.
- jarvis/bot/pipeline.py:1301–1364 receives messages through both transports;
  :487 silently injects clipboard text. This is not image-upload support.
- Display/WorkspaceExportCoordinator.swift:15 uses a text NSSavePanel;
  Display/WorkspaceResultDetails.swift:21 excludes clipboard content from export.
- Display/MemoryGraphStore.swift:187–268 owns selection, filters, paths, camera,
  node placement and reset. Reuse those operations.
- Placement/WindowLookup.swift:17 limits HostWindowKind to three fixed roles;
  ScreenPlacement is the topology observer and DisplayPlacementPolicy preserves
  explicit manual positioning and unplug/reconnect recovery.
- mcp_servers/mcp_screen/logic.py:274/:314 resolve the configured vision profile
  and client. Image attachment analysis must not capture a screen as a shortcut.

Anchor refresh (reconciled 2026-09-22 against main `88b206f`). The list above
is the pre-implementation baseline and has drifted. `b224c84` is a
release-branch commit that is not on `main`; its content reached `main` in
the #80 squash `88b206f`. Several baseline descriptions are now superseded by
this plan's own work. For example, `ClientMessage.swift` now also encodes the
console/inventory and input transfer messages, and the default
`layoutVersion` is 2. Current locations that were checked:

- App/MortimerHostApp.swift:41 is the `@AppStorage` `layoutVersion` (default
  2). :111 is the fixed `Window("Mortimer Display", id: "display")` scene.
- Stores/WorkspaceStore.swift:10–11 is `WorkspaceResult`'s stable UUID. :22 is
  `SupportingDisplayContent` (one result or the memory graph). :36–49 is
  `WorkspaceStore`, which owns results, active/comparison selection, pins and
  the memory-graph store. :167 is `receive(_:)`.
- App/AppMessageRouter.swift:173 creates the `WorkspaceResult` identity.
- Console/AdaptiveStageView.swift:51–56 is `mode(...)`, which chooses
  conversation/rail/bottom. :109 is the `.bottom` presentation.
- App/UICommandRouter.swift:10 is `DrawerState`. jarvis/bot/ui_control.py:25
  is `UI_ACTIONS`.
- macos/JarvisKit/Sources/JarvisKit/AppMessage.swift:226 is `UICommand`
  (action/tab).
- jarvis/bot/pipeline.py:561 is `_inject_silent_clipboard`.
- Display/WorkspaceExportCoordinator.swift:60 creates the `NSSavePanel`.
  Display/WorkspaceResultDetails.swift:43 omits clipboard content from
  export.
- Placement/WindowLookup.swift:18 is `HostWindowKind` (console, display,
  drawer).
- mcp_servers/mcp_screen/logic.py:265 is `_resolve_vision_profile`. :304 is
  `_default_vision_client`.

The pipeline.py:1301–1364 message-receive range and the
MemoryGraphStore.swift:187–268 range were not re-verified.

Short App/, Stores/, Console/, Display/, Drawer/, Placement/ paths below are
under macos/MortimerHost/Sources/MortimerHost/. Other paths are repo-relative.

Non-goals: new memory inference, new relationship edges, 3D physics, audio-engine
changes, new cloud accounts, web redesign, general file management, automatic
outbound messages or changes to existing self-edit/domain approval behavior.
The concept illustration's invented data and simplified controls are not specs.

## 1. Locked architecture and ownership

CC1. Keep SwiftUI/AppKit and existing dependencies. No webview shell, graph DB,
new daemon, second audio engine or alternative model registry.

CC2. Keep one app-owned JarvisClient, AppMessageRouter, UICommandRouter,
DrawerModels, WorkspaceStore, ConversationStore and agent store. Moving views
does not trigger tools, replace drafts or create duplicate network polling.
AppMessageRouter owns display ingestion; UICommandRouter owns UI commands;
JarvisClient retains mic/wake command ownership.

CC3. Add one app-owned ConsoleActionCoordinator. Every new pointer, keyboard
and voice action calls execute(request) through it. It delegates to existing
store setters. Existing workspace/graph buttons also use this coordinator;
legacy ui_control behavior remains compatible. No separate voice action logic.

CC4. Extend WorkspaceStore with presentation-only AtlasStore and PanelStore
children referring to existing IDs. No copying of results, graph payloads,
drafts or transcript content. ShareCoordinator and AttachmentStore are separate
app-scoped owners with bounded lifetimes. None is recreated per window.

CC5. Add ConsoleInteractionSession in Python, created once in run_session and
passed into build_pipeline. It owns handshake, pending requests and transient
input transfers. Use the active transport's app-message channel; no global
client registry or new unauthenticated HTTP upload route.

CC6. New Supervisor-only tools console_action and shared_content consume that
session. Retain ui_control. Existing commit/delete/self-edit domain operations
keep their own tools and confirmation gates. Presentation authority does not
grant repository, credential or memory-write authority.

CC7. No database migration. Only layout metadata goes to versioned UserDefaults.
Result contents, attachment bytes, clipboard text, Atlas cards and share previews
are session-only. No clipboard/screen watcher and no automatic image retention.

CC8. Existing layoutVersion key: previous=0, adaptive=1, commandConsole=2.
Unknown values fall back to 1. Command Console (2) is the shipped default, with
a one-time migration from the prior adaptive default and an explicit Debug-menu
rollback path. Version 2 gets new theme tokens without changing legacy AppTheme
values.

## 2. Exact visual and responsive specification

Top: restrained header with Mortimer name, Connect/Disconnect and honest state,
clock/weather, voice picker, sidecar, display and appearance controls. Errors
and pending confirmations stay in a visible notice row.

Middle: central work surface and complete right sidecar. Central view choices
are Results / Atlas / Memory, followed by stable result tabs and relevant
Sources, Pin, Compare, Move, Copy and Share actions. The graph inspector belongs
inside the work surface, never replaces a sidecar tab.

Bottom: persistent voice console across the entire window. Left: caption and
speaker label. Center: Silo. Right: existing mic/PTT, wake, sound, device/reconnect
and transcript controls. A labeled agent-activity strip opens existing Runs
details. No decorative orbiting satellites. Device notices, rejection notices,
pending drafts, ambient and machine information all remain accessible.

Attachment tray opens above the console, below the work surface, showing text/
image previews, remove, question entry and Ask Mortimer. It never overlays mic
controls or confirmation dialogs.

Single metric owner: CommandConsoleMetrics in AppTuning.swift. AppKit-point
defaults: header min-height 48, outer padding 16, gap 12, control min-height 32,
corner radius 12, readable text width cap 880. System fonts: body 15, headings
24 semibold, labels 13, metadata 12. Apply the existing font-size preference
and bounds. Wrap instead of shrinking text. Captions show 3 lines then scroll.

Width >=1200: one-row header, console min-height 120, Silo ideal width 260/min
180. Work-surface inspector width 280 only if reader retains >=480 points.
Width 900–1199: two-row header, console min-height 168 with caption above
wave/controls; inspector becomes an explicit sheet. Comparison uses two panes
only if the work surface itself is >=960 wide, otherwise existing A/B selection.

Supported minimum remains 900x600. Larger fonts grow rows and scroll content;
unsupported smaller windows use the compact arrangement with scroll fallback.
Never silently hide a drawer or reduce text. Preserve its width clamp and saved
preference. A reader <480 uses one column and sheet inspector. Full-screen and
window resize remain native. Reserve notices outside the scrolling document.

CommandConsoleTheme in AppTheme.swift: bg #10161D, content #18212B, secondary
#141C24, text #EDF2F6, secondaryText #B4C0CD, separator #344352, selection #B39DFF,
user #55D6C2, assistant #B99AFF, warning #FFD089, error #FF8C96. Text >=4.5:1 and
meaningful non-text/focus indicators >=3:1 against their actual backgrounds.
If a pairing fails, use white on #10161D for that pairing and record it. Increase
Contrast uses opaque panels and visible borders; Reduce Transparency removes
blur. State uses words/icons as well as color. Never hardcode colors in views.

Silo preserves current geometry, tuning, measured audio, barge-in priority,
unavailable-meter fallback and <=30Hz meter cap. Optional glow stays within the
wave, never behind text. No fake speech animation. Keep wave tuning accessible.
Transitions are 180ms, disabled during drag/resize/text editing or Reduce Motion.
Speech does not resize the workspace or change its selection. Conversation mode
keeps the bottom console and shows current session results/task state, or a
simple prompt when empty. No invented summaries, agent work or success counts.

Preserve all eight sidecar keys/order, font preferences, scrolling labels,
fixed controls, attention dots and action drafts. Header Status disclosure holds
ambient/system information when compact; all its contents remain voice-queryable.

## 3. Atlas interactions and content lifetime

Atlas is an alternate presentation of session results. Results/Atlas/Memory
share selection, pins, comparison and graph state. Switching views preserves
reading, graph camera, inspector, drafts and pending attachments.

**Atlas source-coverage amendment (2026-09-18, UI2-22):** the Atlas retains
`WorkspaceStore.results` as its authoritative result surface and now adds a
bounded, read-only context projection from the authenticated AdminAPI:
memory overview/facts, the checked-in architecture reference and digest,
current plan status, recent run lineage, and the shared memory-graph summary.
`AtlasStore` assigns stable namespaced identities and merges context refreshes
without resetting result selection, manual placement, or groups. The focused
`KnowledgeAtlasTests` suite covers the merge and identity guarantees. Physical
refresh/error, accessibility, and multi-display receipts remain release gates;
the Atlas implementation itself is complete.

Cards use WorkspaceResult.id. Default logical board placement: ingestion order,
3 columns, width 280, height 184, gap 24, origin (24,24). Show supplied title/type,
4 preview lines and source count when supplied. No automatic summary or extra
thumbnail fetch. New cards occupy the next free slot; existing cards stay put.
Drag bounds are finite coordinates 0...100000. Arrange explicitly resets to
default grid. Fit frames visible cards. Zoom 0.25...2.0; steps multiply/divide
by 1.25; pan steps move 25% of viewport. Voice moves a card relative to another
or to an exact grid row/column, so arranging is not pointer-only.

Groups are explicit presentation groups, never semantic edges: session UUID,
name <=80 characters, maximum 12, at most one group per card. Create/rename/
assign/remove/dissolve all have voice actions. Dissolving keeps cards. No auto
classification; neutral boundaries. Card/group data is not persisted on disk.

Select card: at work-surface width >=960 open board 55% / reader 45%; otherwise
use full reader with Back to Atlas. Compare reuses activeID/comparisonID and A/B.
Reading never requires zooming into small card text.

Memory view reuses current query API, caps, layout and graph stores. Preserve
search-this-view versus server focus, depth, filters, Back, fit/reset, paths,
provenance, original-image fallback, error/truncated states and keyboard list.
Default labels: selected node, up to 20 immediate neighbors sorted by ID, and
loaded group labels; maximum 40 simultaneous labels. Others show on hover/focus.
The accessible full node list is not truncated by this visual label budget.
No invented edges, confidence, dates or causal explanations. Other graph types
retain current rendering behavior. Connections exists only where the payload
maps to a supported graph source. No path in truncated data says "No path in
this loaded view." No speculative links between research cards and memories.

View metadata survives moves within the session. Across relaunch restore layout
preferences only; no missing result UUID placeholders or restored attachment
bytes. Existing graph metadata format remains compatible. Existing pin/history
limits remain; detached/compared/shared items are protected from eviction until
their host or operation releases them.

## 4. Voice and pointer action contract

### 4.1 Wire format, lifecycle and acknowledgement

Preserve legacy ui/action/tab, voice/set and ui/noop. New types are additive.
Use ConsoleProtocol.swift in JarvisKit and console_protocol.py in Python.
All UUIDs below use lowercase canonical representation; integers must be finite
and within specified bounds; reject unknown fields. No arbitrary selector,
executable expression, URL, shell command or file path can be an action argument.

Handshake: server emits console/hello with version:1, session_id and generation
(new connection UUID) after pipeline readiness. Client replies console/ready
with the same fields, actions:[IDs], input_types:[text/plain,image/png,image/jpeg].
This registers supported operations, not user authority to perform them. New
tools refuse cleanly without handshake; never send them to old/web clients.

Request: console/request with version, session_id, generation, request_id UUID,
revision integer, action string, target?, secondary_target?, args object.
Target: kind=result|panel|node|edge|group|attachment|source|image|graph|comparison|
atlas|transcript|preview and id string. Atlas/transcript IDs are the literals
"atlas"/"transcript"; comparison ID is "comparison" and requires both current
result IDs. Graph ID is "memory" or the owning result UUID. Preview ID is the
share transaction UUID. Node/edge operations include graph_id in args; omit it
only when exactly one graph has explicit focus. Never resolve by hover.
Targets come from current inventory. Sources/images use resultUUID:index;
edges use graphRevision:index. No mouse-position or global last-window target.

Response: console/result with version, session_id, generation, request_id,
status=ok|noop|needs_choice|pending_user|unsupported|error, code string,
summary <=240 characters, optional choices:[{id,label}] <=10 and data object.
Total <=32KiB. Summaries are fixed templates with bounded escaped labels. Data
is inventory only, not body/clipboard text or image bytes.

Backend waits for acknowledgement for 5 seconds. Failure/timeout must not
become "done"; timeout says "I couldn't confirm that action." Ignore mismatched
session/generation, unsolicited IDs and late responses. Client deduplicates the
last 128 request IDs for 5 minutes and returns cached responses without repeating
side effects. Disconnect cancels futures and expires transfers. Do not retry
paste/save/share/move automatically. Successful acknowledgement follows the
actual write, applied state or registered/placed window—not request receipt.

OS picker opening returns pending_user, "The picker is open; choose a destination."
Actual completion emits console/completion using the same identifiers and result
shape; schedule one notice through existing speech-idle notification behavior.
Never hold an LLM function open while waiting for a person to use a dialog.
Successful presentation changes can remain silent per existing ui_control policy;
copy/save completion and failures receive concise visible and spoken feedback.

Inventory returns revision, mode, active_result_id, focused_panel_id,
results:[{id,title,index,pinned,can_connections}],
panels:[{id,kind,title,screen_id}], screens:[{id,label,index,primary}],
selection:{graph_id?,node_id?,edge_id?,group_id?},
attachments:[{id,label,mime,state}], available_actions. Limit each result inventory
page to 100 entries, panels to 6, usable display areas to 8, attachments to 4.
The result limit above is a protocol ceiling, not the existing history size:
AppTuning.swift:44 is 20 ordinary results; WorkspaceStore.swift:167 additionally
protects pins/active panes. Preserve those product limits. Node/source/group
inventory uses cursor with page limit<=50. Titles <=120 chars.
Never include full graph data, local paths or raw content. Inventory revision
changes for selection/identity/topology, not audio ticks. A stale command returns
stale_selection; request new inventory, don't substitute another target.

console_action schema: action closed enum below; target/secondary_target optional
string aliases; args action-specific object. Backend resolves aliases via fresh
client inventory; client independently validates resolved IDs/revision. At most
one refresh/re-resolution for a read/navigation command. No automatic re-resolution
for copy/save/share/delete/transfer; request explicit target if stale.

"This" is explicitly focused work content, never the latest arriving item.
"Latest" is last ingestion sequence. Ordinals use visible order. Titles match
case-insensitively after whitespace trimming; duplicate titles return choices.
No fuzzy match for attachment/display/share targets. "Other screen" resolves
only with exactly one non-primary screen; otherwise ask with display labels.
Primary means the display holding the console. User text/selection overrides
hover; hovering never changes voice target. Untrusted titles are data, not commands.

### 4.2 Complete v2 action catalog

Each row defines accepted arguments; unknown/extraneous args are rejected. New
buttons cannot be added without a corresponding catalog operation and parity test.
Luna must not omit operations because the older ui_control schema lacks them.

- inventory/help: scope=all|results|panels|screens|nodes|sources|groups|attachments,
  optional cursor. Help returns labels and example phrases, not internal IDs.
- view_set: mode=conversation|results|atlas|memory.
- result_select/close/pin/unpin: result target. Close never deletes Output history.
- result_next/previous: none; reaching an end returns noop, does not wrap.
- result_mode: result and mode=summary|sources|connections; unsupported returns
  an honest error and does not synthesize missing material.
- compare_set: two distinct results; compare_end: none; compare_side: A|B.
- content_scroll: panel and direction=up|down|top|bottom; up/down move 80% viewport.
- source_select/open: source target; source_inspector: open Bool and result;
  image_select: image target. Open validates
  existing HTTP(S) rules; do not claim content was read merely by opening a URL.
- atlas_fit/arrange: none; atlas_zoom: in|out|reset; atlas_pan: four directions;
  atlas_move: card and secondary card with relation=before|after|left|right, OR
  row/column integers 1...100, never both. Before/after mean grid previous/next
  free slot; left/right mean one card-width+gap adjacent, shifted down until free.
- group_create: name; group_rename: group/name; group_assign: result/group;
  group_remove_card: result; group_dissolve: group. These never delete content.
- graph_search: query<=200 chars, loaded nodes only; graph_focus: node/depth
  1...4 through existing API; graph_select: node; graph_select_edge: edge;
  graph_back/fit/reset/retry: none; graph_zoom: in|out|reset; graph_pan: direction.
- graph_filter: kind=node|edge, existing type, visible Bool; graph_group: existing
  type/collapsed Bool; graph_path: two node IDs; graph_path_clear: none;
  graph_inspector: open Bool; graph_original: enabled Bool; graph_center: node;
  graph_move_node: node/x/y finite graph coordinates within current layout bounds.
- panel_detach/move: content target/screen ID; panel_return/close/focus: panel;
  panel_fullscreen: panel/enabled Bool; panels_return_all: none. Auxiliary close
  returns content, never deletes it. Mirror/copy-panel is deliberately not an action.
- sidecar_width: points 300...720 subject to current clamp; sidecar_text:
  existing font-size preset; sidecar_scroll_tabs: left|right. Retain all legacy
  drawer/tab/popout/popin aliases and current domain-specific voice operations.
- appearance_set: layout=0|1|2; console_caption: expanded Bool; console_status:
  open Bool; wave_tuning_open: none; wave_tuning_set: existing tuning key/value
  through existing bounds validator; reset_layout: none, layout metadata only.
- share_preview: result|image|graph|comparison|attachment target, format=text|png,
  optional scope=whole|section|paragraph (text only), ordinal for latter two;
  share_copy/save/picker/cancel: preview transaction ID; share_source: source ID.
- input_paste: format=text|image|auto; input_choose: text|image; input_remove:
  attachment; input_clear/preview: none; input_question: text<=2000 chars;
  input_cancel: request ID. Paste stages locally; it does not send to a model.
- input_new_conversation: confirmed Bool; false previews the consequence,
  true clears shared material and disconnects/reconnects after the user's request.
- export_folder_choose/clear: none; choose opens the native folder selector,
  clear removes only the bookmark, never files in that folder.

shared_content schema: attachment_ids (1...4 inventory IDs), question (1...2000
chars). "Use these images and explain the difference" resolves the exact tray
selection. Ask Mortimer button calls the same server service with its question.
It never implicitly reads clipboard or captures screens. Existing screen-vision
commands remain separate and retain their existing permissions and kill switch.

Mic-off remains off: voice control requires the current mic, PTT or enabled wake
path. No hidden listener. OS permission prompts, recipient selection and OS file
choosers remain OS-owned. Voice can prepare/copy, launch/cancel a picker, and save
to a previously selected export folder. Do not claim full voice automation of
another app or macOS security dialogs. Every Mortimer-owned new operation is
voice-accessible; external sending is still the user's action.

## 5. Multiple displays and detachable content

Keep console, legacy display and whole sidecar scenes. Add ONE value-addressed
WindowGroup named content-panel with PanelID UUID as value, maximum 6 simultaneous
new content panels. A nil/restored value whose content no longer exists shows
"This session's content is no longer available" plus Close, never loads a file.

PanelContent is a closed enum: result(UUID), sources(UUID), comparison(UUID,UUID),
memoryGraph(graphKey), atlas, transcript. graphKey is either global memory graph
or the existing result UUID's graph store. No detachable individual sidecar tabs
in this release; the entire sidecar can move, and transcript can have a read-only
viewer backed by ConversationStore. Explicitly do not clone Repo/Edit/Memory models.

PanelRecord: id UUID, content PanelContent, origin view reference, assigned screen
ID, frame, manualRevision, optional recovery, focused Bool. PanelStore owns the
records. View state remains in its existing owner. There is at most one content
host per exact PanelContent. Repeating detach focuses/moves its existing panel.
Result+sources may coexist because they are different views, using the same
WorkspaceResultPresentation. Graph has exactly one active renderer; no second
physics/layout computation or fetch subscriber. A moved region shows a small
"On [display] — Return here" locator at its previous location.

**Multi-window acceptance amendment, 2026-09-18 (UI2-19):** the two-screen
candidate exercise exposed a gap between this rule and the current renderer:
the same memory graph was visible in the main work surface and on the external
display, while repeated display requests accumulated several graph panels.
The external stage is therefore a presentation target, not a second history.
An exact graph/result identity has one authoritative renderer and one active
fetch/subscription owner. Assigning it to a supporting display replaces or
focuses that identity's existing external panel and leaves a compact
"On [display] — Return here" locator at the source surface. Additional
simultaneous panels require an explicit pin action; repeated voice or pointer
requests must never create another equivalent panel. With no supporting
display, the main surface remains the renderer. CC4/CC7 acceptance must record
one- and two-display runs, repeated graph requests, return-to-main, bounded
visible panel count, and duplicate-fetch/subscription evidence before UI2-19
or the related UI2-06/UI2-09 gates can close.

The sandbox renderer now applies the first part of this contract: exact
payload identities are reused and focused, while opening another copy is a
separate explicit pin action. The remaining gate is runtime evidence that the
main surface yields to the selected external owner and that repeated voice or
pointer requests produce no duplicate fetch/subscription work.

**External-display content amendment, 2026-09-18 (UI2-20):** the recent
two-screen exercise also showed a presentation-policy problem: the external
screen contained the graph and several other windows that were not useful for
the current task, and the window log recorded repeated `re-added` display
entries during a single attach cycle. The external screen is a presentation
stage, not a mirror of the work surface. Its default budget is a single outer
stage containing one to four active research/graph/result tiles: one result
uses the full stage, two results split the stage, and three or four use a
bounded adaptive grid. The console, complete sidecar, transient status panels
and duplicate graph windows remain on the primary surface unless the user
explicitly moves or pins them. Repeated requests replace or focus the active
identity; explicit pin is the only path to additional overflow panels. The
stage never opens a nested information window inside another stage window.
The acceptance receipt must record the visible-panel count, tile identities,
console/display screen roles, attach/reconnect transitions and the absence of
duplicate fetch/subscription work on one, two and three displays. This gate is
separate from UI2-19's exact-identity deduplication and is required before
UI2-06/UI2-09 can close.

The sandbox `DisplayWindowStore` now enforces the bounded four-result
unpinned-stage budget while the supporting scene is open, orders the focused
result first, and preserves explicit pinned overflow. The supporting view
renders one outer stage with adaptive tiles inside a bounded scrolling
viewport; tiled cards use finite heights so a three- or four-result stage
cannot collapse into negative AppKit geometry. It does not fan out nested
windows. The remaining evidence is physical: stable console/display roles,
reconnect recovery, and confirmation that no transient or sidecar window is
fanned out on the external screen.

The router now asks the display owner for an exact presented workspace
identity before creating a new `WorkspaceResult`. A repeated window payload
therefore reuses both the external renderer and its source history row; a new
section from the same Developer `run_id` still creates its own workspace row
and appends to the run's single outer panel. If an older owner was evicted,
the next delivery repairs the panel's workspace reference rather than leaving
a stale return locator.

**Live candidate note (2026-09-18):** the rebuilt candidate rendered one
bounded graph stage with the `SUPPORTING DISPLAY` header and no nested window
fan-out. Closing the display returned the graph to the main surface, but the
client reported a socket error during the same exercise. Reconnect-after-close
is therefore an observed acceptance defect, not a presumed pass; its receipt
is `docs/acceptance/command-console/receipts/candidate-supporting-stage-live-2026-09-18.md`.
The follow-up external graph receipt is
`docs/acceptance/command-console/receipts/candidate-memory-graph-external-2026-09-18.md`.

**Developer-run presentation amendment, 2026-09-18:** a self-edit request can
read several files and emit several window-routed payloads. Those payloads are
one work product, so the native client carries the backend `run_id` and groups
window-routed Developer results from the same run into one outer display panel,
with readable appended sections. Different runs remain separate; ordinary
research, weather, radar, graph, and explicit pinned copies retain their own
identity and controls. Every supporting-stage tile uses `.mortimerGlass` with
the current Liquid Glass flag, including the single-result stage, multi-result
tiles, and the legacy in-window fallback. Physical acceptance must verify the
grouped self-edit panel and both glass-on and glass-off rendering.

**Persistent-context amendment, 2026-09-18:** the compact command-console
presentation keeps the clock/date block pinned at the top of the voice rail.
It is ambient context rather than conversation history, so it must not move
below the agent/status stack as notices or session content grow. The full
stage keeps the same top-left ambient placement; only the compact rail's
ordering changes.

Extend placement keys, not a second placement service: introduce HostWindowID
with legacy(HostWindowKind) or content(UUID); its stable serialized keys are
console/display/drawer/content:<UUID>. Keep HostWindowKind/findHostWindow wrappers
for legacy callers/tests. Add a registry of live windows in ScreenPlacement,
registered by the existing WindowIdentifierSetter on creation/removal. New
windows use exact identity; do not title-match result titles. New placement
policy dictionaries key on HostWindowID; role defaults remain legacy-compatible.

ScreenPlacement remains the sole topology observer, debounce owner (250ms), frame
adapter and manual-intent recorder. Generalize DisplayPlacementPolicy's pure
algorithm to dynamic keys, retaining all old policy tests. Store v2 metadata
under mortimer.interface.placement.v2; read v1 for legacy roles if no v2 exists.
Do not overwrite v1; version-1 rollback retains its saved arrangement.

Display labels: physical localized name plus stable disambiguating index;
primary first, others sorted by existing stable display ID. Identical mirrored
work areas count once. A display index is a temporary voice/menu label, never
a persisted identity. Offer Move to display menu using these same labels.

Move action: validate current content and screen; register panel; request window
open; await registration <=2s; place via ScreenPlacement; acknowledge after its
reachable frame is verified. Failure returns error and leaves source content
available. Default frame is centered at 90% of destination visibleFrame, min
600x400 or the available area if smaller. Initial slots cascade by 24 points
clamped to visibleFrame. Do not rearrange other user windows or force full screen.

Connecting a monitor does not create or move panels without a saved recovery
record or explicit user command. Unplug clamps existing detached windows onto
the console's display; no content destruction/recreation. Remember prior screen
and frame. Reconnect restores them unless a newer user move, Return or Close
changed manualRevision. Sleep/unlock use the same policy without audio restart.
Return all closes content panels and docks their content; sidecar docks through
its existing owner. It does not clear result histories, drafts, pins or clipboard.

Explicit floating windows on one monitor remain supported. At 6 content panels
return "Return a panel before opening another" with choices; do not evict any.
Closing a source result referenced by a panel first returns that panel, then
closes the workspace tab; Output history remains. Native red-window-close follows
the same return semantics. No duplicate fetch, job, transcript or notification.

## 6. Text and image exchange

### 6.1 Outward: copy, save, system share

One ShareCoordinator serves menus, toolbar, keyboard and voice. Its state machine:
idle -> preparing -> previewReady -> copying|saving|pickerOpen -> completed|
cancelled|failed. Only one active transaction; a second asks to cancel/finish the
first. Freeze selected content, its revision and its title at preview creation;
later result arrivals or monitor moves cannot change what will be shared.

SharePreview has transaction UUID, source IDs/revisions, format, safe title,
in-memory text or PNG bytes, redaction notices and preview dimensions. No bearer
tokens, internal URLs with secrets, other windows, other tabs or clipboard payload
fields enter it. Reuse WorkspaceResultExport.text for text and supplied source
URLs. Preserve existing exclusion of DisplayPayload.content. Text selection
copy still works; voice can choose whole result, section or paragraph ordinal.
Section boundaries are rendered headings; paragraphs are nonempty rendered text
blocks; do not use a model to choose content. Unknown ordinals produce choices.

Format matrix: result and comparison support text/PNG; graph supports text/PNG;
selected image supports PNG; staged text supports text; staged image supports
PNG. Unsupported combinations return unsupported_format with allowed choices.
Graph text exports loaded counts/truncation, then visible node IDs/labels/types
sorted by ID and visible edges sorted by from/to/type, never hidden store data.
Comparison text exports the two supplied results under A/B headings. share_source
prepares its supplied HTTP(S) URL as a text preview, never fetches the page.
Remove URL userinfo and fragments, omit credential/token query parameters
(token, access_token, api_key, key, signature, credential, authorization,
X-Amz-* case-insensitively), and flag altered links in the preview. Never copy
auth headers. This is field exclusion, not a promise to detect arbitrary secrets
that a user intentionally includes in ordinary text or an image.

PNG uses a dedicated SwiftUI content renderer with ImageRenderer: supplied
result title/body/links/images, graph viewport, selected image, or frozen A/B
comparison. Render only the chosen surface, not a screen capture. Include source
attribution/truncation/footer when applicable. Default width 1600 pixels,
max edge 4096, max area 16 megapixels; oversized document previews show the
bounded visible viewport and "Visible portion only; use text for full content."
Graph export states loaded node/edge counts and truncation. No voice controls,
sidecar, active notifications or private adjacent content in exported pixels.

Render from successfully loaded, decoded assets only. Missing assets show
"Image unavailable" in preview; share requires explicit acceptance of that
visible preview. Do not issue hidden image fetches, use screen capture, fabricate
a basemap, or claim export contains an original-resolution asset when it is a
render. Reuse authenticated JarvisHTTP/AdminAPI for existing protected graph
images; never attach its token to third-party image URLs. Add app-owned
SharedMediaStore for decoded presentation assets so render and export see the
same image. Cache <=64MiB, eviction excludes active render/share references;
memory warning purges unused entries. No disk cache for private inputs.

Copy writes plain UTF-8 text or PNG to NSPasteboard after successful preparation;
read-back type/byte-size validation precedes "Copied text/image." Copy never
arms/wipes the old clipboard handoff feature or executes copied commands.
Explicit copy requested by voice may prepare and copy in one command, with a
visible preview and cancel during preparation; copying itself needs no extra
confirmation. A general "share this" opens preview with Text/Image choices.

Save defaults to existing NSSavePanel for .txt/.png. Add an optional user-selected
export-folder bookmark using native directory picker; once set, "Save this image"
can save there by voice. No model-specified filesystem path. Filename is
Mortimer-YYYYMMDD-HHMMSS-<first8TransactionID>.txt|png, with numeric suffix for any
collision. Never overwrite silently. Resolve security-scoped access, write
atomically on utility executor, close access in defer; failures never say saved.
No default silent write to Desktop, repository or knowledge vault.

Keep existing keyboard shortcuts. New controls use native tab/focus/menu
activation; Cmd-C in a text field copies its selection through the normal
responder chain. Do not intercept it globally or introduce conflicting shortcuts.

System Share uses NSSharingServicePicker with text or NSImage from the preview.
The user chooses destination/recipient and final send in macOS/receiving app.
Report "Share sheet opened"; only report a service completion if its delegate
confirms it, never claim delivery/receipt. No email/Slack integration or new
account permissions in this release. One-step Copy remains the universally
available way to hand selected information to another app.

Share controls also permit explicit selection of a staged attachment; that is
sharing user-selected content, not adding every attachment to ordinary export.
Transactions expire after 10 minutes or cancel; bytes clear on completion except
the OS clipboard/user-saved artifact, whose lifecycle belongs to the user.

### 6.2 Inward: stage first, analyze on request

Entry points: drag/drop into the tray; Paste into the tray; Choose text/image;
voice "Paste my clipboard"; optional typed question. All converge on
AttachmentStore.stage. Nothing reads clipboard on launch, reconnect or selection.
auto paste chooses an image if both image and plain-text representations exist,
otherwise text. Existing explicitly armed read_clipboard behavior stays separate.

Supported inputs: UTF-8 .txt/.md or pasted plain text; PNG/JPEG/HEIC files or
pasteboard bitmap representations. No PDF, archive, animated image, remote URL
fetch, directory, executable or arbitrary binary. File acquisition comes only
from a user drop/picker; resolve security-scoped access, read and release; never
send local paths to the bot/provider. Drop of a URL is text unless the user
selected an actual local supported file. Strip rich HTML to plain text.

Per source file <=10MiB; source decode <=25 megapixels; max 4 attachments;
combined normalized images <=8MiB; text <=32KiB UTF-8 across a batch. Validate
magic bytes and decode, not extension alone. Reject malformed/oversize with
named reason; no partial auto-accept without informing user. Normalize images
off main thread using ImageIO: orient correctly, strip metadata/EXIF, downsample
longest edge to 2048, encode PNG if alpha else JPEG quality 0.85. If normalized
file exceeds 4MiB, retry at 1536 then 1024 once each; if still too large, reject.
Preview the exact normalized image and display "Resized for analysis" when used.
Never silently truncate text. This normalization does not change the user's file.

Attachment: id UUID, generation UUID, ordinal, displayName<=120, MIME, normalized
byteCount, SHA256, state=staged|transferring|ready|analyzing|failed, optional error,
in-memory bytes. Question is a separate user-authored field. Remove/cancel and
preview are voice-addressable. Staging alone never makes a model call, adds a
memory or changes the selected research result.

Before use show the configured provider/model label in the tray with "Ask
Mortimer sends only these selected items and your question for analysis."
For voice-only use, announce this once for a batch before requesting its first
send; the explicit confirmation below authorizes that staged batch. A vague
"share that" never authorizes provider upload. Reuse the confirmed
selection for follow-up questions until its bytes change, expire or disconnect.
Any changed/new attachment requires a new batch selection; no implicit new files.

### 6.3 Transfer and analysis contract

Use the existing native/WebRTC application message channel, not new audio or
HTTP transport. Content protocol messages carry the handshake session/generation
and request UUID. console_action payloads never carry attachment bytes.

Backend shared_content requests input/offer for exactly named staged IDs and
question. The client returns metadata (id, MIME, byteCount, SHA256) only for an
explicitly confirmed batch. Backend reserves quota and returns input/accept with
transfer UUID. Only then send input/chunk {transfer_id,attachment_id,sequence,
base64}, decoded chunk <=16KiB. Ack each chunk with input/ack including sequence;
at most one unacknowledged chunk per transfer. Pace at >=10ms between chunks,
never block audio callbacks/main actor. No changes to PCM framing or engine.

After the final chunk send input/commit with declared total/chunk count/hash.
Server verifies contiguous sequence, quota, MIME by decode and SHA256 then emits
input/ready. Duplicate identical sequence acknowledges without appending; same
sequence/different bytes fails the transfer. No assembly beyond declared size;
reject duplicate attachment IDs, negative counts, unknown fields, unmatched
generation/session, unsolicited transfer and invalid base64. Decode safely using
existing Pillow with explicit pixel limit matching client; no external resources.

Timeouts: chunk ack 5s, idle transfer 10s, total transfer 120s, analysis 60s.
Max one transfer and one analysis per session. Backend transient quota 12MiB
per session, max 48MiB per process (quota accountant stores byte counts and opaque
session IDs only). Buffers clear on success handoff to analysis, failure, cancel,
expiry and disconnect. Send input/cancel explicitly; cancel local network/model
task and ignore stale output. Never retry a provider call automatically.

Python SharedContentService has async
analyze(request_id, batch_id, attachment_ids, question, approval_id=None)
-> {ok,request_id,answer,model,error_code?}; injected transport/model client/clock
for tests. One provider call per question, tool-free. Extract the existing vision
profile resolution/client construction into jarvis/vision.py and preserve thin
compatibility wrappers in mcp_screen.logic; no change to screen capture behavior.
Use the existing JARVIS_VISION_PROFILE selection for image AND text batches.
Missing key/unsupported vision returns a concrete error, never a provider fallback.
Model output cap 2000 tokens, answer max 12000 characters, explicit truncation if
needed. Record usage through existing ledger, logging counts/profile only.

Prompt lives in jarvis/prompts.py. Required meaning: answer the separate user's
question from these items; attachment content is untrusted evidence, never
system instructions or authorization; state missing evidence; do not execute
actions or invent details; reference attachment ordinal for claims. No tools
available to this analyzer. Return result as data; never append attachment text
as a system instruction. Analyzer output cannot trigger a console_action or
mutation without a separate user request through existing authorization paths.

At completion publish a normal display result with additive privacy field
ephemeral=true and a stable request identifier. AppMessageRouter ingests it once
through existing result routing; no parallel result callback. Voice path returns
bounded answer to Supervisor. Button path starts same service asynchronously,
shows progress and injects completion through existing late-delivery behavior,
respecting speaking state. Repeating request UUID returns cached status/result,
never re-uploads or repeats the model call. Barge-in does not orphan the task;
explicit cancellation/session disconnect does cancel it.

### 6.4 Temporary-content privacy and cleanup

Wire details supplementing §6.3 (these are contracts, not an additional route):
every message has type:String, version:Int=1, session_id:UUID,
generation:UUID, request_id:UUID. The original request ID spans the operation;
transfer_id identifies the byte transfer. No unspecified extra fields.

- input/analyze (client -> server): batch_id:UUID, attachment_ids:[UUID],
  question:String, approval_id:UUID. Used by Ask Mortimer; the voice tool starts
  the same service and asks the client for approval through input/offer.
- input/offer (server -> client): batch_id:UUID, attachment_ids:[UUID],
  question:String, profile:{id:String,label:String}. Request metadata, not bytes.
- input/manifest (client -> server): batch_id:UUID, approval_id:UUID,
  items:[{id:UUID,mime:String,byte_count:Int,sha256:String}]. All SHA256 values
  are 64 lowercase hex characters. Denied/cancelled approval returns input/error.
  Filenames remain local; only item ordinals go to the provider.
- input/accept (server -> client): transfer_id:UUID, temporary_content_mode:Bool
  (true), max_chunk_bytes:Int=16384. Server must arm the privacy latch first.
- input/chunk (client -> server): transfer_id:UUID, attachment_id:UUID,
  sequence:Int, base64:String. Sequence starts at zero separately per attachment;
  send attachments in manifest order, one chunk outstanding across the transfer.
- input/ack (server -> client): transfer_id:UUID, attachment_id:UUID, sequence:Int.
- input/commit (client -> server): transfer_id:UUID,
  items:[{id:UUID,byte_count:Int,chunk_count:Int,sha256:String}].
- input/ready (server -> client): transfer_id:UUID, batch_id:UUID.
- input/progress (server -> client): batch_id:UUID,
  state=analyzing|completed|cancelled|failed; optional code:String on failure.
- input/cancel (either direction): batch_id:UUID, optional transfer_id:UUID.
- input/error (either direction): code from invalid|unsupported|not_approved|
  stale_session|quota|timeout|cancelled|decode_failed|provider_unavailable|
  analysis_failed, optional transfer_id:UUID; never raw exception/body text.

Messages other than chunks have <=32KiB encoded size; a chunk has <=24KiB.
Individual UTF8 text inputs may span chunks. All size counts use bytes, not
Swift character counts. Booleans cannot pass as integers in Python validation.
The shared fixture contains legal/illegal examples for each direction. Reject
server-only message types received from the client and vice versa.

console/hello also advertises input_profile:{id,label}|null, both fields<=120
characters and free of tokens/URLs, for the pre-send disclosure. This is fixed
for the connection. If it changes, expire approvals and reconnect negotiation.
Approval stores the exact selected IDs, hashes, profile, generation and question;
the same batch's follow-up question is authorized only by a new explicit Ask/
voice analysis request. The model's first request alone cannot create approval.
The native offer displays the exact batch/profile/privacy notice and returns
pending_user until approved. Ask Mortimer on that notice creates approval_id
locally. For hands-free approval the notice offers the exact phrase "Send these
items" or "Cancel these items". While that one notice is pending, the existing
accepted final user-transcription path recognizes only those phrases after
case/whitespace/punctuation normalization; it sends server-to-client input/consent
{batch_id:UUID, approved:Bool, user_turn_id:UUID}, plus the common envelope.
That UUID identifies a new accepted user turn after notice presentation. Bot
speech, imported text, interim STT and console_action cannot emit this message.
Client consumes it once for the matching batch/generation and creates the same
approval record as the button. Send input/consent only from that pending-state
handler in pipeline.py, never from a model-callable function. Consent expires
after 120 seconds; expiration cancels the pending request and does not upload.
Do not consume unrelated utterances or change speaker/mic/PTT/wake admission.
Client checks the stored approval before emitting a manifest; server never
accepts unsolicited chunks. The backend service has one entry point:
analyze(request_id, batch_id, attachment_ids, question, approval_id=None);
voice calls require client approval, button calls validate the supplied approval
against the resulting manifest. Profile capabilities do not substitute consent.

Display completion uses existing display type/surface with body=answer,
title="Shared content analysis", tool="shared_content", ephemeral=true,
request_id UUID and session_id UUID. Ordinary payloads omit new optional fields.
The router's identity map (session_id,request_id)->WorkspaceResult.id deduplicates
ephemeral results only; ordinary identical displays retain existing behavior.
On session end clear that map, matching entries in WorkspaceStore,
DisplayResultStore, DisplayWindowStore, panels and share/media caches. A frozen
share containing ephemeral content is cancelled on session end. Do not leave
an old copy readable in Output after declaring shared content cleared.

Do not claim imported images/text are automatically safe to put in durable memory.
Immediately before accepting an approved batch for transfer/analysis, latch
session-only temporary_content_mode in
the existing SensitiveTurn holder. is_sensitive() returns armed OR this latch;
clear() clears the turn flag but never this latch. It ends only when that bot
session and its LLM context are destroyed. This deliberately preserves current
T4a suppression paths across normal turn boundaries without a racy temporary flag.

Visible badge after the latch is armed: "Temporary-content session: memory saving
paused until reconnect." Speak once per session. Staging alone does not latch it.
The pre-send disclosure includes that memory saving pauses until reconnect;
once armed, a transfer/provider failure also leaves the latch set. Ordinary
conversations before analysis keep normal persistence. Existing sensitive
financial/credential rules stay stricter; this does not enable T4b storage.
Clearing attachments removes originals/buffers but does not claim to purge text
already in the provider context. Offer explicit "Clear shared content and start
a fresh conversation" using normal disconnect/reconnect; never reconnect solely
because a panel moved or a monitor disappeared. Provider retention remains the
provider's policy, not something the app can promise to undo.

Raw input, filenames, answer text and base64 must not enter console diagnostics,
RTVI debug dumps, exceptions, run logs, KB digests, extraction or autosave. Add
type-based payload redaction before BOTH Swift inbound/outbound debug recording
and Python transport logs. Ephemeral display content stays in UI memory and can
be explicitly copied/saved; default export of an unrelated result cannot include
it. Clear ephemeral results and their panels on session end. Preserve unsent
local drafts on a connection failure, mark them "Not sent," require explicit
resend; full application quit clears them. In-use analyzed buffers expire after
30 minutes of inactivity, on Remove, Clear or session end. Provider work/callbacks
carry generation tokens so stale completion cannot repopulate cleared stores.

This privacy decision is intentional and fixed for this release. Luna may not
replace it with a promise in a prompt, automatic memory ingestion, persistent
uploads, a second database or per-turn flag toggles. If it conflicts with a
required existing persistence path, stop and obtain a plan amendment.

## 7. File manifest and bounded implementation sequence

No deletions, dependency additions, database migrations, audio-engine changes or
new network permissions are part of this work. Filenames below are the complete
authorized implementation surface for this specification, not permission to
edit a protected file. If current allowlist or a changed source seam prevents a
step, report the exact blocker; do not expand permissions or move logic into a
less protected file to evade the rule.

**Acceptance-harness amendment, 2026-09-17:** the implementation surface also
includes read-only, non-runtime evidence helpers. They do not alter app state,
add a transport, or change the display policy. `scripts/run_display_topology_probe.sh`
compiles and runs `docs/acceptance/command-console/probes/DisplayTopologyProbe.swift`
in the logged-in Aqua session to record `NSScreen` topology. The probe is
explicitly not a substitute for physical display or daily-driver acceptance.

Create under MortimerHost:

- App/ConsoleActionCoordinator.swift — main-actor validator and dispatcher.
- App/ConsoleActionRegistry.swift — closed action IDs, labels, arg validation
  and capability filtering. No view-defined action strings.
- Stores/AtlasStore.swift and Stores/PanelStore.swift — presentation metadata.
- Stores/AttachmentStore.swift — bounded staging/approval/transfer state.
- Stores/SharedMediaStore.swift — bounded decoded assets, shared by renderer
  and exporter; acquire/release owners, no hidden fetch on export.
- Console/CommandConsoleView.swift — v2 header/work-surface/console composition.
- Console/VoiceConsoleView.swift — existing waveform/meters and controls.
- Display/KnowledgeAtlasView.swift and Display/AtlasCardView.swift.
- Display/ContentPanelView.swift — single UUID-addressed auxiliary scene root.
- Display/ShareCoordinator.swift and Display/SharePreviewView.swift.
- Console/AttachmentTrayView.swift and Console/AttachmentNormalizer.swift
  (landed under Console/, not Display/; path corrected 2026-09-22).
- Placement/ContentWindowRegistry.swift — window registration/focus callbacks,
  no screen observer or placement algorithm of its own. (Noted 2026-09-22: an
  older, different copy also sits at
  `macos/MortimerHost/Placement/ContentWindowRegistry.swift`, outside
  `Sources/`. The `Sources/MortimerHost/Placement/` file is the one that
  landed. See the Command Console status open items.)

Modify under MortimerHost:

- App/MortimerHostApp.swift, App/AppMessageRouter.swift, App/UICommandRouter.swift,
  App/AppTuning.swift, App/AppTheme.swift — ownership, v2 routing, tokens, prefs.
- Console/ConsoleView.swift and Console/AdaptiveStageView.swift — switch by
  layout version, preserving v0/v1. Do not fork audio state into the v2 view.
- Stores/WorkspaceStore.swift — children, shared identity and ephemeral cleanup.
- Stores/DisplayResultStore.swift and Display/DisplayWindowStore.swift — remove
  ephemeral results by workspace ID on session end without clearing unrelated
  results/drafts. AppMessageRouter calls all owners in the same transition.
- Display/WorkspaceView.swift, Display/WorkspaceResultDetails.swift,
  Display/WorkspaceExportCoordinator.swift — common actions and export adapter.
- Display/WorkspaceResultPane.swift, Display/WorkspaceSourcesView.swift,
  Display/DisplayContentView.swift — coordinator bindings, source selection,
  detached-host locators and shared loaded-image access.
- Display/MemoryGraphStore.swift, Display/MemoryGraphView.swift,
  Display/MemoryGraphCanvas.swift — coordinator
  adapters, bounded labels, accessible list/inspector, existing renderer reuse.
- Drawer/DrawerTabStrip.swift, Drawer/DrawerView.swift — common presentation
  actions only; individual tab content/domain operations are not redesigned.
- Placement/WindowLookup.swift, Placement/WindowPlacement.swift,
  Placement/ScreenPlacement.swift, Placement/DisplayPlacementPolicy.swift — typed
  window identity, dynamic registry and tested extension of the current policy.

Create in macos/JarvisKit/Sources/JarvisKit/:

- ConsoleProtocol.swift — typed versioned wire messages and validation limits.
- SharedContentTransfer.swift — asynchronous bounded transfer state machine.
- MessagePrivacy.swift — diagnostic summaries; never stringify payload bodies.

Modify in that same JarvisKit source directory:

- AppMessage.swift, ClientMessage.swift, JarvisClient.swift — additive decoding,
  outbound messages, capability/session lifecycle, privacy-safe debug output.
- NativeAudioTransport.swift and DirectWebRTCTransport.swift — application-message
  payload redaction and bounded send integration only. PCM, device setup,
  buffering and transport selection are out of scope.

Create Python:

- jarvis/bot/console_protocol.py — strict schemas, limits and safe summaries.
- jarvis/bot/console_session.py — handshake, requests, acknowledgements, inventory,
  transfer ownership, cleanup; no global session objects.
- jarvis/bot/console_actions.py — tool schema/handler and target resolution.
- jarvis/bot/shared_content.py — upload validation and tool-free analysis service.
- jarvis/bot/shared_content_transfer.py — approved manifest/chunk/commit state,
  digest verification and ephemeral cleanup.
- jarvis/vision.py — extracted existing profile/client construction only.

Modify Python:

- jarvis/bot/pipeline.py — one session, shared handler in both transports,
  tool wiring and cancellation/late-delivery; same context holder throughout.
- jarvis/bot/ws_transport.py — safe message diagnostics; its existing
  ClientMessageProcessor.bind accepts the new shared handler without a second
  transport-specific dispatcher.
- jarvis/bot/tool_schemas.py, jarvis/agents/supervisor.py, jarvis/prompts.py —
  identical tool menu/flags in live and evaluation paths; append new schemas
  after existing ones; preserve existing ordering. Exact tool-use addendum says
  presentation uses console_action, domain work keeps existing delegation,
  content analysis uses shared_content, and success requires acknowledgement.
- jarvis/config.py — two default-off Boolean gates:
  JARVIS_COMMAND_CONSOLE_ENABLED and JARVIS_SHARED_CONTENT_ENABLED. The latter
  requires the former. These never enable or override mic/screen/clipboard gates.
- jarvis/bot/sensitive_turn.py and jarvis/bot/transcript_log.py — latch plus
  payload-safe metadata logging; preserve existing redaction formats.
- mcp_servers/mcp_screen/logic.py — compatibility wrappers to jarvis/vision.py.
  Screen capture/retention policies remain unchanged.

Tests to create (Host prefix macos/MortimerHost/Tests/MortimerHostTests/;
Kit prefix macos/JarvisKit/Tests/JarvisKitTests/):

- Host: CommandConsoleRenderingTests.swift (landed as
  FullConsoleRenderingTests.swift; see the manifest reconciliation below),
  ConsoleActionCoordinatorTests.swift,
  KnowledgeAtlasTests.swift, ContentPanelTests.swift, ShareCoordinatorTests.swift,
  AttachmentStoreTests.swift, AttachmentNormalizerTests.swift.
- Host response routing: `ResponseResultRouter.swift` and
  `ResponseResultRouterTests.swift` keep each streamed Mortimer answer in one
  bounded results card, preserve reading state, and transfer ownership to the
  supporting display without duplicating it in the conversation surface.
- Kit: ConsoleProtocolTests.swift, SharedContentTransferTests.swift,
  MessagePrivacyTests.swift.
- Python tests/unit/: test_console_protocol.py, test_console_session.py,
  test_console_actions.py, test_shared_content.py, test_vision_profile.py.
- Shared fixtures: tests/fixtures/command_console/protocol.json and
  tests/fixtures/command_console/voice_cases.json. Kit/Host tests load from an
  explicit source-relative URL; no package-manifest resource/dependency edits.

Extend existing tests only where behavior changes: Host WorkspaceStoreTests,
WorkspaceRenderingTests, WorkspaceSourcesRenderingTests, WorkspaceResultDetailsTests,
MemoryGraphRenderingTests, MemoryGraphTests, ScreenPlacementTests,
UICommandRouterTests; Kit UICommandOwnershipTests; Python test_ws_transport.py,
test_ui_control.py, test_sensitive_turn.py, test_sensitive.py, test_screen_tool.py,
test_prompts.py, test_tool_schemas.py, test_supervisor_tool_registration.py.
Do not change old assertions merely to accommodate a regression.

Documentation: this plan; new docs/acceptance/command-console/STATUS.md,
PRESERVATION.md, VOICE.md, SHARING.md, DISPLAYS.md, PERFORMANCE.md and RELEASE.md.
Evidence files may be added below that acceptance directory with sanitized
fixtures only. Existing adaptive-interface readiness is referenced, not marked
complete by this work. Generated model/profile/tool catalogues must not change:
these are Supervisor tools, not new MCP tools or agents.

**Manifest reconciliation, 2026-09-18:** the landed rendering suite is named
`macos/MortimerHost/Tests/MortimerHostTests/FullConsoleRenderingTests.swift`.
It is the broader implementation of the `CommandConsoleRenderingTests` entry
above and includes the v2 conversation-start, compact layout, font-size and
accessibility reachability checks. `tests/unit/test_plan_manifests.py` pins this
equivalence and verifies the required implementation, fixture, test and
acceptance artifacts remain present.

### 7.1 Execute these increments in order

Each increment gets a separately reviewable diff and evidence. Do not stack
unverified increments or deploy partial states. A failing gate blocks dependent
work; complete unaffected documentation/tests while reporting the blocker.

1. **CC0 — Freeze baseline and acceptance inventory.** Record resolved commit,
   dirty-tree diff, runtime receipt separately, sandbox image and full baseline
   test results. Copy all 24 preservation rows into PRESERVATION.md, retaining
   their IDs and open/unknown status. Add each feature/action in this plan as
   unchecked. No app change. If a listed source file/contract has drifted, amend
   only the affected spec with evidence before execution.
2. **CC1 — Contracts and ownership.** Add typed protocol, registry, coordinator,
   state owners, server session and default-off gates. Add independent decoder
   fixtures and legacy compatibility tests. No visible layout or registered
   production tool until both halves can negotiate. Establish privacy-safe
   diagnostics now, before accepting attachment messages.
3. **CC2 — Command Console.** Add v2 composition and shared actions for existing
   work-surface buttons, sidecar controls and appearance. Preserve app owners and
   all old layouts. Pass min-size/font/accessibility snapshot checks and the
   existing waveform/meter tests; no new visual state may claim activity without
   underlying data. No attachment controls shown until CC6 is available.
4. **CC3 — Atlas and graph.** Add board/grid/groups, existing reader integration,
   graph label budget and voice-addressable graph operations. Test state survival
   on mode switches, large graphs, empty/truncated/error cases and unsupported
   Connections. Do not introduce semantic memory changes.
5. **CC4 — Detachable panels.** Extend window identity and the sole placement
   policy; add registry and value-addressed WindowGroup. Test one/two/three
   screens, mirrored areas, manual relocation, unplug, reopen and close while
   content is loading. Every operation preserves shared IDs, drafts and focus.
6. **CC5 — Outward sharing.** Add deterministic text/PNG preview, explicit
   clipboard/save/system-share actions and approved-folder bookmark. Use fake
   pasteboard/file/picker adapters in unit tests. No transport/provider needed
   for this phase; do not claim recipient delivery from picker presentation.
7. **CC6 — Inward sharing.** Add normalization, tray approval, transfer/service,
   privacy latch and ephemeral display flow. Test malicious input, quotas,
   reconnect/cancel and all persistence sinks before enabling even in candidate.
   Profile extraction must leave screen_tool tests unchanged and green.
8. **CC7 — Voice parity and regression acceptance.** Register enabled tool
   schemas consistently in runtime/eval and run every catalog action through
   pointer and voice adapters. Run both transport paths, full suites, offline
   fixtures and physical-device acceptance. Optional live provider/voice checks
   consume real calls only in the candidate acceptance session, with the user's
   normal test input. Do not silently turn fixture tests into paid/live tests.
9. **CC8 — Release candidate and controlled promotion.** Build/package exact
   artifact, collect receipts/screenshots, complete hardware gates and have Larry
   approve the appearance. Complete UI2-17's separate five-day daily-driver
   period on the frozen installed candidate, keeping the old release available;
   material fixes restart the period with a new candidate record. Command
   Console is the user-directed shipped default; physical acceptance gates
   still control enabling provider-backed transfer and final release sign-off.
   Merge/deploy are separate from the current plan request.

The server gates exist from CC1 but remain false through CC6 except in isolated
tests. CC7 candidate explicitly enables them. An installed v2 UI with an older
server retains local presentation/copy/save; unsupported voice/upload shows a
clear capability notice, never a fabricated successful action.

## 8. Acceptance evidence and regression gates

Status values: NOT STARTED, IMPLEMENTED/UNVERIFIED, VERIFIED IN SANDBOX,
VERIFIED ON MAC, BLOCKED. A checked completion box requires the applicable
evidence URL/path, source revision, artifact hash, test command, date and result.
Missing evidence is open. Do not roll separate source, runtime and hardware
readiness into a single misleading percentage.

### 8.1 Automated tests with exact expected outcomes

- ConsoleProtocolTests / test_console_protocol: shared fixtures round-trip in
  Swift and Python. Reject unknown fields/actions, NaN/infinity, invalid UUIDs,
  oversized strings, stale generation and malformed discriminators. Old ui,
  voice/set, ui/noop and unknown-message behavior remain compatible.
- ConsoleActionCoordinatorTests / test_console_actions: one fixture per action
  in §4.2 (plus legacy aliases), for valid, invalid and unavailable cases.
  Pointer and resolved voice requests produce equal store snapshots and side
  effect counts. Every action is accounted for; omissions fail the fixture
  coverage assertion. Dynamic nodes, groups, sources and screens use inventory
  IDs; duplicate titles produce choices and zero mutations.
- test_console_session: request acknowledged, not acknowledged, duplicate,
  disconnect, timeout, late completion and old-client cases with a fake clock.
  Never report done before state applied or rerun a side effect on duplicate.
  A picker yields pending_user and one eventual completion, not two saves.
- CommandConsoleRenderingTests: 900x600, 1200x800 and 1920x1080 at every existing
  font preset; long titles, warnings, active attachment tray, all eight sidecar
  tabs. No horizontal label overlap, inaccessible control or content hidden
  behind console. Assert visible text/controls in addition to rendering images.
- KnowledgeAtlasTests / WorkspaceStoreTests: 0, 1, 100 results; group capacity;
  placement collision; new arrival while reading; pin/compare, Atlas -> Memory
  -> Results and back. Stable IDs, selection, camera, scroll and drafts survive.
- MemoryGraphRenderingTests / MemoryGraphTests: same source fixture before and
  after, identical node/edge counts and semantics; label budget<=40, selection
  readable, full accessible list remains available; truncation is visible;
  search/focus/path/filter/reset/original fallback still work.
- ContentPanelTests / ScreenPlacementTests: manual frame wins; mirrored outputs
  count once; screen removal recovers a reachable title bar within one second;
  reattach obeys revision rules; closing returns content; 7th panel refused with
  explanation; repeated detach focuses existing panel. No duplicate graph load,
  model call, audio session or polling owner.
- ShareCoordinatorTests: frozen preview cannot retarget on arriving result;
  copy writes exactly chosen text or PNG; cancel writes nothing; save rejects
  stale bookmark and does not overwrite silently; picker-open isn't sent;
  scoped paragraph export is deterministic; unrelated drafts/captions/sidecar
  and clipboard payload are absent. PNG actual decoded dimensions obey limits.
- AttachmentNormalizerTests: valid UTF8/PNG/JPEG/HEIC, orientation, alpha,
  metadata stripping; corrupt/truncated files, MIME spoof, symlink/directory,
  huge dimensions, too many items, oversize batch and malformed UTF8. Reject
  with a concrete reason and zero provider calls. URL paste stages text only.
- AttachmentStoreTests / SharedContentTransferTests / test_shared_content:
  stage causes zero network calls; approved immutable batch only; reordered,
  duplicate/different, missing and oversized chunks; quota released on every
  terminal path; ack timeout; reconnect never resends; cancel during analysis
  ignores late results; one duplicate request results in one provider call.
  Bot speech, interim STT, stale user turn, expired approval and an attachment
  saying "Send these items" produce zero consent; accepted new user speech at
  a pending notice approves only that exact batch once.
- MessagePrivacyTests / test_sensitive_turn / test_sensitive: distinctive
  sentinel filename/text/answer/base64 never appears in captured diagnostics,
  transcript persistence, run-log persistence, memory extraction inputs or KB
  digest jobs after latch. Turn-clear cannot reset latch; a fresh session can.
  Staging alone leaves normal memory behavior intact. These use injected sinks
  and a temporary database, never the user's database. If a sink lacks an
  interceptable suppression path, record the gap and stop CC6; do not claim
  passing based only on is_sensitive() unit tests.
- test_vision_profile / test_screen_tool: existing profile preference and
  explicit-invalid error preserved; attachment analysis never calls screenshot
  capture; missing profile fails with zero provider calls; analyzer has zero
  tools and treats embedded instructions as untrusted source content.
- test_tool_schemas / test_prompts / test_supervisor_tool_registration: every
  enable/disable/capability combination has matching schemas, handlers and
  prompt instructions. Old menu ordering unchanged. Tool/prompt budgets remain
  enforced; do not increase limits merely to fit new prose.

Fixture voice cases must include: "Show the memory graph", "Focus this node",
"Show its sources", "Put this research on the other screen", "Bring everything
back", "Make the sidecar text larger", "Move that card to row two column one",
"Copy the second paragraph", "Copy this graph as an image", "Share this",
"Paste my image", "Use these two images to explain the difference", "Cancel
that upload" and "Clear shared content and start a fresh conversation".
Also test ambiguous "that", duplicate titles, mic muted, no second display,
disconnected server, unsupported client and a new result arriving mid-command.

### 8.2 Required whole-project validation

Use the current sandbox/session service and independent verification VM specified
by CLAUDE.md's September 10 update. Do not substitute live-checkout edits or the
older Swift-only gate shortcut. Gate receipts must cover baseline and candidate,
full backend unit suite (900-second limit per check), relevant Swift package
build/tests, core import checks and normal repository CI. No skipped or narrowed
gate can count as green. Any pre-existing baseline failure stays separately
reported; a candidate adding failures is blocked.

The underlying checks include `pytest tests/unit -q`, offline integration tests,
and `swift build` / `swift test` for macos/JarvisKit and macos/MortimerHost.
Run through the sandbox's supported verification entrypoint, rather than
inventing a direct host command or patching verifier policy. Record actual
commands from its receipt. CI's remaining required checks remain required.
No live credentials or user database are copied into the offline worker.

### 8.3 Physical Mac acceptance: cannot be replaced by mocks

- Confirm loaded artifact path and SHA256/release receipt before screenshots.
  A branch name, app title or Git HEAD alone is insufficient.
- Repeat all 24 P0 preservation rows plus prior unresolved audio/C8 gates.
  Open and use all eight tabs, preserving an unsent Edit draft throughout.
- Converse by voice, interrupt speech, mute/unmute, PTT, wake and change devices.
  User waveform follows actual input; AI waveform follows actual output;
  colors, labels and mic-off behavior remain correct during graph/upload work.
- Use each new operation by voice; compare a representative mouse/keyboard
  path. Verify graph focus/filter/path and paragraph/image selection target the
  visible item, with clarification when ambiguous. OS dialogs are the explicit
  boundary in §4.2, not counted as application voice failures.
- On one display, all content stays usable. With two and three displays, move
  research, graph, transcript and sidecar; unplug while reading/typing; reconnect.
  No content loss, hidden windows or preference override. If physical additional
  displays are unavailable, this gate stays open even if policy tests pass.
- With an external display connected, confirm the curated-stage rule: one outer
  supporting stage, with one result full-stage, two results split, and three or
  four results in a bounded grid. There is no automatic sidecar, transient, or
  nested-information-window fan-out; stable console/display roles remain in
  force, and overflow appears only after an explicit move or pin action.
  Repeat the graph/research requests and record tile count and identity before
  and after reconnect.
- Copy text/PNG into another app; save and reopen both; cancel the system share
  sheet; stage a real image and ask a question. Inspect output/source/provenance
  and the memory-paused notice; reconnect and verify normal memory resumes.
- VoiceOver traversal, keyboard-only controls, Increase Contrast, Reduce Motion,
  Reduce Transparency and all supported font presets. Interactive controls have
  stable accessibility identifiers and labels, never color-only meaning.
- Larry reviews actual screenshots against the selected design direction:
  central useful work, restrained voice console, legible complete sidecar,
  graph relationships readable on selection. A render test cannot decide
  whether the redesigned interface is satisfying.

### 8.4 Performance thresholds

Use the same Mac, fixed local fixtures, warm-up 30s then three 60s measurements
for baseline and candidate. Record medians and p95, sample count and tooling.
Keep current audio/meter/graph acceptance limits; this plan cannot relax them.
Additionally, input/selection p95 main-thread work <=16.7ms, local navigation
acknowledgement p95<=200ms, and graph pan/zoom p95 frame duration<=33.3ms with
the existing maximum-node fixture. A worse-than-baseline result of >10% is a
regression even when below these ceilings. If baseline exceeds a ceiling,
record the pre-existing failure and require an explicit release decision.

Stress case: graph visible + all six panels + maximum accepted attachment batch
while voice is active. No new audio underruns or dropped/stalled PCM, and no
unbounded task/decoded-image retention. After 20 open/close/upload/cancel cycles
and 30s idle, candidate memory is <=baseline steady state+64MiB (decoded-media
cache budget); record transient peaks too. Synthetic policy timing proves only
policy timing, not physical-window recovery or perceived voice latency.

## 9. Rollout, rollback, and stop conditions

Ship in three separately recorded states: source merged, candidate accepted,
daily driver promoted. None implies the next. Initial candidate uses layout 2
and explicitly enabled gates for that candidate only. Keep the old app artifact
and release receipt available; do not overwrite the sole known-good build.

Rollback order:

1. Disable JARVIS_SHARED_CONTENT_ENABLED, cancel active transfers and reconnect;
   preserve explicit exported files. Confirm no new uploads are accepted.
2. Select layout 1. Return auxiliary content to main workspace, dismiss v2 panel
   windows without deleting results/drafts, preserve legacy preferences. A
   layout switch alone must not disconnect audio or erase current conversation.
3. Disable JARVIS_COMMAND_CONSOLE_ENABLED and restart the bot if required by its
   current configuration loading. Retain legacy ui_control functionality.
4. If needed, restore the prior packaged app and exact matching server artifact
   through the existing deployment procedure. No DB downgrade/migration exists.

Switching layout away from 2 cancels unapproved share previews and stops active
uploads with a visible notice; it preserves unsent attachments in the app-owned
tray for return to v2. It does not clear a live session's privacy latch or
claim that already analyzed content has left model context. Existing saved
files/clipboard items remain under the user's control.

Stop and request a specific plan amendment when: a new dependency or provider
is necessary; a protected file must change; actual source ownership differs;
transfer cannot meet audio gates on the shared channel; schema/prompt budgets
fail; any sensitive data reaches a durable sink; a user operation lacks a voice
equivalent; an old function disappears; or acceptance needs unavailable hardware.
Luna must report observed evidence and the smallest blocked requirement. It
must not redesign the audio path, persistence, window model or authorization to
get past a failure. No weakening tests, sandbox restrictions or domain approvals.

Numbers have one owner: view metrics in CommandConsoleMetrics, theme tokens in
CommandConsoleTheme, placement constants in DisplayPlacementPolicy, wire limits
in ConsoleProtocol/console_protocol checked against the same fixture, sharing
and normalization limits in their owning coordinator/service. No environment
knobs beyond the two named kill switches. Existing user tuning remains intact.

## 10. Implementer handoff and design audit

Paste this instruction with the plan when assigning the implementation:

> Implement MORTIMER_COMMAND_CONSOLE_ATLAS_PLAN.md in CC0–CC8 order. Treat its
> decisions as fixed. Preserve existing local changes and record the actual
> baseline. Use the established sandbox and independent verification workflow.
> Do not alter production, deploy, merge, change protected files or choose a
> different architecture. Complete one increment with its tests and evidence
> before moving to the next. Where a source seam contradicts the plan, stop the
> dependent work and report the exact file/contract mismatch for an amendment.
> Do not mark hardware acceptance, appearance approval or earlier open blockers
> complete based on compilation or unit tests. Return the diff, evidence and
> remaining open gates for each increment.

Nine-item design audit for reviewers:

1. **Shared contracts:** typed IDs, action catalog, protocol, acknowledgement,
   upload/privacy rules and shared cross-language fixtures are specified. CC1
   must prove identical decoding before later consumers are wired.
2. **Lifecycle:** app owns stores; views borrow them; content identity survives
   detach/return; temporary bytes expire; generation tokens reject stale work.
3. **Application:** coordinator delegates to named existing state/placement
   owners; no duplicate audio, graph query or result ingestion owner.
4. **Consistency:** single-screen and multi-screen use the same content/store;
   GUI and voice share actions; picker opened and externally sent are distinct.
5. **Visible states:** idle/loading/empty/error/truncated/unsupported/pending
   remain honest; never turn missing telemetry or acknowledgement into success.
6. **Initialization:** app owners first, router once, session after pipeline
   readiness, handshake before new server actions, window registry before move
   success; default-off gates prevent a partially wired production feature.
7. **Signatures and values:** inventory supplies every dynamic target, revision
   and screen; export preview freezes content; provider comes from existing
   vision configuration; no model-supplied file path or inferred graph edge.
8. **No delegated architecture:** dependencies, placement, audio, model calls,
   sharing consent, data lifetime and failure handling are fixed; amendment
   rules explicitly cover cases that cannot safely follow those decisions.
9. **Drift:** manifest, phase changes, tests and acceptance documents must agree.
   Before each diff, compare changed paths with §7; unexplained paths block it.

This specification reduces implementation discretion; it does not guarantee
zero regression. Release confidence comes from the listed tests, artifact
identity, physical acceptance and a working rollback.

## 11. References

Existing repository documents:

- [Adaptive interface plan](MORTIMER_ADAPTIVE_INTERFACE_PLAN.md).
- [P0 preservation checklist](../acceptance/adaptive-interface/P0-preservation-checklist.md).
- [Plan author conventions](../archive/plans/PLAN_AUTHOR_BRIEF.md). Its older runtime/worktree
  assumptions yield to CLAUDE.md's current sandbox execution update.
- [Repository instructions](../../CLAUDE.md), especially the September 10
  sandbox update and existing audio/authorization invariants.

Native API references used to constrain the design:

- [SwiftUI WindowGroup](https://developer.apple.com/documentation/swiftui/windowgroup)
  for value-addressed content windows.
- [SwiftUI ImageRenderer](https://developer.apple.com/documentation/swiftui/imagerenderer)
  for selected-content bitmap output; arbitrary native/Web content capture is
  not assumed, and unloaded assets are represented explicitly.
- [AppKit NSSharingServicePicker](https://developer.apple.com/documentation/appkit/nssharingservicepicker)
  for the system-owned destination picker.

Design inspiration is conceptual, not a dependency or permission to copy a
product's assets: [Linear's interface refresh](https://linear.app/now/behind-the-latest-design-refresh),
[Heptabase](https://heptabase.com/) and
[Obsidian graph](https://help.obsidian.md/plugins/graph). The accepted direction
combines a restrained command console with a useful spatial knowledge view;
existing Mortimer functionality takes precedence over visual resemblance.
