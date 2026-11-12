---
date: 2026-11-11
system: codex
rows: [WS-35]
prs: [334]
---

# WS-35 C10 baseline preparation

Codex prepared `docs/acceptance/ws35-c10-freeze-performance-baseline.md`: exact frozen-source component probes, installed-app provenance, the six-result/graph/attachment/voice scene, measurement boundaries, repeated runs, accessibility matrix and receipt checklist. Review: Kimi. Session: `codex/ws35-c10-baseline-20261111`, Larry's 2026-11-11 starter-prompt dispatch.

C10 measurements are not run. Larry captures the verified freeze baseline before C1a merges. Missing full-scene instrumentation is a blocker, not a pass; existing component probes are explicitly not substituted for it. No source, deployment, model or runtime setting changed. #334 remains the independent contract-review handoff; this is a separate C10 item.

Integration: merged the Codex #334 review branch into this documentation branch so #334 then this C10 PR can land serially without losing either WS-35 update. Both review findings and baseline gates are preserved; no runtime changes were imported.

- 2026-11-12 (Codex, WS-35 C10, #335): Larry requested reviewer-ready draft promotion. Exact prior head `745b76b649dea9b08cb39f8a518d8c44d11c2579` had green hosted workflows and no merge conflict. This handoff changes documentation only; source and prior test evidence are unchanged. Kimi reviews the instructions; Larry captures the freeze baseline before #337 merges. Reviewer-ready is not approval to merge or live acceptance.
