---
date: 2026-11-17
system: codex
rows: [WS-35]
prs: []
---

# WS-35 C10 external measurement claim

- Date: 2026-11-17 UTC.
- System: Codex.
- Session: parent thread `6afac5ab-3210-8191-a87a-f40521cd30ce`.
- Row/item: WS-35 / C10.
- PR: this claim-only PR into `main`.
- Authority: Larry approved a separate claim-only PR updating WS-35 ownership/location before harness edits; Codex waits for Larry to merge it. The implementation PR still targets `next` and contains no roadmap edits.
- Change: retain the existing `codex` Owner and all existing assignments; append follow-up branch `codex/ws35-c10-measurement-harness-20261117` to WS-35's Where line. This registration is prepared on `codex/ws35-c10-harness-claim-20261117`; its historical branch is kept here so the active row does not name a merged claim branch. No status line, checklist, plan, source, or test is changed.
- Follow-up boundary: evaluate external input-to-presentation measurement on an unmodified local build of `7e8adc9`; write the requested design note in `docs/roadmap-log/`. Only if demonstrated viable, prepare external tools, trace parsing, raw samples, nearest-rank percentiles and fixed synthetic actions under the separately dispatched C10 scope. If app changes are required, stop at the design note and return that decision to Larry. No deployed-app changes, deploy/bundle/start scripts, live voice, model calls, or external workload calls.
- Evidence: refreshed `origin/main` is `7e8adc9c294e82e673e69c3bc621d8f4f25af60b`; claim branch starts there and `git merge --no-edit origin/main` reports already up to date. Preliminary roadmap checks exited 1 before the claim commit (branch still pointed at main) and before adding this log's required front matter. Final checks and commit identity are recorded in the PR body.
- Reservations: none.
- Remaining: independent Kimi or Claude review and Larry's merge of this claim; then Codex may begin the follow-up. No C10 design, implementation, local app build, measurement, acceptance or deployment is claimed here.
