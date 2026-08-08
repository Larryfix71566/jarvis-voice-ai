# AGENTS.md — Agent Conventions Contract (mortimer-dev branch)

This file is the written contract for agent-driven development on Mortimer.
All agent writes happen on the `mortimer-dev` branch of this repo; `main`
changes only via human-merged pull requests.

## Branches

- `main` is human-controlled. Agents NEVER commit, push, or force-push to `main`.
- `mortimer-dev` is the working branch for agent-driven development and app storage.
- Feature branches (`feat/*`, `fix/*`) follow the existing UpgradeAgent PR-only flow.
- Agents NEVER force-push and NEVER delete branches.
- Merging to `main` is always a human action on GitHub.

## Workflow tiers

1. **repo-read** — read-only exploration: file contents, directory listing, code search.
2. **upgrade-assist** — the existing UpgradeAgent (`jarvis/agents/upgrade_agent.py`):
   allowlisted edits, validation gate, session branch, PR only. Unchanged.
3. **app-storage** — the `mcp_apps` skill server: stores new applications developed
   by Mortimer under `apps/` on this branch (see below).

## Commit discipline

- Small atomic commits; one logical change per commit.
- Conventional commit messages: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`.
- Every write session ends with a summary: files changed, commit SHAs, how to revert.

## App storage convention

New applications live under `apps/<app-name>/` on the `mortimer-dev` branch:

```
apps/
  index.json          # registry, updated on every new app
  <app-name>/
    manifest.json     # { name, version, created_by, created_at, entry_point, dependencies, description }
    README.md
    src/
```

- On every new app, update `apps/index.json` atomically.
- Never overwrite an existing app without an explicit version bump.
- Name collisions: stop and ask the human before proceeding.
- App names: kebab-case, validated in code (no path traversal).
