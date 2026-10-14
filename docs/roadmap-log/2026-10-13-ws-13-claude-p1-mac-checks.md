---
date: 2026-10-13
system: claude
rows: [WS-13]
prs: [204, 205]
---

- 2026-10-13 (WS-13 P1 Mac checks M1-1 to M1-3 pass): Claude (Cowork). Larry ran P1's three Mac checks on 10-13 against the deployed 575cc7b. M1-1: with the four mail names in the vault, the corrected preflight showed each reaching mcp-mail and none of the other 14 servers, with env scoping on. M1-3: bellsouth.net (imap.mail.att.net, secure mail key) and Gmail (app password) both returned status ok with exact counts and complete headers in 3.1 to 3.6 seconds; the first Gmail attempt failed login_rejected, and a names-only diagnostic showed why without printing either value: the user was not the full address and the stored password was not an app password. Both were corrected in the vault, and Larry changed his Google account password before creating the app password, since the account password had been stored briefly. M1-2: one unread test message per account was still counted UNSEEN on a second read (exact 1 on both), so the headers read set no Seen flag, and Larry confirmed both still unread in webmail. The bot log shows mcp_server_started name=mcp-mail tools=1 at the first session after the deploy. Codex's review of #204 revision 3 and of #205 remain open.
