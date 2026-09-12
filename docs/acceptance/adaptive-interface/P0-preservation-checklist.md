# Existing-function preservation checklist

Status: source inventory prepared; interaction acceptance pending. This document
is not a claim that checked-in views work on deployment hardware. Inspected
native sources at `60a6cda`, alongside the earlier phase records and plan UI-1.
Paths below are under macos/MortimerHost/Sources/MortimerHost unless qualified.
Only the decorative central lettering is intended to disappear.

Use synthetic data and authorized test services. For each row record baseline
and candidate steps/outcomes, viewport, screenshot/log, tester and date. Exercise
both old-layout rollback and adaptive mode. Repository push, edit submission,
memory approval/deletion and other writes must use disposable test targets;
listing these controls does not authorize production actions.

## Console and conversation

- [ ] TopBarView: Connect/Disconnect, raw connection state and errors; voice
  selection and unavailable state; degraded-capability information.
- [ ] TopBarView: drawer toggle/aggregate activity, display open/return, drawer
  return from pop-out. Actions still reach the shared WindowPlacement owner.
- [ ] MicControlsView: microphone toggle, disconnected disabling, SPACE press
  and release ownership, typing-target exemption, wake toggle/availability,
  sound toggle and keyboard hints. Never leave capture enabled after PTT release.
- [ ] ConsoleView: T transcript shortcut and Escape behavior; text editing retains
  its keystrokes. Window resize, drawer resize/double-click reset and full screen.
- [ ] OrbFieldView: listening/speaking/thinking and muted/wake labels, current
  captions and speaker rejection. Verify both full and compact presentations.
- [ ] OrbFieldView: agent satellites, working/completion indications, progress
  and selecting an agent's Runs view. No duplicate job or result on selection.
- [ ] OrbFieldView: pending draft notice, input-device notice, output-device
  notice with Reconnect and Dismiss. Reconnect is explicit, never a layout effect.
- [ ] AmbientStripView/SystemVitalsView: ambient and machine information remains
  available in full/compact voice regions; failed/unavailable states remain honest.
- [ ] App menus: Full Screen, Reset Layout, layout preview/rollback, clear stored
  token and message log. Reset Layout must not clear drafts or content.

## All eight sidecar tabs and common behavior

- [ ] DrawerView/DrawerTabStrip: same keys/order Repo, Edit, Memory, Runs, Agents,
  Output, Log (`transcript`) and Costs. Fixed close/pop-out controls, attention
  dots, selected border, scroll arrows and entire selected label stay reachable.
- [ ] Common: loading, empty, failure, 401/403 and reconnect handling; existing
  voice aliases still select the same tab; keyboard and large text remain usable.
- [ ] Common: active tab, scroll, selected records, drafts and in-flight actions
  survive tab switches, dock/pop-out and monitor loss; no duplicate polling.
- [ ] RepoTab: repository status/diff information, commit-message draft, Draft,
  commit confirmation/discard, Push preparation and its confirmation/discard.
- [ ] EditTab: model choice and goal draft; Run, Validate, Submit and Revert,
  action-busy disabling; job progress/logs and expandable details.
- [ ] MemoryTab: memory sections/fact content and review entries; Approve/Reject;
  delete confirmation, Really delete and Keep; cancelling leaves data intact.
- [ ] RunsTab: agent/status filters, Refresh, stored run details/events, model,
  latency and tool results; changed selection rejects stale replies; detail retry.
- [ ] AgentsTab/CouncilRosterView: live agent history, planner/model and unusable
  model information; council rounds, proposer results, chosen response, reasons,
  retries, token/cost/provenance details and their existing help text.
- [ ] OutputTab: history expansion/collapse, dismiss and Clear; pending-draft
  attention; every existing display field and original result remains readable.
- [ ] LogTab: conversation/message entries, existing follow-to-latest behavior,
  restored reading position and keyboard shortcut; no duplicate transcript rows.
- [ ] CostsTab: existing cost totals, breakdowns and unavailable/error states.

## Results and supporting windows

- [ ] DisplayContentView: body text, image/basemap layering, supplied links,
  manual command copying and output instructions, ephemeral clipboard content,
  character counts and truncation indications. Commands do not become execution.
- [ ] SingleDisplayPanel/DisplayWindowView: existing window-surface panels,
  drag, resize, close, title double-click Fit and return-to-main behavior.
- [ ] AppMessageRouter/stores: original surface routing, attention and auto-open
  semantics; one receipt per incoming result. Closing a central tab does not
  remove Output history; moving a result does not invoke its tool again.
- [ ] Workspace additions: persistent reading/selection, pins and A/B comparison,
  sources/inspector, explicit export, graph original/interactive modes; existing
  sidecar remains accessible throughout. Clipboard content never enters export.

Source presence is only inventory evidence. P0 still requires baseline captures
and real audio/performance measurements; P1–P6 acceptance records identify the
limited automated/visual checks already performed. Every unchecked row above
remains a release gate until its complete interaction scope is verified.

## Pre-existing at baseline (closure plan C0.3, gap G22)

Recorded 2026-09-11 against baseline `2ccf66c`. These are conditions the
candidate inherited; a row here is not a regression attributable to any
phase, and each names the item that resolves or accepts it.

- `macos/JarvisKit/Sources/JarvisKit/WakeWordListener.swift:162-178` runs its
  own `AVAudioEngine` input tap (a second microphone capture engine). It runs
  only while the mic is muted (N10 rule 1) and is not echo-cancelled
  (`AudioSession.swift:116-118`). UI-2's "no second capture engine" applies to
  the meter; this tap is pre-existing and stays until the native-audio plan
  (closure C6) owns capture. Not a P2 violation.
- Two window minimums: `NSWindow.minSize`/`contentMinSize` are 400×300
  (`macos/MortimerHost/Sources/MortimerHost/App/MortimerHostApp.swift:239,244`,
  set deliberately to defeat SwiftUI's own limits) while the SwiftUI frame
  minimum is 900×600 (`Console/ConsoleView.swift:96` in the candidate). The
  900×600 SwiftUI value is the preserved contract of interface-plan §7; the
  NSWindow floor is intentionally lower and is not a supported size.
- `Display/GraphImageView.swift:125` fetches graph images with
  `URLSession.shared` and no Authorization header, bypassing `JarvisHTTP`
  (the "one attach point", K1). Harmless today only because
  `/api/graph/{name}` carries no server-side auth. Closed by closure C3.3
  (2026-09-12: `GraphImageView` now fetches via `AdminAPI.graphImageData(at:)`;
  see `C3-p4-gaps.md`).
- An unsaved Edit draft did not survive drawer pop-out/pop-in: `EditViewModel`
  was `@State` on `DrawerView` (baseline `Drawer/DrawerView.swift:18-24`) and
  the console and drawer windows each built their own `DrawerView`. Closed by
  the app-scoped `DrawerModels` hoist (locked decision L3).
