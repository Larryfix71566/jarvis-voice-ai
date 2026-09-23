# Live response/display ownership check — September 18, 2026

Candidate: `macos/MortimerHost/.build/MortimerHost.app` PID 82363,
executable SHA-256:
`81cdfb0efeabfec9b9c83a3e4661f04fa708d82303ff6be2d5df0463faaea4aa`.

The candidate was manually reconnected and reached `READY VOICE`. With the
existing response card and memory graph loaded, the graph was sent to the
supporting display. Native accessibility inspection then showed:

- Main console: `READY VOICE`, `Display window is open`, `Mortimer response`,
  `Memory graph is on the supporting display`, and `Return here`.
- Supporting display: `Supporting display · 2 results`, one memory-graph tile,
  and one Mortimer response tile. No sidecar, nested information window, or
  extra floating result appeared.

This proves live window ownership and the bounded two-result composition for
the current session. It does not prove a new spoken model response, physical
unplug/reconnect recovery, mirrored/three-display behavior, or final release
acceptance.

The supporting window was then closed through its native close control. The
main window remained at `READY VOICE`, retained the selected response, and
rendered the memory graph in the main surface without creating another
window. This verifies the live close-and-return path for the current session.
