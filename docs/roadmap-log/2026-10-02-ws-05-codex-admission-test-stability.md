---
date: 2026-10-02
system: codex
rows: [WS-05]
prs: [162]
---

- 2026-10-02 (WS-05 test stability): PR #162 replaces the priority test's fixed 20 zero-delay ticks with a two-second deadline for worker-thread waiter registration, preserving its capacity and ordering assertions. Thirty focused repeats and all 38 model-execution tests passed locally. MAR-A route rollout and live account gates remain open.
