---
date: 2026-11-10
system: claude
rows: [WS-32]
prs: [275, 296]
---

# WS-32 — canonical roadmap read cap raised to 1 MiB, Claude, 2026-11-10

System: Claude (Claude Code cloud session `session_01EHREEUSG5e6zqMeBYUecdg`, started from Larry's Claude Duet channel). Planned and checked by the thread session; code and tests implemented by a Claude Sonnet subagent from that plan.
Branch: `claude/ws32-roadmap-read-cap-20261110`, based on main `c5e1550`.

Why: Larry, 2026-11-10 14:51:35 UTC, in his Claude Duet channel, after being told that `ROADMAP_READ_MAX_BYTES` (384 KiB) makes the reader refuse `ROADMAP.md` once it grows past it: "The limit is causing more issues that it needs too". At 15:24:22 UTC he answered the plan to bring this PR before the freeze SHA with "Proceed".

Change: `ROADMAP_READ_MAX_BYTES` in `mcp_servers/mcp_repo/logic.py` goes from `384 * 1024` to `1024 * 1024`, equal to `ROADMAP_SNAPSHOT_MAX_BYTES`. The host verifier in `jarvis/skills/registry.py` imports the same constant, so it follows without an edit. Unchanged: the 256,000-byte cap for every other file, stat-before-read and the second-read race check, the 1 MiB parsed-snapshot cap, the 1024-file / 4 MiB log caps, the display-event caps in `jarvis/agents/base.py` (1 MiB snapshot, 1200 KiB envelope), the Swift `RoadmapPayload` check (encoded payload at most 1 MiB, `macos/JarvisKit/Sources/JarvisKit/AppMessage.swift`) and the host tool-result cap (`_MAX_RESULT_CHARACTERS = 1_000_000` in `jarvis/privacy_policy.py`).

Which limit binds after this change. Measured with Python 3.12 against main `c5e1550` by growing the real `ROADMAP.md` synthetically, either by appending copies of existing workstream cards under new ids or by appending prose outside any card; not measured on a Mac:

| Limit | Applies to | Card growth: last accepted / first refused roadmap bytes | Prose growth |
|---|---|---|---|
| Host tool-result cap, 1,000,000 characters of the sealed result (`sort_keys`, `ensure_ascii=True` JSON of content plus snapshot) | every scoped `repo_read_file('ROADMAP.md')` through the registry, which is how agents and the console read it | 357,172 / 366,564 | 478,057 accepted |
| Snapshot cap, 1 MiB | every read, scoped or direct | 556,010 / 597,808 | not reached below 1 MiB |
| Read cap, now 1 MiB (was 384 KiB) | every read | above both | 1 MiB |

Today's 301,854-byte roadmap gives a 519,580-byte snapshot and an 823,292-character sealed result. Before #318 the 357,442-byte roadmap gave 906,984 characters, still under the cap.

So for agents and the console this change adds headroom only when the roadmap grows outside workstream cards (up to about 478 KB instead of 384 KiB). When it grows inside cards, the host tool-result cap was already the binding limit below 384 KiB and still is, at about 357 to 367 KB. The sealed result is large because it carries the roadmap twice: once as `content` and again inside the snapshot's card `details`.

Not changed, and why:
- The host tool-result cap also bounds what enters model context and the subscription transport buffers (`jarvis/model_execution.py`, `jarvis/subscription_tools.py`); raising it would send more than a million characters of roadmap into a model turn.
- The snapshot cap is mirrored by the display-event bounds and the Swift payload check; raising it needs a Swift change that CI does not build or test.
- Removing the duplicated roadmap text from the agent-facing result would move the real limit, but it changes what the host attests and seals, so it is a separate decision.

Evidence: see the PR body for the exact test commands and counts at the pushed head.

Not verified: the native console roadmap refresh on a Mac; no deployment or live test.
