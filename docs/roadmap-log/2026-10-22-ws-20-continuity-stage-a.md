---
date: 2026-10-22
system: codex
rows: [WS-20]
prs: [246, 247, 252, 260]
---

# WS-20: full historical testing plan and sanitized continuation adoption

System: Codex. Session: `01a16433-930e-7575-bc0a-11277e3a90e1`;
parent dispatch `01a1573e-ae10-7388-b7c4-e36ff49120e0`.
Publication branch: `docs/ws20-program-receipts-20261022`.
Refreshed base: `ab31dfa8ddf58ad0583afcb25dffd18afbee5765`, tree
`d92643125277273a59ec26fbb415c25d8b55bcb9`.

Stage A selectively adopts nine byte-exact historical attachments from frozen
#246 `028b44e11acff9dff3e00380e1624c8657ce545c`. The complete testing plan v2
is 105,892 bytes / 854 lines, SHA-256
`23fd4aed98c3e86a2d31ee4a4a0fa26568bd7de8c2a0fb7b330c8b8cce840343`.
The [existing joint plan's dated adoption section](../plans/ROADMAP_JOINT_WORKING_PLAN.md#historical-continuity-adoption-and-current-authority--2026-10-22)
links the complete plan, sanitized harness handoff/review state and five Skills
planning attachments, and records every original Git blob and SHA-256.
The documentation map adds one discovery link. No second plan or current
workstream tracker is introduced.

The coordinator's independent Codex `/root/integration_review` found **no
blocking findings** in exact local Stage A patch SHA-256
`d0d3b82ce7c2a3e6bf7edb75776cad2fe12278b1a43db1cc882de633b5e6e868`:
11 files materialized, nine source blobs/hashes/counts matched, and 17 relative
links/anchors resolved. That review covers the original Stage A proposal only;
this additional row/log publication bookkeeping needs independent review and
the published head needs fresh CI. Their exact receipts belong in the PR;
the earlier proposal review is not represented as review of later edits.

Both feature owners agreed to historical attachment adoption. The Skills owner
also approved bounded pointer text, to be added by that owner only after a
verified adoption-main receipt makes its relative link resolve. The coordinator
reserved the docs-map discovery bullet. Outside the standing WS-20 paths,
the authorized changes are therefore only `docs/README.md` and the nine exact
files under the two dated `controller-testing-proposal-2026-10-22` and
`compatibility-planning-2026-10-22` receipt directories. No feature-owner
canonical plan or row is changed; no shared number/config reservation is needed.

The attachments retain their historical labels and limits: the third Claude
plan review was REVISE, with no fourth review of final author clarifications;
historical source ACCEPT does not review later implementation. The 25 Skills
cases are proposed, not passed; landed #251/#258/#261 and 2/12 accepted gates
are preserved. Current #264/#266 source/claim gates remain with their owners.
No model switch, new Claude execution, benchmark, inference or runtime operation
is authorized or performed by this publication.

The newer #260 program remains intact. WS-20 still has **3/4 evidenced
milestones**; every checkbox remains unchanged. Stage B's #252 enforcement
receipt/checkbox synchronization and #247 UI2-23 runbook alignment are separate
review items, excluded here. Frozen #246/#247/#252 are not rewritten or merged
wholesale. Final live/hardware/observation evidence and Phase A/B remain open.

Next: independent bookkeeping review and exact-head publication CI, then the
sole coordinator's disposition and verified main receipt. Only after actual
adoption should the feature owners add their canonical-plan discovery pointers.
No installation, service/cleanup operation or release acceptance follows.
