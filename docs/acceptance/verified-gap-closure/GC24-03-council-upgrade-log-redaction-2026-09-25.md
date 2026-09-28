# GC24-03 receipt — council and upgrade orchestration log redaction

**Date:** 2026-09-25  
**Branch:** `codex/isolated-20260924`  
**Base/HEAD at start:** `977f50bec7b77bd7d3381d3b8f3d63fa69bd00e2`  
**State:** verified in the dirty isolated tree; concurrent edits in these
files were preserved.

## Change

Council failure paths now share a logger helper that emits only a static
event and a bounded exception class. This covers convene/draft failures,
shadow execution and writes, score/round/payload writes, retry bookkeeping,
and user-choice persistence. Proposer and judge failure logs no longer
include exception messages. User-choice labels and unknown retry-outcome
values are no longer echoed in warnings.

Upgrade-agent cleanup and council escalation/scope/retry-recording catches
use the same bounded diagnostic pattern local to that module. Planner
failover messages retain the existing profile transition and bounded error
class without exception text. Catch behavior, return values, failure-open
behavior, retries, and council selection remain unchanged.

## Verification

- `./.venv/bin/pytest -q tests/unit/test_council_gather.py tests/unit/test_upgrade_agent.py tests/integration/test_council_cli.py tests/integration/test_council_escalation.py --tb=short`
  — **88 passed**.
- `./.venv/bin/ruff check --select F,I jarvis/council/council.py jarvis/agents/upgrade_agent.py tests/unit/test_council_gather.py tests/unit/test_upgrade_agent.py`
  — passed.
- `./.venv/bin/python -m compileall -q jarvis/council/council.py jarvis/agents/upgrade_agent.py tests/unit/test_council_gather.py tests/unit/test_upgrade_agent.py`
  — passed.
- `git diff --check` — passed.
- Canary tests cover council helper/convene, proposer and judge failures, and
  the upgrade-agent safe logger. They verify event/type visibility and
  absence of exception text, private paths, and traceback output.
- A source search confirms no `logger.exception`, `exc_info=True`, or
  equivalent traceback arguments remain in the two modules.

## Still open

This receipt covers only the council and upgrade-agent logging paths. It
does not prove privacy of council content in model requests, durable council
records, result delivery, or other data flows. Slices D–E and the full GC24-03
source-to-sink audit remain open. No live provider, installed Mac,
deployment, or release check was run.
