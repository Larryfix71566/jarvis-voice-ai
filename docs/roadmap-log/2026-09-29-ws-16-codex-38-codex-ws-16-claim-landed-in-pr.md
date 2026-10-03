---
date: 2026-09-29
system: codex
rows: [WS-16]
prs: [116]
---

- 2026-09-29: Codex WS-16 claim landed in PR #116 (`5182bdf`). Codex changed only the protected-window test fixture: protected and body-only payloads now render in the same live window; the full-frame exact comparison remains, with bounded pixel-difference diagnostics. Full MortimerHost passed 374 tests, seven skipped, zero failures. The capture test skipped because this shell's test host could not activate, so foreground capture and DEPLOY-MAIN remain open.
