# Candidate monitor unplug acceptance — 2026-09-18

Candidate: release-review `MortimerHost.app` (exact path used by the live
inspection). Baseline topology had two displays: built-in Retina plus the
external `C34H89x` at `3440x1440`.

After the external cable was physically unplugged, the topology probe reported
one display (built-in Retina only). The candidate's main console then exposed
the existing `Memory graph is on the supporting display` locator and `Return
here` action. Activating `Return here` moved the memory graph and Mortimer
response into the main workspace; the display window closed, leaving one
bounded in-window presentation and no duplicate window.

The candidate showed `ERROR VOICE` / `Socket is not connected` during this
observation. That is recorded as a separate live voice/reconnect failure; it
does not invalidate the observed display fallback. Reconnect, role restoration,
and voice recovery remain open.
