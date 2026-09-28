# GC24-03 receipt — T4a offline security tests

**Date:** 2026-09-25  
**Platform:** Darwin host  
**Branch:** `codex/isolated-20260924`; dirty isolated worktree at baseline
`977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`.  
**Scope:** offline test portion of Security Hardening Plan V1 only.

## Verification

Command:

```bash
./.venv/bin/pytest tests/unit/test_sensitive.py tests/unit/test_env_scoping.py \
  tests/unit/test_requires_env_snapshot.py tests/unit/test_agent_isolation.py \
  -q -s
```

Result: **152 passed** in 1.60s. The tests cover the sensitive-detail
detector, scoped MCP child environments, the frozen `requires_env` snapshot,
and agent isolation. The test output included its expected D-H9 exposure
assertion (`none — V7 commit is in`); this is test output, not evidence of a
new commit, merge, or deployment.

## Limits

This does not complete the security-hardening plan's V1 sign-off or its V2–V6
Mac/provider acceptance. It does not inspect running child-process
environments, exercise tools by voice, prove live sensitive-turn behavior,
test production memory storage, or run the paid routing evaluation. Those
checks remain open and must follow the plan's stated procedures and cost
authorization boundaries.
