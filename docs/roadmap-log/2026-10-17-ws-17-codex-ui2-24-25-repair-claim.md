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


## Roadmap access and awareness follow-up

Larry asked Codex to ensure Mortimer has roadmap access and knows it. A read-only
probe of `mcp_servers.mcp_repo.logic.repo_read_file("ROADMAP.md")`, with the
repository root explicitly set to production, succeeded: 154,209 bytes, WS-17
present. No contents were sent to a model or printed. Developer has `mcp-repo`
in its configured roster; map injection exists in both developer loops. The
injected map previously contained no `ROADMAP.md` reference, and neither did
the Supervisor/Developer prompt instructions. Source navigation now documents
the existing route; the pending claim explicitly covers the missing prompt
routing and focused tests before code edits. This is not proof that a running
Supervisor has loaded the new instructions. Deployment/restart and an actual
voice check remain separate, and the #210 deployment caution is unchanged.


## In-app roadmap view authorized

Larry additionally requested the display capability. Added a bounded WS-17
scope and acceptance checklist to the same pending claim and canonical plan:
voice-opened, expandable read-only workstream cards, provenance/refresh,
complete document coverage, and existing results/share/supporting-display
behavior. Code inspection found the existing `repo_read_file` display route
clips at 30,000 characters; simply displaying the full-file response would
hide later roadmap sections. A dedicated bounded presentation must preserve
all source workstreams instead. No runtime code or wire identifier is added
in this claim; runtime implementation waits for the claim on main.


## Roadmap filters added to the implementation plan

Larry requested the previously discussed filters. The existing §7.2 roadmap
view specification now includes blockers, Larry's acceptance/decision items,
current ownership, topic/open status, named-workstream checklists, completion
and dated changes. Defined source evidence, prerequisite distinctions, AND/OR
combination, voice refinement, visible chips/counts, reset, empty states,
refresh/transfer preservation and filtered sharing. Added fixtures/acceptance
requirements and the matching WS-17 checklist item. Documentation only; no
filter runtime, source status or acceptance gate was changed.
