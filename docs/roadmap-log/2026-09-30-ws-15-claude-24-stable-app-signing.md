---
date: 2026-09-30
system: claude
rows: [WS-15]
prs: []
---

- 2026-09-30 (stable app signing): Claude (Cowork). Larry: the app asked for microphone and location on every deploy. Evidence: `codesign -d -r-` showed `designated => cdhash H"74b9..."`; bundle.sh signed ad hoc, so each rebuild was a new app to macOS. New `scripts/setup_signing_identity.sh` creates a local code-signing identity once per Mac; bundle.sh signs with it when present and falls back to ad hoc otherwise. Codex: bundle.sh is shared release tooling.
