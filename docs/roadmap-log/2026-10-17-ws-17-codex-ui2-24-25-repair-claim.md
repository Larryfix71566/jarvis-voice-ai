---
date: 2026-10-17
system: codex
rows: [WS-17]
prs: [213]
---

# UI2-24/25 repair branch and scope claim

Larry's dispatch is merged as `c097ee0` (#213). Codex claims
`codex/ws17-ui2-24-25-repair-20261017` from that main revision, preserving the
diagnosis's slice order 3.2+3.5 → 3.3 → 3.1 → 3.4(b). The existing Command
Console plan §7.2 records the approved context-stub amendment, its boundaries
and evidence requirements. The WS-17 row now names the actual branch and the
bounded prompt/evaluation/context paths before code edits. No shared numbers
are reserved; no implementation, provider run, deployment or gate closure occurs.

#209 merged as `a9701c2`; correct the stale open-PR wording in Codex's WS-17 row
and preserve the receipt qualifications. #210 merged unchanged as `34e5d55`:
`git diff 8842503..c097ee0 -- sandbox/prune.py sandbox/verify.py` is empty.
Both recorded cleanup findings therefore remain, notwithstanding the merge.
They are outside WS-17; this claim neither edits that code nor enables cleanup.
WS-13's stale #212 handoff remains with Claude. The two-city title/rows
observation remains open and can run on the already installed app without
first deploying main.
