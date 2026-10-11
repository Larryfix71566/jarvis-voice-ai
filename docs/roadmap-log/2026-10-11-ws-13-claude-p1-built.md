---
date: 2026-10-11
system: claude
rows: [WS-13]
prs: []
---

- 2026-10-11 (WS-13 P1 built; PR open for cross-review): Claude (Cowork). P1, the read-only mail header source from plan section R.6, is built on ws13/p1-mail-headers: a new mcp-mail MCP server with one tool, mail_headlines, that reads unread-arrival counts and the newest senders and subjects per account over verified TLS, with the plan's command gate, per-phase byte budgets and abort table, per-account deadlines and watchdog, latch checks at every connection step, single flight per account, UTC windows, and content-free logs. The registry pins mcp-mail as a confidential source whose envelope carries the D4 level and the scope mail:<account> derived from the request; those are the only registry.py lines touched (CX-21, WS-05 reviews). Tests run against a scriptable TLS IMAP server with generated certificates and cover acceptance rows S1-1 to S1-9; the snapshot tests (requires_env, TOTAL_TOOLS 82, EXPECTED_TOOLS) are updated; scripts/check_mail_env.py is the names-only preflight for M1-1. An adversarial review pass before handoff found and fixed four defects (single flight admitted a second worker before start, a metadata-phase abort bypassed the 25-per-account cap, a SEARCH reply with no SEARCH line read as an exact zero, a socket timeout reported failed rather than timeout). Nothing contacts a real mailbox; M1-1 to M1-3 are Larry's Mac checks after merge and need the vault names from D6. P2 and P3 are not claimed.
