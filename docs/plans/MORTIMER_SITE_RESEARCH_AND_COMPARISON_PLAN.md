# Mortimer — Site Research & Comparison

**Author:** Claude Opus 5 (Cowork session), 2026-08-24
**Status:** IMPLEMENTED (approved and built 2026-08-24, see §8)
**Origin:** Larry — *"let's expand the analyst toolkit to include extensive
research on web site content. So if I give Mortimer 2 web addresses, I want
to be able to get a comparison review about the content of each."*
Scope answered by Larry in-session: **crawl each site** (not just the two
pages named), output **to the display window, saved on request**.

---

## 0. What exists, and the gap

The analyst has exactly one web tool that reaches the open internet:
`web_search` (Tavily `/search`). There is **no way to fetch a named URL's
content at all** — so "compare these two pages" currently has nothing to
read, and "compare these two sites" is further still.

Three measured constraints shape everything below:

1. **The analyst's budget is 45s / 5 tool iterations** (`config/agents.yaml`
   defaults; only `developer` was ever raised). Tavily's `/crawl` accepts a
   `timeout` of **10–150s** and defaults to 150. Two crawls is therefore up
   to **300s against a 45s budget** — 6.7x over. This is the single fact
   that decides the architecture: it cannot be an inline analyst tool.
2. **Content volume.** A 50-page crawl returning full `raw_content` is far
   past any usable context, twice over. Tavily's answer is built in:
   `chunks_per_source` (1-5 chunks, ≤500 chars each) caps per-page content —
   but it is available **only when `instructions` are provided**. That
   coupling is load-bearing and is why R3 below is not optional.
3. **Cost is real and metered.** With `instructions`, mapping costs 2
   credits per 10 pages; `basic` extract costs 1 credit per 5 successful
   pages. So ≈0.4 credits/page → a 50-page × 2-site comparison ≈ **40
   credits**. Larry's plan is the free tier (1,000 credits/month), i.e.
   **~25 comparisons per month** before hitting a wall. A model choosing
   `limit: 500` would spend a fifth of the monthly budget in one sentence.

---

## 1. Locked decisions

**R1 — This is an ASYNC SIDECAR JOB, not an analyst tool call.** A fifth
job slot in `jarvis/admin/server.py` (`_research_job` / `_research_lock`),
the same background-thread-plus-polling shape as `_run_job` / `_plan_job` /
`_council_job` / `_appbuild_job`, with `POST /api/research/start`,
`GET /api/research/job`, `POST /api/research/save`, `POST /api/research/cancel`.
The analyst gets three THIN HTTP-client tools mirroring `mcp_selfedit`'s
convention exactly — `research_compare_start`, `research_status`,
`research_save` — reusing `mcp_selfedit.logic.AdminClient` rather than a
second implementation. *Why:* §0.1. A 300s job inside a 45s voice-loop
budget is the failure mode `MORTIMER_PLANNING_PATHWAY_PLAN.md` P1 already
diagnosed once (two live 120s timeouts); repeating it knowingly would be
worse than the first time.

**R2 — Crawl bounds are CONFIG, never model-chosen.** `config/research.yaml`
carries `max_depth: 2`, `max_breadth: 20`, `limit: 40`, `extract_depth:
basic`, `chunks_per_source: 3`, `timeout_s: 120`, `max_sites: 2`. The tool
schema exposes only `urls` and `focus` — a model cannot set `limit`, and
`limit` is clamped server-side to `RESEARCH_HARD_PAGE_CAP = 60` per site
regardless of what config says. *Why:* §0.3. This is the same reasoning
that keeps `config/upgrade_agent.yaml` off the self-edit allowlist — an
agent must not be able to widen its own spend. Two independent bounds
(config value, hard cap) because a config typo is a plausible accident and
a 500-page crawl is not recoverable after the fact.

**R3 — `instructions` are always sent, derived from the user's stated
focus.** The crawl is steered ("compare their pricing and support options"),
and that is ALSO what unlocks `chunks_per_source`. When the user names no
focus, a neutral default is used (`"Identify what this site offers, who it
is for, and what distinguishes it"`) rather than omitting instructions.
*Why:* omitting `instructions` silently disables chunking and returns full
`raw_content` — the context blowout of §0.2 — so "no focus given" must
never take the uncapped path. The coupling is Tavily's, not ours, and it
is the kind of API detail that is invisible until it costs you a run.

**R4 — The comparison is written by ONE model call in the sidecar, reusing
the planning pathway's resolution.** `JARVIS_PLANNING_PROFILE` env → registry
default, via the same `load_model_registry`/`resolve_profile` every other
path uses. `RESEARCH_PROMPT` lives in `jarvis/prompts.py` (the single source
of truth for prompts). It receives per-site digests, never raw HTML. *Why:*
one model registry, one prompts module; a second copy of either is how they
drift.

**R5 — Structure is code, judgment is the model.** The sidecar assembles a
deterministic per-site digest (url, pages crawled, titles, chunk text,
credits used) — the model never sees crawl mechanics and never decides what
was crawled. The model's ONLY job is the prose comparison. *Why:* the
`WeatherReportMerger` precedent — merge in code, reason in the model.

**R6 — Output: display window now, repo file on request** (Larry's choice).
On completion the job pushes a `research_report` pseudo-tool payload through
`jarvis/bot/display.py`'s existing machinery (the `plan_ready` precedent —
a pseudo-tool name, not a second display path), `surface: "window"`.
`POST /api/research/save` then writes `docs/research/<slug>.md` through the
SAME `mcp_repo.logic.repo_write_file` draft→confirm gate voice already uses,
with an attribution footer naming the model, the URLs, the page counts, and
the date. *Why:* casual comparisons stay free; the useful ones persist. The
footer exists because a comparison without its sources and date is a claim
with no provenance.

**R7 — Announcement rides the existing watcher pattern.** A `ResearchWatcher`
in `jarvis/bot/` modeled on `PlanWatcher` (one-shot per `(started_at, state)`
transition, `TTSSpeakFrame`, no LLM in the speak path). It announces
completion and pushes the display payload. G12's `ProgressWatcher` already
covers "still working" pings, so this watcher does NOT duplicate progress —
it only announces terminal states. *Why:* two watchers narrating the same
job is how the interruption-notice flood happened.

**R8 — Cost is reported, every time.** `include_usage: true` on every crawl;
the job payload carries `credits_used` per site and a total, the spoken
summary names the total, and the saved document's footer records it.
*Why:* §0.3 — 25 comparisons exhausts a month. A feature that can quietly
consume the budget must say what it spent, in the same way the run log
records which model actually ran.

**R9 — Failure is per-site, never all-or-nothing.** One site failing
(403 unsupported, 429, timeout) still produces a report on the other, with
the failure stated plainly in both the spoken summary and the document —
never a silent one-sided "comparison". Tavily's own error taxonomy is
preserved: 432/433 (plan/PayGo limit) is reported as a BUDGET problem
naming the limit, distinct from 429 (rate) and 500 (their outage), matching
`jarvis/keyhealth.py`'s rejected/unfunded/unreachable discipline. *Why:* a
comparison that silently became a one-site summary is the fabrication class
this repo keeps closing.

**R10 — Kill switch `JARVIS_RESEARCH_ENABLED=false`**, enforced at one
point (the top of the sidecar's start endpoint), matching every other
feature here. Disabled means the tools return a plain "site research is
turned off" — never a crash, never a partial run.

---

## 2. Implementation order

1. `config/research.yaml` + bounds constants + `RESEARCH_PROMPT`.
2. `jarvis/research/crawl.py` — Tavily `/crawl` client (pure, injected
   httpx client, no DB), digest assembly, error taxonomy. Unit-testable
   with zero network, same discipline as `logic.py` elsewhere.
3. Sidecar: `_research_job` slot + 4 endpoints.
4. `mcp_web` (or a new thin `mcp_research`) tools — decided at build time
   by where `AdminClient` fits most cleanly; leaning `mcp_web` since it is
   already the analyst's web server and the tools are HTTP passthroughs.
5. `RESEARCH_PROMPT` wiring + the one model call.
6. Display payload (`research_report` pseudo-tool) + `DisplayContent`
   rendering for a two-column comparison.
7. `ResearchWatcher` + pipeline wiring + kill switch.
8. `POST /api/research/save` → repo write gate + footer.
9. Analyst prompt sentence routing URL comparisons here.
10. Tests, CLAUDE.md, §8 status.

## 3. Tests

| Test | Pins |
|---|---|
| `test_crawl_always_sends_instructions` | R3 — the chunking coupling |
| `test_model_cannot_widen_crawl_bounds` | R2 — schema exposes no limit |
| `test_limit_clamped_to_hard_cap` | R2 — second, independent bound |
| `test_digest_is_assembled_in_code_not_by_model` | R5 |
| `test_one_site_failure_still_reports_the_other` | R9 |
| `test_budget_error_distinguished_from_rate_limit` | R9 — 432/433 vs 429 |
| `test_credits_reported_in_payload_and_summary` | R8 |
| `test_second_start_refused_while_running` | R1 — one slot |
| `test_watcher_announces_once_per_transition` | R7 |
| `test_save_goes_through_the_repo_write_gate` | R6 |
| `test_kill_switch_returns_plain_message` | R10 |

## 4. Acceptance (Larry runs)

1. Two real URLs by voice → spoken 2-3 sentence verdict, full comparison in
   a display window, credits named.
2. "Save that" → draft appears, confirm → `docs/research/<slug>.md` with
   footer naming models, URLs, page counts, credits, date.
3. A deliberately bad URL alongside a good one → honest one-sided report
   naming the failure.
4. Ask for a third comparison while one runs → refused, offers status.
5. `JARVIS_RESEARCH_ENABLED=false` → plain refusal, no crash.
6. Check Tavily dashboard: credits spent match what was reported.

## 5. Cost, stated before approval

≈0.4 credits/page → **~40 credits per 2-site comparison** at `limit: 40`.
Larry's free tier is 1,000/month = **~25 comparisons**. Lowering `limit` to
20 halves it (~50/month) at the cost of shallower coverage. This is the one
number worth tuning against real use; it is config, not code.

## 6. Self-audit

- **R1 vs "just raise the analyst's budget"**: rejected. 300s inside a voice
  turn is not a budget problem, it is a wrong-place problem — the user would
  sit in silence through it, and barge-in would kill it. The async slot is
  the pattern this repo already uses four times for exactly this shape.
- **R2's double bound looks redundant** — it is not. Config guards against a
  model; the hard cap guards against the config.
- **R3 is an API-detail dependency.** If Tavily ever decouples
  `chunks_per_source` from `instructions`, this decision becomes
  unnecessary but not harmful. Recorded so a future reader knows it was a
  vendor constraint, not a preference.
- **R4/R5 split** keeps the model out of crawl mechanics entirely — it
  cannot report pages it did not receive, because it never sees the crawler.
- **Legal/politeness**: crawling is delegated to Tavily, which handles
  robots and rate limits as the vendor. Mortimer does not implement its own
  crawler, and should not — that is a whole discipline (politeness, backoff,
  robots parsing) this repo has no reason to own.
- **Scope NOT built**: no scheduled re-crawls, no diffing a site against a
  previous crawl, no more than 2 sites. Each is a plausible next step and
  none is needed to answer the question Larry asked.
- **The analyst's 45s budget is unchanged by this plan** — the tools it
  gains are instant HTTP passthroughs. If that assumption breaks in
  testing, the fix is the tools, not the budget.

## 7. Approval

- [ ] §1 locked decisions, especially R1 (async slot) and R2 (bounds)
- [ ] §5 cost — ~40 credits/comparison, ~25/month on the free tier
- [ ] §2 implementation order
- [ ] Scope exclusions in §6

## 8. Implementation status

Approved and implemented 2026-08-24, all 10 steps of §2 in order:

1. `config/research.yaml` (max_depth 2, max_breadth 20, limit 40, extract_depth basic, chunks_per_source 3, timeout_s 120, max_sites 2) + `RESEARCH_HARD_PAGE_CAP = 60` and `DEFAULT_FOCUS` in `jarvis/research/crawl.py` + `RESEARCH_PROMPT` in `jarvis/prompts.py`.
2. `jarvis/research/crawl.py` — pure Tavily `/crawl` client (`TavilyCrawlClient`, injected for tests), `crawl_site`/`build_site_digest`/`assemble_digests`/`total_credits`. R9's taxonomy: 432/433→`budget`, 429→`rate`, 400/401/403→`invalid`, 5xx/timeout/network→`unreachable`. Tavily's `/crawl` response has no page-title field (only `url`/`raw_content`), so `_derive_title` reads the first non-empty content line — a deviation from the plan's assumed shape, discovered against the real OpenAPI spec, not a design choice.
3. `jarvis/admin/server.py` — `_research_job`/`_research_lock`, `POST /api/research/start`, `GET /api/research/job`, `POST /api/research/save`, `POST /api/research/cancel`. Background thread crawls both sites sequentially (Tavily's own crawl is already internally parallel), builds the digest, resolves the model via `JARVIS_PLANNING_PROFILE` → registry default (the same `load_model_registry`/`resolve_profile` path every other pathway uses), and calls `council_mod._call_profile` with `RESEARCH_PROMPT` and `council_config.PLANNING_MEMBER_TIMEOUT_S`.
4. Tools landed in `mcp_web` (not a new `mcp_research` server) — the analyst's own web server, HTTP passthroughs only, per §2 step 4's own leaning.
5. Model call wiring: done inside step 3's background thread (`RESEARCH_PROMPT.format(focus=..., site_a=..., site_b=..., digests=...)`).
6. Display: `research_report` pseudo-tool in `jarvis/bot/display.py` (`DISPLAY_TOOLS`, `DISPLAY_SURFACE="window"`, `_fmt_research_report`). No bespoke two-column DisplayContent.tsx component was built — the existing generic markdown renderer already renders `RESEARCH_PROMPT`'s `### {site_a}` / `### {site_b}` headers as two clearly separated sections, matching every other formatter's (plan_ready, weather_report) reuse of the same renderer; building a dedicated grid would have been a second rendering path for no visible gain.
7. `jarvis/bot/research_watcher.py` (`ResearchWatcher`, modeled verbatim on `PlanWatcher`'s shape) wired into `jarvis/bot/pipeline.py` alongside `plan_watcher`/`progress_watcher`, its own kill switch `JARVIS_RESEARCH_WATCHER_ENABLED` (independent of R10's `JARVIS_RESEARCH_ENABLED`, which disables the feature itself).
8. `POST /api/research/save` → `repo_logic.repo_write_file` (the same draft→confirm gate voice already uses), footer naming model, both URLs, per-site page counts (or failure), and total credits.
9. Analyst prompt gained one routing sentence; kept the prompt under the `test_no_agent_prompt_is_mostly_boilerplate` 1,200-char ceiling by trimming wording repeatedly (1,564 → 1,191 chars) rather than requesting an exception to that test.
10. Tests: `tests/unit/test_research_crawl.py` (10 tests — R2/R3/R5/R9), `tests/unit/test_admin_research.py` (12 tests — R1/R6/R8/R9/R10), `tests/unit/test_research_watcher.py` (9 tests — R7), covering all 11 named tests from §3. `tests/integration/test_registry.py`'s `TOTAL_TOOLS` 61→64 (+research_compare_start/research_status/research_save). `mcp_servers/mcp_web/skill.yaml`'s `tools:` list updated to match. Full suite verified: 1,521 unit tests pass, the registry integration test passes, `scripts/check_skills.py` passes (with TAVILY_API_KEY/GITHUB_TOKEN set — both are genuinely absent in this sandbox, unrelated to this change), the backend import smoke test passes, and `tsc -b` type-checks clean (the frontend build's final `vite build` step hit this sandbox's known EPERM file-permission quirk on `web/dist/**`, the same class of issue documented for `.git/index.lock` — not a code defect; no `.tsx`/`.ts` files were touched by this feature at all, since step 6 reused the existing renderer).

Not yet exercised: a real Tavily crawl (needs `TAVILY_API_KEY`, which is not in this sandbox) and a live voice acceptance pass (§4) — both need Larry's machine. Unverified but low-risk: the model-call profile resolution path is shared with the planning pathway, already live-verified there.
