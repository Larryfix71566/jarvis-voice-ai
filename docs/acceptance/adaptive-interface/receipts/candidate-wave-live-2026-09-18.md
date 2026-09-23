# Candidate measured-wave inspection — 2026-09-18

## Artifact

- Source base revision: `b224c84` (`MORTIMER_SOURCE_REVISION` used by the
  bundle script); the bundle includes the current release-review working-tree
  changes listed by `git status`.
- Candidate: `macos/MortimerHost/.build/MortimerHost.app`
- Launch mode: debug bundle, no automatic launch from the bundle script

## Observed sequence

1. The candidate opened in the Command Console's **Conversation** view with
   the compact rail visible.
2. The app connected and exposed `READY VOICE`.
3. With the microphone disabled, the rail reported `MUTED` and the trace held
   its quiet baseline.
4. Enabling the microphone changed the accessibility state to `HEARING YOU`,
   exposed `Mic on`, and produced a visible measured cyan lobe in the compact
   rail.
5. Disabling the microphone returned the state to `MUTED`; after the pending
   turn settled, the rail reported `Microphone muted` and `Standing by`.

No user speech was injected during this inspection, so this receipt proves
live eligibility and the measured input presentation path only. It is not a
playout/amplitude receipt and does not close the two-channel P2 arrival-count
gate. The microphone was left disabled.
