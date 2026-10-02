---
date: 2026-09-30
system: codex
rows: [WS-04]
prs: []
---

- 2026-09-30: Codex WS-04 selected the supervised local-only onboarding design in Addendum R2. It reserves `JARVIS_REMOTE_BIND_ENABLED` as a separate remote-listener gate, specifies vault/Keychain provisioning without an HTTP mint endpoint, and separates preparation from later local auth activation. This planning change creates no token, changes no runtime flag, and opens no listener; implementation and live acceptance remain open.
