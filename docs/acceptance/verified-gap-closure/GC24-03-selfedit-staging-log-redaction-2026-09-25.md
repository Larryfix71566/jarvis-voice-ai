# GC24-03 F14 — self-edit staging log redaction

**Snapshot:** dirty isolated worktree `codex/isolated-20260924`, base/HEAD `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; not a clean commit or deployed Mac result.

The staging-resolution path emits the fixed `selfedit_run_staging_resolved` event without requested or selected staging IDs. A synthetic requested-ID canary is absent from captured logs; with exactly one live stage, the approved staged goal still starts and the stage is consumed. Existing multiple-stage refusal behavior is outside this focused assertion and remains governed by its existing tests.

**Evidence:** `tests/unit/test_admin_selfedit.py::test_run_resolves_a_mangled_staging_id_without_logging_ids` passed as part of:

```text
./.venv/bin/python -m pytest tests/unit/test_admin_selfedit.py tests/unit/test_subagent.py tests/unit/test_admin_api.py tests/unit/test_council_gather.py -q --tb=short
168 passed, 1 warning in 6.35s
```

The warning is the existing Starlette `httpx` deprecation. Ruff `F`/`I` for the seven affected source/test files, `compileall` for the three changed Python modules, and `git diff --check` passed. This closes only F14's staging-ID log field; it does not close GC24-03 privacy source-to-sink coverage.
