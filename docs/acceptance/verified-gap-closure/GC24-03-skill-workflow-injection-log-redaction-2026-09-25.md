# GC24-03 receipt — skill/workflow injection log redaction

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** residual diagnostic slice F18 only.

The skill and workflow injection events retain their stable event names and
agent identity, but no longer log local skill/workflow names or the workflow
source path. Matching, prompt injection, and the user-visible result remain
unchanged. A canary test supplies distinct synthetic names and a fake source
path, asserts both injection events remain observable, and verifies that all
three labels are absent from captured logs.

Validation on this dirty isolated snapshot:

- `./.venv/bin/python -m pytest tests/unit/test_subagent.py::TestSubAgentLoop::test_skill_and_workflow_injection_logs_omit_local_labels -q --tb=short` — **1 passed**.
- `./.venv/bin/python -m pytest tests/unit/test_subagent.py -q --tb=short` — **65 passed**.
- `./.venv/bin/ruff check --select F,I jarvis/agents/base.py tests/unit/test_subagent.py` — passed.
- `./.venv/bin/python -m compileall -q jarvis/agents/base.py tests/unit/test_subagent.py` — passed.
- `git diff --check -- jarvis/agents/base.py tests/unit/test_subagent.py` — passed.

This receipt closes only the F18 injection-log fields exercised by the
canaries. It does not close other diagnostic sinks or the broader GC24-03
privacy source-to-sink audit. The worktree contains many concurrent dirty
changes; no clean commit, full-suite run for this exact snapshot, live Mac,
provider, deployment, or release acceptance is claimed.
