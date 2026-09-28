# GC24-04 receipt — explicit environment credential isolation

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Baseline:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**Scope:** checked SAYGM route resolution when a caller provides an explicit
environment mapping. This is a bounded source-level route-isolation fix; it
does not prove provider isolation, confidential execution, or billing.

## Finding and change

`resolve_model_route_checked(..., environ={})` previously used `environ or
os.environ` to obtain the SAYGM catalog credential. An intentionally empty
environment therefore fell back to the process environment for the catalog
request, even though the subsequent route resolution used the explicit empty
mapping and rejected the missing credential. The catalog call could thus
cross the intended credential boundary before the final rejection.

The resolver now treats a supplied environment mapping as authoritative,
including an empty mapping. It reads the configured SAYGM credential name,
fails with `ModelRouteError` before fetching the catalog if that credential
is absent, and passes only that explicit value to the catalog client. Calls
that omit `environ` continue to use the process environment as before.

## Verification

- Added a canary test that sets an ambient process key, supplies
  `environ={}`, and verifies route resolution fails before `fetch_catalog` is
  called.
- `./.venv/bin/pytest -q tests/unit/test_model_routing.py --tb=short` —
  **12 passed**.
- `./.venv/bin/pytest -q tests/unit/test_model_routing.py tests/unit/test_model_routing_client.py tests/unit/test_saygm.py tests/unit/test_memory_model.py tests/unit/test_model_execution.py --tb=short`
  — **66 passed**.
- `RUN_LIVE=0 ./.venv/bin/python -m pytest tests/unit tests/integration -q --tb=short`
  — **3,054 passed, 4 skipped, 11 warnings, and 2 subtests** in 117.14s.
  This is the full dirty isolated-tree snapshot, not candidate or release
  acceptance.
- Ruff `F`/`I`, Python compileall, and `git diff --check` passed for the
  changed Python files.

## Remaining gates

This closes only explicit-environment fallback during the SAYGM catalog
lookup. It does not establish that the provider runtime is isolated, that a
SAYGM route qualifies for confidential content, that provider tools are safe,
or that usage/billing is correct. Those GC24-04 proofs and the dependent
GC24-05 production-memory gates remain open.
