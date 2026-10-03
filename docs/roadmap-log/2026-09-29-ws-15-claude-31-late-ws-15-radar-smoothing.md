---
date: 2026-09-29
system: claude
rows: [WS-15]
prs: []
---

- 2026-09-29 (late, WS-15 radar smoothing): Claude (Cowork). Larry: the weather card works, but radar comes up slowly and flashes. Cause in code: each loop step removed the shown radar overlay and added the next one before its tiles were loaded, and no tiles were kept. Now all frames stay on the map with only the shown one visible, tiles are kept per map and warmed across frames after the visible tile loads, the loop steps only to loaded frames, and the card says "Loading radar…" until the first frame is in.
