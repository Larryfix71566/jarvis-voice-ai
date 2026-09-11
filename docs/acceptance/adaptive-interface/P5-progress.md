# Screen placement and shared presentation progress

Status: implemented in development; acceptance remains incomplete.
Starting application commit: `0b98722`. No merge or deployment.

## Implemented

- Pure display-placement policy with an AppKit adapter. Stable display identities,
  mirrored-area deduplication, visible-frame clamping and a single 250 ms debounce
  cover placement without opening empty windows or reconnecting conversation.
- Manual placements survive reachable-display changes. Unplugged windows recover
  even when AppKit has already moved them. Reconnection restores the previous
  position unless a newer manual move, close or docking action supersedes it.
  Resolution changes and reopening saved windows retain bounded frame metadata.
- Reset Layout resets placement and drawer width without clearing application data.
- Drawer models are app-owned. Visibility leases prevent a disappearing drawer
  from stopping a replacement drawer's polling. Drafts and model selections survive
  window reconstruction; scroll offsets remain session-only. Output expansion is
  owned by its result store rather than reset on every view appearance.
- Results and the memory graph can move to a supporting display. The main view
  yields while that renderer is live. Existing display panels remain accessible.
  Shared result identity, graph state, pinned results and compact A/B selection
  survive presentation changes. Supporting results are protected from history
  eviction until their assignment is removed.
- Selecting the previous layout also restores the supporting display's original
  panel presentation. The new assignment stays in memory for returning to preview.
  This condition compiles and the host suite passes; an interactive rollback check
  remains required.

## Automated evidence

Offline prepared Mortimer VM, synthetic data; task `66fed310bde6`.
Full `swift test --package-path macos/MortimerHost`, no skipped tests.

- `p5-native-scroll-restoration`: 77 tests, zero failures. Native NSHostingView
  test observes actual offset 500 ±2 points in both the original and replacement
  NSWindow, rather than merely asserting stored metadata. Log SHA-256:
  `96f96507b0983d76da7ee807137344cc704d1f4d3384cf7c036ba5d647ac3615`.
- After the supporting-display rollback correction, `p5-display-rollback`:
  77 tests, zero failures; verifier duration 8.884 seconds. Log SHA-256:
  `48b11d23cd80e7b80fa3279280e585fbbdbb8a06fa14f3839cc41294ef38807f`.
- Nine new policy tests cover unplug/reconnect, newer manual intent, close/dock,
  stable role ordering, mirrored screens, negative coordinates and title-bar
  reachability, resolution restoration and reopening manual windows.
- Shared-owner tests cover model identity, drafts, configuration replacement,
  overlapping visibility leases, result retention and output expansion behavior.
  They do not establish real HTTP poll counts or every tab's widget state.

## Open acceptance

- Real one/two/three-display, mirrored, sleep/wake, unplug/reconnect and fullscreen
  cases; Retina/non-Retina scaling; measured recovery within one second.
- Actual manual dragging during topology changes and notifications from the OS.
- All eight tabs' selections, drafts, keyboard focus, attention and scroll behavior
  through docking and monitor transitions; prove no duplicate HTTP subscriptions.
- Tight-width toolbar/layout inspection, main/supporting result scroll behavior,
  graph interactions and rollback with live windows and synthetic drafts.
- Source freeze and final full library/backend/profile checks, accessibility,
  graph interaction timing and audio/hardware acceptance across the full plan.
- Dual-speaker audio remains unimplemented. Passing this phase's tests is not
  evidence that P2 or the overall plan is complete.
