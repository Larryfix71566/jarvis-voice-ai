---
date: 2026-10-05
system: claude
rows: [WS-17]
prs: []
---

- 2026-10-05 (WS-17 CC7a.3 Recents menu): Claude (Claude Code), branch `ws17/cc7a3-recents` from main `bde22bb`. Results ▾ becomes Recents: Pinned, then the newest 10 unpinned, numbered to match voice, with ages; Older lists the rest, so the bound removes nothing. Voice result actions (select, close, pin, unpin, compare) take a Recents number or subject as well as a UUID. The app resolves it to one UUID; an ambiguous match returns `needs_choice` with numbered choices and changes nothing. Pin and unpin now advance the inventory revision (Codex boundary 3). Plan §7.2 progress entry added. Codex reviews before merge; the Mac checks are in WS-17's next step.
