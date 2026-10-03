---
date: 2026-09-29
system: claude
rows: [WS-06, WS-14]
prs: []
---

- 2026-09-29: Claude (Cowork). WS-06 check #2 traced on the Mac with Larry. There were three causes:
  1. The CLI isn't on the launchd PATH. Larry linked it into `/opt/homebrew/bin`.
  2. The bot strips `USER`, so the CLI can't find its Keychain sign-in (`Not logged in`).
  3. The command variable fed only the installed check, and the probe discarded the runtime's failure category.

  Added WS-14 and CX-13 for fixes 2 and 3. Larry decided Claude lands them and Codex reviews. Targeted tests pass: 95 total, 18 of them new; the related status suites give the same result before and after. Protocol note: while checking for overlapping edits, Claude compared `jarvis/subscription.py` hashes in Codex's worktrees (read-only). That goes against rule 9 and won't be repeated. Future overlap checks go through this file and open PRs.
