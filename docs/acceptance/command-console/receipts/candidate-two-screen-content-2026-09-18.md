# Candidate two-screen content receipt

Observed: 2026-09-18T17:13:14Z

This receipt records a focused inspection of the release-review candidate after
the two-screen role run. It is evidence for the content-governance behavior,
not a claim that the full physical-display gate is closed.

## Observed behavior

- The candidate was connected and displaying the Command Console conversation
  surface with the sidecar still available.
- The main console retained a locator for the transferred result:
  `Research — Friends TV show plot cast seasons air dates` and a
  `Return here` affordance. The main surface did not open a second copy of the
  supporting card or a sidecar/transient fan-out.
- The focused `Mortimer Display` window contained one bounded research card
  with its result text and links. The display window exposed one pin action and
  one close action; no additional graph, console, sidecar, or transient windows
  were present.
- The supporting window was otherwise empty, giving the presentation a clear
  single-stage budget instead of reproducing the whole console.

## Acceptance effect

This supplies physical candidate evidence for a bounded one-presentation
stage, the main-surface return locator, and suppression of automatic sidecar or
transient-window fan-out for this scenario. It does not close UI2-19/UI2-20:
repeated-request focus/reuse, explicit pin duplication, duplicate
fetch/subscription instrumentation, unplug/reconnect recovery, and the
one/three-display matrix still require dedicated acceptance runs.
