# WS-35 C6: frame-rate-independent easing (scope decision, 2026-11-13)

Row: WS-35. Plan item: C6 (glass energy orb on the Mac), `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md`. Builder: whoever builds C6, into `next`. This is a decision record for the daily batch to fold into the C6 plan row and the WS-35 row. It changes no code.

## Decision

Larry, 2026-11-13 20:05:53 UTC, answering "Should the easing fix go into C6, even though it changes the ported numbers?": "Add it to C6".

C6 adds one frame-time helper. Every per-frame easing step in the orb and wave becomes scaled by the time the frame actually took. The orb spec's per-frame numbers are restated in time-based terms. This deliberately changes the spec's "port as written" rule (`docs/interface-research/orb-plasma/ORB_SPEC.md` item 2) and its flash-cap wording (item 6). Larry approved both changes. Nothing else in C6 changes.

## Why (checked on `next` at `b17842c`)

- `macos/MortimerHost/Sources/MortimerHost/Console/VoiceWaveView.swift` line 72 redraws at `1.0 / 60` when active and `1.0 / 15` when idle.
- Lines 242 to 263 ease by fixed factors per frame: level `0.45` rising and `0.06` falling, dynamics and colour `0.06`, stage centre `0.12`.
- So the same fade runs about four times slower when idle (about 0.27 s active against about 1.08 s idle for the `0.06` step).
- The source finding is the igloo.inc review, revision 2 (`/mnt/project-files/mortimer/igloo-review-2026-11-13.md`, finding F4): igloo's bundle defines `damp(k, r) = 1 - exp(log(1 - k) * r)` with r = frame delta ÷ (1000/60).

## What C6 restates

The reference rate is 60 Hz, the active redraw rate above. With dt the frame's measured duration in seconds and r = dt × 60:

- **Easing factor k per frame** becomes `1 - (1 - k)^r`. This applies to the wave's `0.45`, `0.06` and `0.12` steps and to the demo's colour and level easing.
- **Fixed step per frame** (the arc-end depth walk, ±0.025 per frame in spec item 3) becomes that step × r.
- **Flash cap** (spec item 6): the anchor's limit of 4% of Lref per frame becomes 4% × r; the decay `Lref = max(0.995·Lref, L)` becomes `0.995^r`. The 220 ms reversal limit and the ±3% clamp are already time- or level-based and stay as written.
- **Reduce Motion** (spec item 9) "every 6th frame" is a frame count. C6 decides whether to keep it or restate it as 0.1 s. If it is restated, C6's PR says so.

C6's own tests should show one fade taking the same time at 60 Hz and 15 Hz. That claim is untested until C6 runs it.

## Also noted from the same review (not part of this decision)

Shader warm-up with an opaque-glass fallback if compiling fails, and corner brackets on the focused carousel card for C5. Neither is decided here.
