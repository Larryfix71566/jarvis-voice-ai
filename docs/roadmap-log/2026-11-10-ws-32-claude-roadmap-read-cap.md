---
date: 2026-11-10
system: claude
rows: [WS-32]
prs: [275, 296, 322]
---

# WS-32 — roadmap reads carry the text once; read cap 1 MiB, Claude, 2026-11-10

System: Claude (Claude Code cloud session `session_01EHREEUSG5e6zqMeBYUecdg`, started from Larry's Claude Duet channel). Planned, measured and checked by the thread session; code and tests implemented by Claude Sonnet subagents from that plan.
Branch: `claude/ws32-roadmap-read-cap-20261110`, based on main `c5e1550`, PR #322.

Why: Larry, 2026-11-10, in his Claude Duet channel: at 14:51:35 UTC "The limit is causing more issues that it needs too"; at 15:24:22 UTC "Proceed"; at 15:41:01 UTC "Yes, fix it too", answering whether to also stop sending the roadmap twice per read.

## Change

1. `ROADMAP_READ_MAX_BYTES` (`mcp_servers/mcp_repo/logic.py`) goes from 384 KiB to 1 MiB. The host verifier in `jarvis/skills/registry.py` imports it.
2. A roadmap read result carries the text once. `_roadmap_snapshot` now returns a compact source snapshot, schema `mortimer.roadmap.source.v1`: provenance (including the text's sha256), the dated logs and the Git/log issues, with no cards. Cards are a pure function of the text, so the new `expand_roadmap_snapshot(content, source)` rebuilds the full `mortimer.roadmap.v1` snapshot from the single copy after checking the source schema, its exact keys and that the provenance sha256 matches the text.
3. The console still receives the complete v1 snapshot: `jarvis/agents/base.py` (the roadmap display event) and `jarvis/bot/display.py` (the console refresh) expand it. A failed check gives the existing "roadmap unavailable" result. No Swift change.

What the host attests is unchanged in mechanism: the registry rebuilds the compact snapshot from guarded disk reads and requires exact JSON equality with the result, and checks the text against the file byte for byte, as before. A forged `cards` key, an altered text and every earlier tamper case are refused (tests).

## Measured limits

Python 3.12, main `c5e1550` code ("before") against this branch ("after"), the same 302,915-byte `ROADMAP.md`, grown synthetically by appending copies of existing workstream cards under new ids ("card growth") or prose outside any card ("prose growth"). Each pair is the last accepted and first refused roadmap size in bytes. Not measured on a Mac.

| Path | Before, card growth | After, card growth | Before, prose growth | After, prose growth |
|---|---|---|---|---|
| Agent read through the host (1,000,000-character tool-result cap) | 359,294 / 368,686 | 902,223 / 922,512 | 389,395 / 411,015 | 908,275 / 929,895 |
| Console event and console refresh (1 MiB snapshot) | 359,294 / 368,686 | 559,193 / 600,991 | 389,395 / 411,015 | 908,275 / 929,895 |

Today's roadmap: sealed result 826,936 characters before, 379,372 after.

The agent limit stays under the 1 MiB read cap because the sealed result escapes non-ASCII characters (`ensure_ascii`) and carries the logs. The console limit for card growth is the existing 1 MiB snapshot bound, mirrored by the display-event bounds in `base.py` and the Swift `RoadmapPayload` check; raising it needs a Swift change that CI does not build, so it is left as is.

Evidence: see the PR body for the exact test commands and counts at the pushed head.

Not verified: the native console roadmap refresh on a Mac; no deployment or live test.
