---
date: 2026-10-31
system: codex
rows: [WS-05]
prs: []
---

# WS-05 — confirmed provider-phase cancellation test

Coordinator: current WS-05 Codex implementation owner. Claim candidate base is
GitHub PR #290's verified base commit `5310d1a9305035f43143fcffad6161619281f475`.
Future test branch: `codex/ws05-deadline-confirmed-phase-20261031`.

Exact source scope: `tests/unit/test_model_execution_deadlines.py` only. The
registered WS-05 worker-fixture lane remains on its own branch and exact path
`tests/unit/test_claude_developer_capability.py`; no overlap was found in the
current open-PR search or the merged #272 registration. This new claim changes
no production source or CI configuration.

CI run `41159320847`, validation job `124413109250`, reports one failure at
`test_provider_swallowing_cancellation_cannot_return_or_publish_late_result[False-True]`:
`asyncio.wait_for(entered.wait(), 1)` timed out. `execute_chat` sets the request
budget deadline before durable child-budget resolution and invokes the provider
after that resolution. A local controlled 30 ms preflight delay with a 20 ms
request timeout reproduced the same symptom and terminal `TimeoutError`; the
unchanged exact test passed locally. This demonstrates a plausible phase
mismatch, not the actual CI cause. The test module's existing
`expire_at_confirmed_phase` helper explicitly targets cancellation after a
provider/observer starts, while a separate test already exercises early
pre-admission timeout.

Planned change after independent claim review: give admission a bounded initial
allowance, wait for the fake provider's entry event, and expire the actual
request deadline through the existing helper; retain explicit task cancellation
for the explicit-cancel cases. Preserve all three parameter combinations and
all late-publication, cleanup, event, and ledger assertions. Keep the separate
early-admission timeout regression intact. Do not add timing sleeps or change
`jarvis/model_execution.py`.

Validation plan: run the entire deadline test module and adjacent model-execution
regression modules with the existing approved environment; record exact result
and runtime. Source review and corrected-head CI remain separate. No provider
traffic, settings, dependencies, installation, or live acceptance.

Claim documentation candidate: commit `bf5fd6a2a857ce1c3a64d6827b43cee9bfd1c322`
(tree `cafc67c0e29daa2d47877eaf18f557b9a98d6003`); source candidate:
`465060b0758fe44018814353ddf2d862c7128025` (tree
`c82573799e4585042cdcf9e1ce4243f640fac4a4`). The source diff changes only
`tests/unit/test_model_execution_deadlines.py`; SHA-256:
`8d5736ddd02e7f245f0013516adc347bf78df72fc4db18db2cb055e4fef63172`. `git diff --check` and `python3 scripts/check_roadmap.py --main HEAD`
pass on the local candidate.

Validation completed in a disposable Python 3.12.13 venv at
`/tmp/ws05-deadline-test-venv312`, with the existing repository test venv
site-packages visible and Anthropic's dependencies aligned to
`requirements-lock.txt`. Versions: pytest 9.1.1, pytest-asyncio 1.4.0,
anthropic 0.125.0, OpenAI 2.53.0, httpx 0.28.1, pydantic 2.13.4,
pydantic-core 2.46.4, and anyio 4.14.2. The complete deadline module passed
16 tests. The seven related model-execution/budget/ledger modules passed 230
tests. Commands used `PYTHONDONTWRITEBYTECODE=1` and
`--confcutdir=tests/unit`; no provider traffic was made. The initial failed
runs before installing the missing dependency are historical and superseded
by this complete run. The original CI run remains failed; corrected-head CI
has not run. The CI cause remains unproven, and no flaky/unrelated
classification is claimed. Exact-source independent review remains pending;
no production source, runtime behavior, model setting, or acceptance closure
changed.
