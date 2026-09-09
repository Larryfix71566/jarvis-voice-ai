# Mortimer graph layer — derived relationship graphs, seam repairs, and a visual viewer

**Status:** **IMPLEMENTED, 2026-09-05.** All 13 implementation steps landed; every §8 verification cleared on Larry's hardware — §8.1 suite (2186 unit / 102 integration, 0 failed), §8.2 endpoints via curl, §8.3/§8.4 librarian and developer voice checks, §8.5 MortimerHost render, §8.6 the GL9 seam (round `8d8ecfad` carries `run_id` `3040823a`, the only non-NULL of 36 rounds, E2 scope council), §8.7 routing eval 63/70 = 90% on two independent runs with an identical miss set (deterministic, gate met). One sub-check of §8.4 is **OPEN as a defect, not deferred**: the gap-closure §8.7 replay ran on 2026-09-05 and produced 20 superseded rows on `d6e0059b`, but the fade is still not visible, and the cause is in this plan's own code. `deliberation_graph.py:73` emits an edge for the kept row AND another for the dropped row of the same `(judge, proposal)` pair; `Graph.add_edge` appends without dedup (`model.py:56`), so both land at identical endpoints and `render.py:278` paints the faded one (`FADED_ALPHA` 0.45) over the normal one (`EDGE_ALPHA` 0.70). Composited that is ~0.835 — a superseded edge renders *bolder* than an unsuperseded one, the exact inverse of the intent. 20 of the 36 judge×proposal positions on that round carry both lines. Needs a decision on how supersession should read visually (one edge per pair, or parallel offset edges) before it can be closed. Rev 2, 2026-09-04 — approved direction (Rev 1 GL1–GL15 unchanged in substance), revised for implementation by a **Sonnet-class model** after the re-evaluation against `main` (`docs/reviews/GRAPH_LAYER_PLAN_REEVALUATION_2026-09-04.md`). Branch: `feat/graph-layer`, cut by Larry from `main` @ `e101758` (after gap-closure Phase B). The implementer never runs git.
**Author / origin:** Larry, 2026-09-04: *"does it not make sense to have different graphs for different graphable data?"* and *"could we include a way to view each of these to understand the edges and relationships visually."* Decided: separate graphs per domain, derived at read time from tables that already exist, no graph database, viewing only (never an editor), a server-rendered picture both clients can show today, and a native MortimerHost tab specified but gated.
**Roadmap constraints this plan is bound by:** C3 (no financial data — none touched); C6/K4 (no new agent, no new MCP server; two tools added to existing servers, neither outbound); the self-edit deny tier (`jarvis/admin/**`, `jarvis/agents/upgrade_agent.py`, `jarvis/skills/registry.py` are Tier 0 — every step here is a human PR, never a self-edit).
**Contracts this plan INTRODUCES:** G1 — the graph JSON shape (§3 GL4). G2 — `run_id` injection for named MCP tools (§3 GL9).
**Contracts this plan CONSUMES:** K2 env scoping — the two MCP servers that gain a tool declare `optional_env: [JARVIS_GRAPHS_ENABLED, JARVIS_GRAPH_DEPTH, JARVIS_GRAPH_MAX_NODES, JARVIS_GRAPH_SINCE]`; `JARVIS_ADMIN_URL` and `JARVIS_DB_PATH` are already in `BASE_ENV_KEYS` (`jarvis/skills/registry.py:49`).
**Supersedes / relates:** `MORTIMER_OPTIMIZATION_PLAN.md` Phase 4 Stage B B1 (a second memory graph) is **superseded** by GL7 *memory* — Stage B's remaining scope is B2's `search_facts` ranking, which this plan does NOT touch. `MORTIMER_OPTIMIZATION_PLAN.md` Interface Task "Stage B — card adjacency" names the same `run_id` threading GL9 does; after GL9 only its card UI remains. `docs/reviews/graph-engineering-fit-for-mortimer.md` (2026-08-18) rejected a graph *runtime* for the agent loop; nothing here contradicts it — these are read-only views over rows. Gap-closure GC6(b)'s supersession rule (`jarvis/council/agreement.py`) is reused, not re-implemented (GL7 *deliberation*).

**Rev 2 — what changed from Rev 1 and why (every item traced to the re-evaluation):**
- `TOTAL_TOOLS` 64 → 66 was stale; it is **67 → 69** (GC1 added mcp-kb's three tools).
- §0.2's "6-failure baseline" was stale; the baseline on `main` is **0 failures**.
- `tests/unit/test_requires_env_snapshot.py` freezes `optional_env` — its `EXPECTED` changes in the same commit (§5 step 9(g), Larry's hand-edit by standing rule, exact text given).
- GL7 *deliberation*: `scored` edges carry `attrs.superseded` from `agreement.supersede_score_rows` (new, factored out of `compute_agreement`) so the picture agrees with `--agreement`.
- GL3: tenant sentence added (GC8's `user_id` column exists; nothing filters by it yet).
- `_trim_to` with no focus keeps nodes by (degree desc, id) — alphabetical order cut the structural nodes first (live memory graph is 526 nodes). `GRAPH_MAX_NODES` 400 → 500.
- `promoted_from` regex accepts `procedure:18+22` (a skill promoted from two procedures exists on disk).
- `since` that normalises to `None` means no lower bound (matches `parse_since`'s contract) — the literal `>= ?` would have returned zero rows silently.
- `config/agents.yaml` gains one description clause per affected agent (GL16, new) so the two eval cases route on description text, and §8.7 has a permitted fix.
- Restart commands in §8 account for GC7's launchd supervision.
- `observations` rows are **not** part of the memory graph (decided; recorded in the Optimization-plan line, §5 step 12).
- GL4 gains a top-level `truncated_reason` (additive) so a no-focus picture keeps its reason; the deliberation summary excludes superseded edges from its judge/abstention counts so the sentence agrees with `--agreement`.
- Every new module is given as literal code; every change to an existing file is given as FIND → REPLACE. Line numbers are gone; quoted text is the anchor.
- **The literal code in §5 steps 1–7 and the `supersede_score_rows` refactor were smoke-tested on 2026-09-04** in an isolated copy of `jarvis/` against a migrated temp DB with §7's fixtures: all four graphs + federated build, every GL6 resolver path, the row/node caps, the trim rule, both renderers (byte-identical on re-render, legend counts exact, error images), and `compute_agreement` field-equal before/after the refactor. What is NOT smoke-tested: the FIND→REPLACE edits of steps 9–11 (anchors were verified to exist exactly once) and the §7 test files themselves, which the implementer writes.

---

## §0 Binding constraints for the implementing model

Read this section twice. Every rule here has been broken before, at a cost.

1. **Never run git.** Not `git status`, not `git diff`, not inside another command, not "just to check". Larry commits; you hand him the `git add` list in §12. (`sandbox-git-creates-unremovable-index-lock` — six incidents.)
2. **The test baseline is clean.** `main` @ `e101758` runs `2209 passed, 3 skipped, 0 failed`. Run `pytest tests/unit -q` before every checkpoint you report as done. **Any failure is yours.** Never add `xfail`, `skip`, or a `try/except` around an assertion to make a test pass. If an existing test fails after your change, the change is wrong or the test's fixture needs the new parameter — fix the cause, and say which in your report.
3. **One implementation of graph construction.** `jarvis/graphs/` is the only place a node or edge is derived. The sidecar endpoints, the two MCP tools, and the renderer all call `jarvis.graphs.build(...)`. Never compute an edge, a mean, or a supersession in an endpoint or a tool.
4. **Graphs are read-only views.** No step writes to `memories`, `procedures`, `agent_runs`, `agent_events`, `council_rounds`, or `council_scores` except GL9, which causes `council_rounds.run_id` to be non-NULL on NEW rounds only, through writers that already exist. No migration. No backfill.
5. **No graph database, no new process, no new port, no cache, no background job.** Rendering happens inside the admin sidecar on request.
6. **No system binaries.** Layout and rendering are pure Python (`networkx` for layout, `Pillow` for PNG, hand-written SVG). Never shell out to `dot`.
7. **Kill switch read in exactly one place:** `JARVIS_GRAPHS_ENABLED` (default on) in `jarvis/graphs/__init__.py:graphs_enabled()`. Nothing else reads that variable.
8. **Every number lives in §6.** If you need a constant not listed there, stop and add it to §6 in the same edit — never inline a magic number.
9. **Tool descriptions state which system they touch** ("Mortimer's own memory store", "Mortimer's own run log and council records") — tool selection happens off schema text.
10. **`macos/**` and `web/**` are untouched.** Stage 2 (GL13) is specified so a later human PR can build it; do not build it, do not open those directories to "check".
11. **Anchors are quoted text, not line numbers.** Every edit to an existing file in §5 is given as FIND (an exact string that occurs once) → REPLACE. Locate it with `grep -n -F`. If the FIND text is not in the file, or occurs more than once, **stop and report** — do not guess an equivalent.
12. **Literal code is transcribed, not paraphrased.** The code blocks in §5 are the implementation. Copy them exactly; the tests in §7 are written against them. Where a block says `# implementer:` a decision is delegated to you and bounded in the comment.
13. **Placeholder node, then edge.** Every builder obeys one rule: before `add_edge`, make sure both endpoints exist, creating a placeholder node (`attrs["missing"]=True`, `["pruned"]=True`, or `["unknown"]=True` as the step says) when the referenced row is gone. `Graph.add_edge` raising `KeyError` is a test failure, never a runtime path.
14. **Read constants at call time.** Every module in the package does `from jarvis.graphs import config as gcfg` and reads `gcfg.NAME` inside functions — never `from jarvis.graphs.config import NAME` (a bound copy defeats the monkeypatch the tests rely on).
15. **Stop-and-report conditions** (do not work around, do not "fix" adjacent code): a FIND anchor missing or ambiguous (rule 11); a pre-existing test failing before you touch anything; `networkx`, `PIL`, or `numpy` failing to import in the venv; `python scripts/check_skills.py` reporting a skill.yaml/server.py mismatch you did not cause; any need to change a file not in §4.

**Commands you use (and only these):**
- Unit suite: `uv run pytest tests/unit -q` (on Larry's Mac) — in a Linux sandbox venv use `<venv>/bin/python -m pytest tests/unit -q`. Never bare `pytest`.
- One file: `uv run pytest tests/unit/test_graphs_model.py -q`.
- Integration (no live keys): `uv run pytest tests/integration -q`. `tests/integration/test_mcp_servers.py::test_mcp_web_server` fails only in a sandbox without network; on Larry's Mac it passes.
- Manifest check: `uv run python scripts/check_skills.py` (needs the macOS keychain; if it fails with `NoKeyringError` in a sandbox, say so — Larry runs it).

---

## §1 What exists today (verified against `main` @ `e101758` and the live store, 2026-09-04)

**Tables that already hold graph-shaped data** (all in `jarvis/db.py`; column lists are exact):
- `memories`: `id, kind, key, content, source_session_id, created_at, updated_at, tier, archived_at, became, audience, recurrence_count, last_seen_at, provenance, source_turn`. Unique index on `key WHERE kind='fact'` (live AND archived — keys are unique across both; after migration 0020 the index becomes `(user_id, key)`). Live store: 71 live facts (identity 9 / preference 55 / project 7), 345 archived; `became` prefixes: `aged-out` 127, `consolidated` 87, `merged` 37, `workflow` 33, `auto-consolidated` 29, `deleted` 27, `reviewed` 3, `rejected` 2. Distinct key prefixes at all depths: 83. Facts with `source_turn`: 1.
- `memory_recall_events`: `id, session_id, source_turn, key, outcome, created_at`. 1 row with `source_turn`.
- `conversations`: `id, session_id, role, content, created_at`.
- `procedures`: `id, agent, label, description, status, success_count, failure_count, source_run_ids, created_at, updated_at, last_used_at, task_tokens`. `source_run_ids` is a JSON array string. 61 rows, all with run ids; `status` ∈ {`active`, `candidate`, `deprecated`}.
- `agent_runs`: `run_id, session_id, agent, display_name, task, status, started_at, ended_at, latency_ms, tool_count, error, reply_preview, payload_path, tools_ok, tools_failed, model`. 400 rows, 117 in the last 7 days, 46 with NULL `model`; `status` ∈ {`ok`, `failed`, `orphaned`, `timeout`}.
- `agent_events`: `id, run_id, seq, type, tool, server, ok, latency_ms, args_preview, result_preview, created_at`. Live: 1,474 `mcp_call`, 1,476 `tool_result`, 1,476 `tool_call` — one real call writes `tool_call` + `tool_result` in the sub-agent loop AND `mcp_call` in the registry; drawing more than one of them doubles every edge (GL7 *execution* `called`).
- `council_rounds`: `round_id, run_id, workflow, placement, trigger, tier, goal, proposer_count, judge_count, abstentions, winner_profile, winner_label, winner_mean, select_reason, retry_validated, status, started_at, ended_at, latency_ms, prompt_tokens, completion_tokens, registry_order, proposers_attempted, judges_attempted, retry_outcome`. 35 rows; `run_id` NULL on all 35; `status` ∈ {`ok`, `too_small`}.
- `council_scores`: `id, round_id, judge_profile, judge_tier, shadow, proposal_label, proposal_profile, score, abstain_reason, justification, created_at`. `score` NULL = abstained.
- Files: `skills/<name>/SKILL.md` frontmatter `metadata.source` (live values: `procedure:16`, `procedure:15`, `procedure:17`, `procedure:18+22`, `authored 2026-08-18`) and `metadata.agent`; `config/workflows/*.yaml` (16 files; 20 distinct `workflow:<slug>` values in `memories.became`, the 4 without a file: `user-style-ui-geometry`, `user-preference-model-selection`, `user-preference-model-defaults`, `project-weather-map-provider-backup-plan`); `config/agents.yaml` `sub_agents[*].name` (five: scheduler, librarian, analyst, systems, developer) and `.description` (what the Supervisor routes on).

**Read paths that exist and are reused, never re-implemented:**
- `jarvis.memory.search_facts(conn, query, limit=10) -> list[dict]` — LIKE over key+content, live + archived; dicts carry `key`.
- `jarvis.runlog.store.parse_since(value) -> str | None` — `"Nd"/"Nh"/"Nm"`/ISO → UTC ISO string; **`None` for `None`, empty, or unparseable; never raises** ("no lower bound").
- `jarvis.council.council.build_roster(round_row: dict, score_rows: list[dict]) -> dict` — `["proposers"]` is a list of `{label, profile, mean, scored_by, abstained_by, is_winner}` computed from LIVE rows with D5's judge-that-also-proposed filter. Both arguments must be plain `dict`s (it uses `.get`; `sqlite3.Row` has no `.get`).
- `jarvis.council.agreement.compute_agreement` — holds the GC6(b) supersession rule inline today; §5 step 6(a) factors it out as `supersede_score_rows`.
- `jarvis.agent_skills.discover(directory) -> list[tuple[Path, Skill | None, list[str]]]` — the `Path` is the `SKILL.md` file (folder = `path.parent.name`); `Skill` has `name, description, path, metadata: dict, has_scripts`. `enabled_names(config_path) -> list[str]`. `SKILLS_DIR`, `SKILLS_CONFIG` are module constants.
- `jarvis.workflows.load_workflows(directory) -> list[Workflow]` — `Workflow` has `name, when, steps, done_when, agents, source`. `WORKFLOWS_DIR` is a module constant.
- `jarvis.db.get_conn(db_path=None)` — `sqlite3.Row` factory (rows index by column name; `dict(row)` works). `run_migrations(conn=None)`. `JARVIS_DB_PATH` selects the file.

**Display path that exists:** `jarvis/bot/display.py` — `DISPLAY_TOOLS` (a set), `DISPLAY_SURFACE` (dict tool → `"window"`/drawer), `_FORMATTERS` (dict tool → `(args, data) -> (kind, title, body, images, links)` 5-tuple or `None`), `build_display_payload(...)` which returns `None` for `data["ok"] is False` (so a disabled tool never pops a card). Sub-agent tool results are routed through it in `jarvis/bot/pipeline.py:on_agent_event`. MortimerHost decodes `images[]` (`JarvisKit/.../AppMessage.swift` `DisplayPayload`) and renders each with `AsyncImage` (`DisplayContentView.swift`); it already talks to `http://127.0.0.1:7861` (`JarvisConfig.swift`). **No Swift change for Stage 1.** `web/` is frozen (gap-closure GC4); MortimerHost is the client that matters.

**Run correlation that exists:** `jarvis.runlog.context.get_run_id()` (ContextVar set by `SubAgent.run` via `run_logger_scope`, `jarvis/agents/base.py`), read in `SkillRegistry.call()`. `selfedit_start`/`plan_start` are developer-owned tools (`config/agents.yaml`: developer's `mcp_servers` includes `mcp-selfedit`), so they run inside a sub-agent run and `get_run_id()` is set when they are called. Tool schemas reach the model via `SkillRegistry.openai_tools()`, which copies `tool.inputSchema` verbatim. No code validates model-supplied arguments against that schema client-side.

**Self-edit start path that exists:** `mcp_servers/mcp_selfedit/server.py:selfedit_start(goal, profile, confirm, plan_path, staging_id)` → `logic.selfedit_start(client, ...)` → `POST /api/selfedit/stage` (`SelfEditStageIn`, staging record dict) → `POST /api/selfedit/run` (`GoalIn.staging_id`) → `_make_agent(service, profile)` is called twice (once synchronously to fail fast on an unknown profile, once in `_run_agent`'s thread) → `UpgradeAgent(service, profile=profile)` → `convene(...)` in `_maybe_escalate` (E1) and `_maybe_scope_council` (E2) **without `run_id`**, though `convene` accepts `run_id`. Planning: `POST /api/plan/start` (`PlanStartIn`) → thread `_run_plan_council(goal, members, context)` → `draft_candidates(goal, members=, judge=, context=)` → three `run_id=None` write sites (`_finalize_too_small` ×2, `_write_round_row` ×1).

**Dependencies:** `networkx==3.6.1`, `pillow==12.3.0`, `numpy==1.26.4` are pinned in `requirements-lock.txt` as transitive deps and import cleanly; none is in `requirements.txt`. numpy present means `spring_layout` uses its vectorised path. `matplotlib` is not used.

**Environment:** `scripts/run_admin.sh` and `run_bot.sh` `set -a`-source `.env`, so a kill switch in `.env` reaches the sidecar (under launchd too) and, via `optional_env`, the two child servers.

**Counts other files pin:** `tests/integration/test_registry.py` `TOTAL_TOOLS = 67`; `tests/evals/cases.yaml` header "= 68 total" (66 inline `- {input…}` + 2 multi-line `- input:`); `tests/unit/test_prompts.py` asserts `len(SUBAGENT_PROMPTS[name]) < 1200` for the conversational agents and `< 1100` for the developer's core-only prompt; `DEVELOPER_CORE` is 1,098 chars, librarian 970, analyst 1,196 (4 from its cap — do not touch analyst).

**The gap:** nothing walks any of these relationships. `search_facts` cannot see that `user.preference.temperature_units` and `user.style.units_display` are siblings; `became` is written and never read for display; procedure→run→model is three joins nobody runs; council rounds are unjoinable to the runs that convened them; and there is no picture of any of it.

## §2 Non-goals

- No change to `search_facts` ranking, `render_memory_context`, `_find_fact_match`, or any recall path.
- No Knowledge graph (kb docs / research notes); no World graph (people/places/dates). GL14 reserves their names and ids.
- **No `observations` rows in the memory graph** (decided Rev 2: they have their own review lifecycle in `memory_reviews`; a later plan may add a node type).
- No graph editing, no write endpoint, no graph database, no persisted cache, no background rebuild.
- No `web/src` or `macos/**` changes.
- No Supervisor rule text change in `jarvis/prompts.py`. (Two `config/agents.yaml` description clauses ARE in scope — GL16.)
- No backfill of `council_rounds.run_id` on the 35 existing rounds; they render as a disconnected component — the honest picture.
- Not a performance feature; row guards bound the worst case.

## §3 Decisions

**GL1 — Six named graphs, four built now.** `memory`, `capability`, `execution`, `deliberation` are built; `knowledge` and `world` are reserved names that return `{"ok": false, "error": "graph 'knowledge' is not built yet"}` from every surface. `federated` is the union of the four.

**GL2 — Derived at read time, per request, from SQLite and the skills/workflows directories. No cache.** Row guards (§6) bound the worst case.

**GL3 — Node id scheme is `<type>:<key>`, identical across graphs, so federation is set union.** Types: `fact:<memories.key>` · `prefix:<dotted prefix>` · `turn:<conversations.id>` · `archive:<reason>` · `run:<agent_runs.run_id>` · `session:<session_id>` · `agent:<agent name>` · `tool:<tool name>` · `model:<agent_runs.model>` · `procedure:<procedures.id>` · `skill:<skill name>` · `workflow:<workflow name>` · `round:<round_id>` · `proposal:<round_id>/<proposal_label>` · `profile:<registry profile name>` · reserved: `doc:<kb id>`, `note:<path>`, `entity:<kind>/<name>`. *Tenant (Rev 2):* the `user_id` column (gap-closure GC8) is NOT filtered on by any builder in this plan — gap-closure's binding rule. When tenant filtering arrives, builders filter by `jarvis.tenant.current_user_id()` and ids stay as they are (a graph is one tenant's); a cross-tenant graph, if ever wanted, prefixes ids with `<user_id>/`. Stage 2 must not assume `fact:<key>` is globally unique across tenants.

**GL4 — The graph JSON contract (G1):**
```json
{
  "ok": true, "graph": "memory", "focus": "fact:user.style.answer_length", "depth": 2,
  "edge_types": ["child_of", "became", "stated_in", "restated"],
  "node_count": 41, "edge_count": 58, "truncated": false, "truncated_reason": "",
  "nodes": [{"id": "fact:user.style.answer_length", "type": "fact", "label": "user.style.answer_length",
             "attrs": {"tier": "preference", "archived": false, "updated_at": "…"}}],
  "edges": [{"from": "fact:user.style.answer_length", "to": "prefix:user.style", "type": "child_of", "attrs": {}}],
  "legend": {"node_types": {"fact": "#5ec8ff"}, "edge_types": {"child_of": "solid"}}
}
```
`attrs` are flat `str → str|int|float|bool|null`; `label` ≤ `GRAPH_LABEL_MAX_CHARS`; every `from`/`to` names an id in `nodes`; `truncated` is `true` when a guard cut the graph, top-level `truncated_reason` names it (`""` otherwise), and the focus node's `attrs["truncated_reason"]` repeats it when there is a focus (Rev 2: the top-level field exists so a no-focus picture keeps its reason); `legend` is the full per-graph table (GL10). Failure: `{"ok": false, "error": "<one sentence>"}`.

**GL5 — `depth` is hop count from `focus` over undirected adjacency; `focus` is required for `execution`, optional elsewhere.** Without focus, `memory`/`capability`/`deliberation` return the whole graph (subject to guards); `execution` returns `{"ok": false, "error": "the execution graph needs a focus (a run id, tool, agent, model, or session) — it is too large to draw whole"}`.

**GL6 — Focus resolution is deterministic and per graph.** Step 1 (all graphs): if `focus` is `<type>:<rest>` with a known GL3 type → that id verbatim if in `graph.nodes`, else `None` (step 2 is NOT tried). Step 2, per graph, first hit wins, matching `graph.nodes` ids only:
- `memory`: `fact:<focus>` → `prefix:<focus>` → `search_facts(conn, focus, 1)[0]["key"]` as `fact:<key>` only if in `graph.nodes` → `None`.
- `capability`: `skill:<focus>` → `workflow:<focus>` → `procedure:<focus>` if `focus.isdigit()` → `agent:<focus>` → `None`.
- `execution`: `run:<focus>` → the unique id in `graph.nodes` starting with `run:<focus>` (0 or >1 → continue) → `tool:<focus>` → `agent:<focus>` → `model:<focus>` → `session:<focus>` → `None`.
- `deliberation`: `round:<focus>` → the unique id starting with `round:<focus>` → `profile:<focus>` → `run:<focus>` → `None`.
Signature: `resolve_<graph>_focus(conn, graph: Graph, focus: str) -> str | None`. The only miss sentence: `"no node matches '<focus>' in the <graph> graph"`.

**GL7 — Edge sets per graph (exhaustive; an edge type not listed here does not exist).**

*memory* — nodes: every `memories` row with `kind='fact'` (live AND archived; `attrs`: `tier`, `archived`, `updated_at`, `recurrence_count`, `provenance`, `content_preview`), one `prefix:` node per distinct dotted prefix at every depth, `turn:` nodes only for facts/recall events with a non-NULL `source_turn`, `archive:<reason>` and `workflow:<slug>` nodes as `became` targets need them. Edges: `child_of` (`fact:k → prefix:parent`; `prefix:a.b → prefix:a`, each once); `became` (`merged:<key>` → `fact:<key>`, or `archive:merged-missing` if that fact is gone; `workflow:<slug>` → `workflow:<slug>`; `config:*` → `archive:config`; anything else → `archive:<head>`; `attrs.archived_at`); `stated_in` (`fact → turn:<source_turn>`); `restated` (from `memory_recall_events`; `attrs.outcome`). Siblings are NOT materialised — depth 2 through the shared prefix reaches them.

*capability* — nodes: every `procedures` row (`attrs`: `agent`, `status`, `success_count`, `failure_count`, `label`), every skill folder on disk (`attrs`: `enabled`, `description` preview; an unparsable one gets `invalid: true` and no edges), every workflow file (`attrs`: `when` preview), `agent:` nodes for every name in `config/agents.yaml`, `run:` nodes ONLY for ids named in some `source_run_ids` (`attrs`: `status`, `started_at`, or `pruned: true`), `fact:` nodes ONLY for archived facts whose `became` starts with `workflow:`. Edges: `learned_by` (`procedure → agent`), `learned_from` (`procedure → run`, one per id), `promoted_from` (`skill → procedure`, one per id in `metadata.source` matching `^procedure:(\d+(?:\+\d+)*)$` — Rev 2), `for_agent` (`skill → agent:<metadata.agent>`), `extracted_from` (`workflow:<slug> → fact:<key>`). Placeholders: `procedure:<id>` `missing`, `workflow:<slug>` `missing`, `agent:<name>` `unknown`, `run:<id>` `pruned`.

*execution* — nodes: `run:` (label `run_id[:8]`; `attrs`: `agent`, `status`, `started_at`, `latency_ms`, `tools_ok`, `tools_failed`, `task_preview`), `session:`, `agent:`, `tool:`, `model:` (NULL model → no node, no edge), `procedure:` only for procedures whose `source_run_ids` name a run in the window. Edges: `in_session`, `by_agent`, `ran_on`, `called` (one edge per `agent_events` row with `type='mcp_call'` and non-NULL `tool`; for a run with ZERO `mcp_call` rows, its `tool_result` rows instead — **never both**; `attrs`: `ok` (1/0/null), `latency_ms`, `seq`, `server`, `event_type`; parallel edges allowed), `taught` (`run → procedure`).

*deliberation* — nodes: `round:` (label `round_id[:8]`; `attrs`: `workflow`, `placement`, `trigger`, `tier`, `status`, `winner_profile`, `winner_mean`, `retry_validated`, `retry_outcome`, `started_at`), `proposal:<round_id>/<label>` (`attrs`: `profile`, `mean` — the SAME number `build_roster(...)["proposers"][i]["mean"]` gives, never averaged by hand), `profile:` for every proposer or judge that appears, `run:` when `run_id` is non-NULL (`attrs` from `agent_runs`, or `pruned: true`). Edges: `proposed` (`profile → proposal`), `scored` (judge `profile → proposal`, one per `council_scores` row, shadow included; `attrs`: `score` (null = abstained), `shadow` (0/1), `judge_tier`, `abstain_reason` preview, **`superseded` (bool, Rev 2 — from `agreement.supersede_score_rows`)**), `won` (`proposal → round`, the roster's `is_winner`), `in_round` (every proposal), `for_run` (`round → run`). A round with no score rows has a round node and no proposals; a score row whose label has no proposal node is skipped.

**GL8 — Federation is union plus nothing.** `federate(graphs)` merges nodes by id (first writer's attrs win; later attrs fill missing keys) and concatenates edges de-duplicated on `(from, to, type, frozenset(attrs.items()))`.

**GL9 — Seam repair (G2): voice-initiated self-edits and plans carry the delegating run's `run_id` into `council_rounds`.** `SkillRegistry.call()` injects `run_id = get_run_id() or ""` into the arguments of `selfedit_start` and `plan_start` (always overwriting what the model passed); `openai_tools()` strips `run_id` from those two schemas so the model never sees it; the MCP server, its logic, the sidecar models (`SelfEditStageIn`, `GoalIn`, `PlanStartIn`), the staging record, `_make_agent`/`_run_agent`/`_run_plan_council`, `UpgradeAgent`/`AppBuildAgent`, and `draft_candidates` all thread it through; `""` becomes `None` at the sidecar. Console-initiated runs still write NULL (correct — no run). Not behind the graph kill switch (data-correctness fix).

**GL10 — Rendering: one layout, two encoders, fixed palette.** Literal in §5 step 7. Palette: `fact #5ec8ff` · `prefix #2f6f8f` · `turn #9aa5b1` · `archive #4a5561` · `run #7ee787` · `session #3b6b3f` · `agent #d2a8ff` · `tool #ffa657` · `model #f778ba` · `procedure #79c0ff` · `skill #a5d6ff` · `workflow #56d4dd` · `round #ffdf5d` · `proposal #e3b341` · `profile #f778ba` · reserved `doc #c9d1d9`, `note #c9d1d9`, `entity #ff7b72`. Edge styles: solid — `child_of, in_session, by_agent, ran_on, called, proposed, in_round, learned_by, for_agent`; dashed — `became, promoted_from, extracted_from, learned_from, taught, stated_in, for_run`; dotted — `scored, restated`; `won` solid 3 px `#ffb454`. `called` with `attrs.ok == 0` draws `#f85149`. Faded (45 % alpha): nodes with `archived`/`pruned`/`missing`/`invalid` true or `status` ∈ {`deprecated`, `failed`, `timeout`, `orphaned`, `too_small`}; edges with `superseded` true. Background `#15191d`, labels `#e6edf3`, edges `#8b98a5` at 70 %. Deterministic: same graph → byte-identical picture.

**GL11 — Sidecar endpoints (GET, read-only, `graphs_enabled()` checked inside `build`):** `GET /api/graph/{name}` (query `focus`, `depth`, `edge_types`, `since`) → GL4 JSON; `GET /api/graph/{name}/image.png` and `.svg` (same query + `w`, `h` clamped to `GRAPH_IMAGE_MIN_PX..GRAPH_IMAGE_MAX_PX`) → the render, and on an `ok: false` graph an HTTP **200** image whose only content is the error sentence (an `<img>`/`AsyncImage` shows nothing for a 4xx). Unknown name → `{"ok": false, "error": "unknown graph '<name>'; one of memory, capability, execution, deliberation, federated"}`. (FastAPI's own 422 for a non-integer `depth`/`w`/`h` is accepted — unreachable from the tools, which build the URLs.)

**GL12 — Two voice tools, one per owning specialist, thin over `jarvis.graphs`, display-routed.** `mcp-memory` (librarian): `memory_graph_view(focus="", depth=2, edge_types="")`. `mcp-runlog` (developer): `graph_view(graph, focus="", depth=2, since="7d")` for `execution|deliberation|capability`. Both return `{ok, graph, focus, depth, node_count, edge_count, truncated, truncated_reason, image_url, summary}` — never `nodes`/`edges`. `image_url = f"{admin_url}/api/graph/<name>/image.png?<query>"` with `admin_url = os.environ.get("JARVIS_ADMIN_URL") or "http://127.0.0.1:7861"`. Both names join `DISPLAY_TOOLS`/`DISPLAY_SURFACE` (`"window"`) with formatter `_fmt_graph_view`. Descriptions verbatim in §5 step 9.

**GL13 — Stage 2: native Graph tab (SPECIFIED, NOT BUILT).** Unchanged from Rev 1: `macos/MortimerHost/Sources/MortimerHost/Drawer/GraphTab.swift`, a `GraphViewModel` owned by `DrawerView`, fetches `GET /api/graph/{name}` on demand via `JarvisKit.AdminAPI.graph(...)` decoding GL4 into `GraphPayload`; picker for the four graphs, focus field, depth stepper 1…`GRAPH_MAX_DEPTH`, edge-type chips, a `Canvas` with client-side Fruchterman–Reingold seeded from a hash of node ids, click → re-fetch with `focus = node.id`, hover → `attrs`. Read-only. Fixture `admin-fixtures/graph_memory.json` captured from the running sidecar. Gate: Larry says G1(e) has started (gap-closure GC11 notes its clock began at the GC4 commit; the call is Larry's). `macos/**` is Tier 0 — this plan does not touch it.

**GL14 — Reserved names and ids** (`knowledge`: `doc:`, `note:`; `cites`, `derived_from`, `neighbor`. `world`: `entity:<kind>/<name>`; `mentions`, `located_at`, `attends`) live in `jarvis/graphs/__init__.py:RESERVED_GRAPHS` and the GL10 palette, nowhere else.

**GL15 — Kill switch `JARVIS_GRAPHS_ENABLED`** (default on; off when the value is one of `0`, `false`, `no`, `off` — byte-for-byte the shape of `env_scoping_enabled()`), read once in `graphs_enabled()`. Disabled: `build` returns `{"ok": false, "error": "graphs are disabled (JARVIS_GRAPHS_ENABLED=false)"}`; images render that sentence; tools return it; `DISPLAY_TOOLS` membership is unaffected (`build_display_payload` skips `ok: false`). GL9 is not behind it.

**GL16 — Routing clauses (Rev 2).** `config/agents.yaml`: the librarian's `description` gains *" Also draws a picture of how memories relate around a topic (memory_graph_view)."* and the developer's gains *" Also the council rounds behind plans and self-edits, and draws a relationship graph of runs, tools, models, and council rounds on request (graph_view)."* — appended inside the existing quoted string, before its closing quote. *Why:* the Supervisor routes on description text; "council" and "graph" appeared in neither description, so the two eval cases (§7) would have routed on inference alone. This is a config edit, not a Supervisor rule change (§2 stands). No test pins description text.

## §4 Files (complete manifest)

**Create**
- `jarvis/graphs/__init__.py`, `jarvis/graphs/config.py`, `jarvis/graphs/model.py`, `jarvis/graphs/memory_graph.py`, `jarvis/graphs/capability_graph.py`, `jarvis/graphs/execution_graph.py`, `jarvis/graphs/deliberation_graph.py`, `jarvis/graphs/render.py`.
- `tests/unit/test_graphs_model.py`, `test_graphs_memory.py`, `test_graphs_capability.py`, `test_graphs_execution.py`, `test_graphs_deliberation.py`, `test_graphs_render.py`, `test_admin_graph.py`, `test_run_id_injection.py`.
- `tests/fixtures/graphs/skills/graph-test-skill/SKILL.md`, `tests/fixtures/graphs/skills/graph-two-proc-skill/SKILL.md`, `tests/fixtures/graphs/workflows/graph-test-workflow.yaml`, `tests/fixtures/graphs/skills.yaml`, `tests/fixtures/graphs/agents.yaml`.

**Modify**
- `jarvis/council/agreement.py` — `supersede_score_rows` factored out; `compute_agreement` calls it. `tests/unit/test_council_agreement.py` — one test added.
- `jarvis/admin/server.py` — three GET endpoints; `run_id` on `SelfEditStageIn`/`GoalIn`/`PlanStartIn`, staging record, `_make_agent`/`_run_agent`/`_run_plan_council`, both `_make_agent` call sites, both thread launches.
- `jarvis/agents/upgrade_agent.py` — `run_id` kwarg on `UpgradeAgent.__init__` and `AppBuildAgent.__init__`; both `convene(...)` calls.
- `jarvis/council/council.py` — `draft_candidates(..., run_id=None)`; three write sites.
- `jarvis/skills/registry.py` — `RUN_ID_INJECTED_TOOLS`; `call()` injection; `openai_tools()` schema strip.
- `mcp_servers/mcp_selfedit/server.py`, `mcp_servers/mcp_selfedit/logic.py` — `run_id` parameter on `selfedit_start`/`plan_start`.
- `mcp_servers/mcp_memory/server.py`, `logic.py`, `skill.yaml` — `memory_graph_view`; `optional_env`.
- `mcp_servers/mcp_runlog/server.py`, `logic.py`, `skill.yaml` — `graph_view`; `optional_env`.
- `jarvis/bot/display.py` — `DISPLAY_TOOLS`, `DISPLAY_SURFACE`, `_FORMATTERS`, `_fmt_graph_view`.
- `jarvis/prompts.py` — one sentence in `SUBAGENT_PROMPTS["librarian"]`, one in `DEVELOPER_CORE`.
- `config/agents.yaml` — two description clauses (GL16).
- `requirements.txt` — `networkx`, `pillow`.
- `tests/integration/test_registry.py` — `TOTAL_TOOLS` 67 → 69.
- `tests/evals/cases.yaml` — two cases; header 68 → 70.
- `tests/unit/test_requires_env_snapshot.py` — `EXPECTED["mcp-memory"]`, `EXPECTED["mcp-runlog"]` (Larry's hand-edit, §5 step 9(g)).
- `tests/unit/test_prompts.py` — the developer core cap `< 1100` → `< 1250` with a comment.
- `tests/unit/test_mcp_memory_logic.py`, `test_mcp_runlog_logic.py`, `test_display.py`, `test_admin_selfedit.py` (four `_make_agent` lambdas + two tests), `test_admin_appbuild.py` (one lambda), `test_upgrade_agent.py`, `test_mcp_selfedit_logic.py` — additions in §7.
- `docs/REPO_MAP.md`, `CLAUDE.md`, `docs/plans/MORTIMER_OPTIMIZATION_PLAN.md` (two lines), this file (status line → "IMPLEMENTED …" is Larry's, after §8).

**Delete** — nothing.

## §5 Implementation steps, in order

Each step ends with its named tests green and `pytest tests/unit -q` at 0 failures. Do not start step N+1 with step N red. Transcribe the code blocks exactly.

### Step 1 — `jarvis/graphs/model.py`

```python
"""The graph shape every builder fills and every consumer reads (MORTIMER_GRAPH_LAYER_PLAN.md GL3/GL4/GL8).

Pure data + pure functions. Imports nothing from the rest of the package."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

Attrs = dict[str, "str | int | float | bool | None"]

#: GL3 — the `<type>` half of every node id, reserved types included.
KNOWN_TYPES = frozenset({
    "fact", "prefix", "turn", "archive", "run", "session", "agent", "tool", "model",
    "procedure", "skill", "workflow", "round", "proposal", "profile",
    "doc", "note", "entity",
})


@dataclass(frozen=True)
class Node:
    id: str          # "<type>:<key>"
    type: str
    label: str
    attrs: Attrs = field(default_factory=dict)


@dataclass(frozen=True)
class Edge:
    src: str         # node id
    dst: str         # node id
    type: str
    attrs: Attrs = field(default_factory=dict)


@dataclass
class Graph:
    name: str
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    truncated: bool = False
    truncated_reason: str = ""

    def add_node(self, node: Node) -> None:
        """First writer wins; later attrs fill only missing keys (GL8)."""
        cur = self.nodes.get(node.id)
        if cur is None:
            self.nodes[node.id] = node
        else:
            merged = {**node.attrs, **cur.attrs}
            self.nodes[node.id] = Node(cur.id, cur.type, cur.label, merged)

    def add_edge(self, edge: Edge) -> None:
        """Both endpoints must exist; a dangling edge is a bug in the builder (§0.13)."""
        if edge.src not in self.nodes or edge.dst not in self.nodes:
            raise KeyError(f"dangling edge {edge.src}->{edge.dst}")
        self.edges.append(edge)

    def adjacency(self, edge_types: set[str] | None = None) -> dict[str, set[str]]:
        adj: dict[str, set[str]] = {nid: set() for nid in self.nodes}
        for e in self.edges:
            if edge_types is not None and e.type not in edge_types:
                continue
            adj[e.src].add(e.dst)
            adj[e.dst].add(e.src)          # undirected (GL5)
        return adj

    def neighbors(self, node_id: str, depth: int = 1,
                  edge_types: set[str] | None = None) -> set[str]:
        """Ids within `depth` undirected hops of node_id, node_id included."""
        adj = self.adjacency(edge_types)
        seen, frontier = {node_id}, deque([(node_id, 0)])
        while frontier:
            nid, d = frontier.popleft()
            if d == depth:
                continue
            for nxt in sorted(adj.get(nid, ())):
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append((nxt, d + 1))
        return seen

    def subgraph(self, keep: set[str], edge_types: set[str] | None = None) -> "Graph":
        g = Graph(self.name, truncated=self.truncated, truncated_reason=self.truncated_reason)
        for nid in sorted(keep):
            if nid in self.nodes:
                g.nodes[nid] = self.nodes[nid]
        for e in self.edges:
            if e.src in g.nodes and e.dst in g.nodes and (edge_types is None or e.type in edge_types):
                g.edges.append(e)
        return g

    def to_json(self, *, focus: str | None, depth: int, edge_types: list[str], legend: dict) -> dict:
        nodes = [{"id": n.id, "type": n.type, "label": n.label, "attrs": dict(n.attrs)}
                 for n in sorted(self.nodes.values(), key=lambda n: n.id)]
        edges = [{"from": e.src, "to": e.dst, "type": e.type, "attrs": dict(e.attrs)}
                 for e in self.edges]
        if self.truncated and focus in self.nodes:
            for n in nodes:
                if n["id"] == focus:
                    n["attrs"]["truncated_reason"] = self.truncated_reason
        return {"ok": True, "graph": self.name, "focus": focus, "depth": depth,
                "edge_types": list(edge_types), "node_count": len(nodes), "edge_count": len(edges),
                "truncated": self.truncated, "truncated_reason": self.truncated_reason,
                "nodes": nodes, "edges": edges, "legend": legend}


def from_json(result: dict) -> Graph:
    """Inverse of Graph.to_json (used by the image endpoint, §5 step 10)."""
    g = Graph(str(result["graph"]), truncated=bool(result.get("truncated")),
              truncated_reason=str(result.get("truncated_reason") or ""))
    for n in result["nodes"]:
        attrs = dict(n.get("attrs") or {})
        if g.truncated and "truncated_reason" in attrs and not g.truncated_reason:
            g.truncated_reason = str(attrs["truncated_reason"])
        g.nodes[n["id"]] = Node(n["id"], n["type"], n["label"], attrs)
    for e in result["edges"]:
        g.edges.append(Edge(e["from"], e["to"], e["type"], dict(e.get("attrs") or {})))
    return g


def federate(graphs: list[Graph]) -> Graph:
    """GL8 — union plus nothing."""
    out = Graph("federated")
    seen: set[tuple] = set()
    for g in graphs:
        for n in g.nodes.values():
            out.add_node(n)
        out.truncated = out.truncated or g.truncated
        if g.truncated and not out.truncated_reason:
            out.truncated_reason = g.truncated_reason
    for g in graphs:
        for e in g.edges:
            key = (e.src, e.dst, e.type, frozenset(e.attrs.items()))
            if key in seen:
                continue
            seen.add(key)
            out.add_edge(e)
    return out


def typed_lookup(graph: Graph, focus: str) -> tuple[bool, str | None]:
    """GL6 step 1. (True, id-or-None) when focus is '<known type>:<rest>'; (False, None) otherwise."""
    head, sep, _ = focus.partition(":")
    if sep and head in KNOWN_TYPES:
        return True, (focus if focus in graph.nodes else None)
    return False, None


def unique_prefix_match(graph: Graph, prefix: str) -> str | None:
    """The one id in graph.nodes starting with `prefix`, else None (0 or >1 matches)."""
    hits = [nid for nid in graph.nodes if nid.startswith(prefix)]
    return hits[0] if len(hits) == 1 else None


def preview(text: object, max_chars: int) -> str:
    """Label/preview truncation with a trailing ellipsis (GL4 label rule)."""
    s = "" if text is None else str(text)
    return s if len(s) <= max_chars else s[: max_chars - 1] + "…"
```
Tests: `tests/unit/test_graphs_model.py` (§7).

### Step 2 — `jarvis/graphs/config.py` and `jarvis/graphs/__init__.py`

`jarvis/graphs/config.py` (imports nothing from the package):
```python
"""MORTIMER_GRAPH_LAYER_PLAN.md §6 — every tuning knob, read ONCE at import.

Other modules read these as `gcfg.NAME` at call time (never `from ... import NAME`)
so tests can monkeypatch `jarvis.graphs.config.NAME`."""
from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _str_env(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


GRAPH_DEFAULT_DEPTH = _int_env("JARVIS_GRAPH_DEPTH", 2)
GRAPH_MAX_DEPTH = 4
GRAPH_MAX_NODES = _int_env("JARVIS_GRAPH_MAX_NODES", 500)
GRAPH_MEMORY_MAX_FACTS = 5000
GRAPH_EXECUTION_MAX_RUNS = 200
GRAPH_DELIBERATION_MAX_ROUNDS = 100
GRAPH_DEFAULT_SINCE = _str_env("JARVIS_GRAPH_SINCE", "7d")
GRAPH_LABEL_MAX_CHARS = 48
GRAPH_IMAGE_W = 1400
GRAPH_IMAGE_H = 900
GRAPH_IMAGE_MIN_PX = 400
GRAPH_IMAGE_MAX_PX = 3000
GRAPH_MARGIN_PX = 60
GRAPH_LEGEND_W_PX = 170          # left column reserved for the legend block; nodes start right of it
GRAPH_NODE_RADIUS_PX = 9
GRAPH_FOCUS_RADIUS_PX = 14
GRAPH_LABEL_FONT_PX = 12
GRAPH_PARALLEL_OFFSET_PX = 6
GRAPH_LAYOUT_SEED = 42
GRAPH_LAYOUT_K = 1.6
GRAPH_LAYOUT_ITERATIONS = 120
```

`jarvis/graphs/__init__.py`:
```python
"""Derived, read-only relationship graphs over Mortimer's own stores
(MORTIMER_GRAPH_LAYER_PLAN.md). `build()` is the ONE entry point (§0.3); the
sidecar endpoints and the two MCP tools call it and nothing else computes an edge."""
from __future__ import annotations

import os
from collections import deque
from urllib.parse import urlencode

from jarvis.graphs.model import Edge, Graph, Node, federate, from_json  # noqa: F401 — re-exports

GRAPH_NAMES = ("memory", "capability", "execution", "deliberation")
RESERVED_GRAPHS = ("knowledge", "world")
ALL_NAMES = (*GRAPH_NAMES, "federated")

DISABLED_ERROR = "graphs are disabled (JARVIS_GRAPHS_ENABLED=false)"
EXECUTION_NEEDS_FOCUS = ("the execution graph needs a focus (a run id, tool, agent, model, "
                         "or session) — it is too large to draw whole")


def graphs_enabled() -> bool:
    """GL15 — the kill switch, read here and nowhere else."""
    return os.environ.get("JARVIS_GRAPHS_ENABLED", "").strip().lower() not in ("0", "false", "no", "off")


def _trim_to(graph: Graph, focus_id: str | None, n: int) -> set[str]:
    """Node cap. With a focus: BFS order from it (undirected, all edge types), first n.
    Without: (degree desc, id) so prefix/archive/session hubs survive and leaves are cut (Rev 2)."""
    adj = graph.adjacency()
    if focus_id is not None and focus_id in graph.nodes:
        seen, order, frontier = {focus_id}, [focus_id], deque([focus_id])
        while frontier and len(order) < n:
            nid = frontier.popleft()
            for nxt in sorted(adj.get(nid, ())):
                if nxt not in seen:
                    seen.add(nxt)
                    order.append(nxt)
                    frontier.append(nxt)
                    if len(order) >= n:
                        break
        return set(order[:n])
    ranked = sorted(graph.nodes, key=lambda nid: (-len(adj[nid]), nid))
    return set(ranked[:n])


def build(name: str, conn, *, focus: str = "", depth: int | None = None,
          edge_types: str = "", since: str | None = None) -> dict:
    """The ONE entry point. Returns GL4 JSON or {"ok": False, "error": ...}."""
    from jarvis.graphs import (capability_graph, config as gcfg, deliberation_graph,
                               execution_graph, memory_graph, render)
    from jarvis.runlog.store import parse_since

    if not graphs_enabled():
        return {"ok": False, "error": DISABLED_ERROR}
    if name in RESERVED_GRAPHS:
        return {"ok": False, "error": f"graph '{name}' is not built yet"}
    if name not in ALL_NAMES:
        return {"ok": False, "error": f"unknown graph '{name}'; one of memory, capability, "
                                      "execution, deliberation, federated"}
    depth = gcfg.GRAPH_DEFAULT_DEPTH if depth is None else max(1, min(gcfg.GRAPH_MAX_DEPTH, int(depth)))
    wanted = [t.strip() for t in (edge_types or "").split(",") if t.strip()] or None
    wanted_set = set(wanted) if wanted else None
    since_norm = parse_since(since or gcfg.GRAPH_DEFAULT_SINCE)      # None => no lower bound

    resolvers = {
        "memory": memory_graph.resolve_memory_focus,
        "capability": capability_graph.resolve_capability_focus,
        "execution": execution_graph.resolve_execution_focus,
        "deliberation": deliberation_graph.resolve_deliberation_focus,
    }
    builders = {
        "memory": lambda: memory_graph.build_memory_graph(conn),
        "capability": lambda: capability_graph.build_capability_graph(conn),
        "execution": lambda: execution_graph.build_execution_graph(conn, since=since_norm),
        "deliberation": lambda: deliberation_graph.build_deliberation_graph(conn, since=since_norm),
    }

    def _resolve_any(conn_, graph_, focus_):
        for n in GRAPH_NAMES:                     # first graph whose resolver answers wins
            hit = resolvers[n](conn_, graph_, focus_)
            if hit is not None:
                return hit
        return None

    if name == "federated":
        graph = federate([builders[n]() for n in GRAPH_NAMES])
        resolver = _resolve_any
    else:
        graph = builders[name]()
        resolver = resolvers[name]

    focus_id: str | None = None
    if focus.strip():
        focus_id = resolver(conn, graph, focus.strip())
        if focus_id is None:
            return {"ok": False, "error": f"no node matches '{focus.strip()}' in the {name} graph"}
    elif name == "execution":
        return {"ok": False, "error": EXECUTION_NEEDS_FOCUS}

    if focus_id is not None:
        keep = graph.neighbors(focus_id, depth, wanted_set)
        graph = graph.subgraph(keep, wanted_set)
    elif wanted_set:
        graph = graph.subgraph(set(graph.nodes), wanted_set)

    if len(graph.nodes) > gcfg.GRAPH_MAX_NODES:
        keep = _trim_to(graph, focus_id, gcfg.GRAPH_MAX_NODES)
        graph = graph.subgraph(keep, wanted_set)
        graph.truncated, graph.truncated_reason = True, f"node cap {gcfg.GRAPH_MAX_NODES}"

    return graph.to_json(focus=focus_id, depth=depth,
                         edge_types=wanted or render.all_edge_types(name),
                         legend=render.legend_for(name))


def summary_line(result: dict) -> str:
    """§5 step 8 — the spoken sentence, deterministic templates only."""
    nodes = result.get("nodes") or []
    edges = result.get("edges") or []
    depth = result.get("depth")
    focus = result.get("focus")
    label = "the whole graph"
    if focus:
        for n in nodes:
            if n["id"] == focus:
                label = n["label"]
                break
    by_type: dict[str, int] = {}
    for n in nodes:
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
    name = result.get("graph")
    if name == "memory":
        archived = sum(1 for n in nodes if n["attrs"].get("archived") is True)
        s = (f"{by_type.get('fact', 0)} memories and {by_type.get('prefix', 0)} key groups "
             f"within {depth} of {label}; {archived} of them archived.")
    elif name == "capability":
        s = (f"{by_type.get('skill', 0)} skills, {by_type.get('workflow', 0)} workflows and "
             f"{by_type.get('procedure', 0)} procedures within {depth} of {label}.")
    elif name == "execution":
        failed = sum(1 for e in edges if e["type"] == "called" and e["attrs"].get("ok") == 0)
        s = (f"{by_type.get('run', 0)} runs, {by_type.get('tool', 0)} tools and "
             f"{by_type.get('model', 0)} models within {depth} of {label}; {failed} tool calls failed.")
    elif name == "deliberation":
        live = [e for e in edges if e["type"] == "scored" and not e["attrs"].get("superseded")]
        judges = len({e["from"] for e in live})
        abst = sum(1 for e in live if e["attrs"].get("score") is None)
        s = (f"{by_type.get('round', 0)} rounds, {by_type.get('proposal', 0)} proposals and "
             f"{judges} judges within {depth} of {label}; {abst} abstentions.")
    else:
        s = f"{len(nodes)} nodes and {len(edges)} edges within {depth} of {label}."
    if result.get("truncated"):
        s += f" Truncated ({result.get('truncated_reason') or 'guard'})."
    return s


def tool_result(result: dict, *, since: str | None = None) -> dict:
    """GL12 — the dict both MCP tools return for an ok graph (never nodes/edges)."""
    admin_url = os.environ.get("JARVIS_ADMIN_URL") or "http://127.0.0.1:7861"
    query = {"focus": result.get("focus") or "", "depth": result["depth"],
             "edge_types": ",".join(result["edge_types"])}
    if since is not None:
        query["since"] = since
    return {
        "ok": True, "graph": result["graph"], "focus": result.get("focus"),
        "depth": result["depth"], "node_count": result["node_count"],
        "edge_count": result["edge_count"], "truncated": bool(result.get("truncated")),
        "truncated_reason": str(result.get("truncated_reason") or "") if result.get("truncated") else "",
        "image_url": f"{admin_url}/api/graph/{result['graph']}/image.png?{urlencode(query)}",
        "summary": summary_line(result),
    }
```
Tests: `test_graphs_model.py::test_build_rejects_reserved_and_unknown`, `::test_build_execution_without_focus_errors`, `::test_build_disabled_by_env`, `::test_trim_without_focus_keeps_high_degree_nodes` (§7). These need step 3's memory builder for a real graph — write them after step 3, run them then.

### Step 3 — `jarvis/graphs/memory_graph.py`

```python
"""GL7 *memory* — the only place memory nodes and edges are derived."""
from __future__ import annotations

import sqlite3

from jarvis.graphs import config as gcfg
from jarvis.graphs.model import Edge, Graph, Node, preview, typed_lookup


def became_target(value: str) -> tuple[str, str, str]:
    """(node_id, node_type, label) for an archived fact's `became` value."""
    head, _, tail = value.partition(":")
    if head == "merged" and tail:
        return f"fact:{tail}", "fact", tail
    if head == "workflow" and tail:
        return f"workflow:{tail}", "workflow", tail
    if head == "config":
        return "archive:config", "archive", "config"
    return f"archive:{head}", "archive", head


def _add_prefix_chain(g: Graph, key: str, seen: set[tuple[str, str]]) -> None:
    """For key a.b.c: nodes prefix:a and prefix:a.b; edge prefix:a.b -> prefix:a (once)."""
    parts = key.split(".")
    prefixes = [".".join(parts[:i]) for i in range(1, len(parts))]     # ["a", "a.b"]
    for p in prefixes:
        g.add_node(Node(f"prefix:{p}", "prefix", p, {}))
    for child, parent in zip(prefixes[1:], prefixes[:-1]):
        pair = (f"prefix:{child}", f"prefix:{parent}")
        if pair not in seen:
            seen.add(pair)
            g.add_edge(Edge(pair[0], pair[1], "child_of", {}))


def build_memory_graph(conn: sqlite3.Connection) -> Graph:
    g = Graph("memory")
    rows = conn.execute(
        "SELECT key, content, COALESCE(tier,'project') AS tier, archived_at, became, "
        "updated_at, recurrence_count, provenance, source_turn "
        "FROM memories WHERE kind='fact' AND key IS NOT NULL "
        "ORDER BY updated_at DESC, key"
    ).fetchall()
    cap = gcfg.GRAPH_MEMORY_MAX_FACTS
    if len(rows) > cap:
        rows = rows[:cap]                                  # newest by updated_at
        g.truncated, g.truncated_reason = True, "fact cap"
    facts: dict[str, sqlite3.Row] = {}
    for r in rows:
        facts.setdefault(r["key"], r)                      # keys are unique; belt-and-braces

    for key, r in facts.items():
        g.add_node(Node(f"fact:{key}", "fact", preview(key, gcfg.GRAPH_LABEL_MAX_CHARS), {
            "tier": r["tier"], "archived": r["archived_at"] is not None,
            "updated_at": r["updated_at"], "recurrence_count": r["recurrence_count"],
            "provenance": r["provenance"],
            "content_preview": preview(r["content"], gcfg.GRAPH_LABEL_MAX_CHARS),
        }))

    seen_prefix_edges: set[tuple[str, str]] = set()
    for key in facts:
        if "." not in key:
            continue
        _add_prefix_chain(g, key, seen_prefix_edges)
        g.add_edge(Edge(f"fact:{key}", f"prefix:{key.rsplit('.', 1)[0]}", "child_of", {}))

    for key, r in facts.items():
        if not r["became"]:
            continue
        target_id, target_type, label = became_target(str(r["became"]))
        if target_type == "fact" and target_id not in g.nodes:
            target_id, target_type, label = "archive:merged-missing", "archive", "merged-missing"
        if target_id not in g.nodes:
            g.add_node(Node(target_id, target_type, label, {}))
        g.add_edge(Edge(f"fact:{key}", target_id, "became", {"archived_at": r["archived_at"]}))

    recall = conn.execute(
        "SELECT key, source_turn, outcome FROM memory_recall_events WHERE source_turn IS NOT NULL"
    ).fetchall()
    recall = [r for r in recall if f"fact:{r['key']}" in g.nodes]        # unknown key -> skipped
    turn_ids = {int(r["source_turn"]) for r in facts.values() if r["source_turn"] is not None}
    turn_ids |= {int(r["source_turn"]) for r in recall}
    turn_rows: dict[int, sqlite3.Row] = {}
    if turn_ids:
        marks = ",".join("?" * len(turn_ids))
        for t in conn.execute(
            f"SELECT id, session_id, role, created_at FROM conversations WHERE id IN ({marks})",
            tuple(sorted(turn_ids)),
        ):
            turn_rows[int(t["id"])] = t
    for tid in sorted(turn_ids):
        t = turn_rows.get(tid)
        attrs = ({"session_id": t["session_id"], "created_at": t["created_at"], "role": t["role"]}
                 if t is not None else {"pruned": True})
        g.add_node(Node(f"turn:{tid}", "turn", str(tid), attrs))
    for key, r in facts.items():
        if r["source_turn"] is not None:
            g.add_edge(Edge(f"fact:{key}", f"turn:{int(r['source_turn'])}", "stated_in", {}))
    for r in recall:
        g.add_edge(Edge(f"fact:{r['key']}", f"turn:{int(r['source_turn'])}", "restated",
                        {"outcome": r["outcome"]}))
    return g


def resolve_memory_focus(conn: sqlite3.Connection, graph: Graph, focus: str) -> str | None:
    typed, hit = typed_lookup(graph, focus)
    if typed:
        return hit
    for cand in (f"fact:{focus}", f"prefix:{focus}"):
        if cand in graph.nodes:
            return cand
    from jarvis.memory import search_facts
    hits = search_facts(conn, focus, 1)
    if hits and f"fact:{hits[0]['key']}" in graph.nodes:
        return f"fact:{hits[0]['key']}"
    return None
```
Tests: `tests/unit/test_graphs_memory.py`; then the four `build` tests from step 2.

### Step 4 — `jarvis/graphs/capability_graph.py`

```python
"""GL7 *capability* — procedures, skills, workflows, agents, and the runs that taught them."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import yaml

from jarvis.graphs import config as gcfg
from jarvis.graphs.model import Edge, Graph, Node, preview, typed_lookup

_PROMOTED_RE = re.compile(r"^procedure:(\d+(?:\+\d+)*)$")      # Rev 2: "procedure:18+22"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _source_run_ids(raw: object) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return [str(x) for x in value] if isinstance(value, list) else []


def _agent_names(agents_yaml: Path) -> list[str]:
    data = yaml.safe_load(agents_yaml.read_text(encoding="utf-8")) or {}
    return [str(a["name"]) for a in (data.get("sub_agents") or []) if isinstance(a, dict) and a.get("name")]


def _ensure_agent(g: Graph, name: str) -> str:
    nid = f"agent:{name}"
    if nid not in g.nodes:
        g.add_node(Node(nid, "agent", name, {"unknown": True}))
    return nid


def _ensure_run(g: Graph, rid: str, run_rows: dict[str, sqlite3.Row]) -> str:
    nid = f"run:{rid}"
    if nid not in g.nodes:
        row = run_rows.get(rid)
        attrs = ({"status": row["status"], "started_at": row["started_at"]}
                 if row is not None else {"pruned": True})
        g.add_node(Node(nid, "run", rid[:8], attrs))
    return nid


def _ensure_procedure(g: Graph, pid: str) -> str:
    nid = f"procedure:{pid}"
    if nid not in g.nodes:
        g.add_node(Node(nid, "procedure", pid, {"missing": True}))
    return nid


def build_capability_graph(conn: sqlite3.Connection, *, skills_dir: Path | None = None,
                           skills_config: Path | None = None, workflows_dir: Path | None = None,
                           agents_yaml: Path | None = None) -> Graph:
    from jarvis.agent_skills import SKILLS_CONFIG, SKILLS_DIR, discover, enabled_names
    from jarvis.workflows import WORKFLOWS_DIR, load_workflows

    skills_dir = Path(skills_dir or SKILLS_DIR)
    skills_config = Path(skills_config or SKILLS_CONFIG)
    workflows_dir = Path(workflows_dir or WORKFLOWS_DIR)
    agents_yaml = Path(agents_yaml or (_REPO_ROOT / "config" / "agents.yaml"))
    max_chars = gcfg.GRAPH_LABEL_MAX_CHARS
    g = Graph("capability")

    for name in _agent_names(agents_yaml):
        g.add_node(Node(f"agent:{name}", "agent", name, {}))

    procs = conn.execute(
        "SELECT id, agent, label, status, success_count, failure_count, source_run_ids "
        "FROM procedures ORDER BY id"
    ).fetchall()
    for p in procs:
        g.add_node(Node(f"procedure:{p['id']}", "procedure", preview(p["label"], max_chars), {
            "agent": p["agent"], "status": p["status"], "success_count": p["success_count"],
            "failure_count": p["failure_count"], "label": preview(p["label"], max_chars),
        }))
    wanted = sorted({rid for p in procs for rid in _source_run_ids(p["source_run_ids"])})
    run_rows: dict[str, sqlite3.Row] = {}
    if wanted:
        marks = ",".join("?" * len(wanted))
        for r in conn.execute(
            f"SELECT run_id, status, started_at FROM agent_runs WHERE run_id IN ({marks})", tuple(wanted)
        ):
            run_rows[r["run_id"]] = r
    for p in procs:
        pid = f"procedure:{p['id']}"
        g.add_edge(Edge(pid, _ensure_agent(g, str(p["agent"] or "")), "learned_by", {}))
        for rid in _source_run_ids(p["source_run_ids"]):
            g.add_edge(Edge(pid, _ensure_run(g, rid, run_rows), "learned_from", {}))

    enabled = set(enabled_names(skills_config))
    for path, skill, _problems in discover(skills_dir):
        if skill is None:
            g.add_node(Node(f"skill:{path.parent.name}", "skill", path.parent.name, {"invalid": True}))
            continue
        sid = f"skill:{skill.name}"
        g.add_node(Node(sid, "skill", preview(skill.name, max_chars), {
            "enabled": skill.name in enabled, "description": preview(skill.description, max_chars),
        }))
        meta = skill.metadata if isinstance(skill.metadata, dict) else {}
        m = _PROMOTED_RE.match(str(meta.get("source", "")))
        if m:
            for proc_id in m.group(1).split("+"):
                g.add_edge(Edge(sid, _ensure_procedure(g, proc_id), "promoted_from", {}))
        agent = meta.get("agent")
        if agent:
            g.add_edge(Edge(sid, _ensure_agent(g, str(agent)), "for_agent", {}))

    for wf in load_workflows(workflows_dir):
        g.add_node(Node(f"workflow:{wf.name}", "workflow", preview(wf.name, max_chars),
                        {"when": preview(wf.when, max_chars)}))

    for r in conn.execute(
        "SELECT key, became FROM memories WHERE kind='fact' AND became LIKE 'workflow:%' ORDER BY key"
    ):
        slug = str(r["became"]).partition(":")[2]
        if not slug:
            continue
        wid = f"workflow:{slug}"
        if wid not in g.nodes:
            g.add_node(Node(wid, "workflow", preview(slug, max_chars), {"missing": True}))
        fid = f"fact:{r['key']}"
        g.add_node(Node(fid, "fact", preview(r["key"], max_chars), {"archived": True}))
        g.add_edge(Edge(wid, fid, "extracted_from", {}))
    return g


def resolve_capability_focus(conn: sqlite3.Connection, graph: Graph, focus: str) -> str | None:
    typed, hit = typed_lookup(graph, focus)
    if typed:
        return hit
    cands = [f"skill:{focus}", f"workflow:{focus}"]
    if focus.isdigit():
        cands.append(f"procedure:{focus}")
    cands.append(f"agent:{focus}")
    for c in cands:
        if c in graph.nodes:
            return c
    return None
```
Fixtures (create exactly):
- `tests/fixtures/graphs/skills/graph-test-skill/SKILL.md`:
```
---
name: graph-test-skill
description: Fixture skill promoted from procedure 1.
metadata:
  source: procedure:1
  agent: developer
---
Body.
```
- `tests/fixtures/graphs/skills/graph-two-proc-skill/SKILL.md`: same shape, `name: graph-two-proc-skill`, `source: procedure:1+99`, `agent: developer`.
- `tests/fixtures/graphs/workflows/graph-test-workflow.yaml`:
```
name: graph-test-workflow
when: a fixture workflow for the capability graph tests
steps: [do the thing]
```
- `tests/fixtures/graphs/skills.yaml`: `enabled: []`
- `tests/fixtures/graphs/agents.yaml`: `sub_agents:` with five entries `- name: scheduler` … `- name: developer` (name only).
`# implementer:` read `jarvis/agent_skills.py:parse_skill` once to confirm the frontmatter keys it requires (`name`, `description`) and adjust the fixture ONLY if it rejects this shape; report what you changed.
Tests: `tests/unit/test_graphs_capability.py`.

### Step 5 — `jarvis/graphs/execution_graph.py`

```python
"""GL7 *execution* — runs, sessions, agents, tools, models, and the procedures runs taught."""
from __future__ import annotations

import json
import sqlite3

from jarvis.graphs import config as gcfg
from jarvis.graphs.model import Edge, Graph, Node, preview, typed_lookup, unique_prefix_match


def build_execution_graph(conn: sqlite3.Connection, *, since: str | None) -> Graph:
    g = Graph("execution")
    max_chars = gcfg.GRAPH_LABEL_MAX_CHARS
    limit = gcfg.GRAPH_EXECUTION_MAX_RUNS
    sql = ("SELECT run_id, session_id, agent, task, status, started_at, latency_ms, "
           "tools_ok, tools_failed, model FROM agent_runs")
    params: list[object] = []
    if since:                                            # None => no lower bound (parse_since contract)
        sql += " WHERE started_at >= ?"
        params.append(since)
    sql += " ORDER BY started_at DESC, run_id LIMIT ?"
    params.append(limit)
    runs = conn.execute(sql, params).fetchall()
    if len(runs) >= limit:
        g.truncated, g.truncated_reason = True, "run cap"

    for r in runs:
        rid = f"run:{r['run_id']}"
        g.add_node(Node(rid, "run", str(r["run_id"])[:8], {
            "agent": r["agent"], "status": r["status"], "started_at": r["started_at"],
            "latency_ms": r["latency_ms"], "tools_ok": r["tools_ok"], "tools_failed": r["tools_failed"],
            "task_preview": preview(r["task"], max_chars),
        }))
        if r["session_id"]:
            sid = f"session:{r['session_id']}"
            g.add_node(Node(sid, "session", preview(r["session_id"], max_chars), {}))
            g.add_edge(Edge(rid, sid, "in_session", {}))
        if r["agent"]:
            aid = f"agent:{r['agent']}"
            g.add_node(Node(aid, "agent", str(r["agent"]), {}))
            g.add_edge(Edge(rid, aid, "by_agent", {}))
        if r["model"]:
            mid = f"model:{r['model']}"
            g.add_node(Node(mid, "model", preview(r["model"], max_chars), {}))
            g.add_edge(Edge(rid, mid, "ran_on", {}))

    run_ids = [str(r["run_id"]) for r in runs]
    if run_ids:
        marks = ",".join("?" * len(run_ids))
        events = conn.execute(
            f"SELECT run_id, seq, type, tool, server, ok, latency_ms FROM agent_events "
            f"WHERE run_id IN ({marks}) AND type IN ('tool_result','mcp_call') AND tool IS NOT NULL "
            f"ORDER BY run_id, seq", tuple(run_ids),
        ).fetchall()
        by_run: dict[str, dict[str, list[sqlite3.Row]]] = {}
        for e in events:
            by_run.setdefault(str(e["run_id"]), {"mcp_call": [], "tool_result": []})[e["type"]].append(e)
        for run_id in run_ids:
            groups = by_run.get(run_id)
            if not groups:
                continue
            chosen = groups["mcp_call"] or groups["tool_result"]       # never both
            for e in chosen:
                tid = f"tool:{e['tool']}"
                g.add_node(Node(tid, "tool", str(e["tool"]), {}))
                ok = e["ok"]
                g.add_edge(Edge(f"run:{run_id}", tid, "called", {
                    "ok": None if ok is None else int(ok), "latency_ms": e["latency_ms"],
                    "seq": e["seq"], "server": e["server"], "event_type": e["type"],
                }))

    window = set(run_ids)
    for p in conn.execute("SELECT id, agent, status, label, source_run_ids FROM procedures ORDER BY id"):
        try:
            ids = json.loads(p["source_run_ids"] or "[]")
        except (TypeError, ValueError):
            ids = []
        hits = [str(x) for x in ids if str(x) in window] if isinstance(ids, list) else []
        if not hits:
            continue
        pid = f"procedure:{p['id']}"
        g.add_node(Node(pid, "procedure", preview(p["label"], max_chars),
                        {"agent": p["agent"], "status": p["status"], "label": preview(p["label"], max_chars)}))
        for rid in hits:
            g.add_edge(Edge(f"run:{rid}", pid, "taught", {}))
    return g


def resolve_execution_focus(conn: sqlite3.Connection, graph: Graph, focus: str) -> str | None:
    typed, hit = typed_lookup(graph, focus)
    if typed:
        return hit
    if f"run:{focus}" in graph.nodes:
        return f"run:{focus}"
    hit = unique_prefix_match(graph, f"run:{focus}")
    if hit is not None:
        return hit
    for c in (f"tool:{focus}", f"agent:{focus}", f"model:{focus}", f"session:{focus}"):
        if c in graph.nodes:
            return c
    return None
```
Tests: `tests/unit/test_graphs_execution.py`.

### Step 6 — `supersede_score_rows` (6a) and `jarvis/graphs/deliberation_graph.py` (6b)

**6a — `jarvis/council/agreement.py`.** Add this function directly above `def compute_agreement(`:
```python
def supersede_score_rows(score_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """GC6(b) supersession, ONE implementation (shared with jarvis/graphs/deliberation_graph.py):
    among rows sharing (round_id, judge_profile, proposal_label, shadow) keep only the newest by
    created_at — a --replay writes fresh rows for a judge whose original call failed, and the
    newest supersedes the failed original by construction. Returns (kept, superseded); `kept`
    preserves first-seen order of each key in created_at order, exactly as compute_agreement did
    inline before Rev 2 of the graph plan factored it out."""
    keep: dict[tuple, dict] = {}
    for r in sorted(score_rows, key=lambda r: r.get("created_at") or ""):
        keep[(r["round_id"], r["judge_profile"], r["proposal_label"], int(r.get("shadow", 0) or 0))] = r
    kept = list(keep.values())
    kept_ids = {id(r) for r in kept}
    superseded = [r for r in score_rows if id(r) not in kept_ids]
    return kept, superseded
```
Then in `compute_agreement`, FIND (exact, 6 lines):
```
    before = len(score_rows)
    keep: dict[tuple, dict] = {}
    for r in sorted(score_rows, key=lambda r: r["created_at"] or ""):
        keep[(r["round_id"], r["judge_profile"], r["proposal_label"], int(r.get("shadow", 0) or 0))] = r
    score_rows = list(keep.values())
    superseded = before - len(score_rows)
```
REPLACE with:
```
    score_rows, _dropped = supersede_score_rows(score_rows)
    superseded = len(_dropped)
```
Run `uv run pytest tests/unit/test_council_agreement.py -q` — all pre-existing tests must pass unchanged. Add `test_supersede_score_rows_keeps_newest_and_returns_dropped` (§7).

**6b — `jarvis/graphs/deliberation_graph.py`:**
```python
"""GL7 *deliberation* — council rounds, proposals, judges, and the runs that convened them."""
from __future__ import annotations

import sqlite3

from jarvis.graphs import config as gcfg
from jarvis.graphs.model import Edge, Graph, Node, preview, typed_lookup, unique_prefix_match


def build_deliberation_graph(conn: sqlite3.Connection, *, since: str | None) -> Graph:
    from jarvis.council.agreement import supersede_score_rows
    from jarvis.council.council import build_roster

    g = Graph("deliberation")
    max_chars = gcfg.GRAPH_LABEL_MAX_CHARS
    limit = gcfg.GRAPH_DELIBERATION_MAX_ROUNDS
    sql = "SELECT * FROM council_rounds"
    params: list[object] = []
    if since:
        sql += " WHERE started_at >= ?"
        params.append(since)
    sql += " ORDER BY started_at DESC, round_id LIMIT ?"
    params.append(limit)
    rounds = [dict(r) for r in conn.execute(sql, params).fetchall()]
    if len(rounds) >= limit:
        g.truncated, g.truncated_reason = True, "round cap"

    scores_by_round: dict[str, list[dict]] = {}
    round_ids = [str(r["round_id"]) for r in rounds]
    if round_ids:
        marks = ",".join("?" * len(round_ids))
        for s in conn.execute(
            f"SELECT * FROM council_scores WHERE round_id IN ({marks}) ORDER BY id", tuple(round_ids)
        ):
            scores_by_round.setdefault(str(s["round_id"]), []).append(dict(s))

    run_rows: dict[str, sqlite3.Row] = {}
    wanted_runs = sorted({str(r["run_id"]) for r in rounds if r.get("run_id")})
    if wanted_runs:
        marks = ",".join("?" * len(wanted_runs))
        for r in conn.execute(
            f"SELECT run_id, agent, status, started_at FROM agent_runs WHERE run_id IN ({marks})",
            tuple(wanted_runs),
        ):
            run_rows[str(r["run_id"])] = r

    def _profile(name: str) -> str:
        pid = f"profile:{name}"
        g.add_node(Node(pid, "profile", preview(name, max_chars), {}))
        return pid

    for rd in rounds:
        rid = str(rd["round_id"])
        round_id = f"round:{rid}"
        g.add_node(Node(round_id, "round", rid[:8], {
            "workflow": rd.get("workflow"), "placement": rd.get("placement"), "trigger": rd.get("trigger"),
            "tier": rd.get("tier"), "status": rd.get("status"), "winner_profile": rd.get("winner_profile"),
            "winner_mean": rd.get("winner_mean"), "retry_validated": rd.get("retry_validated"),
            "retry_outcome": rd.get("retry_outcome"), "started_at": rd.get("started_at"),
        }))
        srows = scores_by_round.get(rid, [])
        roster = build_roster(rd, srows)                    # the card's numbers, D5 filter included
        for p in roster["proposers"]:
            pid = f"proposal:{rid}/{p['label']}"
            g.add_node(Node(pid, "proposal", preview(p["label"], max_chars),
                            {"profile": p["profile"], "mean": p["mean"]}))
            if p["profile"]:
                g.add_edge(Edge(_profile(p["profile"]), pid, "proposed", {}))
            g.add_edge(Edge(pid, round_id, "in_round", {}))
            if p.get("is_winner"):
                g.add_edge(Edge(pid, round_id, "won", {}))
        kept, dropped = supersede_score_rows(srows)
        for s, superseded in [(s, False) for s in kept] + [(s, True) for s in dropped]:
            pid = f"proposal:{rid}/{s.get('proposal_label') or ''}"
            if pid not in g.nodes:                          # shadow-only label: skipped, never dangling
                continue
            g.add_edge(Edge(_profile(str(s.get("judge_profile") or "")), pid, "scored", {
                "score": s.get("score"), "shadow": int(s.get("shadow") or 0),
                "judge_tier": s.get("judge_tier"),
                "abstain_reason": preview(s.get("abstain_reason"), max_chars) or None,
                "superseded": superseded,
            }))
        if rd.get("run_id"):
            run_id = str(rd["run_id"])
            nid = f"run:{run_id}"
            row = run_rows.get(run_id)
            attrs = ({"agent": row["agent"], "status": row["status"], "started_at": row["started_at"]}
                     if row is not None else {"pruned": True})
            g.add_node(Node(nid, "run", run_id[:8], attrs))
            g.add_edge(Edge(round_id, nid, "for_run", {}))
    return g


def resolve_deliberation_focus(conn: sqlite3.Connection, graph: Graph, focus: str) -> str | None:
    typed, hit = typed_lookup(graph, focus)
    if typed:
        return hit
    if f"round:{focus}" in graph.nodes:
        return f"round:{focus}"
    hit = unique_prefix_match(graph, f"round:{focus}")
    if hit is not None:
        return hit
    for c in (f"profile:{focus}", f"run:{focus}"):
        if c in graph.nodes:
            return c
    return None
```
Tests: `tests/unit/test_graphs_deliberation.py`.

### Step 7 — `jarvis/graphs/render.py`

```python
"""GL10 — one layout, two encoders, fixed palette. networkx is imported inside layout()."""
from __future__ import annotations

import math
from io import BytesIO
from xml.sax.saxutils import escape

from jarvis.graphs import config as gcfg
from jarvis.graphs.model import Edge, Graph, Node

PALETTE = {
    "fact": "#5ec8ff", "prefix": "#2f6f8f", "turn": "#9aa5b1", "archive": "#4a5561",
    "run": "#7ee787", "session": "#3b6b3f", "agent": "#d2a8ff", "tool": "#ffa657",
    "model": "#f778ba", "procedure": "#79c0ff", "skill": "#a5d6ff", "workflow": "#56d4dd",
    "round": "#ffdf5d", "proposal": "#e3b341", "profile": "#f778ba",
    "doc": "#c9d1d9", "note": "#c9d1d9", "entity": "#ff7b72",
}
EDGE_STYLES = {
    "child_of": "solid", "in_session": "solid", "by_agent": "solid", "ran_on": "solid",
    "called": "solid", "proposed": "solid", "in_round": "solid", "learned_by": "solid",
    "for_agent": "solid",
    "became": "dashed", "promoted_from": "dashed", "extracted_from": "dashed",
    "learned_from": "dashed", "taught": "dashed", "stated_in": "dashed", "for_run": "dashed",
    "scored": "dotted", "restated": "dotted",
    "won": "won",
}
GRAPH_NODE_TYPES = {
    "memory": ("fact", "prefix", "turn", "archive", "workflow"),
    "capability": ("procedure", "skill", "workflow", "agent", "run", "fact"),
    "execution": ("run", "session", "agent", "tool", "model", "procedure"),
    "deliberation": ("round", "proposal", "profile", "run"),
}
GRAPH_EDGE_TYPES = {
    "memory": ("child_of", "became", "stated_in", "restated"),
    "capability": ("learned_by", "learned_from", "promoted_from", "for_agent", "extracted_from"),
    "execution": ("in_session", "by_agent", "ran_on", "called", "taught"),
    "deliberation": ("proposed", "scored", "won", "in_round", "for_run"),
}
BG, LABEL, EDGE, FOCUS_RING, FAIL = "#15191d", "#e6edf3", "#8b98a5", "#ffb454", "#f85149"
EDGE_ALPHA, FADED_ALPHA = 0.70, 0.45
FADED_STATUSES = {"deprecated", "failed", "timeout", "orphaned", "too_small"}
DASH = {"dashed": (8, 6), "dotted": (2, 5)}


def _names(name: str) -> tuple[str, ...]:
    return tuple(GRAPH_NODE_TYPES) if name == "federated" else (name,)


def legend_for(name: str) -> dict:
    node_types: dict[str, str] = {}
    edge_types: dict[str, str] = {}
    for n in _names(name):
        for t in GRAPH_NODE_TYPES.get(n, ()):
            node_types.setdefault(t, PALETTE[t])
        for t in GRAPH_EDGE_TYPES.get(n, ()):
            edge_types.setdefault(t, EDGE_STYLES[t])
    return {"node_types": node_types, "edge_types": edge_types}


def all_edge_types(name: str) -> list[str]:
    out: list[str] = []
    for n in _names(name):
        for t in GRAPH_EDGE_TYPES.get(n, ()):
            if t not in out:
                out.append(t)
    return out


def node_faded(node: Node) -> bool:
    a = node.attrs
    return bool(a.get("archived") is True or a.get("pruned") or a.get("missing") or a.get("invalid")
                or a.get("status") in FADED_STATUSES)


def edge_faded(edge: Edge) -> bool:
    return bool(edge.attrs.get("superseded"))


def edge_color(edge: Edge) -> str:
    if edge.type == "called" and edge.attrs.get("ok") == 0:
        return FAIL
    if edge.type == "won":
        return FOCUS_RING
    return EDGE


def _unit_layout(nx, sub, comp: list[str]) -> dict[str, tuple[float, float]]:
    """One connected component laid out into the unit square [0,1]², padded so cells never touch."""
    n = len(comp)
    if n == 1:
        return {comp[0]: (0.5, 0.5)}
    raw = nx.spring_layout(sub, seed=gcfg.GRAPH_LAYOUT_SEED,
                           k=gcfg.GRAPH_LAYOUT_K / max(1.0, math.sqrt(n)),
                           iterations=gcfg.GRAPH_LAYOUT_ITERATIONS)
    xs = [float(raw[nid][0]) for nid in comp]
    ys = [float(raw[nid][1]) for nid in comp]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    out = {}
    for nid in comp:
        fx = 0.5 if maxx == minx else (float(raw[nid][0]) - minx) / (maxx - minx)
        fy = 0.5 if maxy == miny else (float(raw[nid][1]) - miny) / (maxy - miny)
        out[nid] = (0.1 + 0.8 * fx, 0.1 + 0.8 * fy)
    return out


def layout(graph: Graph, focus: str | None, width: int, height: int) -> dict[str, tuple[float, float]]:
    """Deterministic layout inside the margins (GL10). Each connected component gets its own
    spring layout in a square cell whose side is √(component size); cells are packed into rows
    (largest first) and the packed rectangle is stretched onto the canvas — a single spring
    layout over a disconnected graph collapses every component into a blob (smoke test,
    2026-09-04). Isolated nodes go on a bottom row, left to right, in id order."""
    import networkx as nx

    margin = gcfg.GRAPH_MARGIN_PX
    ids = sorted(graph.nodes)
    adj = graph.adjacency()
    isolated = [nid for nid in ids if not adj[nid]]
    pos: dict[str, tuple[float, float]] = {}
    x0, x1 = float(margin + gcfg.GRAPH_LEGEND_W_PX), float(width - margin)   # legend column reserved
    y0, y1 = float(margin), float(height - margin - (gcfg.GRAPH_LABEL_FONT_PX * 3 if isolated else 0))

    G = nx.Graph()
    G.add_nodes_from(nid for nid in ids if adj[nid])
    for e in graph.edges:
        G.add_edge(e.src, e.dst)
    comps = sorted((sorted(c) for c in nx.connected_components(G)), key=lambda c: (-len(c), c[0]))
    if comps:
        cells = [(math.sqrt(len(c)), _unit_layout(nx, G.subgraph(c), c)) for c in comps]
        row_limit = max(max(s for s, _ in cells),
                        sum(s for s, _ in cells) / math.ceil(math.sqrt(len(cells))))
        rows: list[list] = []
        cur: list = []
        cur_w = 0.0
        for side, local in cells:
            if cur and cur_w + side > row_limit:
                rows.append(cur)
                cur, cur_w = [], 0.0
            cur.append((side, local))
            cur_w += side
        if cur:
            rows.append(cur)
        packed: dict[str, tuple[float, float]] = {}
        y = 0.0
        max_w = 0.0
        for row in rows:
            h = max(s for s, _ in row)
            x = 0.0
            for side, local in row:
                for nid, (fx, fy) in local.items():
                    packed[nid] = (x + fx * side, y + (h - side) / 2 + fy * side)
                x += side
            max_w = max(max_w, x)
            y += h
        max_h = y
        for nid, (px, py) in packed.items():
            fx = 0.5 if max_w == 0 else px / max_w
            fy = 0.5 if max_h == 0 else py / max_h
            pos[nid] = (round(x0 + fx * (x1 - x0), 2), round(y0 + fy * (y1 - y0), 2))
    if isolated:
        step = (x1 - x0) / (len(isolated) - 1) if len(isolated) > 1 else 0.0
        row_y = float(height - margin)
        for i, nid in enumerate(isolated):
            pos[nid] = (round(x0 + i * step, 2), row_y)
    return pos


def _edge_segments(graph: Graph, positions: dict) -> list[tuple[float, float, float, float, Edge]]:
    """Centre-to-centre lines; the k-th parallel edge between the same pair is offset
    perpendicular by GRAPH_PARALLEL_OFFSET_PX * ceil(k/2), alternating sides."""
    counts: dict[tuple[str, str], int] = {}
    out = []
    for e in graph.edges:
        key = (min(e.src, e.dst), max(e.src, e.dst))
        k = counts.get(key, 0)
        counts[key] = k + 1
        (x1, y1), (x2, y2) = positions[e.src], positions[e.dst]
        if k:
            dx, dy = x2 - x1, y2 - y1
            length = math.hypot(dx, dy) or 1.0
            px, py = -dy / length, dx / length
            off = gcfg.GRAPH_PARALLEL_OFFSET_PX * math.ceil(k / 2) * (1 if k % 2 else -1)
            x1, y1, x2, y2 = x1 + px * off, y1 + py * off, x2 + px * off, y2 + py * off
        out.append((x1, y1, x2, y2, e))
    return out


def _legend_lines(graph_name: str) -> list[tuple[str, str, str]]:
    """(kind, key, colour_or_style) rows for the legend block, node types then edge types."""
    lg = legend_for(graph_name)
    rows = [("node", t, c) for t, c in lg["node_types"].items()]
    rows += [("edge", t, s) for t, s in lg["edge_types"].items()]
    return rows


def _rgba(hex_color: str, alpha: float) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(round(alpha * 255))


def to_svg(graph: Graph, positions: dict, width: int, height: int, focus: str | None = None) -> str:
    font = gcfg.GRAPH_LABEL_FONT_PX
    r_node, r_focus = gcfg.GRAPH_NODE_RADIUS_PX, gcfg.GRAPH_FOCUS_RADIUS_PX
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'viewBox="0 0 {width} {height}">',
             f'<rect x="0" y="0" width="{width}" height="{height}" fill="{BG}"/>']
    for x1, y1, x2, y2, e in _edge_segments(graph, positions):
        style = EDGE_STYLES.get(e.type, "solid")
        sw = 3 if style == "won" else 1.5
        alpha = FADED_ALPHA if edge_faded(e) else EDGE_ALPHA
        dash = f' stroke-dasharray="{DASH[style][0]} {DASH[style][1]}"' if style in DASH else ""
        parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                     f'stroke="{edge_color(e)}" stroke-width="{sw}" stroke-opacity="{alpha}"{dash}/>')
    for nid in sorted(graph.nodes):
        n = graph.nodes[nid]
        x, y = positions[nid]
        r = r_focus if nid == focus else r_node
        alpha = FADED_ALPHA if node_faded(n) else 1.0
        ring = f' stroke="{FOCUS_RING}" stroke-width="3"' if nid == focus else ""
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{PALETTE.get(n.type, LABEL)}" '
                     f'fill-opacity="{alpha}"{ring}/>')
    for nid in sorted(graph.nodes):
        n = graph.nodes[nid]
        x, y = positions[nid]
        r = r_focus if nid == focus else r_node
        parts.append(f'<text x="{x:.1f}" y="{y + r + font + 2:.1f}" text-anchor="middle" '
                     f'font-family="-apple-system, Helvetica, Arial, sans-serif" font-size="{font}" '
                     f'fill="{LABEL}">{escape(n.label)}</text>')
    ly = 10 + font
    for kind, key, value in _legend_lines(graph.name):
        if kind == "node":
            parts.append(f'<circle cx="16" cy="{ly - font / 3:.1f}" r="5" fill="{value}"/>')
            text = key
        else:
            dash = f' stroke-dasharray="{DASH[value][0]} {DASH[value][1]}"' if value in DASH else ""
            colour = FOCUS_RING if value == "won" else EDGE
            parts.append(f'<line x1="8" y1="{ly - font / 3:.1f}" x2="24" y2="{ly - font / 3:.1f}" '
                         f'stroke="{colour}" stroke-width="{3 if value == "won" else 1.5}"{dash}/>')
            text = f"{key} ({value})"
        parts.append(f'<text x="30" y="{ly:.1f}" font-family="-apple-system, Helvetica, Arial, sans-serif" '
                     f'font-size="{font}" fill="{LABEL}">{escape(text)}</text>')
        ly += font + 4
    parts.append("</svg>")
    return "\n".join(parts)


def _png_line(draw, x1, y1, x2, y2, fill, width, style):
    if style not in DASH:
        draw.line([(x1, y1), (x2, y2)], fill=fill, width=width)
        return
    on, off = DASH[style]
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return
    ux, uy = dx / length, dy / length
    t = 0.0
    while t < length:
        seg = min(on, length - t)
        draw.line([(x1 + ux * t, y1 + uy * t), (x1 + ux * (t + seg), y1 + uy * (t + seg))],
                  fill=fill, width=width)
        t += on + off


def to_png(graph: Graph, positions: dict, width: int, height: int, focus: str | None = None) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    font_px = gcfg.GRAPH_LABEL_FONT_PX
    r_node, r_focus = gcfg.GRAPH_NODE_RADIUS_PX, gcfg.GRAPH_FOCUS_RADIUS_PX
    img = Image.new("RGBA", (width, height), _rgba(BG, 1.0))
    draw = ImageDraw.Draw(img, "RGBA")
    font = ImageFont.load_default(size=font_px)

    def _txt(s: str) -> str:                     # risk 4: default font is Latin-1-safe
        return s.encode("latin-1", "replace").decode("latin-1")

    for x1, y1, x2, y2, e in _edge_segments(graph, positions):
        style = EDGE_STYLES.get(e.type, "solid")
        alpha = FADED_ALPHA if edge_faded(e) else EDGE_ALPHA
        _png_line(draw, x1, y1, x2, y2, _rgba(edge_color(e), alpha), 3 if style == "won" else 2, style)
    for nid in sorted(graph.nodes):
        n = graph.nodes[nid]
        x, y = positions[nid]
        r = r_focus if nid == focus else r_node
        alpha = FADED_ALPHA if node_faded(n) else 1.0
        if nid == focus:
            draw.ellipse([x - r - 3, y - r - 3, x + r + 3, y + r + 3], fill=_rgba(FOCUS_RING, 1.0))
        draw.ellipse([x - r, y - r, x + r, y + r], fill=_rgba(PALETTE.get(n.type, LABEL), alpha))
    for nid in sorted(graph.nodes):
        n = graph.nodes[nid]
        x, y = positions[nid]
        r = r_focus if nid == focus else r_node
        draw.text((x, y + r + 2), _txt(n.label), fill=_rgba(LABEL, 1.0), font=font, anchor="ma")
    ly = 10
    for kind, key, value in _legend_lines(graph.name):
        cy = ly + font_px / 2
        if kind == "node":
            draw.ellipse([11, cy - 5, 21, cy + 5], fill=_rgba(value, 1.0))
            text = key
        else:
            colour = FOCUS_RING if value == "won" else EDGE
            _png_line(draw, 8, cy, 24, cy, _rgba(colour, 1.0), 3 if value == "won" else 2, value)
            text = f"{key} ({value})"
        draw.text((30, ly), _txt(text), fill=_rgba(LABEL, 1.0), font=font)
        ly += font_px + 4
    buf = BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def error_image_svg(text: str, width: int, height: int) -> str:
    font = gcfg.GRAPH_LABEL_FONT_PX
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">'
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="{BG}"/>'
            f'<text x="{width / 2:.1f}" y="{height / 2:.1f}" text-anchor="middle" '
            f'font-family="-apple-system, Helvetica, Arial, sans-serif" font-size="{font}" '
            f'fill="{LABEL}">{escape(text)}</text></svg>')


def error_image_png(text: str, width: int, height: int) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), _rgba(BG, 1.0)[:3])
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=gcfg.GRAPH_LABEL_FONT_PX)
    draw.text((width / 2, height / 2), text.encode("latin-1", "replace").decode("latin-1"),
              fill=_rgba(LABEL, 1.0)[:3], font=font, anchor="mm")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
```
`# implementer:` if `ImageDraw.text(..., anchor=...)` raises on your Pillow, report the version; do not remove the anchor silently (12.3.0 supports it).
Tests: `tests/unit/test_graphs_render.py`.

### Step 8 — `summary_line` and `tool_result`

Already written in step 2's `__init__.py`. Tests: `test_graphs_model.py::test_summary_line_templates`.

### Step 9 — MCP tools, display, prompts, manifests, requirements

**(a) `mcp_servers/mcp_memory/logic.py`.** FIND `from jarvis.memory import search_facts` → REPLACE with:
```python
from jarvis import graphs
from jarvis.memory import search_facts
```
Append at the end of the file:
```python
def memory_graph_view(focus: str = "", depth: int = 2, edge_types: str = "") -> dict[str, Any]:
    """GL12 (MORTIMER_GRAPH_LAYER_PLAN.md) — thin over jarvis.graphs.build; the JSON
    nodes/edges are NOT returned to the model, only the picture URL and one sentence."""
    try:
        run_migrations()
        conn = get_conn()
        try:
            result = graphs.build("memory", conn, focus=focus, depth=depth, edge_types=edge_types)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — a tool returns, never raises
        return {"ok": False, "error": f"could not build the memory graph: {exc}"}
    if not result.get("ok"):
        return result
    return graphs.tool_result(result)
```
**(b) `mcp_servers/mcp_memory/server.py`.** Insert directly above `if __name__ == "__main__":`:
```python
@mcp.tool()
def memory_graph_view(focus: str = "", depth: int = 2, edge_types: str = "") -> dict:
    """Draw the relationship graph of Mortimer's own memory store around a fact, key prefix, or search term: sibling facts under the same key path, what an archived fact became, and the conversation turn that stated it. Read-only; opens the picture on the user's display. Use when the user asks what Mortimer knows around a topic, why it believes something, or what happened to a memory."""
    return logic.memory_graph_view(focus, depth, edge_types)


```
**(c) `mcp_servers/mcp_memory/skill.yaml`.** FIND `tools: [memory_review_list, memory_review_resolve, memory_search]` → REPLACE `tools: [memory_review_list, memory_review_resolve, memory_search, memory_graph_view]`. FIND `requires_env: []` → REPLACE:
```
requires_env: []
# MORTIMER_GRAPH_LAYER_PLAN.md GL12/GL15 (2026-09-04): K2 scoping forwards only
# declared names, so the graph kill switch and knobs must be listed to reach
# this child. All four have code defaults (jarvis/graphs/config.py).
optional_env: [JARVIS_GRAPHS_ENABLED, JARVIS_GRAPH_DEPTH, JARVIS_GRAPH_MAX_NODES, JARVIS_GRAPH_SINCE]
```
**(d) `mcp_servers/mcp_runlog/logic.py`.** FIND `from jarvis.council import council as council_mod` → REPLACE:
```python
from jarvis import graphs
from jarvis.council import council as council_mod
from jarvis.db import get_conn, run_migrations
```
Append at the end of the file:
```python
GRAPH_VIEW_NAMES = ("execution", "deliberation", "capability")


def graph_view(graph: str, focus: str = "", depth: int = 2, since: str = "7d") -> dict[str, Any]:
    """GL12 (MORTIMER_GRAPH_LAYER_PLAN.md) — thin over jarvis.graphs.build."""
    if graph not in GRAPH_VIEW_NAMES:
        return {"ok": False, "error": "graph must be one of execution, deliberation, capability "
                                      "(memory is the librarian's)"}
    try:
        run_migrations()
        conn = get_conn()
        try:
            result = graphs.build(graph, conn, focus=focus, depth=depth, since=since or None)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"could not build the {graph} graph: {exc}"}
    if not result.get("ok"):
        return result
    return graphs.tool_result(result, since=since or None)
```
**(e) `mcp_servers/mcp_runlog/server.py`.** Insert directly above `if __name__ == "__main__":` (same shape as (b)):
```python
@mcp.tool()
def graph_view(graph: str, focus: str = "", depth: int = 2, since: str = "7d") -> dict:
    """Draw one of Mortimer's own relationship graphs from its run log and council records: `execution` (runs, tools, models, sessions — needs a focus), `deliberation` (council rounds, proposals, judges), or `capability` (procedures, skills, workflows and the runs that taught them). Read-only; opens the picture on the user's display. Use when investigating which model or tool a run used, how a council round went, or where a rule came from."""
    return logic.graph_view(graph, focus, depth, since)


```
`# implementer:` if that server has no `if __name__ == "__main__":` line, append the tool after the last existing `@mcp.tool()` function instead and say so.
**(f) `mcp_servers/mcp_runlog/skill.yaml`.** FIND `tools: [runlog_list, runlog_detail, runlog_stats, council_list]` → REPLACE `tools: [runlog_list, runlog_detail, runlog_stats, council_list, graph_view]`; the same `optional_env` block as (c) after `requires_env: []`.
**(g) `tests/unit/test_requires_env_snapshot.py` — Larry's hand-edit by standing rule (the file is allowlist-denied; the implementer reports it is needed and may apply it only if Larry says so in this session).** FIND `    "mcp-memory":    ([], [], {"JARVIS_DB_PATH": "${JARVIS_DB_PATH}"}),` → REPLACE:
```python
    # 2026-09-04 — MORTIMER_GRAPH_LAYER_PLAN.md GL12/GL15 (K2): the graph kill
    # switch and knobs must be declared to reach the child.
    "mcp-memory":    ([], ["JARVIS_GRAPHS_ENABLED", "JARVIS_GRAPH_DEPTH",
                           "JARVIS_GRAPH_MAX_NODES", "JARVIS_GRAPH_SINCE"],
                      {"JARVIS_DB_PATH": "${JARVIS_DB_PATH}"}),
```
FIND `    "mcp-runlog":    ([], [], {}),` → REPLACE:
```python
    "mcp-runlog":    ([], ["JARVIS_GRAPHS_ENABLED", "JARVIS_GRAPH_DEPTH",
                           "JARVIS_GRAPH_MAX_NODES", "JARVIS_GRAPH_SINCE"], {}),
```
**(h) `jarvis/bot/display.py`.** FIND `    "research_report",\n}` (the last entry of `DISPLAY_TOOLS`) → REPLACE:
```python
    "research_report",
    # MORTIMER_GRAPH_LAYER_PLAN.md GL12 — the two graph tools render a PNG the
    # sidecar serves; the spoken part is the tool's one-sentence summary.
    "memory_graph_view",
    "graph_view",
}
```
FIND `    "research_report": "window",` in `DISPLAY_SURFACE` → REPLACE:
```python
    "research_report": "window",
    "memory_graph_view": "window",
    "graph_view": "window",
```
(`# implementer:` if `"research_report": "window",` is not the exact line, find the `research_report` entry in `DISPLAY_SURFACE` and add the two lines after it.) Insert above `_FORMATTERS = {`:
```python
def _fmt_graph_view(args: dict, data: dict) -> tuple | None:
    """GL12 — an image card whose only body is the summary sentence (+ a truncation line)."""
    url = data.get("image_url")
    if not isinstance(url, str) or not url:
        return None
    title = f"{str(data.get('graph') or 'graph').capitalize()} graph — {data.get('focus') or 'whole graph'}"
    body = str(data.get("summary") or "")
    if data.get("truncated"):
        body += f"\nTruncated: {data.get('truncated_reason') or 'guard'}."
    return ("image", title, body, [url], [])


```
FIND `    "research_report": _fmt_research_report,\n}` → REPLACE:
```python
    "research_report": _fmt_research_report,
    "memory_graph_view": _fmt_graph_view,
    "graph_view": _fmt_graph_view,
}
```
**(i) `jarvis/prompts.py`.** FIND (inside the librarian prompt) `Output contract: one or two short sentences with the stored fact(s) or confirmation of what was saved. On failure output exactly: FAILED: <reason>. Maximum 60 words. Plain text.""",` → REPLACE:
```
To show how memories relate (siblings under a key path, what an archived memory became), call memory_graph_view — it draws on the display; say the one-sentence summary it returns.
Output contract: one or two short sentences with the stored fact(s) or confirmation of what was saved. On failure output exactly: FAILED: <reason>. Maximum 60 words. Plain text.""",
```
FIND `Named-model tasks already ran on that model."""` (end of `DEVELOPER_CORE`) → REPLACE:
```
Named-model tasks already ran on that model.
To show how runs, tools, models, council rounds or learned rules relate, call graph_view — it draws on the display; say its summary."""
```
Then `uv run pytest tests/unit/test_prompts.py -q`: the `< 1200` librarian assertion passes (970 + ~180); the developer core assertion at `assert len(self._own("show me the git log")) < 1100` FAILS by design — FIND that line → REPLACE:
```python
        # 2026-09-04 — MORTIMER_GRAPH_LAYER_PLAN.md step 9: the graph_view
        # sentence in DEVELOPER_CORE (1,098 -> ~1,220). Next growth trims first.
        assert len(self._own("show me the git log")) < 1250
```
**(j) `config/agents.yaml` (GL16).** In the librarian's `description: "..."` FIND `rather than a short preference or fact."` (the string's last words) → REPLACE `rather than a short preference or fact. Also draws a picture of how memories relate around a topic (memory_graph_view)."`. In the developer's `description: "..."` FIND `by reading the run log that records every delegation's tool calls and results."` → REPLACE `by reading the run log that records every delegation's tool calls and results. Also the council rounds behind plans and self-edits, and draws a relationship graph of runs, tools, models, and council rounds on request (graph_view)."`.
**(k) `requirements.txt`.** Append after the `keyring` line:
```
# Graph layer (MORTIMER_GRAPH_LAYER_PLAN.md GL10, 2026-09-04): both were already
# transitive deps pinned in requirements-lock.txt; listed so a lock regeneration
# can never drop them. networkx = layout only; pillow = PNG encoder. No matplotlib.
networkx
pillow
```
**(l) `tests/integration/test_registry.py`.** FIND `TOTAL_TOOLS = 67  # ...+2 (2026-08-21: mcp-memory's memory_review_list/_resolve)` → REPLACE:
```python
TOTAL_TOOLS = 69  # ...+2 (2026-08-21: mcp-memory's memory_review_list/_resolve)
                  # ...+2 (MORTIMER_GRAPH_LAYER_PLAN.md GL12, 2026-09-04:
                  #   mcp-memory's memory_graph_view, mcp-runlog's graph_view)
```
**(m) `tests/evals/cases.yaml`.** In the header FIND `# 3 troubleshooting->developer (2026-08-20) = 68 total.` → REPLACE `# 3 troubleshooting->developer (2026-08-20), 2 graph views (MORTIMER_GRAPH_LAYER_PLAN.md, 2026-09-04) = 70 total.`. Append at the end of the file:
```
# --- graph views -> owning specialist (2) (MORTIMER_GRAPH_LAYER_PLAN.md GL12/GL16) ---
- {input: "show me how my memories about temperature connect", expect: librarian}
- {input: "draw the council graph for the last self-edit", expect: developer}
```
Tests: `test_mcp_memory_logic.py`, `test_mcp_runlog_logic.py`, `test_display.py`, `test_prompts.py` (§7); `uv run pytest tests/integration/test_registry.py -q` (starts every server; needs the venv).

### Step 10 — Sidecar endpoints (GL11), `jarvis/admin/server.py`

FIND `from fastapi import FastAPI, Request` → REPLACE `from fastapi import FastAPI, Request, Response`. Directly below the line `from jarvis.db import get_conn, now_iso, run_migrations` add:
```python
from jarvis import graphs
from jarvis.graphs import config as gcfg, render
```
`# implementer:` `from contextlib import closing` — add it beside the other `contextlib`/stdlib imports if not already imported. Insert directly above `@app.get("/api/council/roster")` (grep for that decorator; the function below it is `council_roster`):
```python
# ---- MORTIMER_GRAPH_LAYER_PLAN.md GL11 — read-only graph views. Every edge is
# derived in jarvis/graphs; these endpoints only call build() and render.
@app.get("/api/graph/{name}")
def graph_json(name: str, focus: str = "", depth: int | None = None,
               edge_types: str = "", since: str = "") -> dict:
    run_migrations()
    with closing(get_conn()) as conn:
        return graphs.build(name, conn, focus=focus, depth=depth,
                            edge_types=edge_types, since=since or None)


@app.get("/api/graph/{name}/image.{fmt}")
def graph_image(name: str, fmt: str, focus: str = "", depth: int | None = None,
                edge_types: str = "", since: str = "", w: int = 0, h: int = 0):
    if fmt not in ("png", "svg"):
        return Response(status_code=404)
    width = gcfg.GRAPH_IMAGE_W if w <= 0 else max(gcfg.GRAPH_IMAGE_MIN_PX, min(gcfg.GRAPH_IMAGE_MAX_PX, w))
    height = gcfg.GRAPH_IMAGE_H if h <= 0 else max(gcfg.GRAPH_IMAGE_MIN_PX, min(gcfg.GRAPH_IMAGE_MAX_PX, h))
    run_migrations()
    with closing(get_conn()) as conn:
        result = graphs.build(name, conn, focus=focus, depth=depth, edge_types=edge_types,
                              since=since or None)
    media = "image/png" if fmt == "png" else "image/svg+xml"
    if not result.get("ok"):
        # GL11: never a 4xx for a graph error — an <img>/AsyncImage shows nothing for one.
        body = (render.error_image_png(result["error"], width, height) if fmt == "png"
                else render.error_image_svg(result["error"], width, height))
        return Response(content=body, media_type=media)
    graph = graphs.from_json(result)
    pos = render.layout(graph, result["focus"], width, height)
    body = (render.to_png(graph, pos, width, height, focus=result["focus"]) if fmt == "png"
            else render.to_svg(graph, pos, width, height, focus=result["focus"]))
    return Response(content=body, media_type=media)


```
Tests: `tests/unit/test_admin_graph.py`.

### Step 11 — Seam repair (GL9), sub-steps in order; run each sub-step's test before the next

**(a) `jarvis/council/council.py`.** FIND
```
async def draft_candidates(
    goal: str, *, members: dict[str, list[str]] | None = None, judge: bool = True,
    context: dict | None = None,
) -> RoundResult | None:
```
→ REPLACE
```
async def draft_candidates(
    goal: str, *, members: dict[str, list[str]] | None = None, judge: bool = True,
    context: dict | None = None, run_id: str | None = None,
) -> RoundResult | None:
```
Then, inside `draft_candidates` only, replace each of the THREE occurrences of `round_id=round_id, run_id=None, workflow="planning", placement=placement,` with `round_id=round_id, run_id=run_id, workflow="planning", placement=placement,`. (`grep -n -F 'run_id=None, workflow="planning"'` must show exactly 3 lines before and 0 after.)

**(b) `jarvis/agents/upgrade_agent.py`.** In `UpgradeAgent.__init__` FIND
```
        system_prompt: str | None = None,
        council_workflow: str = "selfedit",
    ):
        self.service = service
```
→ REPLACE
```
        system_prompt: str | None = None,
        council_workflow: str = "selfedit",
        run_id: str | None = None,
    ):
        self.service = service
        # MORTIMER_GRAPH_LAYER_PLAN.md GL9 (contract G2): the delegating sub-agent
        # run, threaded from SkillRegistry.call() through the sidecar; None for a
        # console-initiated run. Every convene() below passes it through.
        self._run_id = run_id
```
FIND (E1, inside `_maybe_escalate`)
```
                workflow=self._council_workflow, placement="planner", trigger=trigger,
                goal=goal, tier=tier, context=context,
            ))
```
→ REPLACE
```
                workflow=self._council_workflow, placement="planner", trigger=trigger,
                goal=goal, tier=tier, context=context, run_id=self._run_id,
            ))
```
FIND (E2, inside `_maybe_scope_council`)
```
                workflow=self._council_workflow, placement="scope", trigger="E2",
                goal=goal, tier=1,
                context={"reason": reason, "allowlist": allowlist},
            ))
```
→ REPLACE
```
                workflow=self._council_workflow, placement="scope", trigger="E2",
                goal=goal, tier=1,
                context={"reason": reason, "allowlist": allowlist}, run_id=self._run_id,
            ))
```
In `AppBuildAgent.__init__` FIND `        client_factory: Callable[[], Any] | None = None,\n    ):\n        # Selection order mirrors` → add `run_id: str | None = None,` as a new parameter line before `    ):`, and FIND `            council_workflow="appbuild",\n        )` → REPLACE `            council_workflow="appbuild", run_id=run_id,\n        )`.

**(c) `jarvis/admin/server.py`.** In `GoalIn` FIND `    staging_id: str | None = None\n\n\nclass SelfEditStageIn(BaseModel):` → REPLACE
```
    staging_id: str | None = None
    # MORTIMER_GRAPH_LAYER_PLAN.md GL9 — the delegating run (bare-form only;
    # the staged path reads it from the staging record). "" is normalised to None.
    run_id: str | None = None


class SelfEditStageIn(BaseModel):
```
In `SelfEditStageIn` FIND `    plan_path: str | None = None\n\n\nclass ConveneIn(BaseModel):` → REPLACE
```
    plan_path: str | None = None
    run_id: str | None = None      # GL9


class ConveneIn(BaseModel):
```
In `PlanStartIn` FIND `    review_path: str = ""\n` (the class's last field) → REPLACE `    review_path: str = ""\n    run_id: str | None = None      # GL9\n`.
FIND
```
def _make_agent(service: SelfEditService, profile: str | None) -> UpgradeAgent:
    """Construct the planner (seam for tests)."""
    return UpgradeAgent(service, profile=profile)


def _run_agent(goal: str, profile: str | None, plan: str | None = None) -> None:
    """Background thread target: plan edits, then settle the job state."""
    global _run_agent_instance
    try:
        agent = _make_agent(_selfedit_service, profile)
```
→ REPLACE
```
def _make_agent(service: SelfEditService, profile: str | None,
                run_id: str | None = None) -> UpgradeAgent:
    """Construct the planner (seam for tests). run_id: GL9 (contract G2)."""
    return UpgradeAgent(service, profile=profile, run_id=run_id)


def _run_agent(goal: str, profile: str | None, plan: str | None = None,
               run_id: str | None = None) -> None:
    """Background thread target: plan edits, then settle the job state."""
    global _run_agent_instance
    try:
        agent = _make_agent(_selfedit_service, profile, run_id)
```
In `selfedit_stage` FIND `            "plan_path": plan_path,\n            "created_at": time.time(),` → REPLACE `            "plan_path": plan_path,\n            "run_id": (body.run_id or "").strip() or None,   # GL9\n            "created_at": time.time(),`.
In `selfedit_run` FIND `        plan_path = rec["plan_path"] or ""\n    else:` → REPLACE `        plan_path = rec["plan_path"] or ""\n        run_id = rec.get("run_id")\n    else:`; FIND `        profile = body.profile\n        plan_path = (body.plan_path or "").strip()` → REPLACE `        profile = body.profile\n        plan_path = (body.plan_path or "").strip()\n        run_id = (body.run_id or "").strip() or None`; FIND `            agent = _make_agent(_selfedit_service, profile)\n        except UnknownModelProfileError as exc:` → REPLACE `            agent = _make_agent(_selfedit_service, profile, run_id)\n        except UnknownModelProfileError as exc:`; FIND `        target=_run_agent, args=(goal, profile, plan), daemon=True,` → REPLACE `        target=_run_agent, args=(goal, profile, plan, run_id), daemon=True,`.
FIND
```
def _run_plan_council(
    goal: str, members: dict[str, list[str]] | None, context: dict[str, Any],
) -> None:
    try:
        result = asyncio.run(council_mod.draft_candidates(
            goal, members=members, judge=True, context=context,
        ))
```
→ REPLACE
```
def _run_plan_council(
    goal: str, members: dict[str, list[str]] | None, context: dict[str, Any],
    run_id: str | None = None,
) -> None:
    try:
        result = asyncio.run(council_mod.draft_candidates(
            goal, members=members, judge=True, context=context, run_id=run_id,
        ))
```
In `plan_start` FIND `            target=_run_plan_council, args=(goal, body.members, context), daemon=True,` → REPLACE `            target=_run_plan_council,\n            args=(goal, body.members, context, (body.run_id or "").strip() or None), daemon=True,`.
Existing tests: change every `lambda service, profile:` that monkeypatches `_make_agent` to `lambda service, profile, run_id=None:` — four in `tests/unit/test_admin_selfedit.py`, one in `tests/unit/test_admin_appbuild.py` (`grep -n -F "_make_agent\", lambda service, profile" tests/unit/` lists exactly five).

**(d) `mcp_servers/mcp_selfedit/server.py` and `logic.py`.** server: FIND
```
def selfedit_start(
    goal: str = "", profile: str = "", confirm: bool = False, plan_path: str = "",
    staging_id: str = "",
) -> dict:
```
→ REPLACE
```
def selfedit_start(
    goal: str = "", profile: str = "", confirm: bool = False, plan_path: str = "",
    staging_id: str = "", run_id: str = "",
) -> dict:
```
In its docstring FIND `    minutes; use selfedit_status to check progress.\n    """` → REPLACE `    minutes; use selfedit_status to check progress. `run_id` is filled in\n    by the system; leave it empty.\n    """`. FIND `        plan_path=plan_path, staging_id=staging_id,\n    )` → REPLACE `        plan_path=plan_path, staging_id=staging_id, run_id=run_id,\n    )`.
FIND
```
def plan_start(
    goal: str, mode: str = "single", profile: str = "", confirm: bool = False,
    review_path: str = "",
) -> dict:
```
→ REPLACE with `review_path: str = "", run_id: str = "",`; in its docstring FIND `    plan, spec, or document reviewed, critiqued, or checked by a model."""` → REPLACE `    plan, spec, or document reviewed, critiqued, or checked by a model.\n    `run_id` is filled in by the system; leave it empty."""`; FIND `        review_path or "",\n    )` → REPLACE `        review_path or "", run_id=run_id,\n    )`.
logic: FIND
```
    plan_path: str = "",
    staging_id: str = "",
) -> dict[str, Any]:
    """Two-phase start of an upgrade run (preview, then confirm).
```
→ REPLACE
```
    plan_path: str = "",
    staging_id: str = "",
    run_id: str = "",
) -> dict[str, Any]:
    """Two-phase start of an upgrade run (preview, then confirm).
```
FIND `            json={"goal": goal, "profile": chosen, "plan_path": plan_path or None},` → REPLACE `            json={"goal": goal, "profile": chosen, "plan_path": plan_path or None,\n                  "run_id": run_id or None},`. FIND `    payload: dict[str, Any] = {"goal": goal, "profile": chosen}` → REPLACE `    payload: dict[str, Any] = {"goal": goal, "profile": chosen, "run_id": run_id or None}`.
FIND
```
def plan_start(
    client, goal: str, mode: str = "single", profile: str | None = None,
    confirm: bool = False, review_path: str = "",
) -> dict[str, Any]:
```
→ REPLACE `    confirm: bool = False, review_path: str = "", run_id: str = "",`. FIND
```
        "/api/plan/start", json={
            "goal": goal, "mode": mode, "profile": profile,
            "review_path": review_path,
        },
```
→ REPLACE
```
        "/api/plan/start", json={
            "goal": goal, "mode": mode, "profile": profile,
            "review_path": review_path, "run_id": run_id or None,
        },
```

**(e) `jarvis/skills/registry.py`.** Directly below the `ENV_SCOPING_ENABLED_ENV = "JARVIS_ENV_SCOPING_ENABLED"` line add:
```python
#: MORTIMER_GRAPH_LAYER_PLAN.md GL9 (contract G2). call() overwrites `run_id` in
#: these tools' arguments with the delegating run's id (or "" outside a run) and
#: openai_tools() strips the parameter from their schemas so the model never sees
#: it. The ContextVar cannot cross the MCP child-process boundary; this is the one
#: point that both knows the run and touches every tool call.
RUN_ID_INJECTED_TOOLS: frozenset[str] = frozenset({"selfedit_start", "plan_start"})
```
In `openai_tools` FIND
```
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema
                    or {"type": "object", "properties": {}},
                },
            })
```
→ REPLACE
```
            parameters = tool.inputSchema or {"type": "object", "properties": {}}
            if tool_name in RUN_ID_INJECTED_TOOLS:
                parameters = copy.deepcopy(parameters)          # GL9: the model never sees run_id
                (parameters.get("properties") or {}).pop("run_id", None)
                if isinstance(parameters.get("required"), list):
                    parameters["required"] = [r for r in parameters["required"] if r != "run_id"]
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": parameters,
                },
            })
```
(add `import copy` to the stdlib imports at the top). In `call()` FIND
```
        session = self._sessions[server]
        # Run-logging plan D3/D18/§5.6: record one mcp_call event with the
```
→ REPLACE
```
        session = self._sessions[server]
        if tool_name in RUN_ID_INJECTED_TOOLS:
            arguments = {**arguments, "run_id": get_run_id() or ""}   # GL9: always overwrites
        # Run-logging plan D3/D18/§5.6: record one mcp_call event with the
```
Tests: `test_upgrade_agent.py::test_convene_receives_run_id`, `test_admin_selfedit.py::test_staging_carries_run_id_to_agent`, `::test_bare_run_empty_run_id_is_none`, `test_mcp_selfedit_logic.py::test_selfedit_start_forwards_run_id`, `::test_plan_start_forwards_run_id`, `test_run_id_injection.py` (§7).

### Step 12 — Docs

- `docs/REPO_MAP.md`: directly after the `jarvis/runlog/` bullet add:
```
- `jarvis/graphs/` — derived, read-only relationship graphs (memory /
  capability / execution / deliberation) + PNG/SVG renderer; served by the
  sidecar's `/api/graph/*` and two voice tools (`memory_graph_view`,
  `graph_view`). One implementation: nothing else derives an edge.
```
Keep `len(text) <= 8000` chars (`tests/unit/test_repo_map.py` pins it; the file is 7,188 chars today).
- `CLAUDE.md`: directly before `## Testing conventions` add one paragraph, ≤ 12 lines, titled `**Graph layer (MORTIMER_GRAPH_LAYER_PLAN.md, 2026-09-04)**`, stating: four derived read-only graphs in `jarvis/graphs/` (`build()` is the one entry point; endpoints and tools never compute an edge); node ids `<type>:<key>` shared across graphs so federation is set union; no cache, no graph DB, no new process; kill switch `JARVIS_GRAPHS_ENABLED` read only in `graphs_enabled()`; `execution` requires a focus; GL9 injects the delegating run's `run_id` into `selfedit_start`/`plan_start` at `SkillRegistry.call()` and strips it from the schema (not behind the kill switch); the two tools return a picture URL + one sentence, never nodes; `optional_env` on both manifests is what lets the switch reach the children (K2).
- `docs/plans/MORTIMER_OPTIMIZATION_PLAN.md`: (1) at the end of the "Stage B (not built) — card adjacency" section (after `stays a section — an honest list beats a guessed attachment.`) add: `*2026-09-04:* the run_id threading above is done by MORTIMER_GRAPH_LAYER_PLAN.md GL9 (contract G2; the sidecar model is `GoalIn`, not `SelfEditRunIn`). What remains here is the card UI only.` (2) directly after the `B1.` paragraph of "Stage B — derived graph + graph-ranked recall" add: `*2026-09-04:* B1 is superseded by MORTIMER_GRAPH_LAYER_PLAN.md GL7 *memory* (`jarvis/graphs/memory_graph.py`): `entity` nodes are `prefix:`, `has_fact` is `child_of` read the other way, `became` is identical, and `observations` rows are deliberately NOT included. B2's `neighborhood()`/`seeds_from_text()` are built over `jarvis.graphs.model.Graph`; Stage B's remaining scope is the `search_facts` ranking change only.`

### Step 13 — Full suite, report

`uv run pytest tests/unit -q` → 0 failed. `uv run pytest tests/integration -q` → 0 failed (sandbox: only `test_mcp_web_server` may fail, say so). `uv run python scripts/check_skills.py` (or report `NoKeyringError`). Report the counts, every `# implementer:` decision you took, and hand Larry §12.

## §6 Tuning knobs (all in `jarvis/graphs/config.py` unless stated)

| Constant | Default | Env override | Meaning |
|---|---|---|---|
| `GRAPH_DEFAULT_DEPTH` | 2 | `JARVIS_GRAPH_DEPTH` | hops from focus when the caller gives none |
| `GRAPH_MAX_DEPTH` | 4 | — | clamp |
| `GRAPH_MAX_NODES` | **500** (Rev 2; was 400) | `JARVIS_GRAPH_MAX_NODES` | post-focus node cap (→ `truncated`) |
| `GRAPH_MEMORY_MAX_FACTS` | 5000 | — | fact row guard |
| `GRAPH_EXECUTION_MAX_RUNS` | 200 | — | newest runs considered |
| `GRAPH_DELIBERATION_MAX_ROUNDS` | 100 | — | newest rounds considered |
| `GRAPH_DEFAULT_SINCE` | `"7d"` | `JARVIS_GRAPH_SINCE` | execution/deliberation window (`parse_since` syntax; unparseable → no bound) |
| `GRAPH_LABEL_MAX_CHARS` | 48 | — | label/preview truncation |
| `GRAPH_IMAGE_W` / `GRAPH_IMAGE_H` | 1400 / 900 | — | default render size |
| `GRAPH_IMAGE_MIN_PX` / `GRAPH_IMAGE_MAX_PX` | 400 / 3000 | — | `w`/`h` clamp |
| `GRAPH_MARGIN_PX` | 60 | — | layout inset |
| `GRAPH_LEGEND_W_PX` | 170 | — | left column reserved for the legend (Rev 2, smoke test) |
| `GRAPH_NODE_RADIUS_PX` / `GRAPH_FOCUS_RADIUS_PX` | 9 / 14 | — | node sizes |
| `GRAPH_LABEL_FONT_PX` | 12 | — | label font |
| `GRAPH_PARALLEL_OFFSET_PX` | 6 | — | parallel-edge offset unit |
| `GRAPH_LAYOUT_SEED` / `GRAPH_LAYOUT_K` / `GRAPH_LAYOUT_ITERATIONS` | 42 / 1.6 / 120 | — | spring layout |
| `RUN_ID_INJECTED_TOOLS` (`jarvis/skills/registry.py`) | `{"selfedit_start","plan_start"}` | — | GL9 |
| kill switch | on | `JARVIS_GRAPHS_ENABLED` | GL15 |

## §7 Tests — by file and function, inputs → expected

All unit tests use a migrated temp DB: `monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "g.db")); conn = get_conn(tmp_path / "g.db"); run_migrations(conn)` (the `tests/unit/test_memory.py` fixture shape), plain-SQL inserts, no rows from the live store. A helper to insert a fact: `conn.execute("INSERT INTO memories(kind, key, content, created_at, updated_at, tier, archived_at, became, source_turn) VALUES ('fact', ?, ?, ?, ?, ?, ?, ?, ?)", (...))` then `conn.commit()`. `# implementer:` read `MIGRATION_0001`'s `memories` columns once for the NOT NULL set and supply every one.

`tests/unit/test_graphs_model.py`
- `test_add_node_first_writer_wins_attrs_fill_missing`: `Node("fact:a","fact","a",{"tier":"x"})` then `Node("fact:a","fact","A",{"tier":"y","z":1})` → label stays `"a"`, attrs `{"tier":"x","z":1}`.
- `test_add_edge_rejects_dangling`: `KeyError`.
- `test_neighbors_depth_is_undirected_hops`: chain `a→b→c→d`; `neighbors("a",2) == {"a","b","c"}`; `neighbors("d",1) == {"d","c"}`.
- `test_neighbors_respects_edge_types`: `a→b` type `x`, `b→c` type `y`; `neighbors("a",2,{"x"}) == {"a","b"}`.
- `test_subgraph_keeps_only_edges_with_both_endpoints`.
- `test_to_json_from_json_roundtrip`: a non-truncated graph → `from_json(to_json(...))` has equal `nodes`, `edges`, `truncated`; a truncated graph with a focus → `from_json(...).truncated_reason == original.truncated_reason`.
- `test_federate_unions_and_dedups_edges`: the same edge in two graphs appears once; differing attrs → twice; the second graph's differing node attrs fill only missing keys.
- `test_typed_lookup_and_unique_prefix_match`: `typed_lookup(g, "fact:a") == (True, "fact:a")`; `typed_lookup(g, "fact:zz") == (True, None)`; `typed_lookup(g, "zz") == (False, None)`; `unique_prefix_match` returns the id for one match, `None` for zero or two.
- `test_build_rejects_reserved_and_unknown` (temp DB): `build("knowledge", conn)` → `ok False`, error contains `"not built yet"`; `build("bogus", conn)` → contains `"unknown graph"`.
- `test_build_execution_without_focus_errors`: error == `EXECUTION_NEEDS_FOCUS`.
- `test_build_disabled_by_env` (`monkeypatch.setenv("JARVIS_GRAPHS_ENABLED", "false")`): every name in `ALL_NAMES` → `ok False`, error names `JARVIS_GRAPHS_ENABLED`.
- `test_build_caps_nodes_and_flags_truncated`: `GRAPH_MAX_NODES` monkeypatched to 20; 30 facts `user.style.f00..f29` → `build("memory", conn, focus="prefix:user.style", depth=1)` → `node_count == 20`, `truncated True`, focus node attrs `truncated_reason == "node cap 20"`, and `"prefix:user.style"` is in the result (BFS from focus keeps it).
- `test_trim_without_focus_keeps_high_degree_nodes`: same 30 facts, `GRAPH_MAX_NODES` 5, `build("memory", conn)` → the result contains `prefix:user.style` and `prefix:user` (highest degree), `truncated True`.
- `test_summary_line_templates`: hand-built GL4 dicts for each graph name (and `federated`) produce exactly the sentences in step 2's `summary_line`; a deliberation dict with one `superseded` abstention counts it in neither judges nor abstentions; a result with `truncated: true, truncated_reason: "node cap 5"` ends with ` Truncated (node cap 5).`.
- `test_tool_result_shape_and_url`: `tool_result(result, since="7d")` has exactly the GL12 keys, no `nodes`, `image_url` starts with `http://127.0.0.1:7861/api/graph/memory/image.png?` and contains `focus=` and `since=7d`; with `JARVIS_ADMIN_URL=http://x:1` it starts with that.

`tests/unit/test_graphs_memory.py`
- `test_prefix_nodes_and_child_of_edges`: facts `user.style.a`, `user.style.b`, `user.name` → nodes `prefix:user.style`, `prefix:user`; edges `fact:user.style.a→prefix:user.style`, `prefix:user.style→prefix:user` exactly once, `fact:user.name→prefix:user`; `neighbors("fact:user.style.a", 2)` contains `fact:user.style.b`.
- `test_became_merged_points_at_surviving_fact`: archived `k1` `became="merged:k2"`, live `k2` → edge `fact:k1→fact:k2` type `became`, `attrs.archived_at` set.
- `test_became_workflow_points_at_workflow_node`: `became="workflow:research-first"` → node `workflow:research-first` type `workflow`, edge type `became`.
- `test_became_reason_points_at_archive_node`: `aged-out`, `consolidated`, `config:jarvis_units`, `something-unknown:x` → `archive:aged-out`, `archive:consolidated`, `archive:config`, `archive:something-unknown`.
- `test_became_merged_missing_target_uses_placeholder`: `merged:gone` → `archive:merged-missing`, no exception.
- `test_stated_in_and_restated_edges`: fact `source_turn=7`, conversations row id 7, recall event `(key, source_turn=7, outcome='exact_update')` → `turn:7` node with `session_id`; `stated_in` and `restated` (`attrs.outcome == "exact_update"`) edges; a recall event for an unknown key is skipped; a `source_turn=99` with no conversations row → `turn:99` with `pruned True`.
- `test_resolve_focus_order`: `"fact:user.name"` verbatim; `"fact:nope"` → `None` (typed miss does not fall through); `"user.style"` → `prefix:user.style`; `"temperature"` (fact `user.preference.temperature_units`, content "Fahrenheit") → that fact via `search_facts`; `"zzz-nothing"` → `None`.
- `test_row_guard_truncates_by_updated_at` (`GRAPH_MEMORY_MAX_FACTS` monkeypatched to 3; 5 facts with distinct `updated_at`) → the 3 newest kept, `truncated_reason == "fact cap"`.

`tests/unit/test_graphs_capability.py` (fixtures from §5 step 4; DB: procedure id 1 agent developer `source_run_ids='["r1","r2"]'`, procedure id 2 agent `ghost` `source_run_ids='not json'`; `agent_runs` row `r1` only; archived fact `k` `became="workflow:graph-test-workflow"`; archived fact `k2` `became="workflow:no-such-file"`)
- `test_procedure_edges`: `learned_by → agent:developer`; `learned_from → run:r1` (attrs `status` present) and `run:r2` (`pruned True`); `agent:ghost` exists with `unknown True`.
- `test_skill_promoted_from_and_for_agent`: `skill:graph-test-skill → procedure:1` (`promoted_from`), `→ agent:developer` (`for_agent`).
- `test_promoted_from_two_procedures`: `skill:graph-two-proc-skill` has `promoted_from` edges to `procedure:1` and `procedure:99`; `procedure:99` has `missing True`.
- `test_skill_enabled_attr_false_when_not_in_skills_yaml`; and `True` when a temp `skills.yaml` lists it.
- `test_workflow_extracted_from_fact`: `workflow:graph-test-workflow → fact:k` (`extracted_from`); `workflow:no-such-file` exists with `missing True` and an edge to `fact:k2`.
- `test_malformed_source_run_ids_is_empty`: procedure 2 has no `learned_from` edges, no exception.
- `test_resolve_focus_order`: `"graph-test-skill"` → skill; `"graph-test-workflow"` → workflow; `"1"` → `procedure:1`; `"developer"` → agent; `"zzz"` → `None`.

`tests/unit/test_graphs_execution.py` (runs `r1` (model `m`) and `r2` (model NULL), same session `s`, agent `developer`; `agent_events` for `r1`: `mcp_call` seq 1 tool `t1` ok 1, `mcp_call` seq 3 tool `t2` ok 0, `tool_result` seq 2 tool `t1`, `tool_result` seq 4 tool `t2`, `tool_call` seq 0 tool `t1`, and one row with `tool NULL`; for `r2`: `tool_result` rows only; procedure id 1 `source_run_ids='["r1"]'`)
- `test_nodes_and_structural_edges`: `in_session` for both, `by_agent` for both, `ran_on` only for `r1`; no `model:` node for `r2`.
- `test_called_edges_prefer_mcp_call_rows`: `r1` has exactly 2 `called` edges, both `event_type == "mcp_call"`; the `t2` edge has `attrs.ok == 0`.
- `test_called_edges_fall_back_to_tool_result_when_no_mcp_call`: `r2`'s `called` edges have `event_type == "tool_result"`.
- `test_taught_edge_from_procedures`: `run:r1 → procedure:1` type `taught`; no procedure node for one whose runs are outside the window.
- `test_since_filters_and_run_cap_truncates`: `since` newer than `r2`'s `started_at` excludes it; `GRAPH_EXECUTION_MAX_RUNS` monkeypatched to 1 → `truncated_reason == "run cap"`; `since=None` includes everything.
- `test_resolve_focus_order`: `"r1"` → `run:r1`; a unique 4-char prefix resolves; an ambiguous prefix falls through to `tool:`/`agent:`/`model:`/`session:`; nothing → `None`.

`tests/unit/test_graphs_deliberation.py` — import `REAL_ROUND`, `_PROPOSALS`, `_REAL_SCORES`, `_score_row`, `STARTED` from `tests.unit.test_council_roster`; insert the round with `conn.execute(f"INSERT INTO council_rounds({','.join(REAL_ROUND)}) VALUES ({','.join('?'*len(REAL_ROUND))})", tuple(REAL_ROUND.values()))` and each score dict the same way (its keys are exactly `council_scores` columns minus `id`).
- `test_proposal_mean_equals_build_roster_mean`: for every proposal node, `attrs.mean == build_roster(REAL_ROUND, rows)["proposers"][i]["mean"]` for the matching label.
- `test_scored_edges_carry_score_shadow_tier_and_abstain`: kimi-k3's rows → `attrs.score None`, `abstain_reason` preview; `shadow` 0; `superseded False`.
- `test_superseded_scored_edge_is_flagged`: add a second row for `("or-gpt-5.1", "Proposal A", shadow=1)` with `created_at=STARTED` and a third with a later `created_at` → exactly one of the two `scored` edges from `profile:or-gpt-5.1` to that proposal with `shadow == 1` has `superseded True`, and it is the older one.
- `test_won_and_in_round_edges`: exactly one `won` (Proposal A); `in_round` for all four.
- `test_for_run_edge_only_when_run_id_set`: NULL → no `for_run`; `run_id="abc"` with no `agent_runs` row → `run:abc` `pruned True` and a `for_run` edge.
- `test_round_without_scores_has_no_proposals`: a `too_small` round with no score rows → round node, zero `proposal:` nodes.
- `test_resolve_focus_order`: full `round_id`, its 8-char prefix, `"kimi-k3"` → `profile:kimi-k3`, `"zzz"` → `None`.

`tests/unit/test_council_agreement.py` — `test_supersede_score_rows_keeps_newest_and_returns_dropped`: three rows for one key with `created_at` `"1"`, `"3"`, `"2"` → `kept` is the `"3"` row, `superseded` is the other two in input order; a different `shadow` is a different key.

`tests/unit/test_graphs_render.py` (a 6-node hand-built `Graph` with two parallel `called` edges, one `ok=0`, one `won`, one `superseded`, one isolated node, one archived node)
- `test_layout_is_deterministic_and_inside_margins`: two calls return equal dicts; every x in `[margin + GRAPH_LEGEND_W_PX, w-margin]`, every y in `[margin, h-margin]`.
- `test_layout_spreads_disconnected_components`: two disjoint 3-node chains → the minimum pairwise distance between any two nodes is ≥ `2 * GRAPH_NODE_RADIUS_PX` (the smoke test's original single-spring layout collapsed them to < 1 px).
- `test_isolated_nodes_sit_on_bottom_row`: y == `h - margin`.
- `test_svg_contains_every_node_and_edge_and_legend`: `svg.count("<circle") == len(nodes) + len(legend node types)`, `svg.count("<line") == len(edges) + len(legend edge types)`; every type name in `legend_for(name)` appears.
- `test_failed_called_edge_is_red_in_svg`: `stroke="#f85149"` exactly once.
- `test_superseded_edge_is_faded_in_svg`: an edge with `stroke-opacity="0.45"` exists.
- `test_png_decodes_to_requested_size`: `PIL.Image.open(BytesIO(png)).size == (w, h)`.
- `test_error_image_has_text_and_no_nodes`: SVG contains the sentence and no `<circle`; PNG decodes.
- `test_two_renders_byte_identical`: PNG and SVG twice → identical.
- `test_legend_for_federated_is_union`: every node type of the four graphs is present once.

`tests/unit/test_admin_graph.py` (`TestClient(app)` with `JARVIS_DB_PATH` on a temp file, the `test_admin_council.py` pattern; one fact `user.style.a` inserted)
- `test_graph_json_ok_shape`: keys == `{"ok","graph","focus","depth","edge_types","node_count","edge_count","truncated","truncated_reason","nodes","edges","legend"}`.
- `test_graph_json_reserved_name`, `test_graph_json_unknown_name`.
- `test_graph_image_png_content_type_and_size` (`w=500&h=400` → decoded size `(500, 400)`), `test_graph_image_svg_content_type`.
- `test_graph_image_error_still_200_png`: `focus=zzz-nothing` → 200, `image/png`, decodable.
- `test_graph_image_bad_fmt_404`.
- `test_graph_disabled_env`: JSON `ok False`; PNG still 200.
- `test_size_query_is_clamped`: `w=10` → width `GRAPH_IMAGE_MIN_PX`; `w=99999` → `GRAPH_IMAGE_MAX_PX`.

`tests/unit/test_run_id_injection.py` — build the registry without starting servers:
```python
reg = SkillRegistry(REPO_ROOT / "config" / "mcp_servers.yaml")   # parses config only
class _Content:  text = '{"ok": true}'
class _Result:   isError = False; content = [_Content()]; structuredContent = None
class FakeSession:
    def __init__(self): self.calls = []
    async def call_tool(self, name, arguments): self.calls.append((name, dict(arguments))); return _Result()
class FakeTool:
    def __init__(self, name, schema): self.name, self.description, self.inputSchema = name, "", schema
reg._sessions = {"mcp-selfedit": FakeSession()}
reg._tools = {"selfedit_start": ("mcp-selfedit", FakeTool("selfedit_start", {"type": "object",
              "properties": {"goal": {"type": "string"}, "run_id": {"type": "string"}}, "required": ["goal", "run_id"]})),
              "plan_status": ("mcp-selfedit", FakeTool("plan_status", {"type": "object", "properties": {"run_id": {"type": "string"}}}))}
```
- `test_call_overwrites_model_supplied_run_id`: inside `with run_logger_scope(RunLogger("abc", "developer", "Developer", "t", enabled=False)):` call `await reg.call("selfedit_start", {"goal": "g", "run_id": "evil"})` → the session saw `run_id == "abc"`.
- `test_call_outside_run_sends_empty_string`: no scope → `run_id == ""`.
- `test_tool_not_in_set_untouched`: `plan_status` with `{"run_id": "keep"}` → `"keep"`.
- `test_openai_tools_strips_run_id_property_and_required`: the `selfedit_start` schema has no `run_id` property and `required == ["goal"]`; `plan_status` still has its `run_id` property; `reg._tools[...]` schema objects are unchanged (deep copy).

Additions to existing files: `test_mcp_memory_logic.py::test_memory_graph_view_returns_url_and_summary_not_nodes` (temp DB with one fact; `"nodes" not in result`, `image_url` starts with the admin URL and contains `focus=`), `::test_memory_graph_view_error_passthrough` (`focus="zzz"` → `ok False`, error contains `"no node matches"`); `test_mcp_runlog_logic.py::test_graph_view_rejects_memory_name`, `::test_graph_view_execution_needs_focus`; `test_display.py::test_graph_view_payload_is_image_window` (`kind == "image"`, `surface == "window"`, `images == [url]`, title `"Memory graph — fact:user.style.a"`), `::test_graph_view_truncated_line`, `::test_graph_view_ok_false_returns_none`; `test_upgrade_agent.py::test_convene_receives_run_id` (monkeypatch `jarvis.council.council.convene` with an async fake recording kwargs; `UpgradeAgent(..., run_id="r9")._maybe_escalate(goal="g", trigger="E1")` → kwargs `run_id == "r9"`; `# implementer:` read `_maybe_escalate`'s full signature first and pass every required kwarg); `test_admin_selfedit.py::test_staging_carries_run_id_to_agent` (stage with `run_id="r9"`, run with the `staging_id`, a `_make_agent` spy `lambda service, profile, run_id=None:` records `"r9"`) and `::test_bare_run_empty_run_id_is_none` (bare `run_id=""` → spy sees `None`); `test_mcp_selfedit_logic.py::test_selfedit_start_forwards_run_id` (`FakeClient.posts` shows `"run_id": "r9"` on `/api/selfedit/stage`) and `::test_plan_start_forwards_run_id` (on `/api/plan/start`); `test_registry.py`: `TOTAL_TOOLS == 69` (integration).

## §8 Verification Larry runs on his hardware

Restart command: `launchctl kickstart -k gui/$(id -u)/com.mortimer.admin` and `… com.mortimer.bot` when gap-closure GC7's launchd supervision is installed; `./scripts/mortimer.sh` otherwise (it exits 3 once launchd owns the processes).

1. `uv run pytest tests/unit -q` → 0 failed; `uv run pytest tests/integration -q` → 0 failed (`TOTAL_TOOLS` 69 green); `uv run python scripts/check_skills.py` clean.
2. Restart. In a browser: `http://127.0.0.1:7861/api/graph/memory?focus=user.style&depth=1` → JSON, `node_count` ≈ 37 (36 `user.style.*` facts + the prefix; varies with the store). `…/api/graph/memory/image.png?focus=user.style&depth=1` → a picture with the legend top-left; `…/image.svg` the same. `…/api/graph/execution/image.png` (no focus) → an image containing the "needs a focus" sentence, HTTP 200. `…/api/graph/memory/image.png` (no focus) → a picture with visible structure (the Rev 2 trim), `truncated: true` in the JSON twin.
3. Voice, librarian: *"show me how my memories about temperature connect"* → a display window with the picture; Mortimer speaks the one-sentence summary; `bot.log` has `display_payload tool=memory_graph_view surface=window`.
4. Voice, developer: *"draw the deliberation graph for the last self-edit"* → picture; proposals and judges visible; on a replayed round (gap-closure §8.7's `d6e0059b`) the superseded rows draw faded.
5. **The Swift check this plan could not make:** in MortimerHost, trigger step 3 and confirm the display window shows the PNG. If it shows nothing, the payload reached (`AgentRunStore` message log under Debug ▸ Show message log) but `AsyncImage` failed → report the URL it tried; the fix is on the Swift side, not here.
6. Seam: one voice-initiated self-edit that fails validation twice (`POST /api/council/convene` is NOT a valid check — no run). Then `sqlite3 data/jarvis.db "select round_id, run_id from council_rounds order by started_at desc limit 3"` shows a non-NULL `run_id` on the new round; `…/api/graph/deliberation/image.png?focus=<that round>` shows a `for_run` edge to a green run node; `python -m jarvis.council --agreement` unchanged.
7. `RUN_LIVE=1 uv run python -m tests.evals.routing_eval` ≥ 90 % with the two new cases (70 total). If either new case fails, the permitted fix is the `config/agents.yaml` description clause (GL16) — never a Supervisor rule.

## §9 Rollback

- `JARVIS_GRAPHS_ENABLED=false` in `.env` + restart: every endpoint and tool returns `ok: false`; images render the disabled sentence; nothing else changes.
- To remove the tools outright: delete the two `@mcp.tool` functions AND their `skill.yaml` entries AND the `optional_env` lines together, restore `TOTAL_TOOLS`/the snapshot, restart the bot.
- GL9 has no switch. To revert: remove the two names from `RUN_ID_INJECTED_TOOLS`; new rounds go back to NULL. No data to undo.
- `supersede_score_rows`: behaviour-preserving refactor; reverting it is reverting the graph plan's deliberation builder too.
- No migration was added; `scripts/init_db.py` is unaffected.

## §10 Risks

| # | Risk | Likelihood | Mitigation |
|---|---|---|---|
| 1 | `AsyncImage` in MortimerHost does not render the PNG | low | §8.5 — reported, not patched here |
| 2 | Execution render slow on a busy week | medium | `GRAPH_EXECUTION_MAX_RUNS`, `GRAPH_MAX_NODES`, focus required; measure in §8.2, lower the cap if > 3 s |
| 3 | Model passes `run_id` despite the stripped schema | low | injection overwrites unconditionally (tested) |
| 4 | Pillow default font lacks a glyph | low | `to_png` replaces non-Latin-1 chars with `?` |
| 5 | Librarian prompt exceeds 1,200 after step 9 | low | 970 + ~180 = ~1,150; the test fails loudly if not |
| 6 | `networkx` import cost on the sidecar's first request | low | imported inside `render.layout` |
| 7 | An implementer computes an edge outside `jarvis/graphs` | — | §0.3; review the diff for `add_edge`/`Edge(` outside the package |
| 8 | `parse_since` gives `None` and a builder binds it | — | Rev 2 §5 steps 5/6 omit the bound; `test_since_filters_and_run_cap_truncates` covers `since=None` |
| 9 | Whole-graph memory picture is unreadable at 500 nodes | known | it is truncated by degree and honest about it; the voice tools always pass a focus |

## §11 Self-audit (9-item taxonomy)

1. **Contracts typed:** GL4 member-by-member; GL12 dict member-by-member (`tool_result`); `Graph`/`Node`/`Edge`/`from_json`/`typed_lookup`/`unique_prefix_match`/`preview` as literal code; `build`/`summary_line`/`tool_result`/`supersede_score_rows` literal; endpoints literal with media types.
2. **Lifecycle:** no caches, no background state; the staging record's `run_id` lives and dies with the record.
3. **How a value is applied:** colours/styles/fading are fixed tables applied by `to_svg`/`to_png` from one `positions` dict; `truncated` appears as a JSON flag, a focus-node attr, and a summary suffix — the three places named.
4. **No two sections disagree:** GL5 = `build` = its test = §8.2; GL7 = steps 3–6 = the per-graph tests; GL12 "no nodes in the tool result" = `tool_result` = its test; GL9 route = step 11 = its five tests; `TOTAL_TOOLS` 69 everywhere; `GRAPH_MAX_NODES` 500 in §6 and `config.py`.
5. **Copy verbatim:** tool descriptions, summary templates, error sentences, prompt sentences, description clauses, eval inputs.
6. **Initialization timing:** env constants once at import of `config.py`, read as attributes at call time; `networkx`/`PIL` imported lazily; `run_migrations()` at the top of every endpoint and tool.
7. **Signatures agree; every column populated:** `build` identical in steps 2, 9, 10; `council_rounds.run_id` is the only column newly populated, by writers that already exist; `image_url` derivable from `JARVIS_ADMIN_URL`; `mean` from `build_roster`; `superseded` from `supersede_score_rows`.
8. **No judgment left:** focus order (GL6), `became` parsing, thresholds, edge lists, layout seed, fade rules, trim rule, FIND/REPLACE anchors, `# implementer:` decisions each bounded.
9. **Drift check:** every file in §5 is in §4; every test in §7 names a function in §5; the re-evaluation's 15 amendments are each present (header list). Re-run this audit after any edit.

## §12 Approval checklist and Larry's commit list

- [x] Larry approves GL1–GL15 (2026-09-04, by proceeding); Rev 2 additions (GL16, `supersede_score_rows`, tenant sentence, trim rule, `GRAPH_MAX_NODES` 500, `observations` out) recorded — Larry may reverse any in this file before step 1.
- [x] `feat/graph-layer` cut from `main` @ `e101758`.
- [ ] Implementer completes §5 steps 1–13; reports 0 failures and every `# implementer:` decision.
- [ ] Hand-edit that is Larry's by standing rule, in the same commit: `tests/unit/test_requires_env_snapshot.py` (§5 step 9(g)). (`test_prompts.py`'s cap raise is a test edit the implementer makes; it is not allowlist-denied.)
- [ ] Larry runs §8.1–8.7; records the Swift outcome of §8.5 in this file's header.
- [ ] Commit list (explicit paths, never `git add -A`):
  `git add jarvis/graphs tests/unit/test_graphs_model.py tests/unit/test_graphs_memory.py tests/unit/test_graphs_capability.py tests/unit/test_graphs_execution.py tests/unit/test_graphs_deliberation.py tests/unit/test_graphs_render.py tests/unit/test_admin_graph.py tests/unit/test_run_id_injection.py tests/fixtures/graphs jarvis/council/agreement.py tests/unit/test_council_agreement.py jarvis/admin/server.py jarvis/agents/upgrade_agent.py jarvis/council/council.py jarvis/skills/registry.py mcp_servers/mcp_selfedit/server.py mcp_servers/mcp_selfedit/logic.py mcp_servers/mcp_memory/server.py mcp_servers/mcp_memory/logic.py mcp_servers/mcp_memory/skill.yaml mcp_servers/mcp_runlog/server.py mcp_servers/mcp_runlog/logic.py mcp_servers/mcp_runlog/skill.yaml jarvis/bot/display.py jarvis/prompts.py config/agents.yaml requirements.txt tests/integration/test_registry.py tests/evals/cases.yaml tests/unit/test_requires_env_snapshot.py tests/unit/test_prompts.py tests/unit/test_mcp_memory_logic.py tests/unit/test_mcp_runlog_logic.py tests/unit/test_display.py tests/unit/test_admin_selfedit.py tests/unit/test_admin_appbuild.py tests/unit/test_upgrade_agent.py tests/unit/test_mcp_selfedit_logic.py docs/REPO_MAP.md CLAUDE.md docs/plans/MORTIMER_OPTIMIZATION_PLAN.md docs/plans/MORTIMER_GRAPH_LAYER_PLAN.md docs/reviews/GRAPH_LAYER_PLAN_REEVALUATION_2026-09-04.md`
- [ ] After merge: Stage 2 (GL13) waits for Larry's "G1(e) started" — do not build unprompted.
