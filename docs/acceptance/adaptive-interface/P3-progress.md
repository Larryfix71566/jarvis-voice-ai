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

Next work: rendered scroll/resize/rollback acceptance, sources/inspector and
graph modes, full preservation inventory and accessibility/performance checks.
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
