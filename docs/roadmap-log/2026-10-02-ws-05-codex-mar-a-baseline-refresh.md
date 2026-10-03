---
date: 2026-10-02
system: codex
rows: [WS-05]
prs: []
---

- 2026-10-02 (WS-05 MAR-A baseline refresh): Codex reconciled deployed `ae70f2c` with main `bd41b5e` and the isolated branch, matched five current launchd service PIDs to the clean deployment receipt, and reran the production and candidate model-call-site audits at 28/28. The read-only ledger has 15 provider calls since deployment, including eight LLM calls, but no populated model-call duration, route, or billing-source fields. A separate ten-call, public, tool-free synthetic direct-API probe recorded five exact matches each for Haiku and Sonnet, with median call durations of 508.3 ms and 994.0 ms. MAR-A remains open for representative quality and production attribution; no production writes occurred.
