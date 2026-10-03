---
date: 2026-10-02
system: codex
rows: [WS-05]
prs: []
---

- 2026-10-02 (WS-05 MAR-E/F readiness): After MAR-A baseline PR #165 merged as `ecdf3a3`, Codex used the Mac vault only for a read-only SAYGM catalog request and public synthetic subscription probes. SAYGM authenticated and listed 64 models with no confidential model advertised. Claude Max account status reported signed in, but both isolated and direct inference failed authentication (direct HTTP 401). Codex CLI reported ChatGPT sign-in, while Mortimer's adapter remained gated pending no-tools verification. See `docs/acceptance/model-use-enhancements/receipts/model-access-live-readiness-2026-10-02.json`. Routing and production settings remain unchanged.
