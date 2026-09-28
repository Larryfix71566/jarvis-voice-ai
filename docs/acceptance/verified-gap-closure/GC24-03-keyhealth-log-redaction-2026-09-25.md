# GC24-03 receipt — key-health probe diagnostics redacted

**Date:** 2026-09-25  
**Worktree:** `codex/isolated-20260924`  
**Base snapshot:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** residual diagnostic-log plan slice F1 only.

Credential-probe outcomes and details are reduced to the existing bounded
health categories. Logs no longer include the credential environment name,
endpoint, provider-controlled detail, exception text, or traceback; persisted
detail remains a fixed safe explanation. Unknown provider output maps to the
existing `unknown` outcome. Probe selection, healthy/unhealthy/unknown
classification, return shape, and best-effort behavior remain unchanged.

Validation:

- `./.venv/bin/python -m pytest tests/unit/test_keyhealth.py -q --tb=short` — **12 passed**.
- `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short` — **3,039 passed, 4 skipped, 11 warnings, 2 subtests passed** on the same current source snapshot.
- `./.venv/bin/ruff check --select F,I jarvis/keyhealth.py tests/unit/test_keyhealth.py` — passed.
- `git diff --check` — passed.

This closes only the F1 credential-probe diagnostic sinks. It does not close
the wider GC24-03 source-to-sink privacy audit or the remaining F2–F17
diagnostic rows.
