# GC24-03 F17 — council too-small diagnostic redaction

**Snapshot:** dirty isolated worktree `codex/isolated-20260924`, base/HEAD `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`; not a clean commit or deployed Mac result.

The `council_too_small` diagnostic omits opaque round ID, provider-resolution reason, and path canaries. The returned round result and durable row retain their existing round ID and reason, so the change narrows only the log event.

**Evidence:** `tests/unit/test_council_gather.py::test_too_small_round_log_omits_round_id_and_reason` passed as part of:

```text
./.venv/bin/python -m pytest tests/unit/test_admin_selfedit.py tests/unit/test_subagent.py tests/unit/test_admin_api.py tests/unit/test_council_gather.py -q --tb=short
168 passed, 1 warning in 6.35s
```

The warning is the existing Starlette `httpx` deprecation. Ruff `F`/`I` for the seven affected source/test files, `compileall` for the three changed Python modules, and `git diff --check` passed. This closes only the F17 diagnostic fields; durable council content and the broader GC24-03 privacy source-to-sink audit remain separate and open.
