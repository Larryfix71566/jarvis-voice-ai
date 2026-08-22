# Mortimer — Weather in Fahrenheit + Radar as Standard

**Author:** Claude Opus 5 (Cowork session), 2026-08-22
**Status:** awaiting implementation
**Origin:** Larry, 2026-08-22 — *"we currently have a weather display that is
incomplete … 1) it displays weather temps in C instead of F which is the
standard for where I am. 2) it lacks a current weather radar display for the
area I am in. I want both of these things to be the standard for this
display/workflow."*

Larry chose all four recommended options when asked for scope (§1's W-series
decisions record what he chose, not what was merely offered).

---

## 0. Diagnosis

Four separate causes, only two of which are the ones Larry named. Each was
verified against the working tree and the live database, not inferred.

**D0 — the Fahrenheit preference had been aged out of memory entirely
(regression introduced earlier the same day, already fixed).** During the
`MORTIMER_GATE_V2_AND_MODEL_REQUEST_PLAN.md` F10 cleanup at 18:05 UTC,
`python -m jarvis.memory_sweep --enforce` archived
`user.preference.temperature_units` with `became="aged-out"`. That was the
single surviving Fahrenheit fact — six duplicates
(`user.preference.units`, `user.preference.temperature_unit`,
`user.temperature_unit`, `user.unit_preference`,
`user.style.accuracy_enforcement`, `user.style.precision_output`) had been
consolidated into it on 2026-08-20. After that run, **zero** live facts in the
store mentioned Fahrenheit, so the Supervisor prompt carried no unit
preference at all.

Root cause of the regression: `run_capacity_enforcement`'s rung (b)
(LLM-assisted merge) requires an API key. The sandbox had none, so the ladder
fell through to rung (c) — mechanical age-out, which orders by age and is
blind to importance. A stated user preference and a stale scratch note are
indistinguishable to it. This is exactly the outcome rung (b) exists to
prevent, and the fallback silently produced it. **Already remediated in the
session that caused it** (fact un-archived; one exact-duplicate preference,
`user.style.tool_specification`, archived as
`merged:user.preference.tool_specification` to make room under the 15-fact
cap, since restoring the fact pushed the tier to 16 and
`render_memory_context` then dropped the newly-restored fact as the oldest).
W7 below hardens the mechanism so it cannot recur.

Larry's response to this diagnosis reframed it usefully: *"to me that is a
system type preference and not necessarily a memory of user preference … if
it doesn't [affect the output] then it is useless to store it."* He is right,
and the sharper finding is that the fact was **already** useless — it was live
and correct on 2026-08-20 while the display still rendered °C, because nothing
in the code path ever read it. D0 is therefore not only "the fact got evicted"
but "the fact never mattered." W3 moves the rule to configuration, where it is
read by code rather than honored by a model.

**D1 — there are TWO weather implementations, and only one was ever fixed.**
`jarvis/ambient_weather.py` was moved to Weather.gov observations with native
Fahrenheit on 2026-08-18 and verified live against Larry's machine. The
*display* does not use it. The display is fed by
`mcp_servers/mcp_web/logic.py`'s `get_weather`, a completely separate
Open-Meteo implementation that returns `temperature_c` / `max_c` / `min_c` and
builds a `human` string with `°C` hard-coded. `jarvis/bot/display.py`'s
`_fmt_get_weather` then renders a `°C` table because Celsius is all it is
given. The archived fact `mortimer.weather.integration` shows Larry had
already decided to unify these ("Weather display will use Weather.gov API for
forecast text and RainViewer for radar tiles"); it was carried out for the
ambient chip only.

**D2 — radar is fully built and never called.** `get_weather_radar` exists in
`logic.py`, is registered in `server.py`, is listed in `skill.yaml`, is in
`DISPLAY_TOOLS` with `DISPLAY_SURFACE = "window"`, has a formatter
(`_fmt_get_weather_radar`), and the frontend has dedicated seamless 3×3 CSS
(`.display-tiles`) plus a `seamless = images.length === 9` branch in
`DisplayContent.tsx`. The gap is one sentence in the analyst's prompt
(`jarvis/prompts.py`): *"Use web_search for anything about current events …
and get_weather for all weather questions."* Radar is never mentioned, and
"all weather questions" actively steers away from it. This matches Larry's
live memory fact `project.weather_radar`: *"RainViewer tiles already wired."*

**D3 — the radar tiles have no basemap, so radar would read as broken even
once it fires.** RainViewer serves *transparent precipitation overlays*
intended to composite onto a map. `DisplayContent.tsx` renders the nine tiles
directly with nothing underneath, so the result is coloured precipitation
blobs on the panel background — no coastline, no state border, no town — and
on a clear day, nine fully transparent images, i.e. an empty box. Radar
without geography cannot answer "is it raining near *me*", which is the
question being asked.

---

## 1. Locked decisions

**W1 — `mcp_web.get_weather` moves to Weather.gov as PRIMARY, Open-Meteo as
fallback, and the two weather paths share ONE implementation.** The shared
Weather.gov code moves into a new module `jarvis/weathergov.py`; both
`jarvis/ambient_weather.py` and `mcp_servers/mcp_web/logic.py` import from it.
Neither keeps a private copy. *Why:* this is the "one implementation, not two"
rule the codebase applies to `classify_tool_result`, `model_key_probe`,
`_overlap_score`, and `load_model_registry`; D1 is precisely the failure that
rule prevents. It also completes a decision Larry already recorded.

**W2 — the tool's RETURN CONTRACT carries units, not just its display.**
`get_weather` returns BOTH `temperature_f`/`max_f`/`min_f` and
`temperature_c`/`max_c`/`min_c` on every call, plus a `units` field naming
which set is primary (`"imperial"` | `"metric"`, from W3's config) and a
`human` string written in the primary unit. *Why:* fixing only `display.py`
would leave the analyst's spoken 60-word brief in Celsius, since it reads the
tool result, not the display payload — the bug would visibly half-persist in
voice. Returning both sets unconditionally (rather than only the configured
one) means a units change never alters the payload's SHAPE, so no consumer
breaks when the setting flips; it is the same additive discipline `surface`
and `tool` followed in `display.py`. `display.py` and the analyst select by
reading `units`, never by guessing from which keys are present.

**W3 — temperature units are CONFIGURATION, not a memory fact.** A new
`Settings` field `jarvis_units: str = "imperial"` (values: `imperial` |
`metric`, validated) sits beside `jarvis_timezone` / `jarvis_user_name` /
`jarvis_name` in `jarvis/config.py`, with `# JARVIS_UNITS=imperial` in
`.env.example`. It reaches its consumers by two paths, both already built:
`bridge_settings_to_env` gains one `os.environ.setdefault("JARVIS_UNITS", …)`
line so MCP children see it (the exact mechanism that already carries
`JARVIS_TIMEZONE`), and `SUPERVISOR_PROMPT` gains a `{units}` format parameter
passed from `settings.jarvis_units` at both call sites that already pass
`timezone=` (`jarvis/agents/supervisor.py:93`, `jarvis/bot/pipeline.py:408`).

*Why (Larry, 2026-08-22 — "to me that is a system type preference and not
necessarily a memory of user preference … if it doesn't [affect the output]
then it is useless to store it"):* the codebase already settled this for the
sibling setting. Timezone is the same kind of thing — a durable, locale-derived
display setting — and it lives in config and reaches the prompt as a format
parameter, never entering the memory store, never competing for
`MAX_CONTEXT_CHARS`, never evictable. Units belong in that block.

The deeper reason is a mechanism change, and it is what makes this more than
tidying. **A memory fact affects output by persuasion; a config value affects
output by construction.** `user.preference.temperature_units` was live,
correct, and in the prompt on 2026-08-20 and the display still rendered °C —
not because the fact was missing, but because no code in the path ever read
it. The fact was decorative, which is exactly why three prior attempts to fix
this bug did not hold. Config is read by `get_weather` and turned into
arithmetic with no model judgment in the loop, the same
grounded-by-construction discipline as the code-appended `[ran on <model>]`
suffix and `ITERATIONS_EXHAUSTED_MESSAGE`.

**The `{units}` prompt parameter is not a second source of truth** — it is the
same config value read by a second consumer. The tool path is binding (it
decides the numbers); the prompt line is advisory and covers only the case
where the Supervisor speaks a temperature that did NOT come from `get_weather`
(a web-search figure, or its own conversion).

**W3a — the memory fact is retired, not kept in parallel.** Once
`jarvis_units` exists, `user.preference.temperature_units` is archived with
`became="config:jarvis_units"`. *Why:* leaving both means two places state the
same rule and they can disagree; the `became` value makes the move traceable
and reversible. This also returns a slot to the 15-fact preference cap.
**Until `jarvis_units` ships, the fact stays live** — it is currently the only
thing carrying the preference at all, and archiving it early re-creates D0.

**W3b — units do NOT govern location, and location stays in memory.**
`user.location.rule` ("use CURRENT device location for weather/local queries;
Spartanburg is ONLY the last resort") is conditional, changes with where Larry
is, and is exactly what the memory store is for. Only the unit setting moves
to config. *Why:* stated explicitly because "move weather settings to config"
would otherwise read as license to move the location facts too, which would
freeze a value that is supposed to track the device.

**W4 — Weather.gov failure falls back to Open-Meteo, and the payload always
says which source answered.** `get_weather` returns a
`source` field with exactly one of `"weather.gov"` (observation),
`"weather.gov-forecast"` (period fallback), or `"open-meteo"`. *Why:* the
`weather.gov-forecast` label is a load-bearing mechanical guard already
established in `ambient_weather.py` — an observation and a forecast period
differ by up to 30°F after dark, and the label is what keeps them from being
confused again. Extending the same vocabulary to the tool keeps one meaning
per label. Open-Meteo remains necessary: Weather.gov is US-only.

**W5 — the analyst calls BOTH `get_weather` and `get_weather_radar` for any
local/current weather question, and the two results render as ONE display
card.** A new pseudo-tool payload `weather_report` combines conditions and
radar; the merge happens in `jarvis/bot/display.py`, not in the model.
*Why:* Larry asked for radar to be "standard for this display/workflow" —
prompt-only wiring would produce two stacked cards per question, in
nondeterministic order, which is a worse display than the one that exists now.
Merging in code (not by asking the model to combine them) follows the
`plan_ready` precedent: a pseudo-tool routed through the existing display
pipeline rather than a second code path.

**W6 — the radar composites over a keyless CARTO dark basemap.** Tiles are
fetched from `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png` at
the SAME z/x/y coordinates `radar_tile_grid` already computes, returned in a
new additive `basemap_tiles` field, and rendered by `DisplayContent.tsx` as a
second 3×3 grid stacked *underneath* the radar grid via CSS `grid-area`
overlap. *Why:* keyless (no new credential, matching RainViewer's own
constraint), and `dark_all` suits the `--bg: #15191d` graphite console far
better than standard OSM, which would glare. Attribution is required by CARTO's
terms and is rendered as a caption line. Reusing the existing tile-coordinate
math means there is no second projection implementation to drift.

**W7 — capacity enforcement's mechanical age-out rung must never silently
archive a `preference`-tier fact when the merge rung was unavailable.** When
rung (b) is skipped for lack of an API key/model, rung (c) archives from
`project` and `system` tiers as before, but for `preference` it **stops,
leaves the tier over cap, and logs one WARNING naming the tier and the
overage**. *Why:* D0. The invariant "live = injected" is important, but it is
strictly less important than not silently deleting something the user
explicitly told Mortimer. An over-cap tier is visible (the Memory panel's
`not_reaching_prompt` amber line exists precisely to show it) and recoverable;
a silently archived preference is neither. This deliberately accepts a
temporary invariant violation as the lesser failure, and that trade is the
decision — an implementer must not "fix" it by resuming the age-out.

**W8 — no new kill switches.** `JARVIS_WEATHER_ENABLED` already gates the
ambient path; the tool path is gated by the analyst having `mcp-web` at all.
*Why:* the repo's own rule — a switch that gates nothing new is a switch to
maintain forever. `JARVIS_UNITS` (W3) is **not** a kill switch and does not
count against this: it selects a display unit, it cannot disable a feature,
and it has no `false` state — an unrecognised value is rejected by the
validator rather than silently degrading to "off".

---

## 2. Implementation order

1. **W7 first** (`jarvis/memory_sweep.py`) — it is independent of everything
   else and prevents recurrence of the regression while the rest is built.
2. **W3 config plumbing** (`jarvis/config.py`, `.env.example`,
   `jarvis/prompts.py`, `jarvis/agents/supervisor.py`, `jarvis/bot/pipeline.py`)
   — add `jarvis_units` with a validator rejecting anything but
   `imperial`/`metric`, the `bridge_settings_to_env` line, and the `{units}`
   prompt parameter. Do this BEFORE touching any weather code so the weather
   work has a setting to read rather than a TODO. **Both prompt call sites
   must pass `units=`** — `SUPERVISOR_PROMPT` is a `.format()` template, so a
   missed call site raises `KeyError` at runtime, not at import.
3. **`jarvis/weathergov.py`** — extract `_observation_temp_f`,
   `_weathergov_current`, the `WEATHERGOV_*` constants and `STATION_ATTEMPTS`
   out of `ambient_weather.py` verbatim; add a `daily_forecast(lat, lon,
   fetch, days)` helper reading `/gridpoints/.../forecast` periods for
   highs/lows (US offices report °F natively — read `temperatureUnit` and
   convert only if it says `C`, the same read-the-unit discipline
   `_observation_temp_f` uses).
4. **`ambient_weather.py`** — replace the moved code with imports. Its public
   behaviour and payload must not change by one byte; the existing ambient
   tests are the acceptance check.
5. **`mcp_servers/mcp_web/logic.py`** — `get_weather` gains the Weather.gov
   chain with Open-Meteo fallback, per W2/W4, reading `JARVIS_UNITS` from env
   for the primary unit. Geocoding still uses Open-Meteo's keyless geocoder
   (Weather.gov has none) — that hop is unchanged.
6. **`mcp_servers/mcp_web/logic.py`** — `get_weather_radar` gains
   `basemap_tiles` (W6).
7. **`jarvis/bot/display.py`** — `_fmt_get_weather` renders the unit named by
   the payload's `units` field; new `weather_report` pseudo-tool + formatter
   merging conditions and radar (W5); `_fmt_get_weather_radar` passes
   `basemap_tiles` through.
8. **`jarvis/prompts.py`** — analyst prompt: call both tools for local weather.
   Watch the 1,200-char conversational-agent budget
   (`test_no_agent_prompt_is_mostly_boilerplate`); the analyst's own text is
   currently ~382 chars so there is room, but check rather than assume.
9. **`web/src/components/DisplayContent.tsx` + `command-deck.css`** — stacked
   basemap/radar grids, attribution caption.
10. Tests (§3), then docs: CLAUDE.md's weather-source paragraph, and this
    file's §6. **W3a's fact archival happens last**, after acceptance 3a
    passes — see §4.

---

## 3. Tests

| Test | Pins | File |
|---|---|---|
| `test_weathergov_module_is_the_only_implementation` | no `api.weather.gov` URL literal outside `jarvis/weathergov.py` (greps source, same shape as `test_module_imports_nothing_that_executes`) | `tests/unit/test_weathergov.py` |
| `test_ambient_payload_unchanged_after_extraction` | ambient chip dict is byte-identical pre/post refactor | `tests/unit/test_ambient_weather.py` |
| `test_units_setting_rejects_unknown_values` | W3 validator: `imperial`/`metric` only | `tests/unit/test_config.py` |
| `test_units_bridged_to_child_env` | `bridge_settings_to_env` sets `JARVIS_UNITS`; a real env var still wins (setdefault precedence) | `tests/unit/test_config.py` |
| `test_supervisor_prompt_carries_units` | both call sites pass `units=`; rendering the prompt without it would `KeyError` | `tests/unit/test_prompts.py` |
| `test_get_weather_defaults_to_fahrenheit_primary` | no `JARVIS_UNITS` set → `units == "imperial"`, `human` contains `°F` and not `°C` | `tests/unit/test_mcp_web_logic.py` |
| `test_get_weather_honors_metric_setting` | `JARVIS_UNITS=metric` → `units == "metric"`, `human` in °C. **The test that proves the setting is load-bearing rather than decorative** (W3's whole point) | `tests/unit/test_mcp_web_logic.py` |
| `test_get_weather_returns_both_unit_sets_either_way` | F and C keys both present under both settings — payload shape never varies (W2) | `tests/unit/test_mcp_web_logic.py` |
| `test_get_weather_source_label_never_plain_weathergov_for_forecast` | forecast fallback labelled `weather.gov-forecast` (W4 guard, mirrors the existing ambient test of the same name) | `tests/unit/test_mcp_web_logic.py` |
| `test_get_weather_falls_back_to_open_meteo_in_fahrenheit` | non-US/failure path converts C→F, `source == "open-meteo"` | `tests/unit/test_mcp_web_logic.py` |
| `test_radar_returns_basemap_tiles_same_coords` | `basemap_tiles` z/x/y match `tiles` exactly (W6 no-second-projection) | `tests/unit/test_mcp_web_logic.py` |
| `test_weather_report_merges_conditions_and_radar` | one payload, both sections, `kind == "image"` with body | `tests/unit/test_display.py` |
| `test_weather_report_survives_missing_radar` | conditions-only card when radar errored — never suppresses the answer | `tests/unit/test_display.py` |
| `test_display_weather_table_follows_units_field` | reads the payload's `units`, never guesses from present keys; replaces the current `°C` assertions at `test_display.py:84-85` | `tests/unit/test_display.py` |
| `test_enforcement_never_ages_out_preferences_without_merge` | W7: preference tier left over cap + WARNING when no model available | `tests/unit/test_memory_sweep.py` |
| `test_enforcement_still_ages_out_project_and_system` | W7 is scoped to `preference` only | `tests/unit/test_memory_sweep.py` |

Existing tests that MUST be updated (not deleted): `test_display.py:84-85`
(°C assertions), `test_mcp_web_logic.py:180,183` (`temperature_c == 30.4`,
`"30.4°C" in human`). `tests/evals/sub_agent_evals.py` also references
Celsius — check before running the eval.

**Test-isolation note:** `JARVIS_UNITS` is process env, so any test that sets
it must use `monkeypatch.setenv`/`delenv` rather than assigning `os.environ`
directly, or it leaks into every later test in the session. The units tests
must assert the DEFAULT case with the variable explicitly *unset*, not merely
absent from that test's own setup.

---

## 4. Acceptance (Larry runs; results appended to §6)

1. `python -m jarvis.memory_sweep --enforce` with no API key → preference tier
   is NOT reduced, one WARNING logged. Confirm
   `user.preference.temperature_units` is still live afterwards.
2. `curl -s localhost:7861/api/ambient | python3 -m json.tool` → unchanged
   from the 2026-08-18 verified shape: `source: "weather.gov"` (not
   `-forecast`), `station` present.
3. Ask by voice: *"what's the weather?"* → one display card, temperatures in
   °F, radar map visible with recognisable geography beneath the
   precipitation layer, spoken brief in °F.
3a. **The decorative-value check (W3's falsifiable test).** Set
   `JARVIS_UNITS=metric` in `.env`, restart, ask again. **Both** the display
   card and the spoken answer must flip to °C. If either stays °F, something
   is hardcoded and the setting is decorative — the same failure as today,
   merely relocated, and the implementation is NOT done. Restore
   `JARVIS_UNITS=imperial` afterwards.
3b. After 3a passes, archive the memory fact per W3a:
   `python -m jarvis.classify` is not needed — one
   `archive_fact(conn, "user.preference.temperature_units",
   "config:jarvis_units")` call. Confirm weather still reads °F with the fact
   gone; that is what proves config, not memory, is now carrying the rule.
4. Ask on a clear day → radar renders the basemap with no precipitation
   overlay (an empty-but-legible map, not an empty box). **This is the check
   D3 exists for.**
5. `RUN_LIVE=1 python -m tests.evals.routing_eval` → still ≥90% (the analyst
   prompt changed).
6. `RUN_LIVE=1 pytest tests/integration -q` → `test_mcp_web_server` passes on
   a machine with network egress (it fails in a restricted sandbox for
   unrelated proxy reasons; see the Gate V2 plan's §6).

---

## 5. Self-audit

- **W2 vs W3** — W2 says the payload always carries BOTH unit sets plus a
  `units` field; W3 says config decides which is primary. No conflict, and the
  split is deliberate: the *shape* is invariant (W2) so consumers never break,
  while the *primary* is configurable (W3). A consumer that switched on
  which keys were present would defeat both, which is why
  `test_display_weather_table_follows_units_field` pins reading `units`.
- **W3 supersedes the original W3.** The first draft of this plan hardcoded
  Fahrenheit and argued the MCP subprocess could not see a setting. That was
  wrong: `bridge_settings_to_env` already carries `JARVIS_TIMEZONE` into MCP
  children and `mcp_web` already reads `os.environ`. Recorded rather than
  quietly edited, because the superseded reasoning is the kind an implementer
  might re-derive and re-apply.
- **W3 vs D0** — D0 shows a memory fact is an unreliable carrier (it was aged
  out). W3 removes the dependency rather than trying to make memory more
  reliable, and W7 independently fixes the eviction bug. Both are needed: W7
  protects the preferences that legitimately remain in memory.
- **W3 vs W3a ordering** — the fact must stay live until the config path is
  verified (acceptance 3a), then be archived (3b). Archiving first would
  re-create D0 for however long the implementation takes. This ordering is
  load-bearing, not incidental.
- **W1 vs the ambient module's verified status** — `ambient_weather.py` was
  verified live 2026-08-18 and its behaviour must not change. Step 3 is a pure
  extraction with an equality test (`test_ambient_payload_unchanged_after_extraction`)
  precisely so a refactor cannot silently regress a verified path.
- **W5 vs `DISPLAY_TOOLS`** — `weather_report` is a pseudo-tool like
  `plan_ready`, so it needs entries in `DISPLAY_TOOLS`, `DISPLAY_SURFACE`
  (`"window"`), and `_FORMATTERS`. Missing any of the three yields a silent
  `None` return and no card. Called out because `plan_ready` needed exactly
  these three and nothing warns when one is absent.
- **W5 vs D3** — merging into one card is independent of the basemap fix; if
  W6 were dropped, W5 still works and simply shows a blob map. They are
  sequenced together but not coupled.
- **W6 vs `radar_tile_grid`** — the basemap MUST use the returned tile
  coordinates rather than recomputing them, or a future zoom change desyncs
  the two layers. The test pins coordinate equality, not just presence.
- **W7 vs the "live = injected" invariant** (CLAUDE.md, MORTIMER_MEMORY_CAPACITY_PLAN.md
  M1-M10) — this **knowingly weakens** that invariant for one tier under one
  condition. That is the decision, not an oversight: the invariant's own plan
  argues archiving is safe *because it is reversible and merge-assisted*, and
  when the merge rung is unavailable that premise does not hold. An
  implementer must not restore unconditional age-out to satisfy the invariant.
- **W7 scope** — deliberately `preference` only. `system` has a live cap of 0
  by design (M4) and `project` facts are re-derivable; applying W7 to those
  would let the store grow without bound.
- **Not addressed here:** the 55 near-duplicate clusters `jarvis.consolidate`
  reported remain unresolved, and W7 makes the preference tier more likely to
  sit over cap. Consolidating them is real work with real judgment calls about
  Larry's own stated preferences, and it belongs in its own pass, not smuggled
  into a weather fix.

---

## 6. Implementation status

All of W1-W8 implemented 2026-08-22, in the order given in §2.

- **W7 (preference age-out guard)** — done first, as specified.
  `jarvis/memory_sweep.py`'s `run_capacity_enforcement` now skips
  mechanical age-out for the `preference` tier whenever the merge rung
  (b) could not run, leaving the tier over cap and logging
  `memory_enforce_preference_left_over_cap`; `project`/`system` keep the
  old unconditional backstop. `--enforce`'s CLI output prints a `⚠ still
  N over cap` line when this fires. Tests:
  `test_preference_left_over_cap_when_merge_rung_unavailable`,
  `test_preference_still_merges_when_model_available` (new);
  `test_enforcement_reaches_cap_without_llm` retargeted from
  `preference` to `project`, since W7 changed exactly the scenario it
  used to test. **Applied immediately, live, to Larry's own store**
  during this session: the F10 cleanup from the prior (Gate V2) plan had
  aged out `user.preference.temperature_units` — the sole surviving
  Fahrenheit fact — a few hours earlier; it was restored
  (`archived_at=NULL`) and one exact-duplicate preference
  (`user.style.tool_specification`, redundant with
  `user.preference.tool_specification`) was archived to free a slot
  under the 15-fact cap, confirmed via `render_memory_context` actually
  including the restored fact afterward.
- **W3 (config plumbing)** — done. `jarvis/config.py`'s `jarvis_units`
  (`imperial` | `metric`, validated); `.env.example` entry;
  `bridge_settings_to_env` gained one `setdefault("JARVIS_UNITS", ...)`
  line (both the primary Settings path and the `.env`-fallback path used
  when full Settings validation fails); `SUPERVISOR_PROMPT` gained
  `{units}`, both call sites (`jarvis/agents/supervisor.py`,
  `jarvis/bot/pipeline.py`) updated. Every `SimpleNamespace`-based test
  fixture across the repo that feeds `SUPERVISOR_PROMPT.format()` needed
  `jarvis_units=` added (`test_orchestrator.py`, `test_bot_wiring.py` ×2,
  `test_speaker_gate.py`, `scripts/context_growth_probe.py`) — a missed
  one raises `KeyError` at prompt-render time, which is exactly the
  fail-loud behavior wanted (a silently-omitted `{units}` would be worse
  than a test failure). Tests: `test_units_defaults_to_imperial`,
  `test_units_setting_rejects_unknown_values`,
  `test_units_setting_accepts_metric`, `test_units_bridged_to_child_env`,
  `test_units_bridge_does_not_override_real_env_var` (test_config.py);
  `test_supervisor_prompt_carries_units` (test_prompts.py).
- **W1 (shared jarvis/weathergov.py)** — done.
  `_observation_temp_f`/`weathergov_current` moved verbatim out of
  `jarvis/ambient_weather.py`; `daily_forecast()` added (new — the
  ambient chip never needed multi-day highs/lows). `ambient_weather.py`
  now imports and re-exports what it still references
  (`WEATHERGOV_UA`/`STATION_ATTEMPTS`/`fetch_headers`/
  `weathergov_current`); its own 25 pre-existing tests pass UNCHANGED,
  which is the extraction's own acceptance check, plus a new explicit
  equality pin, `test_ambient_payload_unchanged_after_extraction`
  (asserts the exact dict, not a subset of keys). New:
  `tests/unit/test_weathergov.py` — `test_weathergov_module_is_the_only_
  implementation` (greps the tree for a stray `api.weather.gov` literal
  outside this one module) plus `TestDailyForecast` (6 tests) and
  `TestFetchHeaders` (2 tests).
- **W2/W3/W4 (get_weather rewrite)** — done.
  `mcp_servers/mcp_web/logic.py`'s `get_weather` is now Weather.gov-
  primary via the shared client, Open-Meteo fallback unchanged in
  mechanism but now ALSO returning `temperature_f`/`max_f`/`min_f`
  alongside the Celsius fields it always had. Every code path — both the
  Weather.gov branch and the Open-Meteo fallback branch — returns both
  unit sets, `units` (read from `JARVIS_UNITS`, defaulting/degrading to
  `imperial` on anything unrecognized), and `source` (`weather.gov` /
  `weather.gov-forecast` / `open-meteo`). `human` is built in the
  configured primary unit. Tests: `TestGetWeather` (existing tests
  updated — none of them mock the Weather.gov URLs, so they exercise the
  Open-Meteo fallback exactly as before, now with the added °F/`units`/
  `source` assertions) plus new `test_defaults_to_fahrenheit_primary`,
  `test_honors_metric_setting` (**the falsifiable test proving the
  setting is load-bearing**), `test_returns_both_unit_sets_regardless_
  of_setting`, `test_unknown_units_env_value_defaults_to_imperial`,
  `test_falls_back_to_open_meteo_in_fahrenheit` (exact conversion math:
  30.4°C -> 86.7°F); new `TestGetWeatherWeatherGov` class (4 tests) with
  all three Weather.gov URLs mocked, exercising the PRIMARY path the
  existing class never reached — `test_weathergov_primary_used_when_
  available`, `test_weathergov_daily_forecast_converted_both_ways`,
  `test_source_label_is_never_plain_weather_gov_for_forecast_fallback`,
  `test_weathergov_current_missing_falls_back_to_open_meteo`.
- **W6 (radar basemap)** — done. `get_weather_radar` returns
  `basemap_tiles` (CARTO `dark_all`, keyless) computed from the SAME
  `radar_tile_grid(lat, lon)` coordinate list as `tiles`, never
  recomputed. `jarvis/bot/display.py`'s `build_display_payload` extended
  to accept an optional 6th formatter-tuple element (`basemap_images`),
  backward-compatible with every other formatter's 5-tuple.
  `_fmt_get_weather_radar` passes it through.
  `web/src/displayResults.ts`'s `DisplayPayload` interface gained
  `basemap_images?`; `DisplayContent.tsx` renders it as a second 3×3
  grid UNDER the precipitation tiles via a CSS Grid same-`grid-area`
  stacking trick (`command-deck.css`'s `.display-tiles-radar`,
  `.display-tile-basemap`/`.display-tile-overlay`), plus an attribution
  caption. Tests: `test_basemap_tiles_same_coords_as_radar_tiles`
  (coordinate-equality, not just presence — the guard W6 exists for),
  `test_basemap_tiles_are_keyless_carto`;
  `test_basemap_images_passed_through`,
  `test_missing_basemap_tiles_defaults_to_empty` (test_display.py).
- **W5 (merge into one card)** — done.
  `jarvis/bot/display.py`'s `WeatherReportMerger` (new class) pairs a
  run's `get_weather`/`get_weather_radar` tool results by `run_id`;
  `jarvis/bot/pipeline.py`'s `make_agent_event_handler` constructs one
  instance per connection and routes those two tool names through
  `merger.offer()` instead of `build_display_payload()` directly,
  flushing any still-pending lone half via `merger.finalize()` on
  `delegate_done` so a real result is never silently dropped (e.g. the
  model only called `get_weather`, or `get_weather_radar` errored). New
  pseudo-tool `weather_report` (same convention `plan_ready` already
  established) registered in `DISPLAY_TOOLS`/`DISPLAY_SURFACE`/
  `_FORMATTERS`. `jarvis/prompts.py`'s analyst prompt now requires
  calling BOTH tools for local/current weather (925 -> 1138 chars,
  under the 1200-char `test_no_agent_prompt_is_mostly_boilerplate`
  ceiling). Tests: `TestWeatherReport` (5, the formatter) +
  `TestWeatherReportMerger` (6, the pairing/flush state machine
  independent of the formatter, including cross-run isolation) in
  test_display.py; `test_analyst_prompt_requires_both_weather_tools` in
  test_prompts.py.
- **W8 (no new kill switches)** — satisfied by construction;
  `JARVIS_UNITS` has no `false`/off state (confirmed: an unrecognized
  value is REJECTED by the validator, never silently treated as
  "disabled" — this was checked explicitly, not assumed).
- **Full suite**: `pytest tests/unit tests/integration -q` -> 1530
  passed, 3 skipped, 1 failed. The one failure
  (`test_mcp_web_server`) is the SAME pre-existing live-network failure
  documented in `MORTIMER_GATE_V2_AND_MODEL_REQUEST_PLAN.md`'s §6 (a
  `ProxyError` hitting weather.gov/Open-Meteo from this sandbox's
  restricted network egress) — unrelated to this plan's changes, and
  expected to fail identically on `main` in any network-restricted
  environment. `pytest tests/unit -q` alone: 1442 passed, 0 failed.
- **Frontend**: `tsc -b` exits 0 (clean compile, confirmed by running it
  directly after `npm run build`'s bundler step failed on an unrelated
  sandbox filesystem permission error — `EPERM` unlinking a stale file
  under `web/dist/`, owned by a different uid in this sandbox, reproduced
  independently via a bare `rm -rf dist` which fails the identical way;
  this is an environment artifact, not a code issue). `npm run lint`:
  0 errors, 4 pre-existing warnings in files this plan did not touch
  (`VoiceWave.tsx`, `SideDrawer.tsx`). **`npm run build`'s full bundler
  pass was NOT completed in this sandbox** — Larry should run it once on
  his own machine to confirm the production bundle actually builds, since
  `tsc -b` only proves type-correctness, not that Rollup/Vite can bundle
  the result.
- **CLAUDE.md**: the Weather source paragraph gained three new
  sub-entries (Fahrenheit-by-default + shared client, units-as-
  configuration, radar-as-standard) plus a note on the live memory
  regression this work surfaced and fixed.
- **Not independently re-verified in this pass**: `RUN_LIVE=1
  python -m tests.evals.routing_eval` (analyst prompt changed) — same
  vault/Keychain limitation as the Gate V2 plan's §6: this sandbox has no
  macOS Keychain, so the credential vault cannot unlock and the live LLM
  keys are unreachable. **Larry should run this on his own machine**
  before treating W5's prompt change as fully verified, per §4's
  acceptance step 5. Live acceptance steps 1-4 and 6 (curl the sidecar,
  ask by voice, check a clear-day radar render) also need his machine —
  none of the upstream APIs (weather.gov, Open-Meteo, RainViewer, CARTO)
  are reachable from this sandbox either.
