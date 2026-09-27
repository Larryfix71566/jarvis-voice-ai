# AGENTS.md

Instructions for **Codex** and any other non-Claude agent working in this repository. Two AI systems (Codex and Claude) and one human (Larry) work on this repo. The coordination rules below are binding. They exist because the systems have already collided: see `scripts/deploy_main.sh`, the note dated 24 Sep, and `docs/reviews/CROSS_SYSTEM_PLAN_EVAL_2026-09-27.md`.

## At the start of every session

1. `git fetch origin`, then read `ROADMAP.md` as it is on `origin/main`: §0 (protocol), §2 (workstreams), §4 (conflicts).
2. Find the row your task belongs to. It must show owner `codex`, and its `Where` must match your branch. If no row matches, **stop and tell Larry.** Do not start.
3. Merge `origin/main` into your branch before editing anything. Resolve conflicts by keeping the intent of both sides; never take one side wholesale. `ROADMAP.md` §4 lists the files where both sides carry fixes.
4. Read the `Scope` of every other active row. Those paths are locked. Do not edit them.

Resolve the open conflicts assigned to `codex` in `ROADMAP.md` §4 before starting any new feature work.

## While working

- **One plan per row.** Add dated progress entries to the row's plan file. Do not create a new plan, index or "gap" document for work that already has a row.
- **Reserve shared numbers first.** Migration ids, self-edit allow-list rows, launchd labels, ports and new config keys go into `ROADMAP.md` §3 before you write them in code.
- **Commit at the end of every slice** on your branch. Push when credentials exist; otherwise say in your summary that Larry needs to push. Do not keep uncommitted work across sessions.
- **Never edit `~/jarvis-voice-ai-clean`.** It is production, and changes reach it only through `scripts/deploy_main.sh`.
- **Stay out of Claude's work.** Do not read or write Claude's working folders or patches (`Claude outputs/`, `closure-checks/`, Cowork VM paths). The one exception is a read-only review Larry asks for. Work reaches you through `ROADMAP.md` and PRs only.

## When you finish a slice or open a PR

- Update your row on the same branch: status, next step, date, and a one-line log entry.
- In the PR body, give: system (Codex), session reference, the row id (`WS-xx`), any numbers reserved in §3, and the files changed that fall outside the row's `Scope`, with the reason for each.

## Repository conventions

`CLAUDE.md` holds the architecture, commands, testing conventions and binding decisions for **every** agent, despite its name. Rules in it that are explicitly Claude-only (for example, Claude never runs git on the Mac) do not restrict you; everything else applies.
Also read:

- `docs/README.md`: map of the docs
- `docs/ARCHITECTURE.md`
- `docs/REPO_MAP.md`
- `docs/plans/ALLOWLIST_SEQUENCE.md`: the self-edit allow-list, where every change is a human commit
