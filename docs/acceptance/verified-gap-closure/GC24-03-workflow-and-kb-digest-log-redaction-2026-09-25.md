# GC24-03 receipt — workflow and KB digest log redaction

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**State:** code and synthetic canary tests verified in the dirty isolated
tree; broader privacy source-to-sink acceptance remains open.

## Change

- `load_workflows()` no longer logs YAML parser tracebacks or file paths. A
  parser exception can include the malformed source line, which may contain
  project instructions. The log now contains only the exception class and
  continues skipping that file without affecting other workflows.
- KB session digest failures no longer log traceback/error strings from model
  calls or the knowledge-base backend. The best-effort digest behavior is
  preserved; errors remain observable as bounded event names and the outer
  exception class.
- No transcript, digest, malformed workflow source, or backend message is
  added to the logs.

## Verification

- `./.venv/bin/pytest -q tests/unit/test_kb_digest.py tests/unit/test_workflows.py`
  — **31 passed**.
- `./.venv/bin/pytest -q tests/unit tests/integration` — **2,967 passed, 4
  skipped, 11 warnings, 2 subtests passed**.
- Ruff `F`/`I` for the four changed Python files — passed.
- `git diff --check` — passed.
- Canary tests inject recognizable strings into a malformed YAML line, a
  provider exception, and knowledge-base error responses; none appear in
  captured logs.

## Still open

This closes only these workflow and KB digest log sinks. It does not establish
general sensitive-data detection, complete privacy source-to-sink coverage,
provider eligibility, or live candidate/release acceptance.
