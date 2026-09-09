# Self-edit allow-list — reconciled final state and ordered commits

**Status:** binding, 2026-08-27. Owner: `MORTIMER_SECURITY_HARDENING_PLAN.md`
(SEC) per `CROSS_PLAN_RESOLUTION.md` §A/§D. This document is the **single owner**
of `config/self_edit_allowlist.json` across the Mortimer track plans. Where a
plan's §8 needs an allow-list change, its Larry-step is: *"apply row N of
`docs/plans/ALLOWLIST_SEQUENCE.md` and run its verify command."* No plan edits
the allow-list directly, and every change is a **human commit** (roadmap C8).

## Why this file exists

Four plans, landing in three waves, each need to add or move one or more entries
in `config/self_edit_allowlist.json`. Stating the deltas inside each plan as a
literal unified diff does not survive — SKILL's diff will not apply cleanly once
SEC's W0 entries land. So the plans state *which entries to add/remove*, and this
file holds the **reconciled final state** (the state no single plan spells out)
plus the **ordered per-wave commits** that reach it.

Larry's decision (`CROSS_PLAN_RESOLUTION.md` §A, 2026-08-26): keep the
2026-08-21 rule that a self-edit may *propose* granting an agent new tools (gate
= validation + Larry merging the PR). So `config/agents.yaml` and
`mcp_servers/*/skill.yaml` stay **editable**; the privilege guard moves into
files the assistant cannot edit — `jarvis/skills/registry.py` (the enforcement
code) and `tests/unit/test_requires_env_snapshot.py` (a frozen privilege
snapshot that fails CI on any drift, SEC §7.6).

## Reconciled final `config/self_edit_allowlist.json`

This is the end state after all five rows below have been applied. Deny wins over
allow (`jarvis/selfedit/allowlist.py` — any deny match rejects; otherwise the
path must match some allow pattern), which is why a denied `tests/unit/…` file
stays denied even though `tests/**` is allowed.

```json
{
  "allow": [
    "web/src/**", "web/public/**", "config/**", "jarvis/prompts.py",
    "jarvis/skills/**", "jarvis/services/**", "mcp_servers/**",
    "skills/**", "tests/**", "docs/**", "*.md",
    "macos/JarvisKit/Sources/**", "macos/JarvisKit/Tests/**",
    "macos/MortimerHost/Sources/**", "macos/MortimerHost/Tests/**"
  ],
  "deny": [
    ".github/**", "jarvis/selfedit/**", "jarvis/agents/**",
    "jarvis/wakeword/**", "jarvis/bot/**", "jarvis/admin/**",
    "config/self_edit_allowlist.json", "config/upgrade_agent.yaml",
    "config/upgrade_models.yaml", "config/skills.yaml",
    "requirements*.txt", "web/package.json", "web/package-lock.json",
    "DEVIATIONS.md", ".env", ".env.*", "**/.env", "**/.env.*",
    "jarvis/vault.py", "data/**", "*.vault", "**/*.vault",
    "macos/**/Package.swift", "macos/**/Package.resolved",
    "macos/**/*.plist", "macos/**/*.entitlements",
    "macos/**/scripts/**", "macos/GlassSpike/**", "macos/MortimerShell/**",

    "jarvis/skills/registry.py",
    "tests/unit/test_agent_isolation.py",
    "tests/unit/test_requires_env_snapshot.py",
    "jarvis/auth.py", "jarvis/authmw.py", "jarvis/bind.py",
    "docs/runbooks/**"
  ]
}
```

## Ordered commits (apply in wave order)

Each row is one human commit. Apply rows in wave order (W0 → W2); within W0,
SKILL then SEC (SKILL moves `skills/**` from deny to allow; SEC's entries are
independent of that move, so either order works, but this is the canonical one).

| # | Wave | Plan | Change to `config/self_edit_allowlist.json` | Verify command |
|---|---|---|---|---|
| **W0-SKILL** | W0 | `MORTIMER_SKILL_AUTHORING_PLAN.md` | Move `"skills/**"` from `deny` to `allow` (add/remove these exact strings — do **not** apply a stored unified diff; SEC's entries below change the surrounding lines). `config/skills.yaml` **stays in `deny`** (the one-at-a-time enable rule); `config/agents.yaml` is **not** touched (it stays editable per resolution §A). | `python -c "import json,sys; a=json.load(open('config/self_edit_allowlist.json')); ok = ('skills/**' in a['allow'] and 'skills/**' not in a['deny'] and 'config/skills.yaml' in a['deny'] and 'config/agents.yaml' not in a['deny']); sys.exit(0 if ok else 1)"` — exit 0. Then `pytest tests/unit -q` stays green. |
| **W0-SEC** | W0 | `MORTIMER_SECURITY_HARDENING_PLAN.md` | Add to `deny`: `"jarvis/skills/registry.py"`, `"tests/unit/test_agent_isolation.py"`, `"tests/unit/test_requires_env_snapshot.py"`. **Do NOT** add `config/agents.yaml` or `mcp_servers/*/skill.yaml` (they stay editable — resolution §A). | `pytest tests/unit/test_agent_isolation.py -q -s` → the exposure line reads `none — V7 commit is in`; and `pytest tests/unit/test_requires_env_snapshot.py -q` passes. |
| **W1-REMOTE** | W1 | `MORTIMER_REMOTE_ACCESS_PLAN.md` | Add to `deny`: `"jarvis/auth.py"`, `"jarvis/authmw.py"`, `"jarvis/bind.py"`. | `python -c "import json,sys; d=json.load(open('config/self_edit_allowlist.json'))['deny']; sys.exit(0 if all(x in d for x in ['jarvis/auth.py','jarvis/authmw.py','jarvis/bind.py']) else 1)"` — exit 0; plus REMOTE's `tests/unit/test_service_token.py` passes. |
| **W2-LOCAL** | W2 | `MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md` | Add to `deny`: `"docs/runbooks/**"`. | `python -c "import json,sys; sys.exit(0 if 'docs/runbooks/**' in json.load(open('config/self_edit_allowlist.json'))['deny'] else 1)"` — exit 0. |
| **W0-SWIFT** | W0 | `MORTIMER_SELFEDIT_AUTHORING_PLAN.md` (SE5) | Remove `"macos/**"` from `deny`. Add to `allow`: `"macos/JarvisKit/Sources/**"`, `"macos/JarvisKit/Tests/**"`, `"macos/MortimerHost/Sources/**"`, `"macos/MortimerHost/Tests/**"`. Add to `deny`: `"macos/**/Package.swift"`, `"macos/**/Package.resolved"`, `"macos/**/*.plist"`, `"macos/**/*.entitlements"`, `"macos/**/scripts/**"`, `"macos/GlassSpike/**"`, `"macos/MortimerShell/**"`. Applied 2026-09-07, out of wave order: it depends on the Swift gate landing first, not on the other W0 rows. | `python3 -c "import sys; sys.path.insert(0,'.'); from jarvis.selfedit.allowlist import Allowlist; a=Allowlist.load('config/self_edit_allowlist.json'); want={'macos/MortimerHost/Sources/MortimerHost/App/AppTuning.swift':'routine','macos/JarvisKit/Tests/JarvisKitTests/AdminAPITests.swift':'routine','macos/MortimerHost/Package.swift':'denied','macos/MortimerHost/scripts/bundle.sh':'denied','macos/GlassSpike/Sources/main.swift':'denied','macos/MortimerShell/Sources/ShellWebView.swift':'denied'}; bad=[(p,a.tier(p),t) for p,t in want.items() if a.tier(p)!=t]; print(bad or 'ok'); sys.exit(1 if bad else 0)"` — prints `ok`. Then `uv run pytest tests/unit -q` stays green. |

General verification available at every row (if present in the repo):
`python3 scripts/check_allowlist.py origin/main...HEAD` — self-edit branches must
stay inside the allow-list (CLAUDE.md CI gate).

## Notes

- **`skills/**` deny → allow (W0-SKILL)** is what lets a self-edit author a new
  Agent Skill folder. The one-at-a-time enable rule still lives in
  `config/skills.yaml`, which stays **denied**, so presence-on-disk grants
  nothing (the skill must be listed under `enabled:` — a human commit).
- **The SEC snapshot guard (W0-SEC)** is the reason `config/agents.yaml` and
  `mcp_servers/*/skill.yaml` can stay editable: any self-edit that changes a
  server's `requires_env`/`optional_env` or a `config/mcp_servers.yaml` `env:`
  map fails `tests/unit/test_requires_env_snapshot.py` (a denied file), so the
  grant cannot merge until Larry updates the frozen snapshot by hand in the same
  commit. That is the review gate, not an outright deny wall.
- **`macos/**` deny → per-path (W0-SWIFT)** was gated on a gate existing.
  The tiers plan denied all of `macos/` with the reason "no Swift gate
  exists, so a self-edit here would be unvalidated"; SE5 built that gate
  (`swift build` + `swift test` per changed package, in the session
  worktree), so the reason expired for the SOURCES. It did not expire for
  manifests, `Package.resolved`, plists, entitlements, `scripts/` or the
  two throwaway targets: a dependency, signing or packaging change is not
  something `swift build` passing can vouch for. `Tests/**` is allowed
  alongside `Sources/**` deliberately — an agent that can change Swift but
  not its tests cannot add coverage, and can only repair a failing
  `swift test` by bending the source until the old assertion passes.
- Nothing here is applied by an implementing model — each row is Larry's commit
  (C8). An implementing model that finds itself opening
  `config/self_edit_allowlist.json` should stop (SEC §0.2).
