# Mortimer — Automated Memory Consolidation

**Status (2026-09-18): August consolidation phase IMPLEMENTED; section B's
policy and sandbox implementation are PRESENT and unit-verified, including
restart-safe daily budget enforcement, durable privacy-safe shadow receipts,
and the executable staged-rollout/first-20 monitoring gate. The provider
shadow and offline rollout evaluation now pass; gradual Mac enablement and
redacted live benefit measurement remain open.**
The implementation evidence is recorded in
`docs/acceptance/memory-automation/STATUS.md` and the consolidated
[`IMPLEMENTATION_STATUS.md`](../acceptance/IMPLEMENTATION_STATUS.md); the shared
[`ACCEPTANCE_RUNBOOK.md`](../acceptance/ACCEPTANCE_RUNBOOK.md) defines the
remaining Mac rollout evidence. This status does not certify the
remaining deployment gates.

*Reconciled 2026-09-22 against main `88b206f`* (header otherwise accurate;
provider-shadow and rollout-monitoring receipts are present and passing).
Caveats:
- **Runtime classification is heuristic, not model-backed.** The live bot
  passes `heuristic_classifier` (`jarvis/memory_automation.py`, no model
  call) to the idle watcher (`jarvis/bot/pipeline.py`,
  `jarvis/bot/memory_watcher.py`) when `JARVIS_MEMORY_AUTOMATION_ENABLED` is
  set (default false). The model classifier (`ProviderClassifier`,
  `jarvis/memory_automation_eval.py`) is used only by
  `scripts/run_memory_provider_shadow.py`. B7's statement that production
  classification resolves `JARVIS_MEMORY_PROFILE` holds for extraction,
  consolidation and the sweep's August A2/A5 classification
  (`jarvis/memory_sweep.py`), not for the B-section automation classifier.
- **B7's locked names differ from the code.** B7 specifies
  `retrieve_memory_context(query, *, subject, project, limit, max_chars)`;
  the implementation is `retrieve_automated_memory_context(conn, query, *,
  subject, project, limit=20, max_chars=1600, session_id, source_turn)` in
  `jarvis/memory.py`. B7's `classify(candidates, *, policy_version)` is
  implemented as `heuristic_classifier(candidates, *, policy_version="b1")`.
  Migrations `0022_memory_automation` and `0023_memory_classification_shadow`
  match B7.

Original plan: Claude, 2026-08-20, approved by Larry for implementation.
September 17 amendment: automatic classification and maintenance, relevant
recall, scoped corrections, minimal interruptions, and measurable user value.
The historical specification and verification are retained below section B.

## B — Automatic, useful memory (sandbox implementation complete; release gates open, 2026-09-18)

Larry's direction: classification should happen automatically, with less
asking him to administer memory; it should be seamless and add value.
He requested these recommendations be added to this existing plan.
The deterministic policy, bounded queue, retrieval validity filters, scoped
revision path and fail-closed classifier boundary are delivered in the
release-review tree. Idle maintenance now commits its queue updates and
recovers abandoned `running` claims through the bounded retry policy. Provider
shadow evaluation and production enablement are still separate gates. Source
role is enforced after provider decoding as well: assistant and quoted-document
inputs retain their provenance and cannot be promoted into trusted user memory
by a mislabelled classifier response.
It supersedes A2/A3/A5's routine human classification and contradiction
review policy, the startup-only restriction, and the blanket prohibition
on automatically resolving any contradiction. The August implementation
and its test results below remain a historical record, not proof of B.

### B0 — Verified starting point and intended outcome

Source reviewed: `5faa2e639918075413c8962eafbbc466770f8111`.
`memory_extraction.py` already extracts per-exchange facts and observations,
deduplicates candidates and promotes repeated observations. `memory.py`
infers durability tiers primarily from dotted keys; its ordinary prompt
context is ordered by tier and recency. `memory_sweep.py` classifies
audience, but task-rule/implemented verdicts require manual review before
changing audience or archiving. Its review cache is keyed by key sets;
changed content must not be assumed to trigger reclassification.

A read-only September 17 database audit found 83 audience review records:
36 resolved, 45 dismissed, 2 open. There were 76 live facts: 9 identity,
59 preference, 8 project, all with effective audience `interaction`.
These are a snapshot, not a quality score; dismissal counts do not explain
why users dismissed the suggestions.

Success means fewer repeated questions, correct reuse of accepted decisions,
less stale or irrelevant context, and fewer unnecessary interruptions.
More stored memories, fewer live rows, or a prettier graph are not success
criteria by themselves. Extend the existing extraction, memory, sweep,
retrieval and native Memory surfaces; do not create another competing store.
Coordinate with `MORTIMER_OPTIMIZATION_PLAN.md` for per-exchange extraction,
`MORTIMER_MEMORY_CAPACITY_PLAN.md` for storage/context limits and
`implemented/MORTIMER_MEMORY_PROCEDURES_PLAN.md` for work rules.

### B1 — Classify at admission, with evidence and scope

Automatically assign a candidate's subject/entity, project or global scope,
type (fact, explicit preference, inferred preference, decision, task rule,
or temporary context), provenance, confidence/evidence status, and lifetime.
Retain the existing tier/audience fields through a compatible migration;
the implementation design must define their mapping to the new metadata.
Users never need to choose internal labels or dotted keys.

- Explicit user preferences and corrections become usable immediately,
  subject to existing content and privacy rules.
- Inferred preferences remain tentative until supported by independent
  evidence across sessions. Repeated extraction of the same exchange is
  not additional evidence and must not inflate recurrence or confidence.
- Attribute user statements, tool-observed facts and assistant assertions
  separately. Mortimer repeating its own claim cannot establish a fact
  about Larry. Quoted documents are not automatically user instructions.
- Link memories to their source turns and preserve revisions. Record why a
  classification changed, not just its latest label.
- Cache classification by content revision and classifier/policy version,
  rather than key alone. Reclassification is bounded and incremental.
- Unknown classification remains tentative and inspectable. It must not
  silently become a permanent global instruction or trigger a question.

### B2 — Resolve ordinary changes quietly

Apply explicit corrections over older inferences. Supersede old values when
the same subject, scope and effective time establish a real replacement;
preserve the prior version and source for undo. Do not use "newer wins" as
the sole rule. A statement about a trip must not replace a home location.

Resolve apparent conflicts by scope or time where evidence permits:
short spoken answers and detailed written plans can both be valid.
When evidence is insufficient, retain uncertainty and avoid relying on the
disputed value. Ask only when that uncertainty would materially change the
current action or answer and cannot be resolved from available evidence.
Questions should describe the practical choice, never ask users to classify
a memory. Do not ask again for an already explicit, applicable decision.

This permits a sourced identity correction to supersede an old value; it
does not permit a model to merge, age out or guess identity information.
An inferred preference cannot override an explicit instruction. Memory
classification never grants permissions, executes an action, or bypasses
the existing gates for changing executable workflows or repository code.

### B3 — Retrieve for the task and verify changing state

Maintain a small standing context of applicable explicit preferences and
identity defaults. Retrieve additional decisions, constraints and prior
work for the current subject, project and task. Rank by relevance, scope,
evidence strength and validity; use recency as one signal, not the policy.
Archive and prompt exclusion must not make historical evidence unreachable.

Keep storage capacity separate from the per-turn context budget. Do not
archive a useful long-term fact merely to fit every live fact into every
prompt. Reconcile A5 and the capacity plan's "every live fact reaches the
prompt" invariant before changing admission or eviction behavior.

For "continue the sandbox work," recover the current objective, accepted
decisions and outstanding blockers, then verify changeable status from the
repository/runtime. A merged PR is not proof that a feature is deployed.
Do not auto-archive a request as implemented solely because the classifier
thinks it sounds familiar or the assistant previously claimed success.
Record which retrieved memories actually informed an answer; retrieval
alone is not evidence that a memory was useful or used correctly.

### B4 — Maintain memory without creating chores

Classify and deduplicate during admission; perform bounded background
consolidation and re-evaluation during idle periods, independently of boot
frequency. Use persistent work records, content versions, retry limits and
per-period budgets. A restart must not reset the budget or endlessly
reprocess the same facts. Failures remain visible without interrupting voice.

Give temporary context an expiry or revalidation rule based on its meaning.
Do not expire an explicit standing preference merely because it is old or
rarely recalled. Retain reversible history for correction and audit.
Unanswered, immaterial uncertainty can remain uncertain.

Replace routine greeting-time review counts with quiet maintenance. Keep
an optional activity/history view and concise explanations on request. An
open review must never be injected into the connect-time voice context; it is
available only from the Memory panel or an explicit memory request.
The native Memory tab and graph become inspection and correction tools:
show provenance, scope, confidence/evidence, what superseded what, why a
memory was used, and undo/forget controls. A dismissal is not corroborating
evidence, and should not permanently suppress reconsideration of changed
content. Preserve existing authorized forget/delete and privacy behavior.

### B5 — Measure benefit and regressions before rollout

Build a versioned synthetic or redacted evaluation corpus with expected
outcomes independently specified before tuning. Include the August failure
corpus and these required scenarios:

1. Explicit units preference is applied later without asking again.
2. Temporary travel does not overwrite home; an explicit move does update it.
3. Concise voice replies and detailed written plans coexist by scope.
4. Resuming a project recalls its accepted decisions and verifies its live
   deployment state instead of treating a plan or merged PR as runtime truth.
5. Assistant-invented claims and quoted external instructions do not become
   trusted user preferences or permissions.
6. Replaying a source exchange does not create duplicates or inflate evidence;
   changed content is eligible for reclassification despite an old review.
7. An uncertain detail creates no interruption until it is consequential;
   an explicit correction is honored and remains reversible.
8. Relevant archived information is recalled; unrelated project memories
   stay out of the answer. Privacy/forget rules apply to every retrieval path.

Record correct preference/decision use, repeated-question rate, unnecessary
interruptions, stale-memory errors, retrieval precision/coverage, unsupported
promotions, classification corrections, latency and model cost. Record
sample counts and denominators. A model's confidence score or its own
assessment of helpfulness is not the acceptance oracle.

All required cases must pass with zero unauthorized scope/permission
expansions and zero privacy/forget regressions. Compare quality, latency and
cost with a captured baseline; set numerical rollout limits in the evaluation
record before the shadow run. Unnecessary interruptions and stale-memory errors must improve on cases
where the baseline fails; an existing zero-error baseline must stay at zero.
Relevant recall and correct explicit-preference use must not regress.
Do not declare success from a lower queue count or reduced prompt size alone.

### B6 — Delivery order and gates

- [x] Inventory current admission, classification, retrieval and review
  behavior; capture baseline metrics and reconcile overlapping plan rules.
- [x] Specify backward-compatible metadata, evidence/version semantics,
  retry/idempotency, budgets, privacy boundaries and rollback.
- [x] Implement admission-time classification and the scoped correction
  policy in the sandbox, using synthetic fixtures and injected model clients.
- [x] Implement task-relevant retrieval and evidence-based validity checks;
  preserve standing preferences and historical recall.
- [x] Add bounded idle maintenance and optional native inspection/undo;
  remove routine classification questions and greeting reminders.
- [x] Shadow existing memories without changing live values, prompts or
  user-facing questions; durable receipts retain only bounded metadata and a
  candidate digest for restart-safe evaluation.
- [x] Run a provider-backed shadow evaluation against the recorded gates. The
  2026-09-18 `claude-sonnet-5` receipt passes all 8 cases with zero regression;
  it touches neither the live database nor production automation.
- [x] Encode the staged rollout, numerical benefit/cost limits, reversible
  first-20 review, and immediate-disable safety checks in the provider-agnostic
  offline evaluator. The checked-in rollout receipt passes the gate without
  credentials, SQLite access, or production writes.
- [ ] Enable gradually with reversible writes and monitor benefit, errors,
  cost and interruptions. Revisit inferred confidence with observed evidence.

**Inspection closure evidence, 2026-09-17:** the admin memory response now
returns the B4 inspection fields (type, subject/scope, provenance,
evidence/confidence, validity, source turn, revision/classifier version,
supersession and bounded usage count). Native and web Memory panels render
those fields with compatibility defaults for legacy rows. This closes the
implementation/decoder portion of B4; gradual Mac enablement and benefit
measurement remain the two runtime gates above.

The approved recovery of 28 failed historical exchanges is separate release
repair, not evidence that B is implemented. Back up first, replay only the
verified failed pairs after deployment, preserve the live extraction cursor,
and record results. Do not combine recovery with bulk reclassification.

### B7 — Locked implementation contract

Use the existing SQLite `memories` and `memory_reviews` tables. Add migration
`0022_memory_automation` with nullable columns `subject`, `scope`, `memory_type`,
`provenance`, `evidence_status`, `confidence`, `valid_from`, `valid_until`,
`source_turn_id`, `content_revision NOT NULL DEFAULT 1`, `classifier_version`,
`classified_at`, and `supersedes_id`. Closed values: scope
`global|project|subject|session`; memory type
`fact|explicit_preference|inferred_preference|decision|task_rule|temporary_context`;
provenance `user|tool|assistant|quoted_document`; evidence
`explicit|corroborated|tentative|disputed|unknown`. Existing rows map to
`global/fact/user/unknown`, revision 1 and classifier `legacy-v1`; content is
unchanged. Invalid enum values reject the write.

Migration `0023_memory_classification_shadow` adds the restart-safe shadow
receipt ledger. It stores bounded classification metadata and a candidate
digest only; it never stores candidate content or changes live retrieval.

The classifier interface is exactly
`classify(candidates: list[Candidate], *, policy_version: str) -> list[Classification]`.
It receives bounded redacted candidate text and source metadata, never tools or
write authority, and returns one result per candidate. Each result has the
closed fields above, confidence 0...1, at most eight source-turn IDs and a
reason code `explicit|repeat_independent|scope_update|insufficient_evidence|
quoted_content|invalid`. Missing/extra/malformed fields abstain the whole batch.
One injected model call handles at most 20 candidates, 12,000 input characters
and 2,000 output tokens; failures change no memory and queue a retry.

Admission classifies after extraction and before durable write. Explicit user
corrections may mechanically replace only the same normalized subject/scope
with an explicit effective time: create a new revision, set `supersedes_id`,
retain the old row, never delete. Inferences require two distinct source-turn
IDs from separate sessions; repeated content hashes count once. Thresholds are
fixed: explicit=1.0, corroborated>=0.80, tentative=0.50...0.79, otherwise
unknown. Tentative/unknown values never enter standing context or authorize an
action and are retrieved only for an explicit subject/project match.

Retrieval is `retrieve_memory_context(query, *, subject=None, project=None,
limit=20, max_chars=1600)`. Filter valid, non-disputed, non-forgotten rows and
sort by scope match, evidence rank (explicit 4, corroborated 3, tentative 2,
unknown 1), explicitness, recency, then ID, descending. Return memory ID,
content, scope, type, provenance, evidence, source turn, superseded ID and
`used_for`; record `used_for` only after insertion into the current prompt.

Persist idle work in `memory_maintenance(id, memory_id, operation,
content_revision, policy_version, attempts, next_attempt_at, status,
last_error_code, created_at, updated_at)`. Operations are
`classify|deduplicate|revalidate|stale_check`. One idle interval handles at
most 20 candidates, one batch/model call or 30 seconds. Retry at most three
times after 60/300/1800 seconds; daily UTC budget is 100 candidates and five
model calls, persisted across restarts. Never run during an active voice turn
or block audio. Idempotency key is memory/revision/policy/operation. Text or
policy changes increment revision and enqueue work.

Background model routing is independent from the voice Supervisor. Production
extraction, consolidation and classification resolve `JARVIS_MEMORY_PROFILE`
through `config/upgrade_models.yaml` (default `claude-sonnet-5`) and use that
profile's provider, endpoint and credential variable. They never reuse
`OPENAI_MODEL`, `OPENAI_BASE_URL` or the Supervisor credential as an implicit
fallback. A missing or invalid memory profile fails closed for that background
operation while preserving voice continuity. Provider-shadow acceptance uses
the same explicit profile contract through
`scripts/run_memory_provider_shadow.py --profile NAME`.

The same separation applies to the other non-voice maintenance calls that
touch the memory/knowledge surfaces. Knowledge-base session digests and
procedure descriptions resolve `JARVIS_BACKGROUND_PROFILE` through the same
registry helper; they never inherit `OPENAI_MODEL`, even when the voice
Supervisor is running Haiku. This keeps the model choice configurable without
making Haiku a hidden dependency of background work.

**Route-boundary implementation status (2026-09-18):** `jarvis/kb_digest.py`
and `jarvis/procedures.py` now use the shared background route helper in
`jarvis/memory_model.py`; `jarvis/config.py` exposes
`jarvis_background_profile`. The model-floor and architecture-reference tests
pin that no registry profile resolves to Haiku and that missing background
  credentials fail closed.

**Runtime staged-admission amendment (2026-09-18):** the same rollout order is
now enforced at the worker boundary by `JARVIS_MEMORY_AUTOMATION_STAGE`.
`shadow` never changes live metadata; `explicit_preferences` admits only
explicit preference classifications; `corroborated_inferences` additionally
admits independently corroborated classifications. Non-admitted results still
receive a bounded shadow receipt, and unknown stage values fail closed before
the worker can claim production admission. This is implementation evidence;
the Mac daily-driver and redacted live benefit/cost receipt remain open.

### B8 — Complete manifest and sequence

Modify `jarvis/memory.py`, `jarvis/memory_extraction.py`,
`jarvis/memory_sweep.py`, `jarvis/db.py`, `jarvis/bot/pipeline.py`,
`jarvis/agents/supervisor.py`, `jarvis/prompts.py`, `jarvis/config.py`,
`jarvis/admin/server.py`, and `web/src/components/MemoryPanel.tsx`. Create
`jarvis/memory_model.py`, `jarvis/memory_automation.py`,
`tests/unit/test_memory_model.py`, `tests/unit/test_memory_automation.py`, and
`tests/fixtures/memory_automation_cases.json`. Add default-off
`JARVIS_MEMORY_AUTOMATION_ENABLED` and `JARVIS_MEMORY_AUTOMATION_SHADOW`.
The acceptance implementation also includes `jarvis/memory_automation_eval.py`,
`tests/unit/test_memory_automation_acceptance.py`,
`tests/unit/test_memory_rollout_acceptance.py`,
`tests/fixtures/memory_rollout_acceptance.json`, and the opt-in
`scripts/run_memory_provider_shadow.py` and
`scripts/run_memory_rollout_acceptance.py`; the runners send or inspect only
checked-in synthetic data and never enable production automation or open the
live DB.
Sequence is fixed: typed schemas/migration; shadow queue; admission
classification; task retrieval/usage; idle worker; inspection/undo; staged
enablement. Every step needs its tests and receipt before the next. No new
database, agent, provider, embedding system or daemon.

The checked-in manifest is also guarded by
`tests/unit/test_plan_manifests.py`, which verifies every B8 implementation,
fixture, acceptance, provider-shadow and rollout-monitoring artifact is present
before the plan can be reported as implemented.

### B9 — Acceptance gates

M0 captures baseline metrics and fixture hash: explicit-preference use,
repeated questions, stale use, unnecessary interruptions, retrieval
precision/coverage, latency, calls and cost. M1 proves migration round-trip,
rollback, zero shadow writes/prompt changes and safe malformed-output abstention.
M2 passes every B5 case: reversible corrections, scope/time coexistence,
assistant/quoted content rejection, duplicate replay protection and relevant
archived recall. M3 requires no regression in explicit use/relevant recall,
improvement on failing interruption/stale cases, zero-error baselines remain
zero, admission p95 <=200ms cache-hit / <=2s one bounded call, and budgets never
exceed. M4 proves redaction/forget/delete across admission, retrieval, queue,
usage records, inspection and undo. M5 proves no greeting chore, restart-safe
queue, voice continuity and Larry's review of the first 20 decisions.

The executable offline B9 gate is recorded in
`docs/acceptance/memory-automation/rollout-monitoring-receipt.json`. It fixes
the rollout order (shadow, explicit preferences, corroborated inferences),
requires all first 20 decisions to be reviewed and reversible, and enforces
the captured latency, daily budget, cost, privacy, duplicate and regression
limits. This closes the sandbox acceptance definition; Mac daily-driver
enablement and redacted live monitoring remain deployment evidence.

Roll out shadow for one daily-driver day, then explicit preferences only, then
corroborated inferences. Task rules remain tentative until the existing workflow
confirmation path accepts them. Disable immediately on privacy regression,
unauthorized scope, duplicate durable row, budget violation or stale-use
regression. Recovery of the 28 failed exchanges remains separate.

### B10 — Self-audit

All cross-consumer schemas, lifecycle states, application owners, thresholds,
retry budgets, rollout order and rollback are fixed above. SQLite is the sole
durable owner; hidden views borrow it. Revision-keyed idempotency prevents
replay drift. Unknown/failed states abstain visibly, and no prompt or model
prose can grant permissions. The file manifest covers every created/modified
path; any source drift blocks implementation pending amendment.

## Historical August implementation specification and evidence

The sections below describe the delivered August behavior. Where they
require routine manual classification, prohibit every automatic correction,
make all interaction facts permanent prompt occupants, or limit maintenance
to startup, section B governs the proposed next implementation. The old
approval checkboxes and test counts do not approve or validate section B.

## 0. What changed, and what the manual cleanup proved

This plan REVERSES the 2026-08-18 D2 decision ("manual-first, no bulk
apply") at Larry's explicit direction. The evidence for reversal is the
manual pathway's own track record: the report-only tools existed for two
days, the review session never happened, and the store grew 180 → 202
facts. A discipline that depends on remembering to run it is a wish, not a
mechanism — the same reasoning as `GOLDEN_RULES`' "every rule names its
mechanical backstop."

The 2026-08-20 manual cleanup (178 → 67 live) is the calibration corpus
for what automation can and cannot decide alone:

- **~80% of the bloat was mechanically obvious**: same tier, high overlap,
  no mixed-content warning, same semantic direction. No judgment used.
- **The dangerous 20% required Larry**: four genuine contradictions
  (short-vs-robust answers, Swift-vs-web environment, current-location-vs-
  Spartanburg-default, contacts-vs-voices), one keep-choice the scorer got
  backwards (cluster 26: it preferred the project-specific echo over the
  durable model-agnostic rule), and one poisoned summary row. **Every one
  of these would have been resolved WRONG by naive auto-merge.**
- The worst finding was not a duplicate but a **false fact cluster**
  ("Swift native app, CSS doesn't apply") that actively misdirected the
  developer — no overlap scorer finds that; only reading the facts does.

So the design principle: **automate the mechanical 80%, queue the
judgment 20% for Larry, and never let the queue be silently skippable.**

## A1 — Auto-consolidation sweep (`jarvis/memory_sweep.py`)

Runs at bot startup on a detached daemon thread (beside the run-log prune
and key-health probe — same pattern, same reason: never delay boot).

Per sweep, using `jarvis.consolidate`'s EXISTING clustering (cliques,
never chains; one scorer, not a second implementation):

1. **Auto-archive** a cluster member only when ALL hold:
   - same tier, and tier ∈ {preference, project, system} (identity NEVER
     auto-touched — existing rule, unchanged);
   - overlap ≥ `SWEEP_AUTO_THRESHOLD` (0.8 — above every misjudged case
     in the calibration corpus; the cluster-26 mistake scored 0.667);
   - NO `mixed_content_warning()` on any member (the Fahrenheit-eaten-by-
     merge hazard stays a hard stop);
   - the kept fact is the LONGEST content, not the scorer's pick — the
     calibration corpus shows longest-content chose correctly in every
     mechanical cluster, and cluster 26's error was preferring specificity
     over durability, which length proxies better than score.
   - Archive via `archive_fact(key, "auto-consolidated:<kept>")` — never
     delete; the `auto-` prefix distinguishes machine decisions from
     human ones forever.
2. **Queue, never touch**, everything else: sub-threshold clusters,
   mixed-content clusters, cross-tier echoes.

Cap per sweep: `SWEEP_MAX_ARCHIVES = 10`. A bug in the sweep must be able
to do only bounded damage between boots; the backlog drains over a few
restarts rather than one big-bang pass.

## A2 — Contradiction detection (the new capability)

Token overlap finds *similarity*; contradictions were found by *reading*.
So this is an LLM pass, not a scorer:

- Per sweep, take fact PAIRS within {preference, identity} tiers that
  share ≥ 2 content tokens (cheap pre-filter), cap
  `CONTRADICTION_PAIRS_PER_SWEEP = 20`, newest-first.
- One small-model call per batch (voice-model client, same convention as
  `jarvis/procedures.py`'s `_describe_procedure` — no new client path):
  classify each pair `duplicate | contradictory | distinct`, one word,
  unparseable = `distinct` (abstention discipline, same as council
  scoring: never guess a verdict from prose).
- `contradictory` pairs go to the review queue with both facts quoted.
  **The model NEVER resolves a contradiction** — resolution changes what
  Mortimer believes about Larry, and the calibration corpus shows the
  correct resolution was unguessable from the facts alone (the Swift
  cluster read as confident and was false).
- Results cached in a `memory_reviews` table so a pair is classified
  ONCE, not per sweep (fact-pair hash, verdict, sweep timestamp).

## A3 — The confirmation loop (Larry resolves, mechanically surfaced)

New table `memory_reviews` (migration `0015_memory_reviews`):
`id, kind ('contradiction'|'cluster'), keys_json, detail, status
('open'|'resolved'|'dismissed'), created_at, resolved_at`.

Surfacing, two channels, both existing patterns:

- **Console**: Memory panel gains a "Needs your review" section fed by
  `GET /api/memory/reviews` — amber, because this is literally the
  engagement layer's "needs-your-confirmation" semantic. Each row shows
  the conflicting facts with three actions: keep A (archive B), keep B
  (archive A), or rewrite (a text field that upserts a replacement and
  archives both). `POST /api/memory/reviews/{id}/resolve`.
- **Voice (superseded by B4)**: the original A3 implementation appended a
  one-sentence review offer at connect time. B4 retires that behavior: the
  connect context contains only the time-aware greeting, while the queue stays
  available in the Memory panel and through an explicit memory request.

Dismissed ≠ resolved: a dismissed review never re-queues for the same
pair (the cache holds), but the facts stay live — Larry saying "they're
both true" is a valid resolution.

## A4 — Stale-fact detection (bounded, no cleverness)

The 23 stale facts in the calibration corpus were all SYSTEM tier —
re-derivable claims about Mortimer's own state that aged out. Automation:
any `system`-tier fact not updated in `SWEEP_SYSTEM_STALE_DAYS` (45) is
auto-archived `auto-stale:aged-out`. System tier is already invisible to
the prompt, so the risk is nil and the tier stops accumulating corpses.
`preference`/`project`/`identity` facts NEVER auto-stale — a preference
stated once two months ago is still a preference.

## A5 — Audience segmentation (Larry 2026-08-20, replacing the budget raise)

*"Memories are for the most part how the interface interacts with the
user, not how the interface asks questions of the LLM — segment those so
we only increase the prompt for things legitimately related to how the
LLM responds."*

The first draft of this section raised `MAX_CONTEXT_CHARS` 1600 → 3200 to
fit the 19 post-cleanup dropped facts. Larry's segmentation is the better
idea and REPLACES it: reading those facts by AUDIENCE shows only one
slice earns every-turn prompt space, and the raise becomes unnecessary —
this section now pulls the same direction as the Supervisor prompt diet
instead of against it.

Every non-system fact belongs to exactly one audience:

- **`interaction`** — how Mortimer speaks to Larry, needed EVERY voice
  turn: name, "Boss", terse replies, the one-confirmation rule, the
  current-location rule, Fahrenheit, voice choice. ~10 facts, ~800 chars.
  This is the ONLY set `render_memory_context` includes.
- **`task-rule`** — how a KIND of work must be done: git workflow,
  review-before-storage, plan-preview-first, web-not-Swift, model-
  agnostic plans, research-first. These matter only during a matching
  delegation, and the framework already built their home: **workflows**
  (K4) — authored rules token-matched per task and injected into the
  SUB-AGENT's prompt. That is also the *correct* prompt: a review-gate
  rule in the Supervisor's voice context was always in the wrong prompt,
  since the developer never sees the conversation. Conversion runs
  through the EXISTING `classify --extract-workflow` pipeline (draft +
  review + `archive_fact(key, "workflow:<name>")`) — no second
  conversion path.
- **`implemented`** — feature requests stored as preferences that have
  since SHIPPED (the model chip, the Agents tab, run status cards).
  These belong in no prompt; queued for archive confirmation as
  `deleted:implemented`.

Mechanics:

1. The A2 small-model pass classifies each non-system fact's audience in
   the SAME batched call as contradiction detection — one word appended
   to the verdict, no extra spend. Cached identically (re-classified only
   when the fact's content changes).
2. `memories` gains an `audience` column (part of migration `0015`),
   NULL until classified; `render_memory_context` treats NULL as
   `interaction` — **fail-open: an unclassified fact keeps reaching the
   prompt**, because silently dropping a real preference is the worse
   error, and `not_reaching_prompt` stays the watchdog either way.
3. `task-rule` and `implemented` verdicts do NOT act automatically —
   they land in the A3 review queue ("convert to workflow?" / "archive
   as shipped?"), because a misclassified interaction fact acted on
   automatically would silently change how Mortimer talks to Larry.
   Identity-tier facts are never classified as anything but
   `interaction` (mechanical override, not model judgment).
4. `MAX_CONTEXT_CHARS` stays 1600. The interaction set fits with room to
   spare; if `not_reaching_prompt` climbs again the segmentation is
   failing, and the number is on the console.

## A6 — Guardrails carried forward, unchanged

- Identity tier: never auto-archived, never auto-merged, never
  auto-staled.
- `archive_fact` everywhere; `delete_fact` remains human-only.
- Mixed-content warnings are hard stops for automation.
- Kill switch `JARVIS_MEMORY_SWEEP_ENABLED=false`, enforced once at the
  top of the sweep entry point.
- One log line per sweep:
  `memory_sweep archived=N queued=N contradictions=N skipped_mixed=N`.

## Module layout

- `jarvis/memory_sweep.py` — sweep logic, pure where possible (clustering
  and thresholds testable without DB or model; the LLM call injected).
- `jarvis/db.py` — migration `0015_memory_reviews`.
- `jarvis/admin/server.py` — `GET /api/memory/reviews`,
  `POST /api/memory/reviews/{id}/resolve` (thin wrappers, sidecar owns
  nothing new).
- `web/src/components/MemoryPanel.tsx` — the review section.
- `jarvis/bot/pipeline.py` — startup hook (beside existing prunes) + the
  greeting sentence.

## Tests

| test | pins |
|---|---|
| `test_identity_is_never_auto_archived` | A6 — the never-evict tier survives every sweep path |
| `test_mixed_content_blocks_auto_archive` | the Fahrenheit hazard stays a hard stop |
| `test_sweep_archives_at_most_the_cap` | bounded damage per boot |
| `test_kept_fact_is_longest_content` | the cluster-26 lesson, mechanical |
| `test_contradiction_verdict_unparseable_is_distinct` | abstention, never inference |
| `test_a_pair_is_classified_once` | the cache prevents per-sweep respend |
| `test_dismissed_reviews_do_not_requeue` | "both true" is a resolution |
| `test_sweep_disabled_touches_nothing` | kill switch |
| `test_system_stale_never_touches_other_tiers` | A4 confinement |
| `test_auto_archive_uses_archive_not_delete` | reversibility |
| `test_unclassified_audience_reaches_the_prompt` | A5 fail-open — NULL audience renders |
| `test_identity_audience_is_always_interaction` | A5 mechanical override, never model judgment |
| `test_task_rule_verdict_queues_never_acts` | A5 — conversion is confirmed, not automatic |

## Deliberately not done

- **No auto-resolution of contradictions** — the calibration corpus
  proves resolution requires Larry.
- **No embeddings** — same scorer as consolidate/procedures/skills; one
  idea, not two that drift.
- **No sweep of the MemoryWatcher's summary row** — but the summary is
  regenerated from live facts, so cleaned facts flow into it naturally;
  the poisoned-summary failure mode dies with the facts that fed it.
- **No scheduled daemon beyond startup** — Mortimer restarts often enough
  in practice; a timer is complexity waiting for a reason.

## Cost

One small-model call per sweep batch (≤ 20 pairs, one completion) ≈
fractions of a cent per boot. Bounded by the pair cache — a stable store
converges to zero calls.

## Approval

- [x] A1 auto-consolidation (0.8 threshold, longest-content keep, cap 10)
- [x] A2 contradiction detection via small-model pass, cached
- [x] A3 review queue: Memory panel section; voice offer retired under B4
- [x] A4 system-tier auto-stale at 45 days
- [x] A5 audience segmentation (interaction-only prompt; task-rules →
      workflows via existing classify pipeline; implemented → archive;
      MAX_CONTEXT_CHARS stays 1600)
- [x] D2 reversal recorded (manual-first retired for consolidation)

## Implementation notes (2026-08-20)

Built as specified, one deviation from the literal Tests table wording
below (functionally equivalent, noted for anyone auditing against it):

- **Module**: `jarvis/memory_sweep.py` — `run_auto_consolidation` (A1),
  `_select_contradiction_pairs`/`_select_audience_candidates`/
  `_classify_batch`/`_apply_classification` (A2+A5, one batched LLM call
  per sweep), `run_stale_sweep` (A4), `list_open_reviews`/`resolve_review`
  (A3), `run_sweep`/`start_background_sweep` (entry point + daemon
  thread). Kill switch `JARVIS_MEMORY_SWEEP_ENABLED`, same
  enabled()-at-the-top pattern as `jarvis/keyhealth.py`.
- **Migration `0015_memory_reviews`**: `memory_reviews` table exactly as
  designed, plus `audience` column on `memories`. `kind` grew a third
  value beyond the doc's `'contradiction'|'cluster'` — **`'audience'`**,
  one row per single-key task-rule/implemented verdict — since the two
  documented kinds are inherently 2-key rows and an audience verdict is
  1-key; no schema change needed (no CHECK constraint on `kind`).
- **"Classified once" cache**: implemented as "does an open, resolved,
  OR dismissed `memory_reviews` row already carry this exact key-set for
  this kind" — `_existing_review_key_sets`/`_queue_if_new` — rather than
  a separate pair-hash cache table. Same effect (a dismissed pair never
  re-queues, `test_dismissed_reviews_do_not_requeue`/
  `test_a_pair_is_classified_once` both pin it) with one fewer table.
- **A5 mechanics point 3** ("task-rule/implemented verdicts do not act
  automatically"): implemented literally — `memories.audience` is left
  NULL for those two verdicts (fail-open, still reaches the prompt) and
  only a review row is queued; `audience` is written eagerly only for
  the safe 'interaction' verdict and the identity mechanical override.
- **`jarvis/memory.py`**: `render_memory_context`'s SQL gained
  `AND COALESCE(audience, 'interaction') = 'interaction'`; `list_facts`
  (the Memory panel's read) gained `tier`/`audience` columns and an
  `archived_at IS NULL` filter it was missing before (archived facts no
  longer clutter the panel — no caller depended on the old behavior).
- **Sidecar**: `GET /api/memory/reviews`, `POST
  /api/memory/reviews/{id}/resolve` (`action` + optional
  `rewrite_content`), thin wrappers per the doc.
- **Console**: `MemoryPanel.tsx` gained a `.memory-review-section`
  ("Needs your review (N)") above the usage readout, amber via the
  existing `--attn` token — same vocabulary as `.knowledge-warn`. Each
  row offers keep-A/keep-B/rewrite (cluster/contradiction) or convert-
  to-workflow/archive-as-implemented/keep-as-is (audience), plus Dismiss
  on every kind.
- **Voice (B4 revision)**: `on_client_connected` now uses
  `connection_greeting_note` and never reads or injects the open-review count.
  The Memory panel and explicit memory requests remain available for
  inspection and correction; maintenance state does not become a spoken
  reconnect task.
- **`extract_workflow`** (reused for the `convert_workflow` action)
  raises `SystemExit` for its CLI-error paths (no live fact, slug
  collision) — `resolve_review` translates that to `ValueError` so it
  doesn't crash the sidecar's request handler, which does not expect
  `SystemExit` from a library call.

## Verification (2026-08-20)

- `tests/unit/test_memory_sweep.py` — 16 new tests, covering all 13
  planned pins plus 3 extra (valid-JSON parse path, interaction-audience
  render, end-to-end fake-model sweep). All pass.
- `pytest tests/unit -q` — 1302 passed (0 failed; `tests/unit/test_db.py`
  updated for the new migration/table).
- `python -c "import jarvis, jarvis.config, jarvis.cli, jarvis.runlog,
  jarvis.memory_sweep"` — clean (CI's backend import smoke check, plus
  the new module).
- `web`: `tsc -b` — 0 errors. `npm run lint` — 0 errors, 4 pre-existing
  warnings unrelated to this change. (`vite build`'s asset copy step hit
  a sandbox-only file-permission error on `dist/` unrelated to any
  change here — `tsc` is CI's actual type-check gate and passed clean.)
