# Candidate external-stage observation — 2026-09-18

This receipt records the live external-display observation made while the
external `C34H89x` monitor was connected. It is evidence for the bounded
supporting-stage renderer, not a complete UI2-06/UI2-19/UI2-20 physical pass.

## Topology

The read-only topology probe reported two non-mirrored displays:

| display | role | visible frame |
| --- | --- | --- |
| Built-in Retina Display (display 1) | secondary | `x=0, y=56, 1710×1017`, scale 2 |
| C34H89x (display 3) | macOS main | `x=1710, y=-333, 3440×1410`, scale 1 |

Probe output is preserved in
`display-topology-2026-09-18-current.json`.

## Exact candidate observation

Candidate bundle:

`macos/MortimerHost/.build/MortimerHost.app`

The display scene was opened from the candidate console while the topology
above was active. Computer-use accessibility state for the focused window was:

- window: `Mortimer Display`, scene id `display`;
- role label: `SUPPORTING DISPLAY`;
- content: `Memory graph`;
- graph summary: `404 visible of 500 loaded nodes · 37 visible relationships`;
- no console, sidecar, transient status panel, or nested information window was
  present in the display scene;
- the scene exposed only graph controls (back, refresh, browse/filter, zoom,
  fit, reset layout, image fallback, focus and depth).

The screenshot showed one full-stage graph renderer with the shared dark glass
surface and no fan-out. Closing the display returned the same graph controls to
the main console; reopening restored the single supporting-stage scene.

## Limits

The candidate's voice state was `ERROR VOICE` with `Socket is not connected`
during this observation, so no voice-triggered repeated-result or provider
journey was claimed. Exact frame coordinates for the focused window were not
available through the accessibility tree; the topology and role receipt are
therefore separate evidence. Unplug/reconnect, one/two/three-display role
recovery, repeated-request fetch instrumentation, and multi-result physical
grid evidence remain open.
