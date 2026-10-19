---
date: 2026-10-19
system: codex
rows: [WS-17]
prs: []
---

# Current-request foreground implementation checkpoint

Session: `01a1140b-72bf-76bc-bc11-ac283fa6b0e2`; isolated implementation branch
`codex/ws17-current-request-arrival-20261018`, based on merged claim #225
`c244963`. Wire reservation `b587cd5` precedes source edits. Candidate request
IDs are host-owned and ephemeral, captured synchronously at real accepted-input,
aggregator and SDK function dispatch boundaries. The native router matches exact
input/session/generation/request identity and permits one foreground winner.
Fresh weather reuses the original native UUID/source time/expiry. Unknown,
background, superseded, cancelled and duplicate arrivals preserve focus;
supporting-display ownership and independent Atlas navigation remain protected.

Exact baseline and candidate reproduce the execution-sandbox XCTest allocator
abort. The identical normal-host baseline command passes eight cases; candidate
focused native verification passes 41. Final focused Python verification passes
135. Later final-source full suites and independent review remain pending.
Original failures are retained locally; no test assertion, runtime check,
skip list, budget or timeout was weakened. No source-policy, model, endpoint,
credential, installation, production/history, deployment or live-acceptance
change occurred. Only source/synthetic tests may enter the review packet;
raw production logs and operational metadata remain local.

00:54 UTC checkpoint: 206 final focused Python tests pass. The same single
SDK/transport/router/store second-city witness fails two baseline foreground
assertions and passes the candidate; its test-only baseline overlay was removed.
The 36 affected native regression/private-capture cases pass with all privacy
assertions intact. Original full-run failures are preserved and classified in
the existing plan; final-source full clean-host suites and review remain open.
