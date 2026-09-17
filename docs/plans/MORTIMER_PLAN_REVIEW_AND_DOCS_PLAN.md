# MORTIMER PLAN REVIEW + DOCUMENT CONSOLIDATION — implementation plan

**Status:** IMPLEMENTED — Parts A, B and C (status line added 2026-09-17;
the document had none). Evidence per decision: R2 `PLAN_REVIEW_PROMPT` at
`jarvis/prompts.py:244`; R1/R4/R5 `review_path` plumbed through
`jarvis/agents/delegate.py`, `jarvis/bot/display.py:343` and
`jarvis/bot/plan_watcher.py:132` as a variant of the planning pathway; R7 the
`Fable` / `Fable 5` → `claude-fable-5` aliases in `config/model_aliases.yaml`;
R8 `STT_KEYTERMS` passed to `DeepgramFluxSTTSettings` (`jarvis/bot/pipeline.py:400`);
D2 nineteen plans retired to `docs/plans/implemented/`; D3 `docs/README.md`
present. R6's routing eval was not re-run for this status line — `tests/evals/`
exists, but whether it still covers the capability-denial case is unverified
here.


**Problem (from the 2026-08-17 12:44–12:50 session's logs).** Larry asked
Mortimer to "use Fable 5 to review this plan" (the geolocation development
plan) and the request failed at every layer at once:

1. STT never produced the word "Fable" — Deepgram heard "table five",
   then "Clyde's frontier model" (conversation log 16:49:02–16:49:52 UTC).
   No keyterm boosting is configured (`jarvis/bot/pipeline.py:271` passes
   only `model=` to `DeepgramFluxSTTSettings`, whose `keyterm` field is
   unused).
2. The Supervisor then **denied its own capability** — "I don't have
   access to Clyde's frontier model or external AI systems", "I don't
   have API keys for external services, and I can't call Claude or other
   LLMs directly" (16:49:56, 16:50:20) — without a single tool call or
   delegation. Both statements are false (the registry has an Anthropic
   frontier profile; the planning tools were registered). Root cause: no
   prompt vocabulary anywhere maps "review a document with a named model"
   to a capability, so rule 8/10 had nothing to route to.
3. Even routed perfectly, the request had nowhere to go — a real
   architecture gap: `plan_start` AUTHORS new plans (`PLAN_AUTHOR_PROMPT`
   receives only the goal; the authoring model has no repo access and
   never sees the document), and `convene()` reviews failed self-edit
   attempts. "Send this existing document to a named model for critique"
   is a third workflow that does not exist.
4. `config/upgrade_models.yaml` has no Fable profile (kimi-k3, kimi-k2,
   claude-opus, gpt-4.1-mini only) — even a perfect route would have hit
   `UnknownModelProfileError`.

**Two secondary defects from the same investigation:**

5. Agent-written documents are scattered and get lost: the geolocation
   docs ended up in TWO places (`docs/GEOLOCATION_DEVELOPMENT_PLAN.md`
   and `jarvis/docs/GEOLOCATION_BACKEND_SPEC.md` — the latter an
   agent-invented directory), which caused two failed reads in the
   12:46–12:47 session (runs `6a3502f1`, `f27645a2`: both looked in
   `docs/`, found nothing, and one told Larry the spec "isn't there").
   Separately, 18 historical plan documents sit loose at the repo root.
6. Test pollution of the live database: `tests/unit/test_upgrade_agent.py`'s
   council-escalation tests never set `JARVIS_DB_PATH`, so every pytest
   run writes junk `council_rounds` rows ("validate me", "rewrite the
   wake word detector" — 8 rows landed in `data/jarvis.db` on 2026-08-17
   alone) into the LIVE DB via `get_conn()`'s default path.

**Ground rule (same as every plan in this repo):** every decision below
has already been made. Implement it exactly as written; if something is
genuinely undecided, that is a defect in this document — stop and report
it rather than choosing.

---

## §1 Decisions — Part A: the review pathway (R1–R6)

### R1 — Review is a variant of the planning pathway, not a new machine

No new job slot, no new endpoints beyond a parameter, no new council
functions. `POST /api/plan/start` gains one optional field,
`review_path: str` — when present, the job is a REVIEW of that document:

- The sidecar reads the document ONCE, synchronously, at start time,
  via `mcp_servers.mcp_repo.logic.repo_read_file(review_path)` — the
  same path-validated, deny-listed, 256KB-capped read voice uses. A
  failed read refuses the start synchronously
  (`{"ok": false, "error": <the read error>}`), before any thread
  launches — a review of an unreadable document must never start.
- The document's content is injected into every author call (single mode
  AND council mode) via the existing `_proposer_user_message` /
  `_judge_user_message` context assembly — see R3.
- Both existing modes work unchanged with it: `mode="single"` = one named
  model reviews; `mode="council"` = every usable profile writes a
  parallel review, judges score advisorily, the USER picks — the same
  founding rule (council ranks/advises, never authors the selected
  artifact; a human selects) carries over with zero new machinery.

`_plan_job` gains one field: `"review_path": None` (set for review jobs,
NULL otherwise). Everything else about the job lifecycle
(running/awaiting_choice/done/error, choose, cancel) is identical.

### R2 — `PLAN_REVIEW_PROMPT` (jarvis/prompts.py, the single source of truth)

A new locked prompt beside `PLAN_AUTHOR_PROMPT`, used for BOTH modes of a
review job (imported by `jarvis/council/council.py` exactly as
`PLAN_AUTHOR_PROMPT` already is — one prompt, never a fork). Verbatim:

```
Review the implementation plan or specification document provided below. Review focus: {goal}

You are reviewing, not rewriting. Produce a REVIEW DOCUMENT in markdown with these sections, in order:
- Verdict: one paragraph — is this document sound enough to implement as written?
- Gaps: decisions the document leaves unmade, missing components, and unstated assumptions an implementer would trip over. Be specific: quote or name the section each gap lives in.
- Corrections: places where the document is wrong (technically, or internally inconsistent), each with the concrete fix.
- Risks the document underweights or omits.
- Recommendations: concrete changes, ordered by importance. Distinguish must-fix from nice-to-have.

Judge the document on its own stated goals — do not substitute a different design because you would have chosen differently, unless the chosen design is actually defective (then say so under Corrections, with reasons).
Do not pad. Do not restate the document's contents back at length. If a section of the document is genuinely fine, say so in one line and move on.
```

The judge prompt for a council-mode review is `PLAN_JUDGE_PROMPT`,
UNCHANGED — its criteria ("is every decision actually made… honest about
risks") read correctly against competing reviews as well as competing
plans, and adding a third judge prompt would triple the maintenance
surface for no measured benefit. Deliberate decision, not an oversight.

### R3 — Document injection: one assembly site, bounded

`_proposer_user_message` and `_judge_user_message`
(`jarvis/council/council.py`) each gain ONE additive branch in their
non-scope arm: when `context["document"]` is present, append (after
GOAL, before any proposals):

```
DOCUMENT UNDER REVIEW ({path}):
{content}
```

`convene()` never passes `document`, so escalation rounds are untouched.
Context keys, fixed: `context["document"]` = the (truncated) content,
`context["document_path"]` = the repo-relative path rendered as `{path}`
in the header above — both set only by the sidecar's review start.
The sidecar truncates the content BEFORE building context, at
`PLAN_REVIEW_DOC_MAX_CHARS = 60_000` (new ⚙ knob in
`jarvis/council/config.py`, beside `PLANNING_MEMBER_TIMEOUT_S`), with
suffix `"\n\n… (truncated for review — flag this truncation in your
verdict)"` — a reviewer must know it saw a partial document.
`_run_plan_single` (`jarvis/admin/server.py`) switches from its ad-hoc
`f"GOAL:\n{goal}"` to calling `_proposer_user_message(goal, context,
"doc")` — so single mode and council mode share ONE user-message
assembly, which is what makes the document injection land in both
automatically. `draft_candidates` gains an optional
`context: dict | None = None` parameter, passed through to both message
builders (default `None` → `{}`, existing callers unchanged).

Round rows for a review job are written with `placement="review"`
(`workflow="planning"` as today — so the existing `compute_agreement`
exclusion covers reviews with no new code).

### R4 — Adoption of a review

Same adopt endpoint, two review-specific differences, both keyed off
`review_path` being set on the job:

- Default path: `docs/reviews/<slugified-goal>.md` (plans keep
  `docs/plans/<slug>.md`).
- The attribution footer's verb changes: `*Review by {profile}
  ({provider_model_string}) — {YYYY-MM-DD}. Reviewed:
  {review_path}.*` (council mode appends the same "Selected by Larry
  from {n} council candidates (round {round_id})." clause). Same single
  stamping site (the adopt endpoint), same rule: candidates on the
  ballot stay footer-free; an unadopted review stamps nothing.

### R5 — Voice tools: parameters, not new tools

`mcp_selfedit`'s `plan_start` gains `review_path: str = ""` (passed
through; empty = authoring mode as today). Its docstring gains:
"REVIEW_PATH, when set, reviews that existing repo document instead of
authoring a new plan — use this whenever the user asks to have a plan,
spec, or document reviewed, critiqued, or checked by a model."
`plan_status`/`plan_adopt` summaries say "review" instead of "plan"
when the polled job carries `review_path` (one conditional in
`mcp_servers/mcp_selfedit/logic.py`; the adopt preview names the
`docs/reviews/` default). `plan_choose` unchanged. **Tool count stays
48** — `test_registry.py` is untouched.

### R6 — Routing vocabulary + eval (the capability-denial fix)

- Developer prompt (`jarvis/prompts.py`), the P7 routing sentence is
  extended to (verbatim replacement of the existing sentence): `"For
  implementation plans, specifications, or design documents, never
  author OR review the document yourself in this conversation — call
  plan_start (choosing mode and profile per the user's words; pass
  review_path to review an existing document) and report its status.
  Quick factual summaries are still yours."`
- Supervisor prompt rule 8 gains one sentence (verbatim, appended before
  the "Merely opening…" sentence): `"Named AI models — Claude, Fable,
  Opus, Kimi, GPT — are planner profiles the developer can use for
  authoring or reviewing plans; never claim you lack access to them or
  their API keys — delegate to developer and let it report what the
  registry actually has."`
- `tests/evals/routing_eval.py` gains three cases, expected agent
  `developer`: "have Fable five review the geolocation plan and report
  gaps", "use Claude's frontier model to critique the backend spec",
  "get kimi to check the development plan for problems".

## §1 Decisions — Part B: registry + STT (R7–R8)

### R7 — `claude-fable-5` registry profile

`config/upgrade_models.yaml` gains (after `claude-opus`, same shape):

```yaml
  - name: claude-fable-5
    label: "Claude Fable 5 — Anthropic Mythos-class, above Opus"
    provider: anthropic
    model: claude-fable-5
    base_url: https://api.anthropic.com/v1/
    api_key_env: ANTHROPIC_API_KEY
    temperature: 0.2
    tier: frontier
```

If the first live call 404s on the model string, the fix is the `model:`
value only (Anthropic's OpenAI-compat endpoint naming) — nothing else in
this plan depends on the exact string. This file is off the self-edit
allowlist by design; this change lands via the normal human PR.

### R8 — STT keyterm boosting

`jarvis/bot/pipeline.py`: `DeepgramFluxSTTSettings` gains
`keyterm=STT_KEYTERMS`, a new module-level constant directly above the
STT construction site (verbatim):

```python
# Deepgram Flux keyterm boosting — proper nouns this vocabulary-heavy
# console actually needs recognized. Static by design: deriving these
# from the model registry at boot would couple STT config to
# upgrade_models.yaml for marginal benefit. Observed failure this fixes:
# "Fable 5" -> "table five" -> "Clyde's frontier model" (2026-08-17).
STT_KEYTERMS = [
    "Mortimer", "Jarvis", "Fable", "Claude", "Opus", "Kimi",
    "geolocation", "self-edit",
]
```

## §1 Decisions — Part C: document consolidation (D1–D4)

### D1 — Canonical structure

```
docs/
  README.md            # the index/convention file (D3)
  plans/               # agent-authored plans & specs; the planning
                       #   pathway's adopt default (unchanged)
  reviews/             # adopted review documents (R4's default)
  plans/implemented/   # completed historical implementation plans,
                       #   moved from the repo root (D2)
```

Moves (all `git mv`, one commit, so history follows):

- `jarvis/docs/GEOLOCATION_BACKEND_SPEC.md` → `docs/plans/GEOLOCATION_BACKEND_SPEC.md`;
  then `jarvis/docs/` is removed (it must not exist — it was
  agent-invented and is exactly the "lost document" failure mode).
- `docs/GEOLOCATION_DEVELOPMENT_PLAN.md` → `docs/plans/GEOLOCATION_DEVELOPMENT_PLAN.md`.

### D2 — Root-level plan documents move to `docs/plans/implemented/`

All 19: `HERMES_INTEGRATION_PLAN.md`, `Jarvis_Upgrade_Plan.md`,
`Jarvis_Voice_AI_Agent_Implementation_Plan.md`, `MORTIMER_AGENT_TRUST_PLAN.md`,
`MORTIMER_CAPTION_PLACEMENT_PLAN.md`, `MORTIMER_CREDENTIAL_VAULT_PLAN.md`,
`MORTIMER_DEVELOPER_AGENT_FIX_PLAN.md`, `MORTIMER_DEVELOPER_DOCK_PLAN.md`,
`MORTIMER_ENGAGEMENT_DESIGN_PLAN.md`, `MORTIMER_INTERFACE_UPGRADE_PLAN.md`,
`MORTIMER_LLM_COUNCIL_EVAL.md`, `MORTIMER_LLM_COUNCIL_PLAN.md`,
`MORTIMER_LLM_COUNCIL_V2_PLAN.md`, `MORTIMER_MEMORY_PROCEDURES_PLAN.md`,
`MORTIMER_PLANNING_PATHWAY_PLAN.md`, `MORTIMER_RUN_LOGGING_PLAN.md`,
`MORTIMER_SIDE_DRAWER_PLAN.md`, `MORTIMER_STAR_LAYOUT_PLAN.md`,
`MORTIMER_VOICE_UI_PLAN.md`.

Stays at root (working files, not documents): `README.md`, `CLAUDE.md`,
`DEVIATIONS.md`, `ROADMAP.md`.

Reference updates in the SAME commit: every path-like mention of a moved
file in `CLAUDE.md` (12 today) and `DEVIATIONS.md`/`README.md` (grep for
each moved filename). Prose citations of plan names inside `.py`/`.ts`
comments are NOT paths and are left alone — the documents remain findable
by name via `docs/README.md` and `repo_search`.

### D3 — `docs/README.md` (new, verbatim skeleton)

```markdown
# Documentation map

- `plans/` — implementation plans and specifications, including those
  authored through the planning pathway (adopt default). One document
  per plan; never create documentation directories anywhere else in the
  repo (`jarvis/docs/` in particular must not be recreated).
- `plans/implemented/` — completed implementation plans, kept for the
  decision history they carry. CLAUDE.md links here.
- `reviews/` — model-authored reviews of plans/specs, adopted through
  the planning pathway's review mode. Each ends with an attribution
  footer naming its reviewer.
```

### D4 — Guardrails against recurrence (prompt + tool description, no hard block)

- Developer prompt gains (verbatim, after the R6 sentence): `"Plan,
  spec, and design documents live under docs/plans/ and reviews under
  docs/reviews/ — write them there and never invent new documentation
  directories."`
- `mcp_repo`'s `repo_write_file` tool description
  (`mcp_servers/mcp_repo/server.py`) gains the same one-line note.
- Deliberately NO deny-list entry forcing `.md` files into `docs/` — the
  developer legitimately edits `README.md`, `ROADMAP.md`, and code-adjacent
  markdown; a hard block would break those. Prompt + description +
  default paths are the mechanism; `docs/README.md` is the map.

## §1 Decisions — Part D: test isolation + cleanup (T1–T2)

### T1 — `tests/unit/test_upgrade_agent.py` DB isolation

New autouse fixture at module level (verbatim):

```python
@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Council escalation paths write rounds via get_conn()'s default
    path — without this, every pytest run pollutes the LIVE
    data/jarvis.db (8 junk rounds observed on 2026-08-17)."""
    db_path = tmp_path / "upgrade_agent_test.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()
```

(imports `get_conn, run_migrations` from `jarvis.db` at top of file).
Audit the other unit/integration files for the same hole with
`grep -L "JARVIS_DB_PATH" $(grep -rl "convene\|council" tests/)` and fix
any file that both convenes and lacks the env var the same way.

### T2 — One-time live-DB cleanup (operator step, not automatic)

```sql
DELETE FROM council_scores WHERE round_id IN
  (SELECT round_id FROM council_rounds WHERE status='too_small'
   AND goal IN ('validate me', 'rewrite the wake word detector'));
DELETE FROM council_rounds WHERE status='too_small'
  AND goal IN ('validate me', 'rewrite the wake word detector');
```

Run once via `sqlite3 data/jarvis.db` after T1 lands (documented in the
acceptance checklist; never wired into startup — startup must not carry
data-deletion logic aimed at a one-time event).

## §1 Decisions — Part E: display overlay resize + translucency (W1–W3)

*(Added 2026-08-17 per Larry: the in-page popup showing a plan document
cannot be resized and is not translucent enough.)*

### W1 — The overlay becomes drag-resizable

`web/src/components/DisplayPanel.tsx` gains a resize handle
(`.display-resize`, bottom-right corner, 14×14px, `cursor: nwse-resize`),
implemented with the same pointer-event drag pattern `SideDrawer.tsx`
already uses for its width drag — this repo's established resize
convention, not a new one. Behavior, locked:

- Size lives in component state as `{w, h}` in px, applied as inline
  `width`/`height`; persisted to `localStorage` under
  `mortimer.display.size` (JSON `{"w": n, "h": n}`), same read-guarded
  try/catch discipline as `mortimer.drawer.*`.
- Clamp: min 280×180, max `0.9 * innerWidth` × `0.85 * innerHeight`,
  re-clamped on window resize.
- No stored size = today's default footprint: the CSS
  `max-width: 40vw; max-height: 40vh` stays as the DEFAULT (it applies
  until the first user resize sets inline dimensions, which override
  it). **Deviation note for DEVIATIONS.md:** MORTIMER_VOICE_UI_PLAN.md
  U4's "never more than ~40% of the viewport" cap is deliberately
  superseded for user-resized windows — an explicit drag is user intent,
  and it outranks the ambient-visibility default. The 40% rule still
  governs every window the user has never resized.
- The narrow-screen media query (`command-deck.css` @860px) keeps its
  full-width override; the resize handle is hidden there
  (`display: none`) — corner-drag on a full-width phone layout is noise.
- The `⧉` popped-out second browser window is untouched: the OS already
  resizes it; verify `DisplayContent` fills 100% of it and fix the CSS
  if it does not (one acceptance item, no speculative code).

### W2 — More translucent

`command-deck.css` `.display-panel`: `background: rgba(4, 9, 12, 0.55)`
→ `rgba(4, 9, 12, 0.35)`, and `backdrop-filter: blur(8px)` → `blur(12px)`
(both the standard and `-webkit-` lines) — lower fill opacity needs more
blur to keep text readable over the animated wave. The
no-backdrop-filter fallback drops `0.92` → `0.85` only (without blur,
translucency costs legibility fast; 0.35 there would be unreadable).

### W3 — Scope guard

No opacity/size controls in the UI beyond the drag handle (no sliders,
no settings entry) — one gesture, one localStorage key. If the new
values prove wrong they are two CSS numbers.

---

## §2 Files

**Modified:** `jarvis/prompts.py` (R2 PLAN_REVIEW_PROMPT, R6 developer +
supervisor sentences, D4 doc-location rule);
`jarvis/council/council.py` (R3 document branch in both message
builders, `draft_candidates` context param);
`jarvis/council/config.py` (R3 `PLAN_REVIEW_DOC_MAX_CHARS`);
`jarvis/admin/server.py` (R1 `review_path` on PlanStartIn/_plan_job +
synchronous read-and-refuse, R3 shared message assembly in
`_run_plan_single`, R4 adopt default path + footer verb);
`mcp_servers/mcp_selfedit/server.py` + `logic.py` (R5 param +
summaries); `mcp_servers/mcp_repo/server.py` (D4 description);
`config/upgrade_models.yaml` (R7); `jarvis/bot/pipeline.py` (R8);
`tests/evals/routing_eval.py` (R6 cases);
`tests/unit/test_upgrade_agent.py` (T1); `CLAUDE.md` +
`DEVIATIONS.md`/`README.md` reference updates (D2). `.env.example` is
UNCHANGED — this plan introduces no environment variables. The one
Edit-panel touchpoint: `web/src/components/EditModePanel.tsx` (Planning card gains
an optional "review an existing document" path input that sets
`review_path` on start; done-state header says "review" when the job has
one). Part E: `web/src/components/DisplayPanel.tsx` (W1 resize handle +
size state/persistence), `web/src/command-deck.css` (W1 `.display-resize`
rule + handle hiding in the @860px query, W2 translucency values),
`DEVIATIONS.md` (W1's U4-cap deviation note).

**Moved (git mv):** the two geolocation docs (D1) and the 18 root plan
documents (D2). **New:** `docs/README.md` (D3),
`tests/unit/test_admin_plan_review.py` (review-mode start/read-refusal/
adopt-footer tests), `tests/acceptance/plan-review-and-docs.md`.
**Test updates:** `test_admin_plan.py` (review_path threading),
`test_planning_council.py` (context/document injection + placement),
`test_mcp_selfedit_logic.py` (R5 param + wording), `test_prompts`-adjacent
none (no prompt unit tests exist).

---

## §3 Implementation order

1. T1 test isolation + T2 cleanup SQL documented — stop the live-DB
   bleed before anything else runs the suite.
2. R2 + R3: prompt, config knob, council message-builder branches,
   `draft_candidates` context param + tests.
3. R1 + R4: sidecar review_path (start/read-refuse/adopt) + tests.
4. R5: mcp_selfedit param + wording + tests.
5. R6 + R7 + R8: prompts/eval cases, registry profile, STT keyterms.
6. D1–D4: git mv moves, reference updates, docs/README.md, guardrail
   text — one commit for the moves + reference updates together.
7. Edit panel review input; W1+W2 overlay resize/translucency;
   build/lint.
8. Acceptance checklist; full pytest; routing eval (live).

---

## §4 Verification (tests/acceptance/plan-review-and-docs.md, key items)

- [ ] Re-run the exact failure: "have Fable 5 review the geolocation
      plan and report gaps" → STT surfaces "Fable" (R8) → Supervisor
      delegates to developer without any "I can't" (R6) → `plan_start`
      with `review_path=docs/plans/GEOLOCATION_DEVELOPMENT_PLAN.md`,
      profile `claude-fable-5` (R7) → review completes, `plan_status`
      speaks it, adopt lands `docs/reviews/…` with the reviewer footer.
- [ ] Council-mode review: parallel reviews with advisory scores; user
      chooses; unchosen reviews retained in the round log.
- [ ] `plan_start` with a nonexistent/denied `review_path` refuses
      synchronously with the read error; job stays idle.
- [ ] A 70KB document reviews with the truncation notice present in the
      injected content (unit-tested, not live).
- [ ] `git log --follow docs/plans/implemented/MORTIMER_LLM_COUNCIL_PLAN.md`
      shows pre-move history; no root `*_PLAN.md` remains; `jarvis/docs/`
      does not exist; CLAUDE.md contains no stale path.
- [ ] Two consecutive `pytest tests/unit -q` runs add ZERO rows to
      `data/jarvis.db`'s council_rounds (count before == after).
- [ ] `--agreement` unchanged by review rounds (placement="review" rides
      the existing workflow="planning" exclusion).
- [ ] Overlay: corner-drag resizes the plan window beyond 40vw/40vh up
      to the 90/85% clamp; the size survives a reload
      (`mortimer.display.size`); a never-resized window still opens at
      the 40% default; the wave reads through the more translucent
      background; the popped-out `⧉` window fills on OS resize.
- [ ] Full pytest + web build/lint clean; routing eval ≥ 90% including
      the three new cases.

---

## §5 Risks

| Risk | Level | Mitigation |
|---|---|---|
| `claude-fable-5` model string wrong for Anthropic's compat endpoint | Medium | Isolated to one YAML value; first live call surfaces it; nothing else depends on it |
| Root-doc moves break an unnoticed path reference | Low | Grep for every moved filename across the repo in the move commit; CI import-smoke + build catch code-level breaks; prose citations unaffected |
| Keyterm list degrades general STT accuracy | Low | Eight terms, well under Deepgram's limits; removable by deleting one constant |
| Review of a truncated doc misleads | Low | Truncation suffix instructs the reviewer to flag it (R3) |
| PLAN_JUDGE_PROMPT scores reviews poorly | Low | Advisory only, user always chooses; revisit only on observed bad rankings |
| 0.35 overlay opacity too low over bright content | Low | Two CSS numbers (W3); blur raised to 12px to compensate; fallback path kept at 0.85 |
| Resized overlay hides too much of the wave | Low | Only ever user-initiated (W1's deviation note); default footprint unchanged |

---

## §6 Rollback

R1–R5 are additive parameters/branches — revert file-by-file; rounds
already written keep `placement="review"` (harmless). R7/R8 are single
config/constant changes. D1/D2 revert with `git mv` back (history
follows both ways). W1/W2 revert file-by-file (a stale
`mortimer.display.size` key is ignored by the reverted component). T1
must NOT be rolled back (it fixes live-DB pollution). No kill switch
anywhere: the review mode only runs when explicitly started, same
rationale as the planning pathway.

---

## §7 Approval

- [x] Larry approves.
- [x] Implementation may begin.

**Implementation complete (2026-08-17).** All 8 steps done: T1/T2 (test
isolation verified — two consecutive `pytest tests/unit -q` runs added
zero rows to `data/jarvis.db`), R1–R8 (review pathway, registry profile,
STT keyterms), D1–D4 (document consolidation via `git mv`, `docs/README.md`),
W1–W3 (overlay resize + translucency). 965 passed / 1 pre-existing
sandbox-network failure (`test_mcp_web_server`, unrelated) / 3 skipped.
Web `tsc -b` and `oxlint` both clean. Not yet run in this sandbox (no
live API keys / no writable outDir for the exact `npm run build` script):
`RUN_LIVE=1` routing eval, live `claude-fable-5` model-string check, and
`npm run build`'s literal `emptyOutDir` step (confirmed as a sandbox FS
limitation, not a code defect — a build to a fresh outDir succeeded).
One documented deviation: `MORTIMER_PLANNING_PATHWAY_PLAN.md` had never
been committed to git before this move, so it was moved with `mv`+`git add`
rather than `git mv` (no history existed to preserve either way).
