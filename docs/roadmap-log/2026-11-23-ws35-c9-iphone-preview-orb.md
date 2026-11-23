---
date: 2026-11-23
system: codex
rows: [WS-35]
prs: [411]
---

## C9: disconnected iPhone orb preview

- Adds an explicit start/stop for a synthetic-only orb in the disconnected iPhone preview. The waveform is deterministic, the decorative canvas is hidden from VoiceOver, and the preview stops when the app leaves the foreground. Reduce Motion renders a still with a text label.
- Moves the C6 drawing and crystal geometry into a local Swift package used by the Mac host and iPhone preview app. Existing Mac activity and theme inputs pass through an adapter; no change to the Mac voice view, layout or tuning. No network, pairing, mic access, live voice, or remote activation.
- Adds waveform and reduced-motion package tests, plus an iPhone UI test for explicit start/stop, banner retention and background/return. `git diff --check` and the roadmap checker pass (0 errors and warnings).
- Next: verify hosted Mac package tests, then build and run the iPhone preview UI test on an Apple simulator. Larry owns merge, any install and acceptance. No acceptance or device performance result is claimed.
