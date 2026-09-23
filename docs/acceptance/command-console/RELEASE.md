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
failures). (Reconciled 2026-09-22 against main `88b206f`: the committed
[`full-verification-2026-09-18.md`](receipts/full-verification-2026-09-18.md)
records 2,611 / 4, JarvisKit 190, and MortimerHost **244** executed (3
skipped, 0 failures). No committed receipt records 242. These are
receipt-time counts. At `88b206f` the static `func test` counts are JarvisKit
195 and MortimerHost 250, and on Linux `pytest tests/unit` gave 2,526
passed, run by Claude on 2026-09-22.) Swift
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
(Reconciled 2026-09-22: 2/2 has no committed log. The committed
`receipts/response-routing-2026-09-18/render-tests.log` records
`SupportingDisplayAcceptanceTests` 4/4, the file's current static count.)

The current candidate bundle launches cleanly after the `PanelStore`
environment-injection fix. Native transport unit coverage is 21/21, including
the main-actor CoreAudio-start regression, and the
live candidate reached the bot's WebSocket HTTP 101 handshake. The logged-in
desktop still needs one unlocked visual run to close bot-ready state, voice
exercise, and panel movement on the external display.

Reconciled 2026-09-22 against main `88b206f`:

- Transport tests: the 21/21 figure has no committed log. The committed
  `receipts/monitor-ownership-2026-09-18/audio-start-deadline-tests.log`
  records `NativeAudioTransportTests` 22/22. The file has 26 static tests at
  `88b206f`.
- Bot-ready state: the previous paragraph is superseded.
  [`candidate-live-response-display-2026-09-18.md`](receipts/candidate-live-response-display-2026-09-18.md)
  records the candidate at `READY VOICE` after a manual reconnect.
- Panel movement: the same receipt records the memory graph moved to the
  supporting display with a two-result stage and return locator.
  [`candidate-monitor-auto-rehome-2026-09-18.md`](receipts/candidate-monitor-auto-rehome-2026-09-18.md)
  records the graph on `Mortimer Display` on the external `C34H89x`.
- Still open: a spoken voice exercise (a new spoken request with output speech
  and both measured audio channels). The live-response receipt states that no
  live spoken response was observed. `READY VOICE` was also not stable across
  sessions: the unplug/reconnect receipts and
  `candidate-reconnect-attempt-2026-09-18.md` record `ERROR VOICE` or no
  settled ready state.
