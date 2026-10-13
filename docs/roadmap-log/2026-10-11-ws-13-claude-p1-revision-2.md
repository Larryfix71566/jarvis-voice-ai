---
date: 2026-10-11
system: claude
rows: [WS-13]
prs: [204]
---

- 2026-10-11 (WS-13 P1 revision 2 answers Codex's review): Claude (Cowork). Codex reviewed PR #204 at 454d856, accepted both registry decisions (mcp-mail outside EXTERNAL_TOOL_SERVERS; request-derived mail:<account> scopes) and requested five P2 corrections and one P3, each reproduced on the Mac. Revision 2 answers all six with regression tests: a message that vanishes between the INTERNALDATE pass and the header FETCH is removed and the count downgraded per R.10.13, never kept as a blank headline in a complete result; every SEARCH token and UIDVALIDITY must be an RFC 3501 nz-number, so malformed data is failed/unknown and only a genuinely empty SEARCH is an exact zero; the surviving-worker cleanup shares one one-second deadline, so the call returns within the call deadline plus one second with any number of stuck resolvers; every socket-close path (a shutdown() override covering imaplib's constructor-failure and LOGOUT paths, the handshake-failure close, close_socket) releases the watchdog registration before the descriptor closes, under the watchdog's lock; the M1-1 preflight prints the forwarding matrix for every configured server plus the effective scoping flag, tested with scoping on and off; and a server BYE during LOGIN is reported server_abort, not login_rejected. The unidentified macOS OSError seen in two Mac test runs remains unexplained; the result records the exception type and errno (content-free) so the next Mac occurrence names it. Nothing contacts a real mailbox.
