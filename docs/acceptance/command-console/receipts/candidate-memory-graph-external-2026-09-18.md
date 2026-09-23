# Candidate memory-graph external-display receipt — 2026-09-18

## Artifact

- Candidate: `macos/MortimerHost/.build/MortimerHost.app`
- Source base revision: `b224c84` with the release-review working-tree changes
- Hardware: logged-in Mac with the connected external display
- Backend: local bot on `127.0.0.1:7860`

## Observed sequence

1. The exact candidate opened in the compact Conversation view and reached
   `READY VOICE` after the native audio device settled.
2. Selecting **Memory graph** loaded the native graph in the primary surface:
   404 visible nodes of the 500-node cap and 37 visible relationships.
3. Choosing **Display → Show memory graph** moved the graph to the supporting
   display. The external window visibly rendered the graph canvas, controls,
   filters, node list, and the same 404/37 summary. The primary surface did
   not open a second graph window.
4. The fresh multi-result stage implementation was built in the same candidate;
   its bounded scrolling grid no longer produced the prior negative-geometry
   AppKit messages during this run.

## Remaining failure

After the session had remained active for several minutes, the native socket
ended with `NSPOSIXErrorDomain Code=57 (Socket is not connected)`. The app
returned to its error/reconnect state while the graph remained available in
the primary surface. This leaves display-close/reconnect recovery and the
long-lived native-session gate open; it is independent of the external graph
rendering pass above.

No credentials or memory contents were written to this receipt.
