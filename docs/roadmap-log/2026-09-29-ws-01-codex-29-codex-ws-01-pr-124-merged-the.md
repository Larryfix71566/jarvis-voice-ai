---
date: 2026-09-29
system: codex
rows: [WS-01, WS-08]
prs: [124, 115]
---

- 2026-09-29: Codex / WS-01: PR #124 merged the action-claim repair claim. The bounded worker fix now settles self-edit and app-build terminal action receipts before publishing terminal job state under the same job lock. Four barrier tests cover success and error ordering; 97 focused admin tests pass. The full Mac unit run had 4,740 passes, three skips and two out-of-scope failures (audio-filter shared state; deploy-script log flush); Linux CI and merge into WS-08 PR #115 remain open.
