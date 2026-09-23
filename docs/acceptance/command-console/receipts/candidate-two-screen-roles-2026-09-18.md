# Candidate two-screen role receipt

Date: 2026-09-18

The release-review candidate (`macos/MortimerHost/.build/MortimerHost.app`)
was connected to the local bot while the Mac reported two displays. The
candidate window log records the current stable role split at `17:10:46Z`:

- Console: external `C34H89x`, visible area `3440x1410`, `fullScreenPrimary`.
- Supporting display: built-in Retina panel, visible area `1710x1016`, with
  `no-fullScreenPrimary`.
- Both windows reached their five-second settled log entries without another
  attach/re-add cycle in this run.

This is placement and role evidence only. No research, memory-graph, repeat
request, explicit-pin, unplug/reconnect, or duplicate-fetch scenario was
exercised, so UI2-06, UI2-19, and UI2-20 remain open.
