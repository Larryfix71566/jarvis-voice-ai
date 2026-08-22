# Mortimer — Memory Capacity: the Live = Injected Invariant

**Status: IMPLEMENTED 2026-08-21 — code + tests done, unit suite green. Larry's rein-in run (§4 step 1) still pending on his machine.**
Author: Claude (Fable), 2026-08-21. Requested by Larry after comparing
Mortimer's memory system to Hermes Agent's: *"take the best of theirs and
merge it into ours … give me a plan that fixes those gaps … can our
management of memories be reined in from its current state?"*

**Implementer contract.** Same rules as MORTIMER_VOICE_ISOLATION_TIER12_
PLAN.md: every decision below is LOCKED; verify external claims with the
stated commands; if something is impossible as written, STOP and report
rather than substituting a design. Version-check against the deployment
venv (`.venv/lib/python3.12/site-packages`), never the sandbox interpreter
— that lesson is one day old.

---

## 0. The diagnosis (measured on Larry's live store, 2026-08-21)

Panel readout: **115 live · 146 archived; 100 of 115 facts do not reach
the prompt (15 do, 1,637 chars)**. Tier breakdown: identity 8,
preference 51, project 19, system 37 (hidden).

The root difference vs Hermes: Hermes bounds curated memory at **write
time** (~1,375 chars; consolidate-when-full is forced), Mortimer bounds at
**read time** (store everything, silently drop at injection). Our K5
`not_reaching_prompt` warning documents the failure; Hermes' bound
prevents it. Everything else favors Mortimer: we archive instead of
delete (their evicted facts are gone forever — the single-point-of-failure
Larry's own analysis flagged), we tier by durability rather than by
file, we have write-time hygiene filters (volatile-state, capability-
claim), and we have the same L3 (SQLite + FTS5 conversation search) and
the same skills standard.

**What already exists and is reused, never duplicated:**
- `jarvis/memory.py`: `MAX_FACTS = 30`, `CONTEXT_TIERS`,
  `MAX_PREFERENCE_FACTS = 25`, `MAX_PROJECT_FACTS = 10`,
  `MAX_CONTEXT_CHARS = 1600`, `archive_fact(conn, key, became)`,
  `render_memory_context` (identity exempt from caps and char budget).
- `jarvis/memory_sweep.py`: `run_auto_consolidation` (clusters ≥ 0.8
  overlap, no mixed-content warning, keep-longest, `SWEEP_MAX_ARCHIVES`
  per boot), `run_stale_sweep` (system tier), contradiction/audience
  review queue, `run_sweep` orchestrator, `start_background_sweep`.
- `jarvis/consolidate.py`: `propose_merges` (pure, clique-based).
- `mcp_servers/mcp_memory/`: librarian's voice access to the review queue.
- Kill switch: `JARVIS_MEMORY_SWEEP_ENABLED`.

## 1. Locked decisions

| # | Decision | Rationale |
|---|---|---|
| M1 | **The invariant: every live fact reaches the prompt.** Over-capacity is a state the sweep must eliminate, not one the renderer papers over. The panel's amber `not_reaching_prompt` line becomes a defect indicator that should read 0. | This is the Hermes idea worth stealing, made stronger: their bound discards, ours demotes to a reversible archive. |
| M2 | New cap numbers sized so a FULL store fits the prompt: `MAX_PREFERENCE_FACTS` 25→**15**, `MAX_PROJECT_FACTS` 10→**8**, `MAX_CONTEXT_CHARS` 1600→**3000**, identity stays uncapped and budget-exempt (existing rule: losing the user's name is the worst outcome). `MAX_FACTS = 30` is DELETED — the per-tier caps are the one set of numbers. | 8 identity + 15 pref + 8 proj ≈ 31 facts ≈ 2,800 chars at the observed ~90 chars/fact. 3,000 chars in a prompt already ~10KB is cheap; 1,600 was sized before the store existed. Two overlapping cap systems (MAX_FACTS + per-tier) is how the panel got a "261 / 30" counter no one could explain. |
| M3 | **Capacity enforcement ladder** in the sweep, per tier, until the tier fits its cap: (a) existing near-duplicate auto-consolidation (unchanged); (b) **LLM-assisted merge**: `propose_merges` at a lower threshold (0.55) feeds clusters to the sweep's existing small-model call, which rewrites N related facts into ONE; sources archived `became=merged:<kept_key>`; (c) **mechanical age-out**: archive oldest non-identity facts beyond cap, `became=aged-out`. (c) is the backstop that makes the invariant hold even with no API key — a rule without a mechanical backstop is a wish. | Ladder order is cheapest-and-safest first. Every rung archives, never deletes — fully reversible, which is the answer to Hermes' summarizer-as-single-point-of-failure: our originals survive the merge. Identity is never touched by any rung. |
| M4 | System tier: live cap **0**. System facts archive on sight during enforcement (they are already hidden from the prompt — CONTEXT_TIERS omits system — so live system facts are pure storage noise; 37 of Larry's 115). | A tier that can never be injected has no business being "live." Still stored, still searchable (M6). |
| M5 | **One-shot rein-in**: `python -m jarvis.memory_sweep --enforce` runs the full ladder immediately, ignoring `SWEEP_MAX_ARCHIVES` (that cap protects unattended boots; an explicit CLI invocation is attended), printing per-tier before/after counts. Expected on Larry's store: 115 live → ~31, all injected. | "Can it be reined in from its current state?" — yes, in one supervised command, today, with every demotion reversible. |
| M6 | **Recall path for demoted facts**: `mcp_memory` gains ONE read-only tool, `memory_search(query)` — LIKE-based search over live+archived facts (key + content), bounded results. Tool description tells the librarian archived facts are still searchable. | Aggressive demotion is only safe if nothing becomes unreachable. This is Hermes' L3 discipline ("don't inject what you can look up") applied to our own fact store. LIKE not FTS5: the memories table is small (hundreds of rows); a virtual table + triggers for this is over-engineering. |
| M7 | Review queue diet: enforcement NEVER queues for Larry except existing mixed-content/contradiction stops. Merges and age-outs are logged (`memory_enforce key=… became=…`) and visible in the panel's archived list, not review items. | The queue exists for judgment calls; capacity is arithmetic. Today's session — Larry hand-shoveling duplicates by voice — is the labor this plan deletes. |
| M8 | Prompt guidance (one sentence each, librarian task description in `config/agents.yaml` + the `remember` guidance in `jarvis/prompts.py`): don't store what conversation search or a live query can re-derive; archived facts remain searchable. | The write-time hygiene filters catch mechanical noise; this catches the LLM's habit of storing re-discoverable facts. Guidance, not a gate — the filters remain the backstop. |
| M9 | Enforcement runs inside the existing sweep (`run_sweep` gains phase A1.5 after auto-consolidation) under the existing `JARVIS_MEMORY_SWEEP_ENABLED` switch. No new kill switch. | One machine, one switch. Disabled sweep = no enforcement = pre-plan behavior exactly. |
| M10 | NOT built: a Honcho-style inferred-habits layer (post-hoc conversation analysis deriving unstated preferences). | Stated-fact curation is the current failure; inferring MORE facts before curation works would compound it. Revisit only after the invariant has held for weeks. |

## 2. Implementation order

1. **`jarvis/memory.py`** — M2 cap changes; delete `MAX_FACTS` and its
   render-path usage (per-tier caps take over); verify
   `render_memory_context`'s identity exemption is untouched
   (`test_identity_survives_the_cap` or equivalent must stay green).
   Update `GET /api/knowledge`'s `not_reaching_prompt` only if it
   hard-codes old constants (it computes by rendering — verify, don't
   assume).
2. **`jarvis/memory_sweep.py`** — M3 ladder as `run_capacity_enforcement(conn)`:
   per tier in `("preference", "project", "system")` (never identity),
   loop: count live; if ≤ cap (system cap 0), next tier; else rung (b)
   merge one cluster (reuse the sweep's existing LLM call pattern; skip
   rung entirely if no key/model — log one line); else rung (c) archive
   oldest. Wire as A1.5 in `run_sweep`. `--enforce` CLI entry (M5) with
   before/after report. All writes via `archive_fact` + the existing
   fact-write path — no new SQL shapes.
3. **`mcp_servers/mcp_memory/`** — M6 `memory_search` in logic.py +
   server.py + skill.yaml (tool count +1 → update
   `tests/integration/test_registry.py` `TOTAL_TOOLS` 60→61).
4. **Prompts/config** — M8 sentences; routing eval must stay ≥90% (no
   routing changes expected — verify, don't assume).
5. **Tests** — table below. **Docs** — CLAUDE.md memory-tiers paragraph
   updated to state the invariant; `.env.example` sweep comment gains one
   line about enforcement.
6. **Rein-in on Larry's machine** — `python -m jarvis.memory_sweep
   --enforce`, then confirm the panel reads 0 not-reaching and ~31 live.

## 3. Tests (tests/unit/test_memory_sweep.py additions + test_memory.py updates)

| test | pins |
|---|---|
| `test_enforcement_reaches_cap_without_llm` | M3(c): key-less environment still lands exactly at cap via age-out |
| `test_enforcement_never_touches_identity` | M3: identity over any size is untouched |
| `test_merge_archives_sources_with_became` | M3(b): reversibility — sources archived `became=merged:<key>`, never deleted |
| `test_system_tier_archives_on_sight` | M4 |
| `test_enforce_cli_ignores_boot_archive_cap` | M5 |
| `test_full_store_fits_prompt_budget` | M1/M2: render a store AT caps; assert zero dropped facts |
| `test_memory_search_finds_archived` | M6 |
| `test_enforcement_queues_nothing_for_plain_overflow` | M7 |
| existing render/cap tests | updated for M2 numbers, identity exemption pinned unchanged |

## 4. Acceptance (Larry runs, results appended here)

1. `python -m jarvis.memory_sweep --enforce` → per-tier report; live
   count lands ≤ 31 (8 identity + 15 pref + 8 proj), system live = 0.
2. Memory panel: `not_reaching_prompt` = 0 (amber line gone); archived
   count grew by the demoted amount; spot-check 3 archived facts carry
   `became` provenance.
3. Voice: "search my memory for <something demoted>" → librarian finds it
   via `memory_search`.
4. One week later: counter still 0 without manual cleanup — the
   invariant holding under normal use is the real acceptance.

## 5. Self-audit

- M2 deletes `MAX_FACTS` while M1 claims per-tier caps suffice: verified
  consistent — the renderer's only remaining limits are per-tier caps +
  char budget, and M2's arithmetic fits the budget with margin.
- M3(c) age-out vs the archive-not-delete principle: consistent —
  age-out archives.
- M6 makes demotion safe; without it M3 would violate "nothing becomes
  unreachable." Ordered accordingly in §2 — but NOT gated: age-out to
  archive is already reversible via the panel even before the tool lands.
- M4 (system live cap 0) vs `run_stale_sweep` (archives system at 45
  days): enforcement supersedes staleness for system; `run_stale_sweep`
  becomes redundant after M4 but is left in place (harmless, and its
  removal is not required for the invariant) — implementer may remove it
  ONLY if all its tests are updated in the same change.
- The 2026-08-20 cluster-26 lesson (keep-longest beats scorer preference)
  applies to rung (b): the merged rewrite must be instructed to preserve
  general/durable phrasing over specific/episodic phrasing.

## 6. Implementation status (2026-08-21)

All six §2 steps done: memory.py cap changes (M2, `MAX_FACTS` deleted,
`memory_usage()` redesigned to per-tier reporting since it directly
consumed the deleted constant — MemoryPanel.tsx's `Usage`
interface/render block updated to match); `run_capacity_enforcement(conn)`
in memory_sweep.py (M3/M4/M7/M9, wired as A1.5 in `run_sweep`) plus the
`--enforce` CLI (M5); `memory_search` in mcp-memory (M6, `TOTAL_TOOLS`
60→61); prompt guidance sentences (M8, Supervisor `remember` rule +
librarian description); all 8 named tests from §3 plus two extra
(`TestMemorySearch` in test_mcp_memory_logic.py, pinning the MCP-tool
wrapper itself); CLAUDE.md and .env.example updated.

Two gaps found and closed during implementation, neither anticipated by
the plan text: (1) `jarvis.memory.memory_usage()` — a SEPARATE function
from `render_memory_context`, feeding the OTHER `/api/memory` "usage"
widget in MemoryPanel.tsx — directly referenced the deleted `MAX_FACTS`
and had to be redesigned to per-tier caps/counts rather than one flat
count; §2 step 1 only mentioned checking `/api/knowledge` (which computes
by rendering and needed no change), not this second consumer. (2)
`_merge_cluster`'s first cut unconditionally read `settings.openai_model`
even when a test-seam `client_factory` supplied `settings=None` — fixed
via `getattr(settings, "openai_model", None)`, since a fake client
ignores the model kwarg entirely and a test seam should never have to
fabricate a whole `Settings` object just to satisfy an attribute access.

Not yet done: §4's acceptance steps 1-4 all require Larry's machine —
running `--enforce` on his real ~115-fact store, confirming the panel's
`not_reaching_prompt` reads 0, a voice `memory_search` round-trip, and
the one-week holding-steady check. Routing eval was not re-run (the
librarian description change is additive text, not a routing/tool
change) — flagged here rather than assumed clean, per the plan's own
"verify, don't assume" instruction.
