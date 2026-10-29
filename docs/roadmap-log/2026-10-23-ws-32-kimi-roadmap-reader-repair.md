---
date: 2026-10-23
system: kimi
rows: [WS-32]
prs: [275]
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

`git diff --check` passes. The roadmap checker had no WS-32 finding but reported
the inherited WS-05 stale `claimed` status after #264 merged. That other owner's
row was preserved here and the drift was resolved separately.

## Post-merge reconciliation

[PR #275](https://github.com/Larryfix71566/jarvis-voice-ai/pull/275) merged at
2026-10-27 01:47:56 UTC with merge commit
`51a3f567d6f1f0ad1dc085cdc1127260cefffb77`. The merge commit is an ancestor of
inspected main `18dad604852da7be72fc6ab2d92fc8728d2b5ca6`.

- Immutable implementation: `5c5cb2ee643655716774e05191e3c14c74504b05`.
- `mcp_servers/mcp_repo/logic.py` and the related reader test blobs are unchanged
  on inspected main.
- Post-merge focused repository/reader/event/plan-manifest pytest: **97 passed**.
- Post-merge strict roadmap checker: **zero errors, zero warnings**.
- All five recorded #275 checks passed: `allowlist`, `policy-tests`, `validate`,
  `controller-tests` and `knowledge-base`.
- Kimi posted a nonauthor exact-source review request on #275. The separately
  reviewed WS-05 metadata delta is not a verdict on the original reader source.

Independent exact-source review remains pending. Larry's merge is not that
review. No production deployment, live acceptance, roadmap-content trimming or
other-owner correction is included.
