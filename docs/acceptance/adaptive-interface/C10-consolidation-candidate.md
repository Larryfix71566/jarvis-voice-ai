# C10 release consolidation candidate

Prepared 2026-09-17 from application source `5faa2e6`. These changes are
pending verification and publication; this document is not deployment proof.
The production checkout and its five local patches have not been reset.

## Existing production behavior to preserve

- `bundle.sh`: the candidate already includes the framework-copy and
  missing-WebRTC refusal. Keep its additional nested signing and verification.
- `progress_watcher.py`: carry the local live event count and last tool name,
  so running work no longer reports zero tools merely because its run has
  not finished. Add a synthetic SQLite regression covering two runs and an
  unfinished tool call.
- `admin/server.py`: carry submit-result diagnostic notices, captured under
  the finish-job lock along with state/run identity. Add an error-result test.
- Launchd template: preserve `/usr/sbin:/sbin` in PATH.
- `prompts.py`: **Larry explicitly chose on 2026-09-17 to preserve current
  behavior**: speak the self-edit preview and begin sandbox work in the same
  turn, using the exact staging ID; review/merge remains human. The separate
  confirmation for creating a new application remains intact.

These are proposed reconciliations in the release candidate. The installed
checkout stays untouched until the candidate has passed checks and the
coordinated deployment is ready. A patch being carried here is not evidence
that a running process has loaded it.

## Additional release corrections

Crossed/equal waveform level windows currently turn any positive input into
full deflection. The candidate restores the measured channel defaults in
that case and keeps the two slider bounds ordered while dragging. Regression
checks cover both channels, equal and inverted windows, zero input and
preserved level variation.

The audio report adds a minimum of 100 distinct buffer arrivals per channel
before a latency pass. This is an operational sample floor, not a statistical
confidence guarantee. It reports level-present activity coverage over the
60-second/30-Hz window; coverage is not a dropped-buffer measurement. The
50 ms observer-arrival threshold is unchanged and is not screen-render
latency. Existing saved reports retain their original meaning.

Bundling records source revision, optional sandbox candidate digest, Git
dirty/unknown status and build configuration before signing. A non-launch
mode allows packaging and signature verification without interrupting the
running app. The source/digest must come from the release driver's frozen
candidate; metadata is provenance, not an independent attestation.

A native interaction fixture exercises the supporting display's Original
display panels button with synthetic research. It checks the rendered button,
original result identity, pins and reading position in legacy/adaptive modes
and emits screenshots. This covers part of C8; it does not replace physical
monitor recovery, VoiceOver use, or the complete preservation matrix.

## Deployment checks still owed

Use `RELEASE_READINESS.md`. In particular, verify the production configuration
keeps the intended absolute database and wake-model paths: the earlier wrong
DB repair was a local `.env` repair, not a new bot environment-precedence
implementation. Never print credential values. Do not replay missed memory
extraction without the separate data-recovery decision.
