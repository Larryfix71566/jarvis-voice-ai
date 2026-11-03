---
date: 2026-11-03
system: claude
rows: [WS-32]
prs: [275, 293, 294]
---

# WS-32 — host-verifier follow-up (B1), Claude, 2026-11-03

System: Claude (Claude Code cloud session `session_01EHREEWWT9PPGKDzg678o9r`). Planned by Claude Opus 5.5; implemented by a Claude Sonnet subagent from that plan, then reviewed, corrected and checked by Claude Opus 5.5.
Branch: `claude/ws32-host-verifier-limit-20261103`. Claim and scope amendment: #294 (Larry-authorized 2026-11-03).

Change: `SkillRegistry._repo_source_refs` (`jarvis/skills/registry.py`) uses `ROADMAP_READ_MAX_BYTES` for the canonical `ROADMAP.md` only. Every other path, and the `repo_search` verifier, keep `REPO_READ_MAX_BYTES`.

Evidence (this session):
- Red/green: `test_canonical_roadmap_between_generic_and_roadmap_limits_is_attested` fails with the old registry and passes with the change.
- Mutation: replacing the host size check with an effectively unlimited bound makes `test_canonical_roadmap_above_roadmap_limit_is_refused` and `test_non_roadmap_file_keeps_generic_limit_at_host` fail.
- Real file: the 295,531-byte `ROADMAP.md` at `9feb38a` is now accepted by the host verifier (it was refused before).
- Focused files and full unit suite: see the PR body for the exact counts at the pushed head.

Not verified: the native console roadmap refresh on a Mac; no deployment or live test.
