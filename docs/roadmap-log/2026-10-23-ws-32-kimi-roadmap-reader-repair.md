---
date: 2026-10-23
system: kimi
rows: [WS-32]
prs: []
---

# WS-32 bounded roadmap source growth repair

Claim #274 merged as `ae035dec57c0eef32cbc5fd38e477f52c3d07441`; implementation
started from that exact main on `fix/ws32-roadmap-reader-limit-20261023`.

The base's 262,207-byte `ROADMAP.md` failed both current-repository reader and
projection tests. Direct diagnosis found a 419,939-byte complete snapshot and a
415,707-byte ordinary-turn projection, within their existing 512 KiB and
600 KiB ceilings. No source was trimmed.

The repair adds a separate 384 KiB canonical-roadmap source bound. The ordinary
256,000-byte limit remains unchanged for every other path and for roadmap logs.
Both the pre-read stat guard and second raw-read race guard use the appropriate
bound. No Base, UI, provider, configuration, credential, access, deployment or
acceptance behavior changed.

Red/green: on unpatched `ae035de`, the two new regressions and two existing
current-repository regressions fail (4 failed, 24 passed across the focused
files). On the candidate, 90 focused repository/reader/event tests pass.
Full offline results: 7,085 unit passes, 11 skips and 29 subtests; 197
integration passes and four skips; 13 offline eval passes. Fixture latency
enforcement and frontend build pass. No live tests were run.

`git diff --check` passes. The roadmap checker has no WS-32 finding but reports
the inherited WS-05 stale `claimed` status after #264 merged. Per C1/C2 that
other owner's row is unchanged and the finding is recorded here. Independent
exact-source review and exact-head CI remain required before Larry merges.
