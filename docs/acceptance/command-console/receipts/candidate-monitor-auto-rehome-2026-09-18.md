# Candidate monitor automatic rehome — 2026-09-18

## Result

Pass. The exact release-review candidate was running with the console on the
built-in Retina display and the memory graph in one bounded `Mortimer Display`
window on the external `C34H89x` display. The external monitor was then
unplugged without selecting the manual “Return here” action.

## Evidence

- Before unplug: the display topology probe reported two screens, including
  `C34H89x` at `3440x1440`; the supporting window exposed one memory-graph
  stage with `405 visible of 500 loaded nodes · 37 visible relationships`.
- After unplug: the probe reported one screen, the built-in Retina display.
- The accessibility tree then contained only the main `Mortimer` console; the
  `Mortimer Display` window was absent, and the graph controls/405-node graph
  were present in the console.
- No manual return or duplicate-window action was used in this run.
- Focused regression coverage: `ScreenPlacementTests` passed 9/9, including
  `testLostSupportingScreenRequestsDisplaySceneClosureBeforeFrameRecovery`.

This closes the physical unplug/rehome gate for the candidate. Reconnect
restoration was also verified in the same acceptance session; voice-triggered
repeat/provider-fetch instrumentation remain separate gates.
