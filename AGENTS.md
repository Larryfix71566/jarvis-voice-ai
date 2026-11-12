# AGENTS.md

Instructions for **Codex** and any other non-Claude agent working in this repository. Three AI systems (Codex, Claude and Kimi) and one human (Larry) work on this repo. The coordination rules below are binding. They exist because the systems have already collided: see `scripts/deploy_main.sh`, the note dated 24 Sep, and `docs/reviews/CROSS_SYSTEM_PLAN_EVAL_2026-09-27.md`.

## At the start of every session

1. `git fetch origin`, then read `ROADMAP.md` as it is on `origin/main`: §0 (protocol), §2 (workstreams), §4 (conflicts).
2. Find the row your task belongs to. It must show owner `codex`, and its `Where` must match your branch. If no row matches, **stop and tell Larry.** Do not start.
3. Merge `origin/main` into your branch before editing anything. Resolve conflicts by keeping the intent of both sides; never take one side wholesale. `ROADMAP.md` §4 lists the files where both sides carry fixes.
4. Read the `Scope` of every other active row. Those paths are locked. Do not edit them.

Resolve the open conflicts assigned to `codex` in `ROADMAP.md` §4 before starting any new feature work.

## While working

- **One plan per row.** Do not create a new plan, index or "gap" document for work that already has a row. Progress reaches the row's plan only through the daily batch PR (see *Status records and the daily batch* below).
- **Reserve shared numbers first.** Migration ids, self-edit allow-list rows, launchd labels, ports and new config keys go into `ROADMAP.md` §3 before you write them in code.
- **Commit at the end of every slice** on your branch. Push when credentials exist; otherwise say in your summary that Larry needs to push. Do not keep uncommitted work across sessions.
- **Never edit `~/jarvis-voice-ai-clean`.** It is production, and changes reach it only through `scripts/deploy_main.sh`.
- **Stay out of Claude's work.** Do not read or write Claude's working folders or patches (`Claude outputs/`, `closure-checks/`, Cowork VM paths). The one exception is a read-only review Larry asks for. Work reaches you through `ROADMAP.md` and PRs only.
- **Assignments prevent overlap; they are not exclusive, and a code-only freeze may apply.** Any system not currently engaged may pick up work another system is not engaged with, after updating the row's Owner and Where; no system reviews its own work. Once Larry records a freeze SHA in WS-17, no PR that changes files outside `docs/` and `ROADMAP.md` merges unless Larry approves it by name as an acceptance fix; docs-only PRs keep merging. See `ROADMAP.md` §0, rules 14 and 15.

## Status records and the daily batch

Larry, 2026-11-12 16:41:17 UTC, "Adopt the batch rule". Every open PR was editing the same progress lines, so each merge broke the rest: on 2026-11-12 eight PRs conflicted with `main` in `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md` and in no other file.

1. **A PR does not edit status lines.** That means a plan's Progress log or dated progress entries, a `ROADMAP.md` row's Status, Remaining work, Next step and Updated lines, and checklist boxes.
2. **A PR records its status in its own new file** under `docs/roadmap-log/`: date, system, row, PR, what changed, evidence, what is left and the next actor. It never edits another PR's log file.
3. **Claude writes one batch PR to `main` each day.** It folds the log files merged since the last batch into the plans' progress logs and the `ROADMAP.md` rows, links each folded line to its log file, and changes nothing else. A system other than Claude reviews it (`ROADMAP.md` §0 rule 14) by checking that every line traces to a merged log file.
4. **These still go in their own PR**, because they are not status: rule, scope and design changes (for example `ORB_SPEC.md`), new rows Larry asks for, a claim (Owner and Where) when you take an item, §3 reservations and §4 conflict entries.
5. **An open PR that already edits status lines** drops those edits and moves the text into its log file. Do not resolve the conflict by merging.

## When you finish a slice or open a PR

- Record status in your PR's `docs/roadmap-log/` file, not in your row or plan (see above).
- In the PR body, give: system (Codex), session reference, the row id (`WS-xx`), any numbers reserved in §3, and the files changed that fall outside the row's `Scope`, with the reason for each.

## Repository conventions

`CLAUDE.md` holds the architecture, commands, testing conventions and binding decisions for **every** agent, despite its name. Rules in it that are explicitly Claude-only (for example, Claude never runs git on the Mac) do not restrict you; everything else applies.
Also read:

- `docs/README.md`: map of the docs
- `docs/ARCHITECTURE.md`
- `docs/REPO_MAP.md`
- `docs/plans/ALLOWLIST_SEQUENCE.md`: the self-edit allow-list, where every change is a human commit
- `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md`: the release closure plan. Which system leads each piece of remaining work, the files each piece touches, the `next` branch used during the freeze, and the review pairs. The lanes are a guide that keeps the systems from editing the same files, not an exclusive claim; read it before picking up work
- `docs/interface-research/orb-plasma/ORB_SPEC.md`: the approved interface direction, palette and orb spec that the plan's interface items build
