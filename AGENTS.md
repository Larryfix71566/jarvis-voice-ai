# AGENTS.md — Agent Conventions Contract (mortimer-dev branch)

This file is the written contract for agent-driven development on Mortimer.
All agent writes to THIS repo happen on the `mortimer-dev` branch; `main`
changes only via human-merged pull requests. New applications developed by
Mortimer each get their OWN separate private repository (see below).

## Branches

- `main` is human-controlled. Agents NEVER commit, push, or force-push to `main`.
- `mortimer-dev` is the working branch for agent-driven development of Mortimer itself.
- Feature branches (`feat/*`, `fix/*`) follow the existing UpgradeAgent PR-only flow.
- Agents NEVER force-push and NEVER delete branches.
- Merging to `main` is always a human action on GitHub.

## Workflow tiers

1. **repo-read** — read-only exploration: file contents, directory listing, code search.
2. **upgrade-assist** — the existing UpgradeAgent (`jarvis/agents/upgrade_agent.py`):
   allowlisted edits, validation gate, session branch, PR only. Unchanged.
3. **app-storage** — the `mcp_apps` skill server: each new application developed by
   Mortimer is scaffolded into its OWN new private GitHub repository (see below).

## Commit discipline

- Small atomic commits; one logical change per commit.
- Conventional commit messages: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`.
- Every write session ends with a summary: files changed, commit SHAs, how to revert.

## App storage convention (separate repo per app)

Each new application gets its own private repository:

- **Naming:** the agent determines the repo name at call time (descriptive,
  kebab-case) and confirms with the human before creating it.
- **Visibility:** private by default.
- **Initial structure** (from template):
  ```
  <app-repo>/
    manifest.json    # { name, version, created_by, created_at, entry_point, dependencies, description }
    README.md
    src/
  ```
- **Registry:** after creating an app repo, the agent records it in
  `apps/index.json` on the `mortimer-dev` branch of THIS repo
  (entry: name, repo URL, created_at, description) so Mortimer can discover
  all apps it has built.
- Agents NEVER delete repositories. Repo deletion is a human-only action
  performed on GitHub.
