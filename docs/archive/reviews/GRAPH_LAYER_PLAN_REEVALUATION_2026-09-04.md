# Graph layer plan — re-evaluation against `main` (2026-09-04, after gap-closure Phase A+B)

**What this is.** `docs/plans/MORTIMER_GRAPH_LAYER_PLAN.md` was written at `baa9838` (tip of `feat/t4a-security-hardening`, before gap-closure). Since then `main` gained the 49-commit T4a branch, Phase A (GC1–GC3) and Phase B (GC4–GC11). This document checks every claim the plan makes against the tree as it is now, and against the live store (read-only), and proposes the amendments needed before §5 step 1 starts. Nothing here has been applied yet.

**How it was checked.** Every `path:line` in the plan was located by its quoted text (§0.11). Counts were read from the files, not recalled. The live database was opened read-only (`mode=ro`). The plan's dependency claims were checked against `requirements-lock.txt` and against the sandbox venv that will run the tests.

---

## A. Must amend before step 1 — these would fail a test or the plan's own rules

**A1. `TOTAL_TOOLS` is 67, not 64.** [certain] `tests/integration/test_registry.py:27` reads `TOTAL_TOOLS = 67` — gap-closure GC1 added mcp-kb's three tools to the count after the plan was written. §4, §5 step 9 and §7 all say "64 → 66". The correct edit is **67 → 69**.

**A2. `tests/unit/test_requires_env_snapshot.py` DOES freeze `optional_env`.** [certain] Lines 74 and 79 compare `optional_env` per server. Step 9 adds `optional_env: [JARVIS_GRAPHS_ENABLED, JARVIS_GRAPH_DEPTH, JARVIS_GRAPH_MAX_NODES, JARVIS_GRAPH_SINCE]` to `mcp_memory/skill.yaml` and `mcp_runlog/skill.yaml` (required — K2 scoping strips undeclared names from the child, so without it the kill switch silently would not reach the tools). That file is allowlist-denied and, by the security plan's own text, "a human commit that edits BOTH the manifest AND this snapshot". The plan anticipated this (§5 step 9, §12) and says it is Larry's hand-edit. The exact edit is in §H below. Decide: Larry applies it, or Larry tells the implementer to.

**A3. §0.2's "6-failure baseline" is stale.** [certain] Those six were fixed by GC1 (Phase A commit `60e9f42`, "Fix six standing test failures"). Larry's native run after Phase B: `2209 passed, 3 skipped, 0 failed`. The working rule for this plan becomes: the baseline is clean; **any** failure during implementation belongs to the implementer.

**A4. §8.2 "`./scripts/mortimer.sh` (restart)" no longer restarts anything once GC7 is installed.** [certain] After `launchd_gen.py --install`, `mortimer.sh` exits 3 with the launchd message by design (GC7 guard). The restart for §8.2–8.4 is `launchctl kickstart -k gui/$(id -u)/com.mortimer.admin` and `… com.mortimer.bot` (labels from `scripts/launchd_gen.py:87`). If GC7 has not been installed yet when §8 runs, `mortimer.sh` still works — the plan should name both.

**A5. `parse_since` returns `None` for empty or unparseable input, by contract, and the plan's SQL then returns nothing.** [certain] `jarvis/runlog/store.py:401` — "Returns None (no lower bound) for None or anything unparseable — never raises". The plan's literal queries in steps 5 and 6 (`WHERE started_at >= ?`) bind that `None`, and SQLite's `>= NULL` is NULL → zero rows, silently, with `ok: true`. Builders must omit the lower bound when `since_norm is None`. (Implementation detail — the implementer will do this; recorded so the plan matches what gets built.)

## B. Gaps created by what landed after the plan was written

**B1. GC6(b) supersession vs GL7's "one `scored` edge per row".** [likely the right call] `jarvis/council/agreement.py` (Phase B) now keeps only the newest `council_scores` row per `(round_id, judge_profile, proposal_label, shadow)` by `created_at` — a `--replay` writes fresh rows for a judge whose original call failed, and the newest supersedes the failed original. GL7 *deliberation* draws every raw row, so on replayed rounds (d6e0059b today; every round Larry replays in gap-closure §8.7) the picture would show the superseded failed rows as extra dotted abstentions — the graph would disagree with `--agreement`'s own "superseded shadow rows: N". Two honest options: (a) drop superseded rows from the graph; (b) keep them, flagged. Recommendation: **(b)** — factor the rule out of `compute_agreement` into `jarvis/council/agreement.py:supersede_score_rows(score_rows) -> tuple[list[dict], set[int]]` (kept rows, superseded row ids), have `compute_agreement` call it (one implementation, §0.3's principle applied across plans), and give `scored` edges `attrs["superseded"]: bool`, drawn at the same 45 % alpha as archived nodes. The raw-row honesty GL7 wanted is preserved and the picture agrees with the report.

**B2. Tenant column (GC8).** [certain, no impact today] `memories`, `procedures`, `agent_runs`, `agent_events`, `council_rounds`, `council_scores` gain `user_id TEXT NOT NULL DEFAULT 'local'` once migration 0020 runs. GL3's ids (`fact:<key>`) carry no tenant segment; gap-closure's binding rule is that nothing filters reads by `user_id` yet, and this plan must obey it (the memory builder does not filter). Amend GL3 with one sentence so the id scheme is not frozen without a tenant dimension: when tenant filtering arrives, builders filter by `jarvis.tenant.current_user_id()` and ids are unchanged (a graph is always one tenant's), or — if a cross-tenant graph is ever wanted — ids gain a `<user_id>/` segment. Stating it now costs nothing; discovering it after Stage 2 has decoded `fact:<key>` costs a Swift change.

**B3. Cross-plan drift with `MORTIMER_OPTIMIZATION_PLAN.md`.** [certain]
- *Interface Task → "Stage B (not built) — card adjacency"* (line 500) specifies the same `run_id` threading GL9 does, with a class name that does not exist (`SelfEditRunIn`; the real model is `GoalIn`, `jarvis/admin/server.py:140`). After GL9, that section's prerequisite is done and only the card UI remains. The plan's §4 appends nothing there. Amend: one line at line 508.
- *Phase 4 → "Stage B — derived graph + graph-ranked recall"* B1 (line 557) specifies a **second** memory graph: `jarvis/memory_graph.py`, `build_graph(conn) -> nx.DiGraph`, node types `entity`/`fact`, edges `child_of`/`has_fact`/`became`, and includes `observations` rows as inferred facts. The graph plan's one-line append covers B2 (ranking) but leaves B1's divergent spec standing for a future implementer to build. Amend that line to say B1 is superseded by GL7 *memory* with the vocabulary mapping (`entity` → `prefix:`; `has_fact` is `child_of` read the other way; `became` identical), and that B2's `neighborhood()`/`seeds_from_text()` are built over `jarvis.graphs.model.Graph`.
- Decision this surfaces: **should the memory graph include `observations` rows?** B1 wanted them (`provenance='inferred'`). GL7 does not list them and GL7 is exhaustive by design. Recommendation: **no, not in this plan** — `observations` has its own review lifecycle (`memory_reviews`, kind `contradiction|cluster`) and would need its own node type and edges; record the decision in the amended Optimization-plan line so Stage B does not add them silently either.

**B4. Web is frozen (GC4).** [certain] Stage 1's "both clients can show it today" is MortimerHost in practice; nothing in the plan changes, but §8.5 (the Swift render check) is now the only render check that matters, not a nice-to-have. Separately: GL13's gate is "Larry says G1(e) has started", and the roadmap line added by GC11 says G1(e)'s clock started at the GC4 commit — so the Stage 2 gate is nominally open as of today. That is Larry's call to make explicitly; Stage 1's scope does not change either way, and `macos/**` stays untouched by this plan (§0.10).

## C. Gaps in the plan itself that would have surfaced mid-implementation

**C1. Skill provenance the regex would drop.** [certain] Live `skills/*/SKILL.md` `metadata.source` values: `procedure:16`, `procedure:15`, `procedure:17`, `procedure:18+22` (technical-plan-document — promoted from **two** procedures), `authored 2026-08-18`. Step 4's `^procedure:(\d+)$` silently emits no `promoted_from` edge for the two-procedure skill. Amend: `^procedure:(\d+(?:\+\d+)*)$`, one `promoted_from` edge per id (placeholder node with `attrs.missing` for an id not in the table, as already specified). `authored …` correctly yields no edge.

**C2. The whole-graph memory picture would lose its structure to the node cap.** [certain — counted from the live store] 416 facts (71 live + 345 archived) + 83 `prefix:` + 6 `archive:` + 20 `workflow:` + 1 `turn:` = **526 nodes > `GRAPH_MAX_NODES` 400**. Step 2's `_trim_to` with no focus keeps "the first n ids in sorted order": `archive:*` then `fact:*` (alphabetical) fill the 400 before any `prefix:*`, `turn:*` or `workflow:*` is reached — exactly the nodes that carry the edges. The no-focus memory picture would be 400 facts and almost no lines. Amend `_trim_to` for the no-focus case: rank by (degree desc, id) — prefixes and archive nodes have the highest degree, so structure survives and the cut falls on leaf facts; still deterministic. Optionally raise the cap to 500 (§6); the amendment stands either way. Focused pictures (the voice tools always pass `depth=2` around a focus) are unaffected.

**C3. Routing for the two new eval cases rests on inference, and the plan names no fallback.** [likely] `config/agents.yaml` descriptions (what the Supervisor routes on — trust plan D13/D14) mention neither "council" nor "graph" for the developer, and nothing about pictures for the librarian. "draw the council graph for the last self-edit" → developer relies on rule 8's "self-development → developer"; "show me how my memories about temperature connect" → librarian is the safer of the two. §8.7 requires ≥ 90 % with these cases, and §2 makes "no Supervisor rule text change" a non-goal — so if a case fails there is no permitted fix. Amend: allow one clause in each `description` (config, not `prompts.py` — consistent with the non-goal): librarian *"…and draws a picture of how memories relate around a topic"*; developer *"…and the council rounds behind plans and self-edits, including drawing a graph of runs, tools, models and rounds on request"*; add `config/agents.yaml` to §4. No test pins description text (`test_agents_yaml_frontend_parity.py` compares names/servers, not descriptions — verify at implementation).

**C4. `image_url` is absolute and built from the bot's `JARVIS_ADMIN_URL`.** [certain, note only] Correct while MortimerHost and the sidecar share a machine (true today; Phase 5's mini would host both). If a client ever runs elsewhere, the fix is a relative path + client-side `adminURL` prefix — a Stage 2 concern, not Stage 1's.

**C5. "Never a 4xx" for images holds for graph errors but not for FastAPI's own validation.** [certain, note only] A non-integer `depth`, `w` or `h` returns 422 before the handler runs. The tools build these URLs themselves, so this is unreachable from voice; a hand-typed URL in a browser would just show FastAPI's JSON. No amendment; recorded so nobody "fixes" it later.

## D. Verified and unchanged — no action

- `jarvis/db.py`: every cited line is exact (memories 65, conversations 37, agent_runs 132, agent_events 151, procedures 175, council_rounds 254, council_scores 281, memory_recall_events 539, tier 341, archived_at/became 377–378, source_turn 457, tools_ok/failed 236–237, model 325, retry_outcome 525, source_run_ids 183) — the Phase B migrations were appended, not inserted. `council_rounds.started_at` exists (275). `council_scores.created_at` exists (needed for B1).
- Quoted text present, lines shifted ≤ 13: `jarvis/admin/server.py` (`_make_agent` 478, `_run_agent` 483, `selfedit_stage` 789, `selfedit_run` 830, `council_roster` 1675, `plan_start` 1703, `_run_plan_council` 676, models at 140/158/176); `jarvis/council/council.py` (`convene` 531 accepts `run_id`; `draft_candidates` 841; the three `run_id=None` literals at 920/936/1018; `list_rounds` 1310, `build_roster` 1374, `list_round_rosters` 1519); `jarvis/agents/upgrade_agent.py` (exact: 301/304/961/992/1064/1078/1095); `jarvis/skills/registry.py` (exact: `env_scoping_enabled` 68, `openai_tools` 285, `call` 308; `optional_env` honoured at 100/202; `BASE_ENV_KEYS` carries `JARVIS_DB_PATH` and `JARVIS_ADMIN_URL`); `mcp_selfedit` server 26/109, logic 64/152/183/383 and `DEFAULT_ADMIN_URL`/`ADMIN_URL_ENV` at 19–20.
- `_make_agent` two-argument monkeypatches: exactly the five the plan names (`test_admin_selfedit.py:102, 231, 273, 325`, `test_admin_appbuild.py:176`).
- `tests/unit/test_prompts.py:221` (`< 1200`) and `:347` (`< 1100`) exact; `DEVELOPER_CORE` is 1,098 chars exactly as stated; librarian 970 (headroom for the new sentence: ~230); analyst 1,196 (untouched, but 4 chars from its cap — do not touch it).
- `tests/evals/cases.yaml` header "= 68 total" is correct (66 inline `- {input…}` + 2 multi-line `- input:`); 68 → 70 stands.
- Dependencies: `networkx==3.6.1`, `pillow==12.3.0`, `numpy==1.26.4` in `requirements-lock.txt`; none in `requirements.txt`; all import in the sandbox venv (numpy present → `spring_layout` is the vectorised path, not pure Python). `matplotlib` unused, as the plan says.
- Live store: `council_rounds.run_id` NULL on all 35 rounds (GL9 still needed); `agent_events` 1,474 `mcp_call` / 1,476 `tool_result` / 1,476 `tool_call` (the double-count trap is real); 61 procedures, all with `source_run_ids`; 400 `agent_runs`, 117 in the last 7 days, 46 with NULL `model`; the four `became = workflow:<slug>` values with no file on disk are exactly the four the plan names; 71 live / 345 archived facts (plan said 72 — one fact moved since); `became` prefix counts identical.
- `run_admin.sh` and `run_bot.sh` `set -a`-source `.env`, so `JARVIS_GRAPHS_ENABLED=false` in `.env` reaches the sidecar under launchd and, via `optional_env`, the two child servers — §9 rollback stands.
- MortimerHost already decodes `images[]` (`AppMessage.swift:140–158`), renders with `AsyncImage` (`DisplayContentView.swift:52,55`), and already talks to `http://127.0.0.1:7861` (`JarvisConfig.swift:7,40`) — no ATS surprise for a loopback PNG.
- `selfedit_start`/`plan_start` are developer-owned MCP tools (`agents.yaml:113`), so they run inside `SubAgent.run`'s `run_logger_scope` (`base.py:471`) and `get_run_id()` is set at `SkillRegistry.call()` — GL9's injection point is real, not theoretical. No client-side argument validation exists that would reject the injected key (only `registry.py:297` touches `inputSchema`).
- `tests/unit/__init__.py` exists — importing `REAL_ROUND`/`_score_row` from `test_council_roster.py` (signature `(judge, label, profile, value, *, shadow=0, reason=None, tier="mid")`) works. `test_admin_council.py`'s `TestClient` + `JARVIS_DB_PATH` pattern (17, 28, 95) and `test_memory.py:25–32`'s temp-DB fixture are as described.
- `jarvis/` has no existing `graph*` module; nothing in `jarvis/`, `mcp_servers/` or `scripts/` imports networkx or PIL yet; `docs/reviews/graph-engineering-fit-for-mortimer.md` exists.
- `build_roster` (council.py 1374) applies D5 (a judge that also proposed never counts toward a mean) on LIVE rows only — reusing it for proposal `mean` gives the card's number, as GL7 requires.

## E. Live-store state worth knowing before §8

Migrations **0020/0021 are not yet applied** (`migrations` ends at `0019_memory_recall_events`) — gap-closure §8.4 (backup) and §8.8 (`init_db.py`) are still pending. This plan adds no migration, so there is no ordering constraint, but `memories.user_id` does not exist on the live store until Larry runs those steps.

## F. Unrelated find

`macos/JarvisKit/Tests/JarvisKitTests/admin-fixtures/council_roster.json` is untracked on `main`. It is the roster-card fixture GL13 refers to ("capture rule from the roster: curl the running sidecar"). It belongs to the macOS work and should be committed with it, not with this plan.

## G. Proposed amendments to `MORTIMER_GRAPH_LAYER_PLAN.md` (apply before step 1)

1. **Header** — replace "Branch: `feat/graph-layer` cut from `feat/t4a-security-hardening` @ `baa9838`" with "cut from `main` after gap-closure Phase B (commit `17cee9e`); line numbers in this plan remain from `baa9838` — locate quoted text (§0.11)".
2. **§0.2** — replace the 6-failure baseline with: "The baseline on `main` is 0 failures (2209 passed, 3 skipped, 2026-09-04). Any failure is yours."
3. **§4 / §5 step 9 / §7** — `TOTAL_TOOLS` 64 → 66 becomes **67 → 69**.
4. **§4 Modify** — add `config/agents.yaml` (two description clauses, C3) and `jarvis/council/agreement.py` (`supersede_score_rows`, B1); add `tests/unit/test_requires_env_snapshot.py` under "Larry's hand-edit" with the §H diff.
5. **§3 GL3** — append the tenant sentence from B2.
6. **§3 GL7 deliberation `scored`** — append: "`attrs["superseded"]` (bool) from `jarvis.council.agreement.supersede_score_rows` — the same rule `--agreement` applies (GC6b); superseded edges draw at 45 % alpha (GL10)."
7. **§3 GL10** — add "edges with `attrs.superseded == True` at 45 % alpha" beside the archived-node rule.
8. **§5 step 2 `_trim_to`** — no-focus case becomes "keep the first n ids ordered by (degree desc, id)". Optionally **§6** `GRAPH_MAX_NODES` 400 → 500.
9. **§5 step 4** — `promoted_from` regex `^procedure:(\d+(?:\+\d+)*)$`, one edge per id.
10. **§5 steps 5 and 6** — "when `since` normalises to `None`, omit the `started_at >=` bound (no lower bound), matching `parse_since`'s contract."
11. **§5 step 12** — the two Optimization-plan lines from B3 (card-adjacency Stage B at line 508; Phase 4 Stage B B1 at line 557), including the `observations` decision.
12. **§7** — add `test_graphs_deliberation.py::test_superseded_scored_edge_is_flagged` and `test_graphs_capability.py::test_promoted_from_two_procedures`; `test_graphs_model.py::test_trim_without_focus_keeps_high_degree_nodes`.
13. **§8.2–8.4** — restart via `launchctl kickstart -k gui/$(id -u)/com.mortimer.{admin,bot}` when GC7 is installed, `./scripts/mortimer.sh` otherwise.
14. **§8.7** — add: "if either new case fails, the permitted fix is the `config/agents.yaml` description clause (C3), never a Supervisor rule."
15. **§12** — the commit list gains `config/agents.yaml jarvis/council/agreement.py tests/unit/test_council_agreement.py tests/unit/test_requires_env_snapshot.py docs/reviews/GRAPH_LAYER_PLAN_REEVALUATION_2026-09-04.md`.

## H. The hand-edit that is Larry's by standing rule

`tests/unit/test_requires_env_snapshot.py`, two entries in `EXPECTED`:

```python
    "mcp-memory":    ([], ["JARVIS_GRAPHS_ENABLED", "JARVIS_GRAPH_DEPTH",
                           "JARVIS_GRAPH_MAX_NODES", "JARVIS_GRAPH_SINCE"],
                      {"JARVIS_DB_PATH": "${JARVIS_DB_PATH}"}),
    ...
    "mcp-runlog":    ([], ["JARVIS_GRAPHS_ENABLED", "JARVIS_GRAPH_DEPTH",
                           "JARVIS_GRAPH_MAX_NODES", "JARVIS_GRAPH_SINCE"], {}),
```

with a comment line above each naming `MORTIMER_GRAPH_LAYER_PLAN.md` GL12/K2 (2026-09-04) as the reason, in the same style as the mcp-notes/mcp-reminders comment already in the file.

---

**Bottom line.** The plan's architecture holds: GL1–GL8 (derived, read-only, one implementation, shared id scheme), GL9's injection route, GL10–GL12 and GL15 all check out against the current tree, and the live data still needs exactly what the plan says it needs. What drifted is arithmetic (A1, A3, C2), one frozen test the plan half-expected (A2), the post-GC7 restart command (A4), one contract mismatch the literal SQL would have hidden (A5), and three things that landed after it was written (B1–B3). Every amendment is a few lines; none changes a contract Stage 2 would consume, except the optional tenant sentence in GL3 — which is the reason to add it now.
