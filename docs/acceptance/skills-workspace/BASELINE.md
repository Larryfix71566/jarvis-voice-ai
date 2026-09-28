# Skills workspace baseline

Captured 2026-09-25 in `work/codex-isolated-20260924`.

## Source and working state

- HEAD: `977f50b` (working tree already contains unrelated active changes; this
  is not a release candidate).
- Runtime: macOS host; repository `.venv` Python 3.12.13.
- Skill config: five registered/enabled: `current-weather-with-fahrenheit`,
  `git-history-and-status-review`, `layered-geolocation`,
  `mcp-server-authoring`, and `technical-plan-document`.
- `python -m jarvis.agent_skills --validate`: all current `SKILL.md` files valid.
- Focused unit suite after SW1 parser fix: `55 passed`.
- Current implementation suite after SW1/SW2 catalog/API work: `69 passed`,
  one Starlette TestClient/httpx deprecation warning.

## Baseline gaps

- Skills are loaded from root `skills/` and enabled by `config/skills.yaml`;
  there is no pinned package-digest registry or metadata catalog yet.
- Matching remains the existing one-skill lexical rule.
- Native library/process/activity screens, skill actions, and skill-run traces
  do not yet exist.
- No verified app screenshot or voice/display recording was captured for this
  increment. SW-A and physical-display gates remain open; do not treat this
  textual baseline as visual or hardware evidence.
- Read-only catalog now validates five metadata process maps and package digests;
  admin API exposes cards and revision-bound detail. Readiness remains unknown
  until actual tool/model/privacy dependency checks are implemented.
- Existing user changes in the worktree were not included in this baseline diff.

## Reproduction

Run from this checkout:

```sh
./.venv/bin/python -m jarvis.agent_skills --list
./.venv/bin/python -m jarvis.agent_skills --validate
./.venv/bin/python -m pytest tests/unit/test_agent_skills.py -q
```

The system Python lacks PyYAML; use the prepared repository environment.
