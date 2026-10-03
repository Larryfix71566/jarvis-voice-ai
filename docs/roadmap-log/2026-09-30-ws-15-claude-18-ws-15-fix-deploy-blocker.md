---
date: 2026-09-30
system: claude
rows: [WS-15]
prs: []
---

- 2026-09-30 (WS-15 fix, deploy blocker): Claude (Cowork). DEPLOY-MAIN for `1a0aac7` stopped on `RadarTileStoreTests.testDroppedDecodedTilesComeBackWithoutADownload` (kept PNG missing, second download). The radar kept PNGs in an `NSCache`, which may evict under memory pressure. Now a dictionary with an explicit 64 MB budget, oldest first, plus a budget test. Radar behaviour otherwise unchanged.
