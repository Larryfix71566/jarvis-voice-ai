# GC24-03 F16 — sidecar repository-root log redaction

**Snapshot:** dirty isolated worktree `codex/isolated-20260924`, base/HEAD `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; not a clean commit or deployed Mac result.

The production `main()` startup call retains the fixed `admin_sidecar_startup` event and host/port metadata, while omitting `repo_root` and the absolute repository path. The test inspects the production call and captures the same bounded event without emitting the local root.

**Evidence:** `tests/unit/test_admin_api.py::TestD17Logging::test_startup_log_line_present` passed as part of:

```text
./.venv/bin/python -m pytest tests/unit/test_admin_selfedit.py tests/unit/test_subagent.py tests/unit/test_admin_api.py tests/unit/test_council_gather.py -q --tb=short
168 passed, 1 warning in 6.35s
```

The warning is the existing Starlette `httpx` deprecation. Ruff `F`/`I` for the seven affected source/test files, `compileall` for the three changed Python modules, and `git diff --check` passed. This closes only the F16 startup-path log field; it does not close GC24-03 privacy source-to-sink coverage or prove a live deployed startup.
