---
date: 2026-10-22
system: codex
rows: [WS-05]
prs: []
---

# WS-05 — 2026-10-22

Claimed bounded selective-policy correction on existing WS-05 branch after
fast-forward to main fccb760. Only direct Anthropic/OpenAI APIs are retired;
other recognized providers retain their existing explicit routing and gates.
No protected endpoint changes, native/installer edits, live inference or
service operations. Release owner retains guarded installation/restoration.

Implemented protected endpoint recognition, SAYGM catalog-policy compatibility
and redirect refusal. Reproduced five failing cases before repair; 243 focused
synthetic tests pass. Full offline and publication checks pending.
