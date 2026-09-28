# GC24-03 F15 — model override refusal log redaction

**Snapshot:** dirty isolated worktree `codex/isolated-20260924`, base/HEAD `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; not a clean commit or deployed Mac result.

The refuse-mode override path logs the stable event and agent name only. Synthetic model-profile and route-reason canaries are absent from captured logs, while the caller still receives the explanatory refusal and no provider completion is issued. No fallback behavior was added.

**Evidence:** `tests/unit/test_subagent.py::TestSubAgentLoop::test_override_refusal_log_omits_profile_and_reason` passed as part of:

```text
./.venv/bin/python -m pytest tests/unit/test_admin_selfedit.py tests/unit/test_subagent.py tests/unit/test_admin_api.py tests/unit/test_council_gather.py -q --tb=short
168 passed, 1 warning in 6.35s
```

The warning is the existing Starlette `httpx` deprecation. Ruff `F`/`I` for the seven affected source/test files, `compileall` for the three changed Python modules, and `git diff --check` passed. This closes only the F15 refusal-reason log field; it does not close GC24-03 privacy source-to-sink coverage.
