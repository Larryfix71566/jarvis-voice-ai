# Release acceptance

The implementation is compiled and unit-tested in the release-review worktree.
Command Console layout version 2 is now the user-directed native default, with
legacy layouts still available through Debug. Production release sign-off is
separate: the remaining UI2 rows require exact-candidate evidence, rollback
record, deployment hash, user visual acceptance, and the five-day daily-driver
period; provider-backed transfer remains feature-gated until those checks pass.

## Reproducible sandbox checks

From the repository root, the current automated evidence is reproduced with:

```sh
UV_CACHE_DIR=/private/tmp/jarvis-uv-cache uv run --with-requirements requirements-lock.txt pytest -q
swift test --package-path macos/JarvisKit
swift test --package-path macos/MortimerHost
npm ci --ignore-scripts --prefix web
npm run build --prefix web
```

The current 2026-09-18 run produced 2,611 Python passes / 4 skips, 190 JarvisKit
passes, and 242 MortimerHost tests executed (3 display-dependent skips; 0
failures). Swift
runs require macOS;
the Python command uses the locked dependency set. These commands are
sandbox evidence, not substitutes for the physical display, OS picker,
VoiceOver, rollback, independent-receipt, or daily-driver gates listed in
`STATUS.md` and `RELEASE_READINESS.md`.

The architecture-context acceptance is included in this evidence: the full
Python suite covers the bounded self-edit injection and `/api/architecture`
source/digest contract, JarvisKit covers native decoding, and MortimerHost
compiles the Repo sidecar's expandable architecture view.

The latest read-only display receipts are
`docs/acceptance/command-console/receipts/display-topology-2026-09-18.json`
and `docs/acceptance/command-console/receipts/display-topology-2026-09-18-two-screen.json`;
the latter confirms two system-recognized displays. The live
`ScreenPlacementTests/testConnectedExternalDisplayIsExposedToPlacementTopology`
check also passed against that two-display session. Three-display and
mirrored-output requirements remain open; automatic unplug/rehome and
reconnect restoration are covered by the candidate monitor receipts.

The content-policy observation is recorded separately in
`docs/acceptance/command-console/receipts/display-content-policy-2026-09-18.md`:
the external display currently needs one curated outer stage with a bounded
multi-result tile budget and stable console/display roles before physical
acceptance can close UI2-20.

The supporting-stage implementation now also covers the legacy pointer path:
when `WorkspaceStore.supportingContent` points to a graph or result, the main
surface keeps a return locator and the supporting display renders one bounded
outer stage instead of an empty window or nested information window. The
focused supporting-display acceptance is 2/2, including the four-result
visible-grid regression; the physical content-policy and
the live provider/voice and duplicate-fetch gates remain open.

The current candidate bundle launches cleanly after the `PanelStore`
environment-injection fix. Native transport unit coverage is 21/21, including
the main-actor CoreAudio-start regression, and the
live candidate reached the bot's WebSocket HTTP 101 handshake. The logged-in
desktop still needs one unlocked visual run to close bot-ready state, voice
exercise, and panel movement on the external display.
