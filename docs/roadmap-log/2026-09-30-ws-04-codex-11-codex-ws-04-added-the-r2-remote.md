---
date: 2026-09-30
system: codex
rows: [WS-04]
prs: []
---

- 2026-09-30: Codex WS-04 added the R2 remote-bind gate on its isolated branch. With `JARVIS_AUTH_ENABLED=true`, a remote host still resolves to loopback unless `JARVIS_REMOTE_BIND_ENABLED=true`; auth-off remains loopback regardless. Existing remote tests now opt in explicitly. Focused auth/bind/caller/bot tests pass 109/109, including the real admin and bot startup host arguments; no token or production setting changed.
