---
date: 2026-10-17
system: claude
rows: [WS-13]
prs: [205]
---

- 2026-10-17 (WS-13 preflight revision 3 as a new PR): Claude (Cowork). #205 merged as 9f9bc71 at revision 2 before Codex's re-review arrived with two further corrections, so they go in a new PR, ws13/p1-preflight-rev3, from main 7324d56. First, the preflight overlaid the startup shell's environment on its own, so a name that .env unsets at startup (an inherited mail credential or scoping switch) stayed visible; it now replaces its environment with the startup snapshot, keeping only the interpreter's own bookkeeping, and the vault then fills what is missing as at startup. Second, a relative --env-file was looked up after the loader changed into the file's directory; it is made absolute first. Both have regressions that fail on 9f9bc71. The row replaces the stale merge-#205 handoff. The formal production M1-1 repeat follows the next deployment; the recorded deployment is still 575cc7b.
