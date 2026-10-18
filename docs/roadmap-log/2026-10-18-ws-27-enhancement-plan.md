---
date: 2026-10-18
system: codex
rows: [WS-27]
prs: [220]
---

# Mortimer subsequent enhancement documentation dispatch

Larry explicitly requested a new implementation plan at the end of the current
Git roadmap, a separate local-model runbook, and a dedicated voice evaluation
protocol. This creates WS-27 for documentation only on
`codex/mortimer-enhancement-plan-20261018`. Session:
`01a1140b-72bf-76bc-bc11-ac283fa6b0e2` (delegated task workspace).
The explicit new-plan dispatch supplies the bounded documentation authority;
the pre-merged-claim rule still applies to all future runtime work.

Read main `28420af29191716945e55f6aeec1f0fd125ea931`, AGENTS.md, CLAUDE.md,
ROADMAP protocol/active scopes/conflicts, docs navigation/architecture/repo map
and ALLOWLIST_SEQUENCE before editing. Used a fresh bare clone and isolated
worktree inside the task directory. Production and other agents' workspaces
were not modified. Read the published #218/#219 branches and GitHub PR metadata;
they were the only open PRs at preparation. #219's proposed WS-23–26 are not on
main and are cross-referenced, not duplicated or claimed. #210 merged unchanged;
its two recorded cleanup findings remain (no diff in sandbox/prune.py or
sandbox/verify.py from its head to this main). No pruning or image setup ran.

The canonical plan covers agent/workflow routing, measured sandbox voice
optimization and model comparison, local privacy, gated durable/recovery and
mail extensions, optional architecture and cloud exceptions. Two appendices
belong to the same plan: executable-instructions-only local setup, and a
reproducible sandbox evaluation protocol with empty result templates. Larry
agreed to baseline → shared sandbox optimization → model comparison; the
production pipeline and selection remain unchanged. Jev is ON HOLD.

Official-source checks are dated in the appendices. No performance results,
paid calls, installation, private records, credential/security changes,
acceptance closure, merge or deployment are claimed. Validation results will
be recorded below before publication.

## Larry's added acceptance-first/status-report scope

Larry subsequently requested an exhaustive acceptance backlog audit, fastest
clearance sequence at the front of the roadmap, and actual current status
updates in Git. Added the clearance design and full 97-source-bullet inventory
to the existing WS-20 joint plan (no competing acceptance plan), and reconciled
ROADMAP current summaries, IMPLEMENTATION_STATUS, Command Console status,
release-readiness counts/CC7a wording and runbook navigation. CX-23 records this
explicit documentation expansion and the #218/#219 boundary. Their branches,
implementation claims and parked proposals are unchanged. New enhancement
implementation remains at the end and gated.

Inspected 22 pre-existing rows: 14 with open obligations, seven closed and one
parked. 97 aggregate bullets are not 97 tests; 23 unique open UI2 requirement IDs
form the current release backbone, while 24 P0 rows and five C8 umbrellas overlap.
Release-readiness actual count is 34 unchecked / 19 checked. All original
ROADMAP and release-readiness checkbox tokens remain identical. No parent test
or acceptance gate closes by audit. The later source-only 563-test native
receipt and earlier physical OCR failures retain their separate applicability.
Mail D1–D9 already answered; R.12 supersedes old V1–V10; P2/P3 remain unbuilt.

Validation: `python3 scripts/check_roadmap.py --main main` reports zero errors /
zero warnings; `git diff --check` passes. A documentation link/scope audit found
all changed files Markdown, all local relative file links present, balanced
code fences, all 97 inventory rows present with consistent category counts,
and unchanged existing checkbox-state sequences. No runtime or live API suite
was run; no acceptance results, private records or provider workloads fabricated.

Published draft [PR #220](https://github.com/Larryfix71566/jarvis-voice-ai/pull/220).
The branch is mergeable at publication; GitHub checks were pending. No merge or
deployment was performed. Final local documentation checks pass.

## Publication-time main refresh

#218/#219 merged while #220 was publishing. Fetched and merged main `9ea27c7`
into this branch; resolved ROADMAP summary and joint-plan appended-progress
conflicts by preserving the restored intake, all four parked cards, WS-22
dependency note, both dated progress records and this newer acceptance audit.
Updated current statuses: 26 existing product/coordination rows = 14 current
open-obligation, seven closed, five parked. 112 unchecked workstream bullets
comprise 97 current obligations plus 15 parked future criteria; eight MAR summary
bullets remain duplicates. UI2/readiness counts and runtime source are unchanged.
Only draft #220 remained open at this refresh. All four restored parked blocks
are byte-identical to current main; all existing checkbox-state sequences match
current main. No implementation ownership, receipt or acceptance is lost.
