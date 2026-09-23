# Live candidate connection check

Date: 2026-09-18

The logged-in Mac inspection found the Mortimer application window running on
the two-display topology, but its connection view displayed:

> Mortimer stack isn't running — Start it with `./scripts/mortimer.sh`, then retry.

The read-only port check also found ports 7860, 7861, 8484, and 8487
unreachable at inspection time. This is a failed readiness check, not a
content-placement result. No UI2-06, UI2-19, or UI2-20 physical acceptance
claim is made from this session. The stack must be healthy before the panel
count, role, repeat-request, and reconnect scenarios can be exercised.
