# Performance acceptance

The graph timing gate remains p95 <= 33 ms with a sensitivity control proving
the measured span includes drawing work. Attachment quotas are bounded at
12,000 text characters and 8 MiB per image. Full six-panel plus maximum-load
voice performance still requires the Mac candidate session.

- [x] The latest clean native run measured 300 graph pan/zoom frames at p50
8.544 ms, p95 9.908 ms and max 13.147 ms on the Apple M5 host; the 33 ms
  gate passed. The complete receipt is
  `docs/acceptance/adaptive-interface/P4-frame-time.json`.
- [ ] Combined six-panel, maximum attachment batch and active-voice stress
  measurement on the installed Mac candidate.
