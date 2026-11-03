---
date: 2026-11-03
system: claude
rows: [WS-13]
prs: []
---

# WS-13 — P3m (mail headlines on request) implemented, 2026-11-03

System: Claude (Claude Code cloud session; plan by Claude on Opus, implementation by a
Sonnet worker, reviewed by Claude). Branch: `claude/ws13-mail-on-request-20261103`.

## Change

- `daily_brief(scope="mail")`: a direct Supervisor tool behind `JARVIS_BRIEF_ENABLED`. It
  returns one fixed sentence before any mail is read, and refuses a session that is not a
  loopback native `/ws-client` session with zero source calls.
- A job in its own context (own `SensitiveTurn`, no foreground run log) makes one classified
  `mail_headlines` call and pushes a `confidential` typed `brief` card to the asking session.
  The card shows each account's status code and count (never a false zero) and up to ten
  literal headlines. The generic body carries fixed host text only.
- Prompt: with the tool on, mail questions go to `daily_brief` and the model never invents mail
  facts or availability. With it off, the assistant says "Mail isn't connected to me yet."
- Swift (untested): JarvisKit `DisplayPayload.brief`, MortimerHost `BriefCardView` (verbatim
  text, no selection), `DisplayContentView` dispatch, and `daily_brief` never opens by itself.

## Evidence

Offline on Linux, Python 3.12: see the PR body for the exact `pytest tests/unit tests/integration`
counts and the pre-existing failures that also fail on main.

## Remaining

- codex: review the R.0f deviations and the WS-17-file Swift lines.
- larry: `swift test` on the Mac, then the P3m Mac check (ask about mail; the card shows Gmail
  and AT&T with their real status). P1's M1-1 repeat stays open.
