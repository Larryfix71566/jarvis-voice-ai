---
date: 2026-11-24
system: claude
rows: [WS-37]
prs: []
---

# 2026-11-24: WS-37 follow glow drawn with masked spots (Claude)

- **System:** Claude (Claude Code cloud session, Opus 5.5).
- **Why:** with the glow on, Larry's Mac measured the follow probe at 3.92/12.899 ms p50/p95 against today's card at 0.899/0.991. #418 turned the glow off by default so the deploy could go ahead. This PR is the attempt to make it cheap enough to turn back on.
- **Suspected cost (a hypothesis, not measured):** the focus point was part of the stroke gradients, so every pointer move changed what the blurred band contained and the full-card blur ran again.
- **Change:** the rings, their blur and their colours stay fixed. Only a small white radial spot, used as a `.mask`, moves with the pointer. The rim is a fixed floor plus a masked peak, with spot stops (o - f)/(1 - f), so the composite reproduces the mockup's stops exactly; a new unit test checks that arithmetic. The glow is still off by default (`JARVIS_CAROUSEL_FOLLOW_GLOW`).
- **Not tested here:** no Swift toolchain in the session; CI compiles it and skips the frame-time test. Whether it is faster is unknown until the Mac runs the follow probe with the glow on.
- **Next actor:** Larry: on the Mac, run `JARVIS_CAROUSEL_FOLLOW_GLOW=1 swift test --package-path macos/MortimerHost --filter CarouselGlassFrameTimeTests` from this branch and compare the follow line with 3.92/12.899 ms. Merge whatever the result; turning the glow on by default is a separate decision.
