---
date: 2026-09-29
system: claude
rows: [WS-14, WS-15]
prs: [102]
---

- 2026-09-29 (later): Claude (Cowork). WS-14 landed (PR #102, `eb24e81`) and was deployed. The live daily check now shows the Claude subscription `ok: true`. Added WS-15 (proposed), Larry's weather rework: "current" weather took its place from memory (Spartanburg) because the device-location resolver feeds only `system_status` and the weather tools take only a city name; the app's location permission has read `not_determined` since 09-28; the radar symptom still needs Larry's description. Evidence came from read-only reads of logs.
