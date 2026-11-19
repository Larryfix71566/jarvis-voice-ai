---
date: 2026-11-19
system: claude
rows: [WS-38]
prs: [400]
---

# 2026-11-19 · WS-38 request resolution design note

- **System:** Claude (Opus 5.5, Claude Code cloud session for Larry's Claude Duet channel).
- **Row:** WS-38, added as `proposed` under §0 rule 13 for an option write-up. No source paths claimed.
- **Larry's words (UTC, Claude Duet channel):** 03:04:04: "perhaps we need a workflow for requests that is persistent and works thru a loop to ensure he gets to resolution istead of giving up after a single try, thoughts". He then gave a thumbs-up to a design note with options before any code.
- **PR:** #400, on `claude/request-resolution-design-note-20261119`.

## Change

- New design note `docs/reviews/2026-11-19-request-resolution-design-note.md`: options and recommended picks for tool fallbacks (1A), failure classes (2A), a bounded attempt ledger for delegated work (3B) and a done-check (4C), with a flow diagram, hook points, costs and rows.
- New WS-38 block in `ROADMAP.md` §2, status `proposed`.

## Evidence

- The 2026-11-18 21:51 ET weather request, read from Mortimer's run log and bot log on the Mac at about 03:20 UTC on 2026-11-19: `local_weather` failed in about 2 ms with its reason redacted; the analyst got `weather_reuse_invalid_request` 4/4 and repeated identical calls; `voice-explain-failure` was injected at 21:51:08 and 21:55:35; three developer runs followed, and the last one refused a code change as based on a false premise. Details are in the note's §3.
- Code read at `origin/next` `530f06c8`.

## Remaining

- larry: pick options in the note's §11.
- Then an implementation claim with branch and scope. No code is part of this PR.
