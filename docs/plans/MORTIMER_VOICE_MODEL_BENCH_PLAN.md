# Mortimer — Voice Model Bench: a measured upgrade of the interface LLM

**Status: APPROVED by Larry 2026-08-20 — IMPLEMENTED (§3/§4 infra). V1/V2 runs
and the V3 adoption attempt COMPLETE 2026-08-20: FINAL VERDICT — latency gate failed, Haiku stays.
Haiku live baseline passed all three targets 2026-08-22. Only the reopened
Gemini-direct live trial (Larry, 2026-08-22) is pending; no results recorded.**
*Reconciled 2026-09-22 against main `88b206f`:* header previously read "live
runs pending", contradicting the recorded runs and verdict below. The final
paragraph's lost lead-in ("What this plan permanently shipped regardless of the
verdict:") was restored verbatim from `a65e336`; `5adfb9c` had dropped it when
inserting the reopened-trial section.
Author: Claude, 2026-08-20. Requested by Larry (*"revisit the selection and
see if we can find a more capable LLM that passes our latency threshold …
a more capable model for the interface could solve some of the issues
related to routing to sub-agents"*).

---

## 0. Premise corrections, verified before writing

1. **The interface model is Haiku, not Sonnet.** `.env`:
   `OPENAI_MODEL=claude-haiku-4-5`, `OPENAI_BASE_URL` →
   `api.anthropic.com`. CLAUDE.md's model-discipline section records the
   voice model as "a small, cheap model — Haiku today." The headroom is
   therefore larger than the request assumed.
2. **The latency threshold is NOT undefined — it is locked.**
   `scripts/latency_probe.py` (plan Phase 7, step 7.3) carries the
   targets: **p50 ≤ 1200 ms** non-delegated, **p50 ≤ 2500 ms** delegated,
   **p90 ≤ 3500 ms** overall, measured `user_end→first_audio` from the
   bot's own `TURN` log lines. Every candidate is judged against these
   numbers, not against feel. (My earlier claim that no threshold existed
   was wrong; the probe's docstring is the source of truth.)
3. **The routing evidence supports the hypothesis, narrowly.** Across two
   full eval runs (89%, 91%), three cases missed BOTH times — "commit
   these changes", "change your interface to use a darker theme", "how is
   the interface edit coming along". These are pragmatic-inference
   failures (a terse imperative means *delegate now*), which is what model
   capability buys and what GOLDEN_RULES-style scaffolding fights for.
   But two runs also proved 55 cases cannot resolve small differences —
   any comparison needs repetition and more cases.

**Architectural note:** "the voice model is a dispatcher, never a
design/build model" constrains what the model *does*, not how capable it
is. A smarter dispatcher violates nothing; K5's refuse mode and the
routing itself still keep build work off it.

## 1. What is being decided, and the decision rule — fixed in advance

One question: **is there a model that beats Haiku on routing without
breaking the locked latency targets, at acceptable cost?**

Promotion rule, stated before any measurement (the council's
fixed-in-advance discipline — thresholds are never tuned after looking):

- **Latency gate (hard):** live `latency_probe` targets hold on Larry's
  machine over a ≥ 15-turn real voice session. No bench proxy substitutes
  for this — the pipeline's STT/TTS overhead is constant across models,
  so the bench only shortlists; the probe decides.
- **Accuracy gate (hard):** mean routing accuracy over **3 eval runs**
  ≥ Haiku's 3-run mean **+ 3 points**, AND each of the three known-miss
  cases passes in ≥ 2 of 3 runs. A candidate that ties Haiku loses:
  churn without measured gain is a cost.
- **Cost note (soft):** reported per-turn, never a gate at these scales —
  Larry decides if the multiplier is worth it.

No winner → **Haiku stays**, and the bench results are recorded so the
question is answered rather than perpetually open.

## 2. Candidates

| candidate | route | why |
|---|---|---|
| `claude-haiku-4-5` | direct (current) | baseline — every number is relative to it |
| `claude-sonnet-4-5` (or current Sonnet string) | **direct** Anthropic | the likely sweet spot; no proxy hop, key already live |
| `google/gemini-3.7-flash` | OpenRouter | fast tier, different lineage |
| `openai/gpt-5-mini` | OpenRouter | fast tier, OpenAI lineage |
| `moonshotai/kimi-k2.5` | OpenRouter | already-trusted vendor, `temperature` omitted per D-003 |

Five is enough for one pass; the bench is rerunnable if a sixth looks
interesting later. Frontier models (Opus/Fable/GPT-5.2) are deliberately
excluded: [likely] none passes p50 ≤ 1200 ms with the full Supervisor
context, and per-turn frontier pricing on a voice loop is the wrong
trade — if the bench proves Sonnet-class insufficient, that is a finding
that reopens the question with data.

**OpenRouter is the audition, not necessarily the venue.** The 2026-08-19
reasoning for keeping voice off the proxy (extra hop, upstream routing
variance, independent failure domain) still holds for production. If an
OpenRouter-routed candidate wins, step 2 of adoption is checking whether
it is reachable direct; only if not does the proxy carry the voice loop,
and that trade is called out to Larry explicitly.

## 3. `scripts/voice_model_bench.py` (V1 — the shortlist)

A standalone script, same conventions as `check_keys.py` (REPO_ROOT
anchor, vault via `inject_env()`, no key ever printed):

- Builds the **real** turn: `SUPERVISOR_PROMPT` fully rendered (agent
  catalog, voice addendum, a representative memory context) plus the
  **real tool schemas** from a started registry — a bench against a toy
  prompt measures a different model than production runs.
- Per candidate: **5 streaming reps** of a canonical routing utterance.
  Records TTFT (time to first content token or first tool-call delta),
  total time, and tokens/sec. First rep discarded (connection warm-up).
- **Tool-fidelity micro-check:** 3 utterances that must produce a valid
  `delegate_task` call ("remind me to water the plants in 3 hours" →
  scheduler, etc.). A model that malforms tool calls is disqualified
  regardless of speed — this is the OpenRouter upstream-variance risk
  made measurable.
- Output: one table, machine-readable JSON beside it
  (`logs/bench/voice-model-<date>.json`) so the decision is auditable
  later.
- Env overrides per candidate (`OPENAI_MODEL` / `OPENAI_BASE_URL` /
  key env), never edits to `.env` — the bench must leave configuration
  untouched.

## 4. Accuracy runs (V2)

- **First, extend the eval corpus** with ~10 cases shaped like the known
  misses: terse imperatives ("commit these changes", "push it", "make the
  background darker"), self-referential status asks ("how is the edit
  going"), and matching `none` controls so the extension cannot be gamed
  by over-delegating. **The extension lands BEFORE any candidate runs and
  every candidate — including the Haiku baseline — runs the same
  corpus.** Comparing models across different corpora is not a
  comparison.
- Then per candidate: `OPENAI_MODEL=<m> OPENAI_BASE_URL=<u> RUN_LIVE=1
  python -m tests.evals.routing_eval`, **3 runs**, mean and per-case
  record kept. (`load_settings` reads these from the environment, so no
  file edits; the env-bridge work of 2026-08-19 made the eval safe to run
  this way.)
- Haiku's baseline is re-measured on the extended corpus first — the
  existing 89/91 numbers are from the old corpus and are not comparable.

## 5. Adoption (V3 — only after both gates pass)

1. `OPENAI_MODEL` (and `OPENAI_BASE_URL` if the route changes) in `.env` —
   the one-line change the architecture already supports.
2. Live acceptance: ≥ 15-turn voice session, `python
   scripts/latency_probe.py logs/bot.log`, all three locked targets hold.
   This is the hard gate; a bench-fast model that feels slow live loses.
3. `check_env.py`'s key probe already covers the new (key, endpoint) pair
   automatically — no new check needed (K1 groups by endpoint).
4. **Only then, as a separate follow-up, consider prompt reduction.** A
   stronger model may need less GOLDEN_RULES-style scaffolding — but
   changing model AND prompt together confounds both measurements. One
   variable at a time; the eval re-run after any prompt trim is its own
   gate.
5. CLAUDE.md's "Haiku today" line and the model-discipline section
   updated to record the change and the numbers that justified it.

Council note: if Sonnet wins, the voice model and the `or-sonnet-5`
council judge share an underlying model. This breaks nothing — the voice
model is not a council member and never proposes or judges — but it is
recorded here so nobody later mistakes it for a disjointness violation.

## What this plan deliberately does not do

- **No swap without measurement.** The entire plan is the measurement.
- **No frontier candidates in round one** (§2's reasoning — the bench is
  rerunnable if Sonnet-class disappoints).
- **No prompt changes in the same change as the model change** (§5.4).
- **No new pipeline code.** `OPENAI_MODEL` is already the knob;
  the bench script is the only new file.
- **No OpenRouter for production voice without an explicit call-out** —
  the audition/venue distinction in §2.
- **No per-candidate `.env` edits.** Environment overrides only; the
  repo's configuration is untouched until adoption.

## Cost estimate

Bench: 5 candidates × (4 timed reps + 3 fidelity checks) × ~6k tokens ≈
200k tokens, dominated by cheap tiers — under a dollar. Accuracy: 5
candidates × 3 runs × 55–65 cases × ~7k tokens ≈ 6–7M tokens, mostly
input; [guessing] $10–25 total, the Sonnet runs dominating. Stated so the
spend is approved with the plan rather than discovered on an invoice.

## Acceptance

1. `voice_model_bench.py` produces the table + JSON; no key material in
   either.
2. Extended eval corpus merged; Haiku 3-run baseline recorded on it.
3. All candidates run; results table appended to THIS document with the
   decision-rule verdict per candidate.
4. If a winner: `.env` updated, live `latency_probe` targets hold on
   Larry's machine, CLAUDE.md updated. If none: this document records
   "Haiku stays" with the numbers.
5. `pytest tests/unit tests/integration -q` green (the eval-corpus
   extension must not break the case-count assertions, if any).

## Approval

- [x] §2 candidate list (edit freely — this is taste as much as analysis)
- [x] §1 decision rule (+3 points over 3 runs; hard latency gate)
- [x] §3 bench script
- [x] §4 corpus extension + 3-run protocol
- [x] §5 adoption steps, including the separate-change rule for prompts

## Implementation note (2026-08-20)

`scripts/voice_model_bench.py` (§3) and the 10-case corpus extension in
`tests/evals/cases.yaml` (§4) are built and unit-tested. **The live bench
and accuracy runs are NOT executed by this change** — both require real API
spend (~$10-25 per §"Cost estimate") against keys that live in Larry's
vault/`.env`, and this is the same hand-off shape `check_keys.py` and
`check_env.py` already use: a script Claude writes and Larry runs, not one
Claude runs against production credentials unattended. Run:

```bash
python scripts/voice_model_bench.py                    # V1, shortlist, ~$1
# then, per candidate that survives V1:
OPENAI_MODEL=<m> OPENAI_BASE_URL=<u> OPENAI_API_KEY=<k> RUN_LIVE=1 \
  python -m tests.evals.routing_eval                    # V2, x3 runs each
python scripts/latency_probe.py logs/bot.log --budget   # V3, after adoption
```

Results get appended to §"Results" below (new section) as they come in;
this document is not "implemented" in the sense of §Acceptance until a
verdict is recorded there.

## Results

### V1 — shortlist bench (run by Larry, 2026-08-20, live keys, vault read ok)

| candidate | route | TTFT mean | total mean | fidelity |
|---|---|---|---|---|
| haiku-baseline | direct (current) | 2399 ms | 2462 ms | 2/3 |
| sonnet-4-5 | direct | **2345 ms** | 2982 ms | 2/3 |
| gemini-3.7-flash | openrouter | 2696 ms | 6799 ms | **3/3** |
| gpt-5-mini | openrouter | 9355 ms | 9909 ms | 2/3 |
| kimi-k2.5 | openrouter | 5110 ms | 8863 ms | 2/3 |

Raw JSON: `logs/bench/voice-model-2026-08-20.json`. These numbers are
COMPARATIVE only (§3's rule): the canonical utterance is a delegated-shape
turn, and live first-audio comes from the rule-1 acknowledgment sentence,
which only the live probe (§1's hard gate) can see.

**Finding 1 — Sonnet TTFT is at parity with Haiku** (2345 vs 2399 ms on
the same direct route). The assumed capability-for-latency trade does not
exist between these two on TTFT; total generation is ~500 ms longer, which
delays the *delegation*, not the first audio.

**Finding 2 — the "commit these changes" fidelity miss is the PROMPT, not
the models.** Four models across three vendor lineages (Haiku, Sonnet,
GPT-5-mini, Kimi) all produced NO tool call on the same utterance. One
model missing is capability; every family missing identically is the
prompt — rule 4's clarify instinct plausibly reads "these changes" as a
missing referent, when for git verbs the working tree IS the referent.
Per §5.4 any prompt fix is a separate, later change — but this finding
softens the original hypothesis: a model swap alone will probably not
recover this particular known-miss case. Only gemini-3.7-flash delegated
it anyway (3/3).

### V1 verdict — who advances to V2 accuracy runs

- **haiku-baseline** — advances (re-baseline on the extended 55-case corpus).
- **sonnet-4-5** — advances (TTFT parity; the likely favorite held up).
- **gemini-3.7-flash** — advances (+297 ms TTFT, the only 3/3 fidelity;
  earns its accuracy runs, with the §2 audition-not-venue caveat).
- **gpt-5-mini** — ELIMINATED, latency (9.4 s TTFT is unrecoverable; no
  accuracy spend).
- **kimi-k2.5** — ELIMINATED, latency (5.1 s TTFT; same).

Eliminating two candidates before V2 cuts the accuracy spend by ~40%.

### V2 protocol deviation — EVAL_KEY_ENV

§4's original command shape (`OPENAI_API_KEY=<k> ...`) cannot work for an
OpenRouter candidate: the key lives in the vault, and the vault never
prints values by design — there is nothing to paste. `routing_eval.py`
therefore gained three optional env vars — `EVAL_MODEL`, `EVAL_BASE_URL`,
and `EVAL_KEY_ENV` (the NAME of the variable holding the candidate's key,
never its value; the eval calls `inject_env()` first so a vault-held key
is present to copy). No file edits, no key ever on a command line, and
the eval now prints `eval model: ...` so a 3-run record is attributable.

### V2 commands (3 runs each, record every "Routing accuracy" line)

```bash
# Haiku re-baseline (extended corpus — the old 89/91 are not comparable)
RUN_LIVE=1 python -m tests.evals.routing_eval

# Sonnet, direct (same Anthropic route and key as the voice model today)
EVAL_MODEL=claude-sonnet-4-5 RUN_LIVE=1 python -m tests.evals.routing_eval

# Gemini Flash via OpenRouter
EVAL_MODEL=google/gemini-3.7-flash \
EVAL_BASE_URL=https://openrouter.ai/api/v1 \
EVAL_KEY_ENV=OPENROUTER_API_KEY \
RUN_LIVE=1 python -m tests.evals.routing_eval
```

### V2 — accuracy runs (extended 65-case corpus; 3 runs per candidate)

| candidate | run 1 | run 2 | run 3 | mean |
|---|---|---|---|---|
| haiku-baseline | 55/65 = 85% | 58/65 = 89% | 59/65 = 91% | **88.3%** |
| sonnet-4-5 | 61/65 = 94% | 61/65 = 94% | skipped (verdict fixed) | 94% |
| gemini-3.7-flash | 63/65 = 97% | 63/65 = 97% | 64/65 = 98% | **97.3%** |

**Run 1 per-case detail (2026-08-20):**

- **haiku** (10 misses): the three known misses (#22 "commit these
  changes", #26 "darker theme", #28 "interface edit coming along"), PLUS
  librarian recall #8/#9 ("when does my passport expire", "what did I save
  about the wifi") which it has historically passed, #25 "what apps have
  you built", #27 "add a clock panel", #56 "commit that", #59 "check the
  build status" → systems, and #40 over-delegated (added scheduler). A
  notably bad run vs its old-corpus 89/91 — variance is real, which is
  what the 3-run mean exists to absorb.
- **sonnet** (4 misses): #22 "commit these changes", #56 "commit that",
  #26 "darker theme", #40 under-delegated (dropped librarian). It PASSED
  #25/#27/#28/#59 — the self-referential status-ask failures that
  motivated this plan are gone. The bare commit imperatives remain,
  consistent with V1 Finding 2: that's the prompt's clarify instinct, not
  model capability, and per §5.4 the prompt fix is a separate change.
- **gemini-flash** (2 misses): #54/#55, the screen-vision `none` cases,
  both routed to systems. PARTLY A HARNESS ARTIFACT: the text
  Orchestrator has no `view_screen` tool, so a model inclined to act
  rather than answer has no correct tool to reach for; in production the
  Supervisor has the direct tool. The harness cannot distinguish "would
  over-delegate" from "would use view_screen correctly" — noted, not
  excused (haiku and sonnet both correctly did nothing on the same cases).

**Interim read against the §1 rule (NOT a verdict — 2 runs remain):**
sonnet beats the +3 mean gate by ~9 points on run 1 but is on track to
FAIL the per-case gate on #22/#56 if runs 2–3 repeat; gemini passes every
original known-miss case and the mean gate, with the OpenRouter
audition-not-venue caveat (§2) and the harness-artifact asterisk. The rule
was fixed in advance and will not be bent mid-measurement: if sonnet's
commit-imperative misses hold, the recorded outcome is "fails the
per-case gate; prompt fix required regardless of model," not a threshold
adjustment.

**Run 2 per-case detail (2026-08-20):**

- **haiku** (7 misses): #9 wifi recall, #22 "commit these changes",
  #25 "what apps have you built", #26 "darker theme", #28 "interface edit
  coming along", #56 "commit that", #61 "is the self-edit still running"
  → systems (a NEW miss shape). Better run than run 1, same core pattern.
- **sonnet** (4 misses): #8 passport recall, #22 "commit these changes",
  #55 screen-vision none-case → systems, #56 "commit that". Note #26/#28
  both PASSED this run.
- **gemini-flash** (2 misses): #40 dropped librarian from the Tokyo
  multi-agent case, #55 → systems.

**Gates mathematically decided after 2 runs:**

- **sonnet-4-5: per-case gate FAILED, verdict fixed.** #22 "commit these
  changes" is 0/2 — a maximum of 1/3 cannot reach the required 2/3. No
  third run changes this. Its mean (+7 over Haiku's 2-run mean) clears the
  mean gate easily, so the precise recorded outcome is: *fails ONLY on the
  bare commit imperatives, which V1's cross-family evidence already showed
  is the prompt's clarify instinct rather than model capability.* Sonnet's
  run 3 is therefore OPTIONAL — spend follows information.
- **gemini-3.7-flash: per-case gate PASSED.** All three original known
  misses (#22, #26, #28) are 2/2 — already ≥2 regardless of run 3. Its
  remaining question is the mean gate, which requires Haiku's and its own
  third runs to compute as specified.
- The screen-vision over-delegation (#54/#55 → systems) is NOT a
  Gemini-specific tic: sonnet did it in run 2 and haiku sent #61 to
  systems. It is what a delegation-inclined model does with a screen
  question in a harness that has no view_screen tool.

**Run 3 per-case detail (2026-08-20):** haiku (6 misses: #9, #22, #26,
#28, #40, #56 — run 1's 85% was the outlier; the honest baseline on this
harder corpus is ~88); gemini-flash (1 miss: #55 → systems, its only
persistent miss, carried the harness-artifact caveat all three runs).
Sonnet's run 3 was skipped: its per-case gate was mathematically failed
after run 2, and spend follows information.

### VERDICT — accuracy gates (per §1's pre-registered rule)

- **Mean gate** (≥ Haiku mean + 3 = 91.2%): gemini-flash 97.3% **PASS**
  (+9.0); sonnet 94% pass (+5.7); haiku baseline 88.3%.
- **Per-case gate** (each of #22/#26/#28 ≥ 2/3): gemini-flash 3/3 on all
  three **PASS**; sonnet **FAIL** (0/2 on #22 "commit these changes");
  haiku fail (0/3 on all three).
- **V1 tool fidelity**: gemini-flash was the only 3/3.

**gemini-3.7-flash is the accuracy winner under the rule as written.**
It is NOT yet adopted — two §1/§5 conditions remain, in order:

1. **The venue decision (Larry's call, §2's audition-not-venue rule):**
   the accuracy runs went through OpenRouter. Production voice on the
   proxy means an extra hop, upstream routing variance, and a second
   failure domain on every single turn. The direct alternative is
   Google's OpenAI-compatible endpoint
   (`https://generativelanguage.googleapis.com/v1beta/openai/`), which
   requires a Google AI Studio key Mortimer does not currently hold —
   [likely] the better production route if a key is acceptable. Fallback
   position if neither is: sonnet-4-5 at 94% on already-trusted direct
   infrastructure, failing only the prompt-level commit-imperative cases.
2. **The latency hard gate:** after the `.env` change, a ≥ 15-turn real
   voice session must hold all three `latency_probe.py` targets. V1's
   caution stands: gemini's TTFT was fine (+297 ms) but total generation
   was 6.8 s — watch delegated-turn p50 specifically.

Prompt note for the follow-up change (§5.4, separate from any model
change): the commit-imperative misses (#22/#56) are prompt-level — every
model except gemini reads "these changes" as a missing referent. One
sentence in SUPERVISOR_PROMPT rule 4 ("for git verbs, the repository's
current state is the referent — do not ask which changes") would
plausibly recover them on ANY model, including Haiku if it stays.

### V2 runs: COMPLETE

### V3 — adoption (Larry chose: Gemini via Google DIRECT, 2026-08-20)

**Parity check #1 FAILED — and that is exactly what the gate existed for.**
Every tool-calling case 400'd: *"Function call is missing a
thought_signature in functionCall parts"*. Gemini 3 attaches an encrypted
`thought_signature` to tool calls and REQUIRES it echoed back when
conversation history is replayed; both jarvis history builders
(`Orchestrator._assistant_message`, `SubAgent._loop`'s twin) kept only the
standard OpenAI fields and dropped it. OpenRouter strips/handles the
requirement server-side, which is why V2's 97-98% went through it without
a single protocol error. A secondary signal: one 503 "high demand" from
AI Studio mid-run.

Larry chose **"fix client first, then direct"** over adopting via
OpenRouter. Investigation of all three history-replay surfaces
(2026-08-20):

1. **`Orchestrator` + `SubAgent` (jarvis code — eval, CLI, and every
   sub-agent even inside the bot process): FIXED.** `_assistant_message`
   now merges `model_extra` — the vendor fields the openai SDK already
   captures via extra="allow" — back into the replayed dict, at both
   message and tool-call level. Generic, not Google-specific; a provider
   that sends no extras gets a byte-identical dict to before
   (`tests/unit/test_vendor_extras.py` pins both halves). One
   implementation: supervisor.py delegates to base.py's.
2. **Pipecat OpenAI path (production voice): UNFIXABLE without forking.**
   `base_llm._process_context` coalesces each streamed tool call down to
   id/name/arguments into `FunctionCallFromLLM` — no extras slot; the
   signature is destroyed at the first aggregation step.
3. **Pipecat native `GoogleLLMService`: FULL signature support already.**
   Captures signatures during streaming (with Gemini 2.5-vs-3 placement
   handling), bookmarks them, and `GeminiLLMAdapter` re-applies them on
   context replay. `pipeline.py` therefore now routes a Google base_url to
   `GoogleLLMService` (lazy import — `google-genai` stays optional for
   non-Google deployments); everything else keeps `OpenAILLMService`
   unchanged. `requirements.txt` gained the `google` pipecat extra.

**Honest measurement gap:** the eval exercises the OpenAI-compat endpoint
via the Orchestrator; production voice will use the native API via
`GoogleLLMService`. Same model, different serving interface — the live
session in step 4 is the gate that covers the difference.

Revised sequence (steps 1 is done — key is in the vault):

1. ~~Get key, `python -m jarvis.vault set GEMINI_API_KEY`~~ DONE.
2. Install the native client and refresh the lock:
   `uv pip install google-genai google-api-core && uv pip freeze > requirements-lock.txt`
3. **Parity check #2** (same command as #1; the jarvis fix should clear
   the 400s): `EVAL_MODEL=gemini-3.7-flash
   EVAL_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
   EVAL_KEY_ENV=GEMINI_API_KEY RUN_LIVE=1 python -m tests.evals.routing_eval`
   — expect ≥ 94%.
4. Flip the voice config: `python -m jarvis.vault set OPENAI_API_KEY`
   (paste the SAME Google key — ANTHROPIC_API_KEY still carries the
   council/planner profiles, nothing else moves), then in `.env`:
   `OPENAI_MODEL=gemini-3.7-flash`,
   `OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/`
   (the base_url is what routes pipeline.py to GoogleLLMService; the
   model string drops the `google/` prefix on the direct route).
5. Restart, ≥ 15-turn real voice session, `python scripts/latency_probe.py
   logs/bot.log --budget` — the §1 hard latency gate. A miss means revert
   step 4's three lines and record "Haiku stays on latency."
6. On pass: update CLAUDE.md's pipeline + "Haiku today" language with
   these numbers; `check_env.py`'s (key, endpoint) grouping picks up the
   new pair with no code change.
7. Separate follow-up change (never bundled): the rule-4 prompt fix for
   commit imperatives, then one eval re-run as its own gate.

### Parity check #2 (2026-08-20, after the fix): protocol FIXED, serving NOT

- **Zero 400s** — the thought-signature round-trip works. Of the 42 cases
  Google actually served, 41 routed correctly (~98%), consistent with the
  OpenRouter-measured 97.3%. Protocol parity is proven.
- **23/65 cases (35%) got 503 UNAVAILABLE** ("high demand"), the run took
  46 minutes, and sub-agents hit their 45 s timeouts repeatedly. The
  headline 63% is an artifact of errors scoring as misses; the real
  reading is "correct when served, frequently not served."
- The venue trade now has data on BOTH sides: direct = protocol fixed but
  unreliable serving on this key today; OpenRouter = zero 503s across
  three full runs of the same model ([likely] paid/priority capacity
  pools). One run at one time of day is not a verdict on AI Studio — but
  a voice loop cannot ship on a route showing a 35% turn-failure rate.
- Two cheap diagnostics before choosing: (1) check whether the AI Studio
  key has billing enabled — free-tier traffic is the first shed under
  load; (2) re-run the same command at a different hour. If 503s persist
  on a billed key, OpenRouter becomes the evidence-backed venue — and
  nothing here is wasted: pipeline.py now supports both routes, and the
  signature fix protects any future OpenAI-compat consumer regardless.

### FINAL VERDICT (2026-08-20): latency gate FAILED — Haiku stays

Larry's key IS billed, so the 503s were real capacity shedding, and
OpenRouter became the adoption route. Live session (voice, OpenRouter):
non-delegated p50 **2544 ms** against the 1200 ms target, n=2. A re-bench
on the new key confirmed it structural rather than a bad sample: Gemini
TTFT **2821 ms** (vs 2696 in V1 — stable across hours and key rotation),
3/3 fidelity again. The model does not produce first tokens near 1200 ms
with the full Supervisor prompt on any route; no larger n changes a
1,300 ms gap. Per §1's rule as written: **accuracy gates passed, latency
gate failed, no adoption. Haiku stays**, and the question is closed with
numbers rather than left open.

Reverted: `.env` back to `claude-haiku-4-5` / Anthropic base_url, vault
`OPENAI_API_KEY` restored to the Anthropic credential (the adoption
attempt had repointed it at OpenRouter, which also explains the
haiku-baseline 401s in the final bench run — expected, not a defect).

**Open finding for the follow-up, not this plan:** Haiku's own bench TTFT
was 2399 ms — only ~400 ms ahead of Gemini — so Haiku's CURRENT live p50
against the Phase-7 1200 ms target is unverified and plausibly also a
miss; the Supervisor prompt has grown substantially since the targets
were locked. Measure Haiku live post-revert. If it also misses, the real
unlock is the already-queued prompt-reduction follow-up (§5.4), which
would then reopen sonnet-4-5: TTFT at parity with Haiku, direct trusted
route, +6 accuracy, and its only per-case failures are the prompt-level
commit imperatives the same follow-up fixes.

### Haiku live baseline — the open finding, closed (2026-08-22)

The final verdict's open question ("is Haiku's own live p50 also a miss?")
is answered: **no**. `latency_probe` over the 2026-08-22 live session
(47 turns, all Haiku — the log starts post-revert): non-delegated p50
**1004 ms** (target 1200, PASS), delegated p50 **1550 ms** (target 2500,
PASS), overall p90 **2489 ms** (target 3500, PASS). The gate is
attainable and Haiku attains it with headroom. The live head-to-head is
therefore Haiku 1004 ms vs Gemini-via-OpenRouter 2544 ms non-delegated
p50 — not the ~400 ms bench delta. [guessing] The bench/live divergence
is Anthropic prompt caching on the direct route, which the bench's
cold-ish reps never captured and which OpenRouter-routed Gemini never got.

### Reopened for live trial (Larry, 2026-08-22)

Larry's hypothesis: the 8/20 failures — the direct route's 35% 503 rate
in particular — were early-release congestion, not steady state. The
DIRECT route is the one this theory applies to, and it was never
latency-measured live (serving failed first), so a multi-session direct
trial is genuinely new information, not a re-run of a settled question.
Protocol: flip `.env` to Gemini direct (the V3 step-4 shape; the
signature fix and GoogleLLMService routing are already shipped), several
sessions of ≥15 turns at different hours, `latency_probe --budget` per
session on a clean log slice, plus a count of 503/error turns. Compare
against the Haiku baseline above. Revert is the same three lines as
before.

**What this plan permanently shipped regardless of the verdict:** the
10-case eval-corpus extension; `scripts/voice_model_bench.py`;
`EVAL_MODEL`/`EVAL_BASE_URL`/`EVAL_KEY_ENV` overrides in the routing
eval; the vendor-extras (thought-signature) round-trip in
`_assistant_message` with tests; the provider-aware Supervisor service in
pipeline.py (Google base_url → native `GoogleLLMService`); and the
pipecat `google` extra in requirements.
