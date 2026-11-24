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
- **Measured on the Mac (Larry, 2026-11-24 19:24 UTC, at 4ba18e6, `JARVIS_CAROUSEL_FOLLOW_GLOW=1`):** today 0.898/1.008 ms p50/p95, crystal with the glow suppressed 0.734/0.822, follow 0.773/0.837, shipped 0.745/0.828. The test passed with the follow probe gated. The follow glow went from 3.92/12.899 ms to 0.773/0.837, which is under today's card and about 5% over the crystal card without the glow. CI compiles the change and skips the frame-time test; this Mac run is the only measurement.
- **Not changed:** the glow is still off by default. Turning it on is Larry's decision.
- **Next actor:** Larry: merge, and decide separately whether the glow should ship on.
