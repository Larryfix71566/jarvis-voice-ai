---
date: 2026-09-30
system: claude
rows: [WS-18, WS-17]
prs: [140]
---

- 2026-09-30 (WS-18 added, in review): Claude (Cowork), at Larry's request. Crash at 18:09:08 after an AirPods to Mac speaker switch: engine rebuilt, Voice Processing downlink state fault, no output IO, `AVAudioPlayerNode.play()` raised `player did not see an IO cycle`. Fix: start the player only once output IO is seen to flow (watch rebuilds a stalled output, 3 tries then a visible session failure) and catch the Objective-C exception around `play()`. Rollback switch `JARVIS_AUDIO_OUTPUT_WATCH`. WS-17 row updated: CC7a.1 landed (#140) and deployed (`39fc6f9`).
