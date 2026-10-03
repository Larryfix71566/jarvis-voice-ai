---
date: 2026-10-02
system: codex
rows: [WS-05]
prs: [162]
---

- 2026-10-02 (WS-05 test stability): PR #162 merged as `30ac2c7`, replacing the priority test's fixed 20 zero-delay ticks with a two-second deadline for worker-thread waiter registration while preserving its capacity and ordering assertions. Thirty focused repeats, all 38 model-execution tests, and all five CI checks passed. MAR-A route rollout and live account gates remain open.
