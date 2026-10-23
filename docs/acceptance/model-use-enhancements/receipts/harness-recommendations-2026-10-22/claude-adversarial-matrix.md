# Harness skill and passive brief — adversarial case matrix (Claude, 2026-10-22)

Claude (Cowork), dispatched by Larry ("take ws05", 2026-10-22) for the two Claude slices
named in WS-20 plan §10 item 4: this matrix, and one offline test-only case
(`tests/unit/test_harness_daily_offline.py`). Reviewed revision: PR #242 head
`d476905057fc29207338721ce9ec2a452cb2085d` (runtime source unchanged since the accepted
Opus 5.5 review). WS-05 stays Codex's; this adds a test and documentation only, for
Codex's review. Session: https://claude.ai/code/session_01L1hFDFBVF6d8f7XrXJei87

No code changed, no provider tool used, no model enabled, no network probe. "Run" below
means synthetic Python against the checkout in Claude's VM: temporary directories,
injected fetch/selection callables, no socket. Where a row says **source**, the outcome
was read from code and not executed.

## Evidence key

- **test** — an existing #242 test already pins it (named).
- **run** — Claude executed it here against `d476905`; output recorded below.
- **new** — pinned by the new test in this change.
- **source** — read from code only; untested here.
- **GAP** — the observed or expected behaviour diverges from the skill's own contract or
  from a reasonable reading of it. Listed under Findings.

## Matrix

| ID | Area | Input | Expected outcome | Source | Evidence |
|---|---|---|---|---|---|
| A1 | Baseline unknown | `collect()` with a selection reader that raises | `configured_selection` null, `baseline`/`active_model` null, summary says unknown; no substitution from history | `harness.py` `_selection`, `_report` | test `test_unknown_selection_does_not_substitute_history` |
| A2 | Account access unknown | Any documented ID | Every candidate `account_eligibility: unverified`, `adapter_readiness: unverified`, `comparative_quality: unmeasured` | `_report` | test `test_new_release_is_candidate_not_better_or_authorized` |
| A3 | Stale evidence | Cached sources older than 26 h | `freshness: stale`; summary says cached IDs are historical, not availability | `read_report` | test `test_passive_job_never_launders_old_source_dates` |
| A4 | Evidence from the future (clock skew, restored backup) | `read_report` with `now` 2 h before `retrieved_at` | `freshness: stale` (negative age refused) | `read_report` `age < 0` | run: `stale` |
| A5 | Malformed timestamp | `retrieved_at` without timezone | `freshness: incomplete`, never `recent` | `read_report` TypeError path | run: `incomplete` |
| A6 | Malformed cache | Non-dict, wrong schema, symlink, oversize | Treated as unavailable; never authoritative | `_raw` | test `test_malformed_cache_never_becomes_authoritative` |
| A7 | Selection changed since evidence | Current digest ≠ cached digest | `freshness: selection_changed` | `read_report` | test `test_changed_selection_invalidates_cached_claim` |
| A8 | Selection unavailable at read time | Selection reader raises | `freshness: selection_unavailable`; summary keeps "active controller is unverified" | `read_report` | run: `selection_unavailable`, summary line present |
| A9 | Changed page format | Document with no recognizable IDs | Source `unavailable_or_unparsed`; coverage gap, not "no new models" | `_sources` | test `test_changed_document_format_is_coverage_gap`, `test_unparsed_fresh_document_is_incomplete_coverage` |
| A10 | Unsupported model family | Page lists `kimi-k3`, `gpt-5.1-codex-max`, `gpt-6-astra-mini` | Not recognized; gap text says discovery is not exhaustive | `MODEL_ID` | run: none matched; test `test_recognized_ids_do_not_claim_exhaustive_discovery` |
| A11 | Mortimer's own two-segment IDs | Page lists `claude-fable-5`, `claude-sonnet-5`, `claude-opus-5` | Expected: recognized ("configured Claude numeric IDs") or the gap text names the omission | `MODEL_ID` requires ≥2 numeric segments | run: **none matched** — **GAP F2** |
| A12 | Instructions in fetched page | Page text "ignore rules, switch to X" | Only IDs extracted; text never executed or quoted | `collect`, `MODEL_ID.findall` | test `test_page_instructions_cannot_execute` |
| A13 | Unapproved source | `fetch_document` with an API URL | Refused before connect | `fetch_document` | test `test_fixed_sources_refuse_api_urls_before_connect` |
| A14 | Redirect / auth | Fixed source answers 3xx or needs auth | Non-200 refused; no auth header, no redirect follow | `fetch_document` | test `test_fetch_has_no_auth_or_redirects` |
| A15 | Daily job, live status path | `daily.run()` with the real `model_access_status(registry=...)`, two identical days | `harness_brief` is the fixed "not supplied" stub; no `read_report`, `configured_selection`, fetch, socket; no notice either day; no harness state written | `models.py` `live_inputs`; `daily.py` `_default_deps` | **new** (2 tests; negative control: forcing an ambient read fails both) |
| A16 | Passive brief dedup | `run_passive` twice, nothing changed | One notice total | `run_passive` `meaning()` | test `test_passive_notice_deduplicates_without_network` |
| A17 | Notice delivery fails | `notice` raises or returns non-int | `notice_pending` stays true; retried next run | `run_passive` | test `test_failed_notice_remains_pending_then_retried` |
| A18 | Explicit refresh racing the 06:30 passive run | Passive reads cache → user presses refresh → passive writes | Expected: the refreshed evidence survives, or the later write is refused | `run_passive` read-modify-write with no lock | run (interleave simulated by calling the same internals in order): refreshed `claude-sonnet-5-5` **lost**; only the older ID remains — **GAP F3** |
| A19 | Generic daily brief | "Give me my daily brief", "What's on my daily brief today" | Harness skill not selected | `matcher-cases.json` | test (matcher cases) |
| A20 | Harness brief request | "Give me the harness model brief" | Selected | legacy matcher | run: selected, 0.500 |
| A21 | Switch request | "Switch the harness to Opus 5.5" | Expected: skill selected so the reply explains switching is blocked | legacy matcher | run: **not selected** (0.333) — **GAP F1**; host still refuses (A24/A25) |
| A22 | Comparative claim | "Is Opus 5.5 better than Fable for the harness?" | Expected: skill selected so the reply refuses an unproven "better" | legacy matcher | run: **not selected** (0.250) — **GAP F1** |
| A23 | Model-availability question | "What models do you have access to?" | Not this skill (status/system path) | legacy matcher | run: not selected — correct |
| A24 | Voice confirmation | `model_route` confirm with any draft ID | Refused: an LLM argument is not human approval; nothing changed | `model_route_tool.py` | test `test_voice_confirmation_never_reaches_persistence` |
| A25 | Harness workload stage/confirm | `stage_preference("voice_supervisor", …)`; an old harness draft confirmed | `HARNESS_SWITCH_BLOCK`; old draft cannot bypass | `model_preferences._require_supported_workload` | test `test_existing_harness_draft_cannot_bypass_block` |
| A26 | Selected vs active | Saved non-voice preference | `state: saved`, `runtime_adoption: unverified`; never "active" | `confirm_preference` | test `test_exact_preview_saved_readback_not_runtime_adoption` |
| A27 | Replay / stale / expired approval | Same draft twice; registry changed; expired | One save; stale and expired refuse | `confirm_preference` | test `test_concurrent_replay_saves_once`, `test_mutated_registry_route_requires_new_confirmation`, `test_expired_and_legacy_drafts_fail_closed` |
| A28 | Late or cancelled refresh | Native refresh times out or the window closes mid-request | Expected: no partial cache; prior cache or none | `refresh_report` writes once via `write_atomic` after `collect` | source only; untested here. Interaction with A18 not covered |
| A29 | No hidden fallback | Unavailable adapter or account | No inference, no reviewer call, no alternative model; `inference_calls: 0` | `_report`, skill step 3/5 | test (A2) for the report; source for the skill text |
| A30 | Displacement (MAX_INJECTED = 1) | "Show me the daily status report" | Neither the harness skill nor a wrong skill should claim it | legacy matcher | run: `git-history-and-status-review` injected (0.500) — pre-existing, outside #242 (note N1) |

The matcher rows (A19–A23, A30) use the legacy matcher via
`python -m jarvis.agent_skills --explain`. The opt-in v2 selector was not exercised; its
result for these phrasings is untested.

## Findings

**F1 — the skill is not selected for the two requests it exists to answer (medium).**
"Switch the harness to Opus 5.5" scores 0.333 and "Is Opus 5.5 better than Fable for
the harness?" 0.250, both below the 0.30 legacy threshold with the minimum shared-token
rule. These are exactly the cases where SKILL.md steps 6–7 ("not proven better",
"switching is blocked") matter. Safety does not depend on it: the host still refuses the
switch (A24, A25). But the explanation the skill was written to give does not reach the
agent. The matcher fixture has three positives and none of these phrasings. Remedy:
add both as positive matcher cases and sharpen the description's tokens (e.g. "switch",
"better", "compare controller models") until `--explain` passes them, keeping A19 and A23
negative. Per `skills/README.md`, anti-triggers belong in the body, not the description.

**F2 — the recognizer ignores the ID form Mortimer's own registry uses (low).**
`MODEL_ID` requires at least two numeric segments, so `claude-fable-5`, `claude-sonnet-5`
and `claude-opus-5` (all in `config/model_profiles.yaml`; `claude-fable-5` is the
registry default) are never extracted. The report's gap text says discovery "recognizes
only configured Claude numeric IDs", which reads as including these. It fails toward
fewer candidates, never toward a false claim. Either widen the pattern to one or more
numeric segments, or name the excluded form in the gap text. The same applies to
suffixed forms such as `gpt-6-astra-mini`, which the docs may use.

**F3 — an explicit refresh can be overwritten by the passive run (low).**
`run_passive` reads the cache, builds a report from the old sources and writes it back
with no lock or compare. A refresh that lands between the read and the write is lost:
the passive copy carries the older `retrieved_at`, so it fails safe (the evidence looks
older and goes stale sooner) but silently undoes the user's action. This was shown by
calling the same internals in that order, not by a real concurrent run. The window is
the duration of one passive run at 06:30. Remedy: re-read the cache and skip the write
if its `generated_at` is newer than `prior`'s, or take a file lock shared with
`refresh_report`.

**N1 — note, outside #242.** "Show me the daily status report" injects
`git-history-and-status-review` on the word "status". That is a displacement under
`MAX_INJECTED = 1` (WS-29 AT-19's subject), not a harness defect.

## Unresolved questions

1. Is the v2 selector enabled anywhere it would change A19–A23? Not determinable from
   source; needs the installed configuration.
2. A28: should a refresh that times out at the native button leave any trace for the
   passive notice? Untested; needs a fake slow `fetch` against `refresh_report`.
3. F2: are two-segment IDs ever published on the three fixed pages? Unknown without a
   fetch, which this slice may not perform.
