# Mortimer — Session Misses (voice transport in the ledger, late-result repeat, TTS markup, speaker gate, attribution)

**Status:** APPROVED 2026-09-03 (Larry: *"let's begin implementation"*). **S1–S5 (Steps 1–4, the ledger) IMPLEMENTED 2026-09-03** — see the commit "Session Misses S1–S5"; one deliberate deviation recorded there: `scripts/cost_report.py` gained a `build_report(conn, month) -> dict` factored out of `main()` so §7's `test_cost_report.py` can assert on the dict rather than on stdout (main() renders exactly that dict; output unchanged apart from the new voice section). **S6–S8 (Step 5, the late-result neutralizer) IMPLEMENTED 2026-09-03** — as specified; one case the plan's §7 list did not name was added as a test after a mutation check exposed it (`test_note_armed_mid_relay_waits_for_its_own_relay`: a second orphaned result landing during the first's relay must not be neutralized by that relay's end — `arm()` re-arms, at the cost of the first note surviving one extra turn). **S9 (Step 6, the markdown filter) IMPLEMENTED 2026-09-03** — as specified, plus one file the plan's §1/§4 missed: `tests/unit/test_speaker_gate.py` has a SECOND TTS fake (`_FakeTTS`, :513) that also had to accept `text_filters`; the full-suite run caught it as 4 new failures. **S10 + S11 (Steps 7–8) IMPLEMENTED 2026-09-03**, completing the plan — with one correction: §5 step 8b said SUPERVISOR_PROMPT's numbered rules are 1–9 and to add rule 10; the list actually runs to 12 (`jarvis/prompts.py:57-69`), so the re-delegation rule is **rule 13**. The Tier-1/2 plan's §6 also gained a second live check in step 3 (another PERSON speaking near the mic — the case that actually occurred on 2026-09-03; the protocol only tested a TV).
**Author / origin:** Claude (Fable 5.1). Larry, after the 13:44–13:47
session review: *"create an implementation plan for the misses from the
recent conversation."* Five misses were found in that session's logs
(`logs/bot.log` lines 388–995, ledger rows 17:44–17:47 UTC); this plan
fixes the four that are code and hands the fifth (the speaker gate) back
as the protocol it has been waiting on since 2026-08-22.
**Optimization-plan constraints this plan is bound by:** the model floor
(only the Supervisor may run Haiku — nothing here changes a model); voice
transport stays on native provider connections for latency (this plan
MEASURES it, changes nothing about how it is transported — see S1's
*why*); Savings Ledger entries are measured, never estimated.
**Contracts this plan INTRODUCES:** `llm_calls.quantity` / `llm_calls.unit`
(S1), the `tts` and `stt` rungs (S1), `costs_api.summary()["voice_usd"]`
and `["llm_usd"]` (S5), `jarvis.bot.late_result.LateResultNeutralizer`
(S6), `python -m jarvis.speaker verify --windowed` (S10).
**Contracts this plan CONSUMES:** `usage_ledger.record_call` /
`compute_cost` / `_conn()`'s in-place ALTER pattern (Phase 3 Rev 3.3);
`UsageMetricsObserver` (Phase 0 step 1); `inject_context` and
`runtime.late_delivery["fn"]` (reliability overhaul 2026-08-21);
`MORTIMER_VOICE_ISOLATION_TIER12_PLAN.md` §6 (the effectiveness protocol).
**Corrections to earlier statements:** in the 2026-09-03 log review I put
the session's TTS cost at $0.19–0.53. The top of that range is the
Multilingual-v2 rate; the pipeline runs `eleven_flash_v2_5`
(`jarvis/bot/pipeline.py:625`), billed at 0.5 credits per character, so
the real range for 2,409 characters is **$0.20–0.27** on Creator/Pro base
rates — still 3–4× the session's $0.069 of LLM spend. The conclusion
stands; the number is corrected here.

---

## §0 Binding constraints for the implementing model

Every decision below is LOCKED. If something is impossible as written,
STOP and report; do not substitute a design. Version-check pipecat
against the deployment venv (`.venv/lib/python3.12/site-packages`,
pipecat **1.4.0**) — every pipecat claim in this plan was read from that
exact version and is cited by `path:line`. The sandbox interpreter is
not the deployment.

Order of implementation is the order of §5. S1–S5 (the ledger) land as
one commit; S6–S8 (late result) as one; S9 (markdown) alone; S10 + S11
(speaker gate helper + prompt rules) together. Each commit's full-suite
run is compared against the standing baseline (real venv: 6 failed /
2105 passed / 3 skipped as of 326a71e), never against "0 failed".

## §1 What exists today (verified, path:line) and the gap

**Ledger.** `jarvis/usage_ledger.py:47-54` `RUNGS` names 15 rungs, all
LLM. `:66-89` `_SCHEMA` has token columns only; `:161-169` `_conn()` adds
`plan_state` in place with one PRAGMA + one ALTER when missing — the
pattern S1 reuses. `:110-143` `compute_cost` prices from
`config/model_prices.yaml` keyed `"{provider}/{model}"`, returning `None`
(never 0) for an unmapped key so the row shows as *unpriced*, not free.
`jarvis/bot/usage_watcher.py:129-130` loops `frame.data` and `continue`s
on anything that is not `LLMUsageMetricsData`; pipecat pushes
`TTSUsageMetricsData(processor, model, value=len(text))` on the SAME
`MetricsFrame` channel from every TTS submission
(`pipecat/processors/metrics/frame_processor_metrics.py:178-190`;
`pipecat/metrics/metrics.py:80-86`, `value: int`). That is the line the
observer already logs as `usage characters: N` — 2,409 of them in the
reviewed session — and drops. Deepgram Flux emits no usage metric
(streaming is billed by audio minute); the STT websocket is open from
`[session] client connected` to `[session] client disconnected`
(`logs/bot.log` 422, 995). **Gap:** the ledger, `cost_report.py`, the
Costs tab and the `cost_summary` voice tool all report LLM-only spend
while the session's TTS alone cost 3–4× its LLM total. The $10/day
(console) vs $0.12/day (ledger) gap noted in the Optimization plan's Rev
3.3 notes is this.

**Late result.** `jarvis/agents/delegate.py:486-505` `_deliver` hands an
orphaned delegation's result to `late_delivery["fn"]` as a USER-role
note: `[system] Background update: the {agent} task … Result: {outcome}
\nRelay this to the user in one or two short sentences.` (`:496-502`).
`fn` is `inject_context` (`jarvis/bot/pipeline.py:1061-1064`, installed at
`:1071`), which appends the dict via `aggregators.user().add_messages`
and pushes a context frame. `pipecat/processors/aggregators/llm_context.py:388-394`
`add_messages` `extend`s `self._messages` with the SAME dict objects; `:240`
`get_messages` reads `self._messages` at request time. So the note stays
in context, verbatim, for the rest of the session. **Observed:** turn 8
(13:46:54) relayed the sperm-history result correctly; turn 9 (13:46:58,
Larry asking about Spartanburg) relayed it AGAIN — 192 output tokens, 244
TTS characters — then delegated; because pipecat holds function-call
results until the bot finishes speaking, the Spartanburg answer waited
behind that repeat: `user_end->llm_done = 23542ms` for a 7.6 s analyst
run. Haiku follows a lingering imperative literally.

**Markup to TTS.** `jarvis/prompts.py:70` `VOICE_ADDENDUM` already says
"no markdown, no bullet points, no numbered lists"; the 13:44:52 turn sent
`**Scheduler**`, `**Librarian**`, … to ElevenLabs anyway. The prompt-only
rule has empirically failed on Haiku. `ElevenLabsTTSService` inherits
`text_filters: Sequence[BaseTextFilter] | None`
(`pipecat/services/tts_service.py:179`, stored `:295`, applied `:916` and
`:1037` before `run_tts`); `pipecat/utils/text/markdown_text_filter.py:23`
`MarkdownTextFilter` (`async def filter(text) -> str`, `:70`). Verified
against 1.4.0 on 2026-09-03: `**Scheduler** handles` → `Scheduler
handles`; em-dashes, apostrophes, digits, quotes untouched; a bare `*` in
`2 * 3` is eaten; `#`, `- `, `1. ` list markers are NOT stripped (the
addendum still covers those). `jarvis/bot/pipeline.py:621-629` constructs
the TTS with no filters. `tests/integration/test_bot_wiring.py:82-89`
`FakeTTS.__init__(self, api_key, settings)` — adding a kwarg to the real
call breaks this fake unless it is widened too (Step 6b does).

**Speaker gate.** `.env:62` `JARVIS_SPEAKER_GATE_ENABLED=false`;
`jarvis/speaker.py:31-36`: the switch "defaults FALSE. The feature is
opt-in until Larry has run the effectiveness protocol (plan §6) and
confirmed it actually helps." `MORTIMER_VOICE_ISOLATION_TIER12_PLAN.md:241`
§6 "Effectiveness protocol (Larry runs; results appended HERE)" — results
section empty; never run. History: on 2026-08-22 the gate was ON and
dropped three of Larry's own 7–12 s TV-mixed turns at 0.29–0.34
(`MORTIMER_GATE_V2_AND_MODEL_REQUEST_PLAN.md` §0); Gate v2 F1/F2 added
windowed max-over-windows scoring (`jarvis/bot/speaker_gate.py:68-105`,
`_window_slices` `:77`) to fix exactly that; the switch has been off since.
`data/speaker_profile.npy` exists; 20 live-mic captures from that Aug-22
session sit in `data/speaker_captures/` (2.8 MB). `python -m jarvis.speaker
verify <wav>` (`jarvis/speaker.py:298-317`) scores the WHOLE file only —
the pre-v2 metric — so nothing offline can show whether v2's windows
would have passed those turns. **Observed this session:** "It's mine." and
"I gotta finish it." (13:46:46, 13:46:48) — side conversation — were
transcribed, answered ("Got it. Yours to keep."), and the first cancelled a
live delegation (barge-in survival recovered it). Exactly the gate's job.

**Attribution / re-delegation.** `jarvis/prompts.py:42` "delegating to a
specialist IS you doing the task"; `:34` rule 1 "If a specialist gave you
no … data … say exactly that." At 13:46:22 ("Kinda humidity do we
have?") Mortimer said *"The analyst's result didn't include it"* — named
the specialist, and followed rule 1 literally instead of delegating again
for the one missing number. Prompt-only, Haiku-fragile; lowest priority.

**New instrumentation, first live reading (for the record):**
`memory_context_rendered chars=9818 approx_tokens=2454 facts=71
dropped_tier_cap=0 dropped_char_budget=0` — Phase 4 Stage A exactly as
the mirror predicted; `memory_recall_events` = 1 after one session.

## §2 Non-goals

- Changing how voice is transported, which TTS/STT vendor or model is
  used, or any latency-affecting setting. This plan meters; it does not
  re-route.
- Pricing the *reported* side (ElevenLabs/Deepgram invoices) — the ledger
  gets `computed_cost` from the price map, same as native Anthropic rows.
  The one-time reconciliation against ElevenLabs' own meter is §8, not a
  puller.
- A multi-turn routing eval. `tests/evals/routing_eval.py` is single-turn
  by design; the attribution and re-delegation rules are verified live
  (§8) and pinned as prompt text only. Building a conversation-level eval
  is its own plan.
- Changing the speaker gate's scoring, threshold, or policy. S10 adds an
  OFFLINE view of the scoring that already ships; the decision to flip
  the switch is Larry's, per the existing protocol.
- The two council defects the roster surfaced (`kimi-k3` empty-error
  abstentions; `claude-opus`/`claude-fable-5` shadow judges failing on a
  deprecated `temperature` parameter), `scripts/mortimer.sh`'s missing
  `restart` verb, and the six baseline test failures. Separate work.

## §3 Decisions (S-prefix), each with a *why*

- **S1 — Voice rows live in `llm_calls`, with `quantity`/`unit` columns,
  not a second table.** *Why:* every consumer (`cost_report.py`,
  `costs_api.summary`, the Costs tab, `summary_text`) already aggregates
  `llm_calls` by `rung`; two new rungs flow through all of them with no
  new joins. Token columns are 0 on voice rows; `quantity` is NULL on
  token rows. A second table would need every consumer taught twice.
- **S2 — TTS rows come from the existing `UsageMetricsObserver`, one row
  per `TTSUsageMetricsData`, `quantity = value` (characters).** *Why:*
  the frame is already observed and deduplicated by id there
  (`usage_watcher.py:122-127`); pipecat measures `len(text)` of exactly
  what is submitted, which is what ElevenLabs bills. Per-chunk rows (not
  per-turn) because that is the granularity the frames arrive at and
  aggregation is the reader's job.
- **S3 — STT is one row per session at teardown, `quantity` = wall-clock
  seconds from `run_session` entry to its `finally`.** *Why:* Flux emits
  no usage metric; it bills audio streamed, and the socket streams for
  the whole connection (Input → VAD → STT; the VAD is a processor in the
  chain, not a gate on the stream — `pipeline.py` linking at
  `logs/bot.log` 13:44:33.111). Wall-clock overstates by connection
  setup (~1 s); stated, accepted.
- **S4 — Prices are per natural unit in the map: `usd_per_1k_chars` for
  `unit: chars`, `usd_per_minute` for `unit: seconds`.** *Why:* the map is
  read by humans against vendor pages that quote exactly those units;
  a synthetic per-unit decimal (`0.000128`) is how a price gets typed
  wrong by a factor of 60. `compute_cost` converts.
- **S5 — The ElevenLabs entry ships at the Pro-tier Flash rate
  ($0.10 / 1K chars) with the tier table in the YAML comment; Larry
  confirms his tier in §8 step 1 and edits one number.** *Why:* the rate
  is plan-dependent and unknowable from the repo; an *unpriced* entry
  would hide the whole point of the change behind "N calls unpriced",
  while a wrong tier is at most ±30% and corrected in one line.
- **S6 — The late-result repeat is fixed in CODE (a context neutralizer),
  with the note text tightened as belt-and-suspenders.** *Why:* two
  prompt-only rules failed in this same session on this same model
  (markdown, attribution). The repo's own lesson (`jarvis_units`, the model
  floor): a rule that must hold is bound in code, not persuaded into a
  model.
- **S7 — Neutralize = rewrite the note's `content` in place to a
  non-imperative record; never delete the message.** *Why:* deleting
  would make "what did you find earlier?" unanswerable and would shift
  message indices under pipecat's aggregator; rewriting the same dict
  object is visible to the next `get_messages()` with no index change
  (`llm_context.py:394`, `:240`).
- **S8 — Neutralize on the FIRST `LLMFullResponseEndFrame` that follows an
  `LLMFullResponseStartFrame` seen AFTER the injection, or on
  `InterruptionFrame` in that same window.** *Why:* the note is injected
  from a background task at an arbitrary moment; a stale end frame from
  the response in flight must not neutralize a note the model has not
  yet seen (that would silently LOSE the result — worse than a repeat).
  Arming on the next start frame excludes the stale case. Interruption
  counts as done: the user chose to move on; the content stays in
  context as a record.
- **S9 — Markdown is stripped by `MarkdownTextFilter` on the TTS service;
  `VOICE_ADDENDUM` stays.** *Why:* binding layer for emphasis/backticks
  (the observed failure), prompt layer for list markers (which the filter
  does not touch — verified). Default `InputParams` (code blocks and
  tables kept).
- **S10 — The speaker gate stays OFF in this plan; it ships an offline
  windowed scorer and the protocol, and Larry flips the switch only on
  passing numbers.** *Why:* the last time it was on it ate his real
  requests; v2's fix has never been measured; the 20 captures from that
  very session are the ideal offline test set and cost nothing to score.
- **S11 — Attribution and re-delegation are one prompt edit each, pinned
  by text tests, verified live.** *Why:* the only binding fix would be a
  post-filter on Mortimer's speech for the word "analyst", which would
  also eat legitimate uses; not worth it for a cosmetic miss.

## §4 Files

Modify:
- `jarvis/usage_ledger.py` — S1/S4: schema, `_conn()` ALTERs, `RUNGS`,
  `compute_cost(quantity=)`, `record_call(quantity=, unit=)`.
- `config/model_prices.yaml` — S5: two voice entries.
- `jarvis/bot/usage_watcher.py` — S2: TTS branch + constructor kwargs.
- `jarvis/bot/pipeline.py` — S3 (STT row at teardown), S6/S8
  (`inject_late_result`, neutralizer observer wired), S9 (TTS filter),
  imports.
- `jarvis/config.py` — S6–S8 kill switch `jarvis_late_result_neutralize_enabled`.
- `jarvis/agents/delegate.py` — S6 note text.
- `jarvis/prompts.py` — S11 two sentences.
- `jarvis/speaker.py` — S10 `verify --windowed`.
- `scripts/cost_report.py` — S1 `voice` bucket + section.
- `jarvis/costs_api.py` — S5 `voice_usd`/`llm_usd` + one `summary_text` sentence.
- `docs/plans/MORTIMER_VOICE_ISOLATION_TIER12_PLAN.md` — §6 gains step 0 (offline windowed scoring).
- `tests/unit/test_usage_ledger.py`, `tests/unit/test_usage_watcher.py`,
  `tests/unit/test_delegate.py`, `tests/unit/test_prompts.py`,
  `tests/unit/test_speaker.py`, `tests/integration/test_bot_wiring.py`
  (incl. `FakeTTS`).

Create:
- `jarvis/bot/late_result.py` — `LateResultNeutralizer`, `LATE_RESULT_RELAYED_NOTE`.
- `tests/unit/test_late_result.py`.
- `tests/unit/test_cost_report.py` and `tests/unit/test_costs_api.py` —
  neither exists today (verified: `ls tests/unit | grep -i cost` is empty).

Delete: nothing.

## §5 Implementation steps

### Step 1 — Ledger schema + pricing (S1, S4, S5) — `jarvis/usage_ledger.py`, `config/model_prices.yaml`

1a. `_SCHEMA` (`:67-85`): after the `plan_state TEXT` column add
```sql
    quantity REAL,                    -- voice rungs only (MORTIMER_SESSION_MISSES_PLAN.md S1):
                                      -- characters (tts) or seconds (stt); NULL on token rows
    unit TEXT                         -- 'chars' | 'seconds'; NULL on token rows
```
1b. `_conn()` (`:161-169`): extend the existing in-place block —
```python
    cols = {row[1] for row in conn.execute("PRAGMA table_info(llm_calls)")}
    if "plan_state" not in cols:
        conn.execute("ALTER TABLE llm_calls ADD COLUMN plan_state TEXT")
    # MORTIMER_SESSION_MISSES_PLAN.md S1 — voice transport rows.
    if "quantity" not in cols:
        conn.execute("ALTER TABLE llm_calls ADD COLUMN quantity REAL")
    if "unit" not in cols:
        conn.execute("ALTER TABLE llm_calls ADD COLUMN unit TEXT")
```
(Keep whatever variable name the existing block uses for the column set;
the shape above is the contract, not the identifier.)
1c. `RUNGS` (`:47-54`): add `"tts", "stt",` on their own line with the
comment `# MORTIMER_SESSION_MISSES_PLAN.md S1 — voice transport`.
1d. `compute_cost` (`:110`): new signature and body —
```python
def compute_cost(provider: str,
                 model: str,
                 input_tokens: int,
                 output_tokens: int,
                 cache_write_tokens: int = 0,
                 cache_read_tokens: int = 0,
                 quantity: Optional[float] = None,
                 unit: Optional[str] = None) -> Optional[float]:
    key = f"{provider}/{model}"
    entry = load_price_map().get("models", {}).get(key)
    if not entry:
        return None
    if quantity is not None:
        # Voice transport (S4): priced per natural unit, never per token.
        if unit == "chars" and "usd_per_1k_chars" in entry:
            return quantity / 1000.0 * float(entry["usd_per_1k_chars"])
        if unit == "seconds" and "usd_per_minute" in entry:
            return quantity / 60.0 * float(entry["usd_per_minute"])
        return None  # mapped model, wrong/missing unit price -> unpriced, never free
    ... (existing token arithmetic unchanged)
```
The existing docstring gains one paragraph naming S4.
1e. `record_call` (`:173-184`): add `quantity: Optional[float] = None,
unit: Optional[str] = None` after `plan_state`; pass both to
`compute_cost`; extend the INSERT column list and VALUES with `quantity,
unit` (16 placeholders). `record_completion` (`:301`) is unchanged — it is
the LLM adapter and never carries a quantity.
1f. `config/model_prices.yaml`: append under `models:` —
```yaml
  # ---- voice transport (MORTIMER_SESSION_MISSES_PLAN.md S4/S5) ----
  # Priced per natural unit; usage_ledger.compute_cost converts. These rows
  # carry quantity/unit, zero tokens.
  #
  # ElevenLabs bills CREDITS; eleven_flash_v2_5 costs 0.5 credit per
  # character (elevenlabs.io/pricing, texttolab.com/blog/elevenlabs-pricing,
  # 2026-09-03), so USD per 1K CHARACTERS is half the plan's USD per 1K
  # credits. Base rates by tier, per 1K chars: Starter 0.085, Creator 0.11,
  # Pro 0.10, Scale/Business 0.085. Overage per 1K chars: Creator 0.15,
  # Pro 0.12, Scale 0.09, Business 0.06. SET FROM YOUR TIER (plan §8 step
  # 1); shipped at Pro base.
  elevenlabs/eleven_flash_v2_5:
    unit: chars
    usd_per_1k_chars: 0.10
    history: []

  # Deepgram Flux streaming, pay-as-you-go list (deepgram.com/pricing,
  # 2026-09-03): $0.0077/min regular; a $0.0065/min promotion was showing
  # that day. Growth tier $0.0065 regular. Shipped at the regular PAYG rate.
  deepgram/flux-general-en:
    unit: seconds
    usd_per_minute: 0.0077
    history: []
```
The `model` strings are the literals in `pipeline.py:625` and `:525`.

### Step 2 — TTS rows from the observer (S2) — `jarvis/bot/usage_watcher.py`

2a. Import: `from pipecat.metrics.metrics import LLMUsageMetricsData,
TTSUsageMetricsData` (`:67`).
2b. Constructor: add kwargs `tts_provider: str = "elevenlabs"`,
`tts_default_model: str = "eleven_flash_v2_5"`; store as `self._tts_provider`,
`self._tts_default_model`.
2c. In `on_push_frame`'s loop (`:129-130`), replace
```python
            if not isinstance(item, LLMUsageMetricsData):
                continue
```
with
```python
            if isinstance(item, TTSUsageMetricsData):
                # MORTIMER_SESSION_MISSES_PLAN.md S2 — one ledger row per TTS
                # submission; value is len(text) of exactly what was sent
                # (pipecat frame_processor_metrics.py:187-188), which is
                # what ElevenLabs bills. Dedup by frame id above applies.
                try:
                    record_call(
                        rung="tts",
                        provider=self._tts_provider,
                        model=item.model or self._tts_default_model,
                        session_id=self._session_id,
                        quantity=float(item.value or 0),
                        unit="chars",
                    )
                except Exception:  # noqa: BLE001 — same discipline as below
                    logger.warning("usage_watcher tts record_call failed", exc_info=True)
                continue
            if not isinstance(item, LLMUsageMetricsData):
                continue
```
2d. `pipeline.py:947-952`: pass `tts_provider="elevenlabs",
tts_default_model="eleven_flash_v2_5"` explicitly (the same literals as
`:625` — one place would be better, but the TTS model string is inline
there today; do NOT refactor it in this plan).

### Step 3 — STT row at teardown (S3) — `jarvis/bot/pipeline.py`

3a. `run_session` is `pipeline.py:816`. Its first statement after the
docstring becomes `session_started = time.monotonic()`. `pipeline.py` does
NOT import `time` today (verified) — add `import time` to the stdlib
import block (`:27` area), and extend `:107` to
`from jarvis.usage_ledger import provider_from_base_url, record_call`.
3b. In the `finally:` at `:1222`, immediately AFTER the existing
`write_session_digest` block (`:1269-1279`) and BEFORE the outer
`finally:` at `:1280`, add
```python
            # MORTIMER_SESSION_MISSES_PLAN.md S3 — Deepgram Flux streams for
            # the whole connection and emits no usage metric; bill the
            # session's wall-clock as streamed audio. Never raises
            # (record_call catches internally); never delays shutdown.
            try:
                record_call(
                    rung="stt",
                    provider="deepgram",
                    model="flux-general-en",
                    session_id=runtime.session_id,
                    quantity=max(0.0, time.monotonic() - session_started),
                    unit="seconds",
                )
            except Exception:  # noqa: BLE001
                _logger.warning("stt_ledger_row_failed session=%s", runtime.session_id, exc_info=True)
```
(`record_call` import added in 3a.)

### Step 4 — Report and API (S1, S5) — `scripts/cost_report.py`, `jarvis/costs_api.py`

4a. `cost_report.py:48-55` `BUCKETS`: add `"voice": {"tts", "stt"},`.
4b. After the "by bucket" section (`:192`) add a section that prints
exactly:
```
voice transport (MORTIMER_SESSION_MISSES_PLAN.md):
  tts: {rows} rows, {chars:,} chars, ${usd:.4f}
  stt: {rows} rows, {minutes:.1f} min, ${usd:.4f}
  llm ${llm_usd:.4f} vs voice ${voice_usd:.4f}  (voice share {pct:.0f}%)
```
where `chars = SUM(quantity) WHERE rung='tts'`, `minutes =
SUM(quantity)/60 WHERE rung='stt'`, `voice_usd = SUM(computed_cost) WHERE
rung IN ('tts','stt')`, `llm_usd = total - voice_usd`, `pct = voice_usd /
total * 100` (0 when total is 0). Add `voice_usd`, `llm_usd`, `tts_chars`,
`stt_seconds` to the `report` dict the script already builds.
4c. `costs_api.py` — the function that builds the dict served by
`@router.get("/summary")` (`:117`; the dict is assembled at `:59-93`):
compute the same `voice_usd`/`llm_usd` from the per-rung totals and add
both keys to the returned dict (and `0.0` for each in the empty-month
dict at `:59-62`). `by_rung` already includes `tts`/`stt` rows by
construction — the Costs tab's `rungBreakdown` needs NO change;
`CostSummary` (`macos/JarvisKit/Sources/JarvisKit/CostsAPI.swift:14-26`)
has explicit `CodingKeys`, so the two new keys are ignored by the app
until a later change chooses to show them.
4d. `summary_text()` (`:97`): after the sentence built at `:102`, append
exactly: `" About {voice_usd:.2f} dollars of that was voice — text to
speech and transcription."` only when `voice_usd > 0`.

### Step 5 — Late-result neutralizer (S6, S7, S8) — `jarvis/bot/late_result.py` (new), `pipeline.py`, `config.py`, `delegate.py`

5a. `jarvis/config.py:98` area: add `jarvis_late_result_neutralize_enabled:
bool = True` next to `jarvis_interruption_notice_enabled`.
5b. New file `jarvis/bot/late_result.py`:
```python
"""LateResultNeutralizer — MORTIMER_SESSION_MISSES_PLAN.md S6-S8.

A delegation orphaned by barge-in delivers its result as a user-role
context note that ends "Relay this to the user …" (jarvis/agents/
delegate.py). Delivered once, that imperative then sits in context for
the rest of the session, and on 2026-09-03 Haiku obeyed it a second time
on the very next user turn — repeating a result the user had just heard
and holding the new answer behind 17 s of redundant speech.

This observer rewrites the note IN PLACE (same dict object the aggregator
holds — llm_context.py add_messages extends with the caller's objects)
to a non-imperative record once the relay turn has ended. State machine:

  IDLE --arm(note)--> ARMED --LLMFullResponseStartFrame--> RELAYING
  RELAYING --LLMFullResponseEndFrame | InterruptionFrame--> neutralize, IDLE

A stale LLMFullResponseEndFrame seen while ARMED (the response that was
already in flight when the note landed) is ignored: neutralizing then
would hide a result the model has not relayed yet — a silent loss,
which is worse than the repeat this fixes.
"""
from __future__ import annotations

import logging

from pipecat.frames.frames import (
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.frame_processor import FrameDirection

logger = logging.getLogger(__name__)

LATE_RESULT_RELAYED_NOTE = (
    "[system] (A background result was delivered here and has already been "
    "relayed, or the user moved on. Do not repeat it unless asked.)"
)


class LateResultNeutralizer(BaseObserver):
    def __init__(self, *, enabled: bool = True) -> None:
        super().__init__()
        self._enabled = enabled
        self._pending: list[dict] = []
        self._relaying = False

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def arm(self, message: dict) -> None:
        """Register a just-injected late-result note (the SAME dict object
        that was handed to add_messages)."""
        if not self._enabled:
            return
        self._pending.append(message)
        self._relaying = False

    async def on_push_frame(self, data: FramePushed) -> None:
        if not self._enabled or not self._pending:
            return
        if data.direction != FrameDirection.DOWNSTREAM:
            return
        frame = data.frame
        if isinstance(frame, LLMFullResponseStartFrame):
            self._relaying = True
            return
        if isinstance(frame, (LLMFullResponseEndFrame, InterruptionFrame)) and self._relaying:
            for message in self._pending:
                message["content"] = LATE_RESULT_RELAYED_NOTE
            logger.info("late_result_neutralized count=%d via=%s",
                        len(self._pending), type(frame).__name__)
            self._pending.clear()
            self._relaying = False
```
Frame classes verified in the venv: `pipecat/frames/frames.py:1018`
`InterruptionFrame`, `:1903` `LLMFullResponseStartFrame`, `:1918`
`LLMFullResponseEndFrame` — the same three `jarvis/bot/interruption.py:31-37`
already imports.
5c. `pipeline.py`: construct `late_neutralizer =
LateResultNeutralizer(enabled=settings.jarvis_late_result_neutralize_enabled)`
before the observers list and append it to `observers=[...]` (`:947`
block). Then, next to `inject_context` (`:1061`), add
```python
        async def inject_late_result(text: str) -> None:
            # S6: same channel as inject_context, but the note is
            # registered with the neutralizer so its imperative dies with
            # the relay turn (see jarvis/bot/late_result.py).
            message = {"role": "user", "content": text}
            late_neutralizer.arm(message)
            aggregators.user().add_messages([message])
            await aggregators.user().push_context_frame()
```
and change `:1071` to `runtime.late_delivery["fn"] = inject_late_result`.
`inject_context` itself is unchanged (reminders and the greeting keep it).
5d. `delegate.py:500`: change `"Relay this to the user in "` … to end
`"Relay this to the user once, in one or two short sentences, and do not
repeat it in later turns. If it prepared an action that needs their
confirmation, say so."` (belt-and-suspenders; the neutralizer is the
binding fix).

### Step 6 — Markdown filter (S9) — `pipeline.py:621`, `test_bot_wiring.py:82-89`

6a. `from pipecat.utils.text.markdown_text_filter import MarkdownTextFilter`
at module top; `ElevenLabsTTSService(api_key=…, settings=…,
text_filters=[MarkdownTextFilter()])`. Comment: `# S9: emphasis/backticks
are stripped here in code; VOICE_ADDENDUM still owns list markers, which
this filter does not touch (verified 1.4.0).`
6b. `FakeTTS.__init__(self, api_key, settings, text_filters=None)` and
`self.text_filters = text_filters or []`.

### Step 7 — Offline windowed verify (S10) — `jarvis/speaker.py`, Tier-1/2 plan §6

7a. `jarvis/speaker.py`: new module-level function
```python
def windowed_score(pcm16: bytes, sample_rate: int, encoder: "Encoder",
                   profile: np.ndarray) -> tuple[float | None, float | None]:
    """(whole_buffer_score, best_window_score) using the SAME slicing the
    live gate uses (jarvis.bot.speaker_gate._window_slices, Gate v2 F1).
    Lazy import: speaker_gate imports this module at load, so the import
    must live here, not at module top."""
    from jarvis.bot.speaker_gate import _window_slices
    slices = _window_slices(len(pcm16), sample_rate)
    scores: list[float] = []
    for s in slices:
        emb = encoder.embed(pcm16[s], sample_rate)
        if emb is not None:
            scores.append(cosine(emb, profile))
    if not scores:
        return None, None
    return scores[-1], max(scores)   # _window_slices puts the whole buffer LAST
```
7b. `_cmd_verify` (`:298`) becomes `_cmd_verify(wav_paths: list[str],
windowed: bool)`; `main` (`:333`) parses `verify [--windowed] <wav...>`.
For each file: read with stdlib `wave` (assert `getsampwidth() == 2` and
`getnchannels() == 1`, else print `skipped: need 16-bit mono` and
continue); `pcm = wf.readframes(wf.getnframes())`; `rate =
wf.getframerate()`. Without `--windowed`: existing behaviour via
`encoder.embed_file`. With `--windowed`: `whole, best =
windowed_score(...)`; print one line per file:
`{name}  whole={whole:.3f}  best_window={best:.3f}  verdict={verdict(best, secs, True)}`
where `secs = len(pcm) / (2 * rate)`; after all files print
`min best_window={…:.3f}  max best_window={…:.3f}  threshold={threshold():.2f}`.
7c. `MORTIMER_VOICE_ISOLATION_TIER12_PLAN.md` §6: insert **step 0** before
step 1:
> 0. Offline, on the captures you already have: `python -m jarvis.speaker
> verify --windowed data/speaker_captures/*.wav`. Listen to any file whose
> whole-buffer and best-window verdicts disagree and label it (you / TV /
> other person). Acceptance to proceed to step 3: every file that is you
> has `best_window ≥ 0.40`; every TV/other file has `best_window < 0.40`.
> Anything else → append the numbers here and STOP (threshold tuning is
> a decision, not an improvisation — same rule as the Acceptance line).
And add to step 3's live checks: *"Have someone else speak normally 2 m
from the mic for one minute → expect `speaker_gate_dropped` lines and no
Mortimer responses."*

### Step 8 — Prompt rules (S11) — `jarvis/prompts.py`

8a. After rule 3 of `GOLDEN_RULES` (`:36`) add rule 4, verbatim:
> 4. Never name a specialist to the user — never "the analyst", "the
> specialist", "the result I pulled". You did the work: say "the weather
> data" or "what I found".
8b. In `SUPERVISOR_PROMPT`'s numbered rules (1–9 at `:57-65`), add rule
10 after rule 9, verbatim:
> When the user asks for a detail the last result did not contain — the
> humidity after a weather answer, a date after a summary — delegate
> again for that detail before saying it was missing. Rule 1's "say
> exactly that" applies only after a fresh delegation also came back
> without it.
(Changing the prompt rewrites the cached prefix once: ≈ $0.011 at Haiku's
cache-write rate, the same one-off every prompt edit costs.)

## §6 Tuning knobs (one place each)

| Knob | Where | Default | Override |
|---|---|---|---|
| ElevenLabs $/1K chars | `config/model_prices.yaml` `elevenlabs/eleven_flash_v2_5.usd_per_1k_chars` | 0.10 | edit file (`JARVIS_PRICE_MAP` path override already exists) |
| Deepgram $/min | `config/model_prices.yaml` `deepgram/flux-general-en.usd_per_minute` | 0.0077 | edit file |
| Late-result neutralizer | `Settings.jarvis_late_result_neutralize_enabled` | `True` | `JARVIS_LATE_RESULT_NEUTRALIZE_ENABLED=false` |
| Neutralized note copy | `jarvis/bot/late_result.py` `LATE_RESULT_RELAYED_NOTE` | (text in 5b) | edit constant |
| Markdown filter params | `pipeline.py` `MarkdownTextFilter()` | pipecat defaults (code/tables kept) | edit constructor |
| Speaker gate | `.env` `JARVIS_SPEAKER_GATE_ENABLED` / `JARVIS_SPEAKER_THRESHOLD` | `false` / 0.40 | unchanged by this plan |

## §7 Tests

`tests/unit/test_usage_ledger.py`
- `test_voice_row_prices_chars_per_1k` — price map fixture with
  `elevenlabs/eleven_flash_v2_5: {unit: chars, usd_per_1k_chars: 0.10}`;
  `record_call(rung="tts", provider="elevenlabs", model="eleven_flash_v2_5",
  quantity=2409, unit="chars")` → row has `quantity=2409.0`, `unit='chars'`,
  all token columns 0, `computed_cost == pytest.approx(0.2409)`.
- `test_voice_row_prices_seconds_per_minute` — `deepgram/flux-general-en`
  `usd_per_minute: 0.0077`, `quantity=165, unit="seconds"` → `computed_cost
  == pytest.approx(165/60*0.0077)`.
- `test_voice_row_with_token_only_entry_is_unpriced` — an entry with only
  `input_per_m` and a call carrying `quantity` → `computed_cost is None`
  (never 0). *Mutation target:* return the token arithmetic instead of
  None → fails.
- `test_token_rows_have_null_quantity_and_unit` — existing `record_call`
  path → `quantity IS NULL`, `unit IS NULL`.
- `test_conn_adds_quantity_and_unit_columns_in_place` — create a DB from
  the PRE-plan schema (the test writes the old CREATE TABLE literally),
  open via `_conn()`, assert both columns exist. Mirrors the existing
  `plan_state` test.
- `test_tts_and_stt_are_known_rungs` — `"tts" in RUNGS and "stt" in RUNGS`.

`tests/unit/test_usage_watcher.py`
- `test_tts_usage_frame_writes_a_chars_row` — `MetricsFrame(data=[
  TTSUsageMetricsData(processor="tts", model="eleven_flash_v2_5",
  value=125)])` (same construction style as `:38`) → one row: rung `tts`,
  provider `elevenlabs`, model `eleven_flash_v2_5`, quantity 125.0, unit
  `chars`, tokens 0.
- `test_tts_frame_is_deduplicated_across_hops` — push the SAME frame
  object twice → one row.
- `test_tts_row_uses_default_model_when_frame_has_none` — `model=None` →
  `tts_default_model`.
- `test_llm_frames_still_recorded_alongside_tts` — one frame with both an
  LLM item and a TTS item → two rows, correct rungs. *Mutation target:*
  drop the `continue` after the TTS branch → the TTS item would fall into
  the LLM branch and fail on `.value.prompt_tokens`.

`tests/unit/test_late_result.py` (new; fake `FramePushed` with
`direction=DOWNSTREAM` and real frame classes)
- `test_relay_turn_neutralizes_the_note` — arm(note); Start; End → note
  content == `LATE_RESULT_RELAYED_NOTE`; pending_count 0.
- `test_stale_end_frame_while_armed_is_ignored` — arm(note); End (no
  Start) → content unchanged; pending_count 1. *Mutation target:* drop the
  `self._relaying` guard → fails.
- `test_interruption_during_relay_neutralizes` — arm; Start;
  InterruptionFrame → neutralized.
- `test_two_pending_notes_both_neutralized` — arm(a); arm(b); Start; End →
  both rewritten.
- `test_nothing_pending_is_a_no_op` — Start; End with no arm → no error,
  no state.
- `test_disabled_never_rewrites` — `enabled=False`; arm; Start; End →
  content unchanged (the kill switch).
- `test_upstream_frames_ignored` — same frames with `direction=UPSTREAM`
  → no change.
- `test_same_dict_object_is_mutated` — the dict passed to `arm` is the one
  rewritten (identity check) — this is what makes the aggregator see it.

`tests/unit/test_delegate.py`
- Extend the existing late-delivery test (`:715-735`) to assert the note
  contains `"once"` and `"do not repeat it in later turns"`.

`tests/integration/test_bot_wiring.py`
- `test_tts_has_markdown_filter` — build pipeline; `FakeTTS` instance's
  `text_filters` contains an instance of `MarkdownTextFilter`.
- `test_late_result_hook_arms_the_neutralizer` — build pipeline; call
  `runtime.late_delivery["fn"]("[system] Background update: … Relay this
  …")` → the neutralizer in the task's observers has `pending_count ==
  1` and the user aggregator's last message is that dict.
- `test_stt_row_written_at_teardown` — run `run_session` with the fakes
  through disconnect → ledger (pointed at a tmp DB via `JARVIS_COSTS_DB`,
  which `tests/conftest.py` already sets) has exactly one `stt` row with
  `unit='seconds'` and `quantity >= 0`.
- Existing tests at `:349-352` keep passing with the widened `FakeTTS`.

`tests/unit/test_prompts.py`
- `test_golden_rule_4_forbids_naming_specialists` — `"Never name a
  specialist to the user" in GOLDEN_RULES`.
- `test_supervisor_prompt_re_delegates_for_missing_detail` — `"delegate
  again for that detail before saying it was missing" in SUPERVISOR_PROMPT`.

`tests/unit/test_speaker.py`
- `test_windowed_score_returns_whole_then_best` — fake `Encoder.embed`
  returning vectors whose cosine to a fixed profile is known per slice;
  a 9 s buffer at 16 kHz → `best == max`, `whole == score of the last
  slice`.
- `test_windowed_score_short_buffer_single_window` — 1 s buffer → whole
  == best.
- `test_verify_cli_parses_windowed_flag` — `main(["verify", "--windowed",
  path])` on a generated 16-bit mono WAV with a fake encoder → exit 0 and
  the printed line contains `best_window=`.
- `test_verify_cli_skips_non_mono` — stereo WAV → `skipped: need 16-bit
  mono`, exit 0.

`tests/unit/test_cost_report.py` (create if absent)
- `test_voice_bucket_and_split` — tmp ledger with one supervisor row
  ($0.05), one tts row ($0.20), one stt row ($0.02) → report dict has
  `voice_usd == 0.22`, `llm_usd == 0.05`, `bucket_of("tts") == "voice"`.

`tests/unit/test_costs_api.py` (exists? if not, create)
- `test_summary_exposes_voice_and_llm_split` — same fixture → `voice_usd
  == 0.22`, `llm_usd == 0.05`, `total_usd == 0.27`;
  `summary_text()` contains `"About 0.22 dollars of that was voice"`.

Mutation discipline (every commit): for each new constant or branch, flip
it and confirm the named test fails — as done for Rev 3.3–3.5.

## §8 Verification Larry runs

1. **Confirm the ElevenLabs tier** (one command, from the repo root with
   the vault running so the key resolves — or paste the key from the
   dashboard):
   `curl -s -H "xi-api-key: $ELEVENLABS_API_KEY" https://api.elevenlabs.io/v1/user/subscription | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["tier"], d["character_count"], "/", d["character_limit"])'`
   Set `usd_per_1k_chars` from the tier table in the YAML comment (base
   column unless `character_count` is over `character_limit`, then the
   overage column). Note `character_count` (A).
2. `./scripts/mortimer.sh stop && ./scripts/mortimer.sh start`.
3. One normal 3–5 minute session with at least one delegation. Then:
   `uv run python scripts/cost_report.py` → the new `voice transport`
   section shows tts rows and one stt row for the session;
   `curl -s localhost:8487/costs/summary` (the route at
   `jarvis/costs_api.py:117`, prefix `/costs` at `:43`) shows
   `"voice_usd"` > 0.
4. Re-run the curl from step 1; `character_count` (B). Compare `B − A`
   with `SUM(quantity) WHERE rung='tts'` for that session (sqlite):
   - equal (±1%) → the meter counts characters; done.
   - ≈ half → the meter counts credits (Flash = 0.5/char); the ledger is
     still right in CHARACTERS and the price is already per character;
     note the finding in the YAML comment and done.
   - anything else → report both numbers and stop; do not adjust the
     price to make them match.
5. Say a weather request, then "what's the humidity" → the ledger shows
   TWO analyst delegations for the session and the spoken answer does not
   contain the word "analyst".
6. Ask for a capabilities rundown → `logs/bot.log` TTS lines contain no
   `**`.
7. Trigger a barge-in during a delegation (start a research question, cut
   it off with an unrelated sentence, let it land), then ask an unrelated
   question → the earlier result is spoken ONCE; `late_result_neutralized
   count=1` appears in the log; the next answer's `user_end->llm_done` is
   not inflated by a repeat.
8. Speaker gate: §6 step 0 (offline windowed scoring on the 20 captures),
   then §6 steps 1–3 and the acceptance line. Only on acceptance: `.env`
   `JARVIS_SPEAKER_GATE_ENABLED=true`, stop/start. Append the numbers to
   §6 either way.

## §9 Rollback

- Ledger (S1–S5): additive columns and rows; no switch. To stop
  recording voice rows, revert Step 2c/3b. Existing rows are harmless
  (`quantity`/`unit` NULL on every pre-plan row). Prices: edit the YAML.
- Late result (S6–S8): `JARVIS_LATE_RESULT_NEUTRALIZE_ENABLED=false`
  restores the exact pre-plan behaviour (note stays imperative). The
  delegate note text is one string.
- Markdown (S9): remove `text_filters=[...]`; one line.
- Speaker gate (S10): the CLI flag is additive; the switch is Larry's and
  stays false unless §8 step 8 passes.
- Prompts (S11): revert two sentences; costs one cache re-write.

## §10 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| ElevenLabs tier guessed wrong (S5) | medium | cost off by ≤ 30% | §8 step 1 sets it in one line; the reconciliation in step 4 catches a unit mistake outright |
| `TTSUsageMetricsData` also emitted by a non-ElevenLabs TTS later | low | mis-attributed provider | `tts_provider` is a constructor kwarg; wire it where the TTS is chosen |
| Wall-clock overstates Deepgram minutes | certain, small | ≈ +1 s/session | stated in S3; Deepgram's own dashboard is the check |
| Neutralizer arms, relay never starts (LLM error) | low | note stays imperative until the next response cycle, then neutralized | acceptable; the next turn's start/end resolves it |
| Neutralizer fires on an interruption that landed before any relay audio | low | result content stays in context but is not spoken; user can ask | S8's *why*; copy of `LATE_RESULT_RELAYED_NOTE` covers "or the user moved on" |
| `MarkdownTextFilter` eats a lone `*` in spoken arithmetic | low | "2 3 = 6" | observed in verification; Mortimer speaks numbers, not operators; accepted |
| `FakeTTS` signature drift breaks 3 wiring tests | certain if 6b skipped | test failures | 6b is in the same commit as 6a |
| Windowed scoring shows Larry's own captures < 0.40 | possible | gate stays off | that is the correct outcome; §6 says stop and record, not tune |

## §11 Self-audit (PLAN_AUTHOR_BRIEF taxonomy)

1. Multi-consumer contracts typed — `quantity REAL`/`unit TEXT` named
   member-by-member; `compute_cost` and `record_call` signatures given in
   full; `summary()` gains two named float keys; `windowed_score` returns
   `(whole, best)` in that order with the reason.
2. Lifecycle — the neutralizer's state machine is explicit, including
   the stale-frame and interruption paths; the STT row's timing (finally,
   after digest, before the outer finally) is stated.
3. How values are applied — the note is rewritten via the same dict
   object; where that object comes from (`inject_late_result`) and why it
   is visible (`llm_context.py:394`, `:240`) are cited.
4. Same behaviour described twice — the TTS model literal appears in
   `pipeline.py:625` and now in the observer kwarg and the YAML key; all
   three are the string `eleven_flash_v2_5`; Step 2d says not to refactor.
   The Deepgram literal likewise (`:525`, YAML, Step 3b).
5. Copy specified — `LATE_RESULT_RELAYED_NOTE`, both prompt rules, the
   `summary_text` sentence, the report section, the CLI line formats.
6. Initialization timing — `session_started` is the first statement of
   `run_session`; the neutralizer is constructed before the observers
   list; `late_delivery["fn"]` is installed at the same line it is today.
7. Signatures agree across sections — `record_call(quantity, unit)` in 1e,
   2c, 3b, §7; `compute_cost(quantity, unit)` in 1d and §7. Every new
   column is populated by a step (2c, 3b).
8. Judgment — none left; the one open number (tier) has a table and a
   one-line edit.
9. Manifest — every file in §5 appears in §4; `test_cost_report.py` /
   `test_costs_api.py` are marked "create if absent" in both.

## §12 Approval checklist

- [ ] S5 default tier (Pro base) acceptable as the shipped placeholder,
      to be set in §8 step 1.
- [ ] S8 interruption-counts-as-relayed accepted.
- [ ] S10: the gate stays off until §6 step 0–3 pass — confirmed.
- [ ] Commit grouping in §0 accepted.
