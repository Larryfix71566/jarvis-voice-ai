# Mortimer — Automated Memory Consolidation

**Status: APPROVED by Larry 2026-08-20 ("implement the plan") — IMPLEMENTED,
tests green.**
Author: Claude, 2026-08-20. Requested by Larry (*"memory
optimization/consolidation needs to be automated to keep memory optimized …
ask for confirmation on contradictory rules/memory so that those can be
clarified and resolved"*).

---

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
- **Voice**: the connect-time greeting path (`on_client_connected`)
  appends one sentence when open reviews exist: "I have N memory
  conflicts to resolve when you have a moment." Offered once per
  connect, never blocking, never repeating in-session — the ambient
  strip's dismiss-until-content-changes discipline.

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
- [x] A3 review queue: Memory panel section + one-sentence voice offer
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
- **Voice**: `on_client_connected`'s greeting note in
  `jarvis/bot/pipeline.py` appends one line when
  `memory_sweep.open_review_count() > 0`, asking the model to mention it
  briefly — same "offered once per connect, never repeating in-session"
  shape as the plan specified (a fresh connect re-checks the count; the
  offer never fires mid-session).
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
