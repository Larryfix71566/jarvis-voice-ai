# GC24-03 receipt — MCP registry diagnostics redacted

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** residual diagnostic-log plan slice F3 only.

Registry diagnostics retain fixed event names and bounded exception classes
while omitting skill-manifest paths/parser content, invalid dynamic-source
labels and paths, model-registry parser content/paths, provider exception
messages, and unnecessary run IDs. Three new canary tests exercise malformed
skill YAML, invalid dynamic manifest entries, and malformed
`upgrade_models.yaml`; existing tests cover MCP tool and registry-shutdown
exceptions. The loader continues to return empty declarations on manifest
errors, and invalid dynamic declarations continue to degrade to the declared
base/required/optional environment only.

Validation:

- `./.venv/bin/python -m pytest tests/unit/test_registry.py -q --tb=short` — **21 passed**.
- `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` — **3,043 passed, 4 skipped, 11 warnings, 2 subtests passed** after adding the three registry canary tests.
- `./.venv/bin/ruff check --select F,I jarvis/skills/registry.py tests/unit/test_registry.py` — passed.
- `git diff --check` — passed.

This closes only F3 diagnostic sinks. MCP environment-scope design,
credential transport, tool result privacy, and the broader GC24-03
source-to-sink audit remain open.
