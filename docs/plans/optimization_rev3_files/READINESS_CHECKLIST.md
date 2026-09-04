# Implementation Readiness — Rev 3.2, 2026-09-01 (Phase 0 complete; Phase 1 re-planned for the native SDK)

## Diagnostics COMPLETED (were open gates; now closed)
- [x] OpenRouter chain verified end-to-end: vault has the key, inject_env
      exports it, council calls succeed (or-* members won and judged
      round e48cfbe1)
- [x] DeepSeek mystery resolved: participates in council; nothing else
      assigns it; visibility fix = agent-card roster task
- [x] kimi-k3 root-caused: always-on thinking vs 120s judge timeout
      (probed 5.6s trivial / 36s at 2.3K tokens; projects 90-180s+ real)
- [x] available_models() confirmed listing all 13 profiles

## Rev 3 review — every file-level claim re-verified against the working tree
- [x] All Rev 2 "confirmed exact code" citations matched byte-for-byte
      (supervisor.py:128, base.py _loop site + local run_client seam,
      council.py:235/249, memory_sweep.py:362/649, memory.py:868,
      kb_digest.py:117, procedures.py:361, agents.yaml developer block,
      upgrade_models.yaml default/tiers/identities, vault `get` subcommand)
- [x] Eight conflicts found and resolved — see the plan's "Rev 3
      resolutions" section. Files changed: usage_ledger.py (WAL,
      root-anchored path, RUNGS), costs_api.py (path, read timeout),
      cost_report.py (BUCKETS, honest A3), effort.py (cache-claim
      wording), patches_confirmed_sites.py (sites 12-13 + rung kwarg),
      README_costs.md, this file, the plan (Phase 0b/0/1b/3 + resolutions)

## In hand (file set + plan Rev 3)
- [x] 13 call sites mapped (was 11): + upgrade_agent.py:469 executor
      rung, + council._call_profile `rung` kwarg for its 4 callers
- [x] usage_ledger.py / effort.py / costs_api.py / CostDashboardView /
      cost_report.py / puller / price map (rates to fill) / Procfile line
- [x] Phase 0b fixes written as exact patches: K3 timeout pair + registry
      default flip to claude-fable-5 (blast radius now documented)
- [x] Phase 3 planner/executor split mapped onto the three EXISTING
      seats (planning pathway / UpgradeAgent loop / developer SubAgent)
      with the exact env vars, config constants and registry entry

## Implementation order
1. [ ] Two commits, in this order (Larry 2026-09-01: workflows get their
       own commit): (a) the five untracked config/workflows/user-*.yaml
       drafts — COMMIT_MSG_workflows.tmp; (b) agents.yaml + pipeline.py
       (mcp-kb librarian + session-digest hook) — COMMIT_MSG_kb.tmp.
       DONE 2026-09-01 (d74e40d, 3d63f59 on feat/t4a-security-hardening).
       The model-floor conflict it surfaced is resolved: Phase 0b item 5.
2. [ ] Phase 0b fixes (3 edits, patches file bottom section) — then
       `grep JARVIS_UPGRADE_PROFILE\|JARVIS_PLANNING_PROFILE .env` to
       confirm nothing already overrides the new default — commit
3. [ ] usage_ledger.py (Rev 3, WAL) + model_prices.yaml + supervisor
       patch only; one voice turn; confirm a row in data/costs.db AND
       that `PRAGMA journal_mode` reads `wal` — commit
4. [x] JARVIS_DEBUG_USAGE_LEDGER=1 session: does the Anthropic-compat
       path report cache fields? thinking tokens? — ANSWERED 2026-09-01
       (607588b, then Anthropic's compat docs): it cannot. Prompt caching
       is unsupported through the OpenAI-compatibility layer; the whole
       Phase 1 section was rewritten (plan Rev 3.2) around the native
       Messages API.
5. [~] Effort gate — HALF-ANSWERED by documentation 2026-09-01 (plan
       Phase 1b, Rev 3.2): shape is `output_config.effort` on the native
       API only (compat layer ignores `reasoning_effort`); Haiku 4.5 is
       not a supported model, so the Supervisor never sends it; effort
       changes DO invalidate the messages cache — static-per-rung is a
       requirement, and half (b) is moot. Remaining (a): one `analyst`
       run at `low` through the Path-B shim — no 400, fewer output
       tokens. Runs after Phase 1 landing step (ii).
6. [ ] Remaining 12 call-site patches (incl. upgrade_agent.py:469 and
       the council `rung` kwarg threading) + effort wiring — run
       `pytest tests/unit -q` — commit
7. [ ] Fill model_prices.yaml rates; Procfile costs entry; first
       cost_report.py after a day — sanity-check rung labels against
       usage_ledger.RUNGS (an "unknown rung" line on stderr means a site
       was mislabelled)
8. [ ] pull_openrouter_activity.py (--raw first run)
9. [ ] Voice skill (summary_text hook) + SwiftUI card into the interface
10.[~] After ~a week: baseline report → fill the plan's savings ledger.
       Larry 2026-09-01: Phase 1 starts NOW instead (spend ≥$10/day); the
       caching row of the ledger gets a partial "before". Steps 3-9 all
       DONE 2026-09-01 (55afe06, bc49f4b, 607588b, e83965c, 96a528e,
       7ab613e, 066a690, 37d2516, cec4aaa, 2636cd5).

## Phase 1 landing order (plan Rev 3.2 §Phase 1 — each its own commit)
- [ ] (i)  requirements.txt `+anthropic` extra + lock regenerate;
      jarvis/anthropic_shim.py (rules S1-S9) + tests/unit/test_anthropic_shim.py;
      usage_ledger.py fixes (input = prompt - reads - writes; OpenRouter
      cache_write_tokens alias) + test. Nothing live changes yet.
      Check: `.venv/bin/python3 -c "import anthropic, pipecat.services.anthropic"`;
      `pytest tests/unit -q`.
- [ ] (ii) jarvis/llm_client.py factory; base.py:220/246/250,
      upgrade_agent.py:373-393 (+provider arg, callers :370/:508),
      council.py:219-225 switched to it; OpenRouter anthropic/* extra_body
      cache_control; test_subagent.py:717-745 fixture retargeted
      (openai.AsyncOpenAI + JARVIS_ANTHROPIC_NATIVE=0) + mirror test.
      Gate: rewritten scripts/test_prompt_caching.py (>4,096-token filler)
      shows creation>0 then read>0 for claude-sonnet-5 and claude-fable-5;
      one real analyst/developer run shows cache_read>0 in cost_report.py
      from iteration 2. Then Phase 1b step 5(a) above.
- [ ] (iii) pipeline.py Anthropic branch (AnthropicLLMService,
      enable_prompt_caching=True) + usage_watcher.py native-semantics
      branch + supervisor_cache_cold WARNING + two wiring tests.
      Gate: test_prompt_caching.py for claude-haiku-4-5 (creation>0 on
      turn 1 proves the prefix clears 4,096); a ≥3-turn voice session with
      JARVIS_DEBUG_USAGE_LEDGER=1 shows cache_read>0 on supervisor rows
      from turn 2. One normal day of use before calling Phase 1 done.
      Rollback at any point: JARVIS_ANTHROPIC_NATIVE=0 + restart.

## Phase 0b item 5 — model floor (Larry 2026-09-01; do right after step 3)
- [ ] `claude-sonnet-5` direct profile added to upgrade_models.yaml,
      `or-sonnet-5` deleted in the same edit (identity-uniqueness test)
- [ ] agents.yaml: scheduler/librarian/analyst/systems ->
      `model_profile: claude-sonnet-5`, `on_profile_fallback: refuse`
- [ ] tests/unit/test_model_floor.py (no agent resolves to /haiku/i;
      every agent declares a profile; fallback is refuse)
- [ ] retire config/workflows/user-preference-model-defaults.yaml and
      user-preference-model-selection.yaml (config now binds the rule)
- [ ] confirm interpretation: background rungs (memory_*, kb_digest,
      procedures_describe) are NOT agents and stay below the floor

## Phase 3 prerequisites (can be prepared now, applied after baseline)
- [ ] `JARVIS_UPGRADE_PROFILE` / `JARVIS_APPBUILD_PROFILE` = claude-sonnet-5
      in .env (executor tier is env, never `default`)
- [ ] `PLANNING_DEFAULT_PROPOSER_TIERS = ["frontier"]` in council/config.py
      + draft_candidates honouring it when `members` is None
- [ ] `COUNCIL_PLANNER_START_TIER = 2` + `_maybe_escalate` using it for
      placement="planner" only
- [ ] Executor divergence paragraph in UpgradeAgent's prompt
      (jarvis/prompts.py), injected only when plan/plan_path present

## Deferred by design (tracked, not blocking)
- Agent-card council roster: parallel interface task; candidate first
  job for the planner/executor loop
- Frontier-planning prior gets audited against retry_validated after
  ~a month of rounds (an economy model won a planner round)
- Planner-placement single-escalation rule (tier-2 start, no repeat):
  revisit on retry_validated evidence; one-constant change

## Verdict
Phase 0 complete and verified live (2026-09-01). Both Rev 3 unknowns are
closed by documentation, in the direction that forced a redesign: the
compat layer cannot cache at all, so Phase 1 is a native-SDK migration
(plan Rev 3.2), landing in the three steps above with a one-variable
rollback. Ready to start (i).
