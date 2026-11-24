---
date: 2026-11-24
system: claude
rows: [WS-37]
prs: []
---

# 2026-11-24: WS-37 carousel follow glow off by default (Claude)

- **System:** Claude (Claude Code cloud session, Opus 5.5).
- **Why:** Larry's deploy of `next` at `e655fbe` stopped on `CarouselGlassFrameTimeTests.testFollowGlowStaysWithinTenPercentOfTodaysCard`, the test's first run anywhere (hosted CI skips it). His second run, alone on the Mac (2026-11-24 16:37 UTC, Claude Duet channel): today 0.899/0.991 ms p50/p95, crystal with the glow suppressed 0.762/0.864, crystal with the follow glow 3.92/12.899. The follow glow is reproducibly about 4x today's card and its p95 is over a 120 Hz frame.
- **Change:** `OrbGlassCardSettings.followGlowEnabled` (environment `JARVIS_CAROUSEL_FOLLOW_GLOW=1`, or `defaults write com.mortimer.host JARVIS_CAROUSEL_FOLLOW_GLOW -bool true`; absent means off). With it off the lit card keeps all of its static crystal layers and the arrival sweep; only pointer tracking stops, and the hover handler writes nothing. The Reduce Motion even rim is unchanged. `orbGlassCard` gains an optional `followGlow:` override for tests.
- **Gate:** the frame-time test now gates the shipped card, the lit card exactly as `ResultCarouselView` builds it with the setting as found, at p50 and p95 <= today x 1.10. The follow probe (glow forced on) is still measured, printed and written to `carousel-glass-frame-time.json`, and is gated only when the setting is on. Test name unchanged.
- **Not tested here:** no Swift toolchain in the session; CI's Swift jobs are the compile run and skip the frame-time test. The shipped number has not been measured on the Mac; the crystal probe it closely matches passed there (0.762/0.864 against a 0.989/1.090 limit).
- **Next actor:** Larry: merge, then rerun the deploy's MortimerHost tests.
