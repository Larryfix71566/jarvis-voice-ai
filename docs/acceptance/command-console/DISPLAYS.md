# Display acceptance

`ContentWindowRegistry` preserves value-addressed panel identity and the
existing placement policy remains the sole monitor topology owner.

- [x] Panel registry and return-all state primitives, including stable UUID
  content identities, a six-panel ceiling, focus-on-repeat, and explicit
  capacity rejection without eviction.
- [x] Closed content types (`result`, `sources`, `comparison`, `memoryGraph`,
  `atlas`, `transcript`) use the app-owned stores through the dynamic
  `WindowGroup`; closing a scene returns its record and advances inventory.
- [x] Value-addressed panel `WindowGroup` opens from detach/focus/move and
  dismisses on return/close; coordinator coverage passes.
- [x] Existing placement policy and display-window tests pass, including
  value-addressed panel disconnect/reconnect recovery in the synthetic
  topology suite.
- [x] Synthetic virtual-screen acceptance covers requested-screen clamping,
  manual-frame preservation, disconnect/reconnect recovery, mirrored-screen
  deduplication, negative coordinates, and stable display roles. The latest
  `ScreenPlacementTests` run passed 8 tests with zero failures.
- [x] An earlier read-only probe recorded one available display; that historical
  receipt preserves its ID, frame, visible frame and backing scale.
- [x] A later probe enumerates two system-recognized displays: the built-in
  Retina panel and the `C34H89x` external panel at a negative X origin. The
  two-screen receipt records both frames, visible frames and scales.
- [x] A fresh read-only probe on 2026-09-18 still enumerates two displays,
  with `C34H89x` currently serving as the main display and the built-in panel
  at the origin. This receipt records the changed role/origin without treating
  topology alone as proof of content placement:
  `receipts/display-topology-2026-09-18-current.json`.
- [x] With that topology connected, the live `ScreenPlacementTests` hardware
  check passed: the placement adapter saw two stable, non-mirrored display
  identities with non-zero visible frames and a distinct virtual-screen origin.
- [ ] The two-screen exercise exposed a separate content-policy gap: the
  memory graph remained rendered in the main work surface while the external
  display also showed it, and repeated requests accumulated several graph
  panels. UI2-19 now tracks the required single-authoritative-renderer,
  focus/reuse, explicit-pin and return-locator behavior.
- [ ] UI2-20 adds the external-stage content budget: one outer stage with one
  full-stage result, a two-result split, or a three-to-four-result adaptive
  grid. There is no automatic sidecar, transient-window, or nested-card
  fan-out. The observation is recorded in
  `receipts/display-content-policy-2026-09-18.md`; the bounded-panel and
  stable-role acceptance remains open. A connected candidate inspection now
  records one bounded research card on `Mortimer Display`, a main-surface
  return locator, and no automatic sidecar/transient fan-out in
  `receipts/candidate-two-screen-content-2026-09-18.md`. The native store now
  enforces the one-unpinned-panel rule when the supporting scene is open and
  preserves explicit pins; repeated-request, pin, fetch/subscription,
  multi-result tile, and one/three-display evidence remain open. Automatic
  unplug/rehome and reconnect restoration are covered by the candidate monitor
  receipts.
- [ ] The 2026-09-18 candidate log also showed both the console and display
  window settling on the external `3440x1410` screen; placement stabilization
  and content ownership need one combined acceptance run.
- [x] The later connected-candidate run recorded a stable role split: console
  on the external `C34H89x` and supporting display on the built-in panel, with
  the auxiliary window retaining `no-fullScreenPrimary`. Receipt:
  `receipts/candidate-two-screen-roles-2026-09-18.md`. Content ownership and
  no-fan-out evidence remain open.
- [x] Sandbox store and router behavior now deduplicate exact visual payload
  identities, reuse the existing workspace owner, focus repeated requests, and
  permit an additional copy only through the explicit pin action. Distinct
  sections from one Developer run still append to one outer panel with their
  own history rows; pinned overflow stays outside the default stage. This is
  implementation evidence, not physical-display closure.
- [ ] Three physical displays and mirrored output, plus manual-position and
  no-duplicate recovery across the full matrix. Automatic unplug/rehome and
  reconnect restoration are now covered by
  `receipts/candidate-monitor-auto-rehome-2026-09-18.md`.

## Virtual-display validation

The Mac acceptance run may use a system-recognized virtual display for the
topology portion of this gate. macOS exposes display objects through
`NSScreen`, and the placement adapter consumes that topology directly. A
Sidecar iPad or AirPlay display exercises the same system display list; a
BetterDisplay virtual screen is a practical option when no second Apple
device is available. Record the provider, screen IDs, scale, visible frames,
and the connect/disconnect timestamps in the receipt.

Virtual displays can prove screen enumeration, placement, mirroring, manual
frame preservation, and reconnect recovery. They cannot close the physical
GPU/audio, cable/EDID, sleep/wake, or long-term daily-driver portions of the
gate. Those still require the actual monitor matrix.

Capture a current read-only topology receipt from the Mac with:

```sh
scripts/run_display_topology_probe.sh > /tmp/mortimer-display-topology.json
```

The probe records display IDs, localized names, frames, visible frames,
backing scale, and main-display state. It explicitly records that Spaces are
not screens; it never moves windows or changes display settings. Run it from
the logged-in Aqua desktop; a shell running without a WindowServer session can
legitimately report zero screens and is not a multi-display receipt.

The first 2026-09-18 probe reported one built-in display; a later probe reports
`NSScreen.screens.count == 2`: Built-in Retina Display (ID `1`) and `C34H89x`
(ID `3`, frame origin `x=-844, y=1107`, scale `1.0`). The receipts are
preserved at `receipts/display-topology-2026-09-18.json` and
`receipts/display-topology-2026-09-18-two-screen.json`.
macOS Spaces/desktops do not add entries to `NSScreen.screens`; they are useful
for focus, window persistence and return-to-conversation checks, but cannot
substitute for a second display in this acceptance gate.
When a
Sidecar, AirPlay, or BetterDisplay screen is connected, capture the provider,
screen IDs, scale, visible frames, and connect/disconnect timestamps in the
receipt; keep the physical row open until that evidence exists.
- [ ] A single Developer/self-edit run that reads multiple files renders one
  outer result window with appended sections, and a second run remains a
  separate panel. Supporting tiles and the legacy fallback are inspected with
  Liquid Glass enabled and disabled; every tile follows the same setting.
