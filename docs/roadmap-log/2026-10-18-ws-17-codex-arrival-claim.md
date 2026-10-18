---
date: 2026-10-18
system: codex
rows: [WS-17]
prs: []
---

# Proposed current-request arrival claim and foreground-policy decision

Session: `01a1140b-72bf-76bc-bc11-ac283fa6b0e2`; delegated workspace task-3.
Refreshed main `d38c88646113cf27fd5b165f08f4739d3fe6ca01` and open PRs;
only draft #224 was open. No competing arrival implementation was found.
WS-28 is explicitly limited to cleanup and does not cover UI repair. WS-17's
registered branch currently covers cross-review/release verification.

Prepared a minimal claim-only proposal under WS-17 and CX-25. The approved
plan/UI2-23 rule says weather requested while another result is being read
raises New without taking focus. The proposed exception would open only a
result proven to complete the active explicit request. That requires Larry's
policy/claim decision before code, while unrelated/background, superseded,
stale/cancelled arrivals and supporting-display ownership retain protection.

The existing plan carries the proposed policy and deterministic synthetic
caller-chain verification requirements. Proposed implementation branch:
`codex/ws17-current-request-arrival-20261018`, inactive until approved and
registered on main. No other owner, acceptance checkbox or current no-jump
criterion changed. No new plan, wire identifier or shared number is introduced.

This PR contains repository policy/claim text and synthetic scenarios only.
No production log, transcript, result UUID, service metadata, credential or
private runtime receipt is included. No source/test edit, provider call,
runtime change, merge or deployment occurred.
