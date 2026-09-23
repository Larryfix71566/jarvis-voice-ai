# Automated memory acceptance

Consolidated requirement matrix: [`../IMPLEMENTATION_STATUS.md`](../IMPLEMENTATION_STATUS.md).
Remaining Mac procedures: [`../ACCEPTANCE_RUNBOOK.md`](../ACCEPTANCE_RUNBOOK.md).

## User-facing maintenance behavior

The connect-time voice path is now silent about open review rows. Background
classification, consolidation, and retry bookkeeping continue independently;
the Memory panel and an explicit memory request remain the inspection and
correction paths. This closes the prior regression where a reconnect injected
"memory items waiting for review" into the greeting. The Mac daily-driver
rollout gate is still separate: the release-review checkout keeps production
admission fail-closed until the provider and staged-monitoring evidence is
accepted.

Updated 2026-09-18. The B1 policy layer is implemented in
`jarvis/memory_automation.py` and integrated with admission, retrieval, and
the idle watcher. Python acceptance fixtures cover explicit preference use,
independent-session evidence, scoped reversible correction, validity/privacy
filtering, idempotent replay, and durable daily budgets.

The August consolidation and approved 28-exchange recovery remain complete.
The worker now records privacy-safe, durable shadow receipts keyed to the
maintenance job. Receipts contain the policy result and a SHA-256 digest of
the redacted candidate, never candidate text, so shadow behavior can be
measured across restarts without changing live memory or prompt context.
The provider shadow and the offline staged-rollout/monitoring gate now have
passing receipts below. The Mac daily-driver enablement and its redacted
benefit/cost observation remain deployment gates rather than unit-test claims.

Background extraction, consolidation and classification now resolve through
the dedicated `JARVIS_MEMORY_PROFILE` registry route (default
`claude-sonnet-5`); they no longer inherit the voice Supervisor's
`OPENAI_MODEL` or credential. Missing profile credentials fail closed while
preserving the voice pipeline. Knowledge-base session digests and procedure
descriptions use the separate `JARVIS_BACKGROUND_PROFILE` registry route and
cannot inherit the Supervisor's Haiku route either.

The local classifier baseline now recognizes explicit preference/fact language,
project-key scope, tentative task rules, quoted content, and expiry-bearing
temporary context without asking the user to label a memory. Classifier output
remains metadata-only; content changes still require the explicit correction
path. Rows explicitly classified by the new policy are filtered from standing
context when uncertain, quoted, disputed, or expired; legacy rows retain their
fail-open behavior. Session teardown now drains one bounded queued-classification
batch so the final extraction does not wait for a later connection.

The idle watcher now commits classification metadata and maintenance status
before closing its SQLite connection. A crashed worker's stale `running` claim
is requeued through the same three-attempt retry budget, while a third
interruption becomes a visible failed job; malformed timestamps fail closed as
stale. Source-role attribution is enforced at the policy boundary: assistant
and quoted-document rows cannot be promoted to trusted user memory by a
provider response. Focused tests cover all three paths.

The worker now folds distinct sessions and source turns from the existing recall
ledger into its bounded classifier evidence set, so independent-session
corroboration can mature without introducing another evidence store.

The inspection surface now exposes the automated policy metadata end to end:
the admin API and both native/web Memory panels show type, scope, provenance,
evidence status, confidence, classifier version, revision, supersession, and
bounded `used_for` count. Older rows and captured fixtures decode with explicit
compatibility defaults, so adding the fields does not make legacy memory
unreadable.

The B6 runner now requires an explicit `--profile` from
`config/upgrade_models.yaml`; it never inherits the supervisor's OPENAI_MODEL,
endpoint or key selection. The chosen registry entry supplies model, provider,
endpoint, credential variable and temperature policy together. Unknown profiles
fail closed. `--dry-run` reports the route without reading the vault or making
a provider call. For example, inspect an existing Moonshot route (this does
not select it for production memory):
```sh
UV_CACHE_DIR=/private/tmp/jarvis-uv-cache uv run --with-requirements requirements-lock.txt \
  python scripts/run_memory_provider_shadow.py --profile kimi-k3 --dry-run
```
For live evaluation, select the intended evaluation profile explicitly and
supply `--vault-path` when the candidate checkout does not contain the runtime
vault. On the Mac inspected September 18, the runtime vault exists at
`/Users/larryfix/jarvis-voice-ai-clean/data/secrets.vault`; the release-review
checkout has neither a vault nor a `.env`. Do not copy secrets between them.
The runner uses the standard vault loader, preserves non-empty process overrides,
and falls back to its local `.env` for missing values. The receipt records the
selected profile and route without credentials. Calls omit temperature when
the profile specifies null, cap output at 2,000 tokens, and use a 60-second
client timeout with automatic retries disabled.

Route verification on 2026-09-18 selected `claude-sonnet-5` → Anthropic →
`ANTHROPIC_API_KEY` against the runtime vault path. The logged-in Mac vault
was decryptable and the eight-case provider shadow completed without printing
or copying credentials.

Only the checked-in eight-case synthetic corpus is submitted; no live database
was opened and production automation was not enabled. The live provider
receipt at [`provider-shadow-receipt.json`](provider-shadow-receipt.json)
records 8/8 candidate cases, zero regression, 8 calls, and no database or
production writes. The Mac gradual rollout and redacted live benefit/cost
monitoring gate remains open; the offline staged-rollout gate is recorded
separately below.

Verification on 2026-09-18: the complete project Python suite passes (2611
passed, 4 skipped); the focused memory/database/worker set covers the
durable shadow-receipt assertions, with the watcher tests
covering idle integration. The
classifier boundary accepts only the locked JSON shape, retrieval records
``used_for`` events when a session supplies an ID, and shared maintenance
budgets are restart-safe. The offline eight-case B5 benchmark produces a
zero-regression receipt at [`offline-b5-receipt.json`](offline-b5-receipt.json);
the focused shadow test also verifies that receipts contain no candidate
content. The live provider shadow measurement now passes; Mac rollout and
benefit/cost monitoring are still required before the remaining B6 gates can
close. The separate rollout receipt checks the fixed order shadow → explicit
preferences → corroborated inferences, requires Larry's review of the first 20
decisions, and enforces the numerical latency, call, candidate, cost, privacy,
duplicate and regression limits before a staged enablement can be reported.

The offline staged-rollout receipt at
[`rollout-monitoring-receipt.json`](rollout-monitoring-receipt.json) passes
with a 210 ms candidate admission p95, a $0.04 cost ceiling for the captured
comparison, zero safety violations, and all 20 decisions marked reviewed and
reversible. It is a sandbox acceptance artifact; it does not enable the Mac
worker or satisfy the required daily-driver observation.

The runtime gate now enforces the same order through
`JARVIS_MEMORY_AUTOMATION_STAGE`: `shadow` writes only the privacy-safe shadow
ledger, `explicit_preferences` admits only explicit preference classifications,
and `corroborated_inferences` additionally admits independently corroborated
rows. Unknown stage values fail closed, and non-admitted classifications stay
in the shadow ledger. Configuration, watcher, teardown, and stage-boundary
tests cover this switch; it does not bypass the remaining Mac rollout gate.

The same suite's `tests/unit/test_plan_manifests.py` checks that every B8
implementation, fixture, acceptance, provider-shadow and rollout-monitoring
artifact remains in the repository.

The automated portion is reproducible with:
```sh
UV_CACHE_DIR=/private/tmp/jarvis-uv-cache uv run --with-requirements requirements-lock.txt \
  pytest -q tests/unit/test_memory_automation.py \
  tests/unit/test_memory_automation_acceptance.py \
  tests/unit/test_memory_rollout_acceptance.py tests/unit/test_memory.py \
  tests/unit/test_memory_sweep.py tests/unit/test_memory_watcher.py
```
The same focused command was rerun on 2026-09-18 and passed 196 tests; the
plan-manifest verifier is included and now covers 4 checks. These results cover the sandbox policy
and acceptance fixtures; the provider-backed shadow now also passes, while
gradual Mac enablement remains open.

The current full-project run is recorded in
[`full-python-suite-2026-09-18.md`](full-python-suite-2026-09-18.md): 2611
passed, 4 skipped, with no failures. This updates the earlier 2609-test count.

The offline rollout runner was rerun against the checked-in fixture and
returned `passed: true` with zero violations. The explicit provider dry-run
also resolved `claude-sonnet-5` to Anthropic / `ANTHROPIC_API_KEY` without
loading credentials or making a provider call.
