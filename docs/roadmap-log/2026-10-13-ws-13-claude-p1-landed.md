---
date: 2026-10-13
system: claude
rows: [WS-13]
prs: [204]
---

- 2026-10-13 (WS-13 P1 landed and deployed; M1-1 preflight fixed): Claude (Cowork). Larry merged #204 as 575cc7b (head 8b77df1, revision 3) and deployed it with DEPLOY-MAIN on 10-13: verification on 575cc7b passed 6,678 Python tests plus the JarvisKit and MortimerHost suites, the receipt reports no problems, and the five services and the app restarted on the merged build. GitHub records no formal approval of revision 3; Codex's review of 8b77df1 is requested post-merge. The bot log shows the bot booted on the new code but no skill-server start since, because the shared registry starts with the first session; mcp-mail's start is still to be observed. Larry's M1-1 run on the merged build printed PASS with no mail name set, which proved nothing: nothing was forwarded anywhere, mcp-mail included. The follow-up makes the preflight say NOT TESTED in that case, adds a --sentinel mode that sets placeholder values in-process only to check forwarding before the vault holds real ones, and builds the environment the way the run scripts do (.env over the shell, then the vault) so the effective scoping flag is the bot's. M1-1 to M1-3 remain open. Nothing contacts a real mailbox.
