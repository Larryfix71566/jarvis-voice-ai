# External-display content policy receipt

Date: 2026-09-18  
Source: `logs/mortimerhost-window.log` and the two-screen acceptance notes.

The recent external-monitor exercise exposed a content-governance gap in
addition to the existing panel-identity gap:

- The same memory graph was visible in the main work surface and on the
  external display.
- The display window was re-added multiple times during a single attach cycle
  (`re-added-fullScreenPrimary#1`, `#2`, and `#3` at 16:05:47Z).
- At 16:18:40Z the console was reasserted against the 3440x1410 display, and
  at 16:20:05Z the display window attached there as well. This is evidence of
  unstable role placement, not evidence that the intended presentation policy
  is satisfied.

## New release gate

The external display is a curated presentation stage. Its default visible
budget is one active research, graph, or result presentation. The console,
complete sidecar, transient status panels, and duplicate graph windows remain
on the primary surface unless the user explicitly moves or pins them. Repeated
requests replace or focus the active presentation. An explicit pin/move is the
only path to an additional presentation.

The gate closes only with a Mac receipt showing, on one, two, and three
displays, stable console/display roles, the bounded default panel count,
repeat-request focus/reuse, explicit-pin behavior, and clean unplug/reconnect
recovery without duplicate fetch/subscription work.
