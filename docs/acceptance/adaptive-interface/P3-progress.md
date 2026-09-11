# Central workspace implementation progress

Status: partial implementation, available through an explicit Debug-menu
preview, not accepted or enabled by default.

The app owns a session-only WorkspaceStore. The single message router assigns
a UUID receipt and supplies it to the workspace and the existing destination
store. Existing integer IDs, surface routing and drawer attention behavior
remain compatible. Payload content is not persisted.

The store preserves active and comparison selections on arrival, keeps pinned
results under a finite pin cap, remembers scroll metadata, bounds other history,
and keeps explicit return-to-conversation intent. Central close cannot clear
Output. The new WorkspaceView renders tabs, pin controls, a comparison menu,
wide two-pane and compact A/B presentations using DisplayContentView.

Six focused state tests pass in the offline VM. The full MortimerHost suite
runs 51 tests with eight assertions still failing in the existing new header
accessibility fixture. No tests were skipped. The workspace view compiles.
Latest log: sandbox task `66fed310bde6`,
`interface-checks/p3-workspace-view.log`, SHA-256
`2e2a9f1bdb6e6ac8bae8d47b92143bbf07e9b844a5c1bea20b300f3d24914e27`.

The adaptive console is now connected through `mortimer.interface.layoutVersion`.
Missing/invalid values preserve the previous layout; Debug has a reversible
preview switch. Conversation uses the large wave with a small Mortimer label.
Workspace uses a 200-point left voice rail when it fits, or a bottom voice
region. Compact status retains captions, each existing satellite, confirmation,
mute/wake labels, speaker/input/output notices including reconnect/dismiss,
ambient information and machine vitals. MicControls remains outside the stage.
The shared content renderer now binds scroll observation/restoration to the
workspace's per-result metadata. This has compiled but needs rendered testing.

Check `p3-adaptive-console` ran 51 tests with the same eight header assertions
failing; no new suite failure. Log SHA-256:
`017dcc4493b839f46adcd2507e52bebb09756e87292c54a2a881c3837b510e37`.

Next work: rendered scroll/resize/rollback acceptance, full preservation
inventory and accessibility/performance checks. Sources, export and graph modes
have since been implemented as recorded below and in P4-progress.
The wave still uses the legacy simulation pending P2; the preview is not proof
of dual-speaker audio feedback. P3 is not complete.

The header harness issue was subsequently resolved; the final check for this
iteration, `p3-console-header-labels`, passed all 51 host tests with zero failures.
Log SHA-256:
`b95a7f8d3e0fb8def1dbdd194416fd33ffec238e5b0d33729aa7b6609e4f1a31`.
See P0-P1-progress for the precise harness correction and remaining coverage.

Header work is preserved separately on `feat/adaptive-interface-header`, WIP
commit `741b823`. Workspace work is stacked on `feat/adaptive-workspace`.
Neither branch is a release candidate; no merge or deployment occurred.

## Source inspection and explicit export follow-up

Starting application commit `4da1af7`, stacked development branch
`feat/adaptive-result-details`. No merge, deployment or default enablement.

- Result panes expose Summary (the existing complete renderer), Sources and
  Connections where a memory graph is supplied. No generated summary, inferred
  source date/excerpt or extra model request is introduced.
- Sources retain supplied titles/URLs, readable invalid addresses and explicit
  Open source actions for HTTP(S) only. Selection opens a 300-point inspector
  when the pane is at least 820 points wide; otherwise it uses a sheet. Long
  details scroll while Done stays visible. No existing sidecar tab is replaced.
- App-owned per-result state retains mode, selected source, inspector intent and
  source-list scroll position during comparison or supporting-display moves.
- Export opens an explicit native Save dialog. It writes supplied text, source
  and image/basemap reference URLs, manual command text/notes and truncation
  notices to a plain-text file. Images are not downloaded; clipboard content is
  always excluded. No new auto-save/session persistence is introduced.
- The save coordinator outlives the result view. Destination acceptance precedes
  writing; completion is reported only after an atomic write succeeds. Failure
  and cancellation have separate messages. Concurrent export is disabled.

Prepared offline VM, sandbox task `66fed310bde6`, synthetic fixtures only.
Full `swift test --package-path macos/MortimerHost`:

- Final check `p3-source-inspector-final`: 84 tests, zero failures, 8.423 seconds
  verifier duration; SHA-256
  `7928c8f8ae648d270752a07ce0ddb0b8472d70c55ec911564e2294188bbc61e4`.
- Added checks cover per-result view-state ownership, source-address handling,
  supplied-field export, clipboard exclusion, actual file contents after save,
  failed writes without false success, and synthetic native source renderings.
- No tests were removed, skipped or relaxed. This update touches host code only;
  the prior complete library run remains 103 tests, zero failures (P4 record).

Visual fixtures: source list at 480×500 points and selected inspector at
1,100×500, both inspected by the implementing assistant. PNGs are retained in
sandbox `.build/interface-fixtures` and thread `work/source-fixtures`.

- `workspace-sources-480.png` SHA-256: `7d9ebbcc7e9b7fca5b8a1ab176e2ae68fb09c1f248ac650e80ad111f0e40e14d`.

- `workspace-sources-1100.png` SHA-256: `796aa12c9e60e7b41fa51b0dba33bdb270bf2b084501f71a8d4cefcbf84ea94b`.

Still pending: interacting with the narrow inspector sheet, keyboard/VoiceOver
navigation, native Save destination/cancel/overwrite behavior, export during
window closure/reparenting, actual result scroll restoration, the full payload
and monitor matrix, and final performance/privacy/regression gates. Synthetic
renderings and the tested write seam do not establish those checks. Real audio
metering remains P2 work; this follow-up does not complete the full plan.

## Readable-width correction

Starting application commit `934ebe8`. AdaptiveLayoutMetrics accounts for the
480-point readable result target plus workspace padding, resize handle, voice
rail, comparison spacing and divider. At a 900-point window the adaptive docked
drawer is limited to 378 points without changing its saved width. The previous
layout keeps its previous width policy. Explicit resizing starts from the actual
visible edge and commits only on drag end; passive window shrinking does not
replace the saved preference. A larger window restores the requested width.

The left rail requires a 713-point stage. Side-by-side comparison requires 993
points inside workspace padding; below this it uses existing A/B tabs. Toolbar
controls wrap into two rows rather than squeezing labels at narrow widths.

Offline sandbox task `66fed310bde6`, final full host check
`p3-readable-width-final`: 90 tests, zero failures, no skips. Log SHA-256:
`8dbf3e77dd041bf9f2c77369eb262999688b3ec927881ed364848384270fd1e9`.
Policy tests exercise requested drawer widths across supported window widths,
preserved preference, and rail/comparison boundaries. Native WorkspaceView
fixtures at 512×450 and 1,100×450 points show narrow results and wide comparison;
initial renderings were visually inspected. The final rerender also includes
left-aligned toolbar placement and the corrected comparison threshold.

- `workspace-readable-512.png` SHA-256 `85a903462dadf7d98e196b9672611febdc4308e481dde759afa9febd67a26253`.

- `workspace-readable-1100.png` SHA-256 `fe85e0bfdc99f36c9f8c5ae3ffa287c64b3838bbc08e3ef0c1465f563165304e`.

These fixtures cover the workspace region, not the full 900×600 console with
voice controls and sidecar. Full-window height, large-text/VoiceOver and actual
pointer resize/dock/monitor interaction remain acceptance items. All P0/P2/P6
and other open requirements remain open; nothing was merged or deployed.

## Saved compact conversation preference

The adaptive preview now offers Keep voice compact / Expand voice during
conversation. The additive boolean preference persists the choice; results still
use the responsive rail/bottom presentation. No audio path or workspace identity
changes are part of this addition.

Sandbox check `p3-compact-conversation` completed with 97 host tests and zero
failures. Log SHA-256:
`53cd29bf8d9133bded137282ce3056d4267caa9a91847c278a04d894a9ff3b87`.
The native test mounts both saved preference values and checks the accessible
control label and unchanged conversation selection. Both 1000×600 offline
renderings were visually inspected. This does not prove actual toggle interaction,
minimum-width controls, live audio, or full-console acceptance. The wave remains
simulated pending P2; this preference is not evidence of measured metering.

## Compact conversation interaction and narrow controls

The native fixture now includes an existing research result and remembered scroll
position, exercising all three conversation controls at stage widths 512 and
1,000 points in both saved modes. It checks each control's accessibility frame
is inside the window, invokes the actual accessibility press action on the mode
button, and verifies the opposite control label, persisted preference, unchanged
active result, remembered scroll and conversation selection after rendering.

Full host check `p3-compact-interaction`: 97 tests, zero failures; verifier 11.275
seconds. Log SHA-256:
`9361c13635861fd2225b0ee6f646bb0d3d3f7b800e2f93e70c6b47b43656a545`.
The 512-point compact rendering was visually inspected: all three labels fit,
conversation copy wraps, and the existing compact status/agent scroll region
occupies the bottom beside the wave. This closes the earlier untested toggle
activation at these sizes. It does not establish mouse/keyboard traversal,
full-console minimum-height acceptance, accessibility text scaling, scrolling all
status notices, monitor recovery, or any real audio requirement.
