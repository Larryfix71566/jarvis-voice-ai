# Supporting-stage live inspection — 2026-09-18

## Observed sequence

- The rebuilt release-review candidate connected to `READY VOICE`.
- Pointer navigation opened the Memory graph in the main Command Console.
- `Display → Show memory graph` opened one `Mortimer Display` window.
- The display contained one rendered graph with the `Memory graph — SUPPORTING
  DISPLAY` header, graph controls, 404 visible nodes of the 500-node cap, and
  no sidecar, console, nested information window, or panel fan-out.
- Closing the display returned the graph to the main surface. During this
  exercise the client then reported `ERROR — Socket is not connected`; the
  local bot process remained listening and the candidate was restarted cleanly
  afterward. This leaves reconnect-after-display-close as an open physical
  acceptance item.

This receipt proves the single-stage renderer and bounded graph presentation
on the connected Mac. It does not prove stable reconnect, repeated-request
deduplication, or three-display recovery.
