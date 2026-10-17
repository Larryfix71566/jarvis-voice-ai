---
date: 2026-10-17
system: claude
rows: [WS-13]
prs: [204, 205]
---

- 2026-10-17 (WS-13 #204 revision 3 signed off; #205 revision 2): Claude (Cowork). Codex signed off #204 revision 3 (8b77df1) on re-review: the six original findings and the header-FETCH rejection case are addressed. Codex then requested two corrections to #205 at 47f588a, both reproduced with temporary configurations and fake values. First, the preflight's minimal .env parser kept an inline comment in the value, so a scoping switch written as false with a trailing comment read as on and could print PASS while the bot runs with scoping off; the preflight now has the startup shell load .env exactly as scripts/run_bot.sh does and reads the result back, and reports NOT TESTED when that environment cannot be established (no .env, or a .env the startup shell fails on). Second, a config without the mcp-mail entry printed PASS; that is now a FAIL checked first. Regression tests compare four shell forms with the startup shell's own result; seven of the eight new cases fail on 47f588a. The formal M1-1 repeat from production follows the merge.
