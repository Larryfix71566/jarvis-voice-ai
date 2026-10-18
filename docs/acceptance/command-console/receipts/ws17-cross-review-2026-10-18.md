# Cross-System Review — PR #216 (WS-17 CC7a roadmap/weather-context patch)

Source `61f701d68`, base `ed21d824`, reviewed against plan §7.2. Review is static/read-only: no tests executed, no live calls made, no files touched.

## Finding 1 (Blocking candidate) — Roadmap first‑arrival payload carries no `data_policy`, unlike the refresh path; privacy/functional asymmetry

**Evidence:**

- `jarvis/bot/display.py`, new block at the end of `build_display_payload`:
```python
if tool == "repo_read_file" and data.get("path") == "ROADMAP.md" and isinstance(data.get("roadmap"), dict):
    import os
    payload["roadmap"] = data["roadmap"]
    payload["roadmap_timezone"] = os.environ.get("JARVIS_TIMEZONE")
    payload["title"] = "Project roadmap"
    payload["body"] = "..."
```
  This branch runs for **every** ordinary `repo_read_file(ROADMAP.md)` tool result turned into a display event (the normal "Mortimer, show the roadmap" → Developer delegation → agent event path). It never calls `is_sensitive()`/`_voice_is_sensitive()` and never sets `payload["data_policy"]`.

- Contrast with `jarvis/bot/pipeline.py`, `_read_console_roadmap` (the dedicated "Refresh" transport):
```python
DataPolicy("confidential" if _voice_is_sensitive() else "approved_external", "console-roadmap-refresh")
...
if policy.level != "approved_external":
    raise ValueError("roadmap_source_protected")
payload["data_policy"] = policy.level
```
  This path explicitly computes an ordinary-turn/sensitivity-gated policy and **refuses** to produce a payload unless it resolves to `approved_external`.

- Swift consumers treat `payload.isProtectedLocal` as the gate for the whole feature: `WorkspaceStore.reuseExistingIdentity`, `refreshRoadmap`, `applyRoadmapFilter`, `ConsoleActionCoordinator.refreshRoadmap`, and `WorkspaceResultPane.original` (`if result.payload.roadmap != nil && !result.payload.isProtectedLocal { RoadmapView(...) } else { DisplayContentView(...) }`) all key off this flag. Every Swift unit test that exercises `RoadmapView`/`RoadmapFilter`/dedup (`RoadmapControlsTests.payload(...)`) hard-codes `data_policy` to `"approved_external"` — none of them construct a payload with the field **absent**, which is the actual shape the real first-arrival code path produces.

**Why this matters either way:**
- If `isProtectedLocal` treats a missing/non-`"approved_external"` policy as protected (consistent with the plan's own stated philosophy for weather: *"Missing explicit `approved_external` policy cannot supply a native cache hit, so flag-off or legacy policy is not treated as public approval"*), then the structured `RoadmapView` (filters, cards, provenance, "Refresh" button) would **never render on ordinary first arrival** — only the flat `DisplayContentView` fallback would show, and `reuseExistingIdentity`/`refreshRoadmap` would refuse to dedup it, so every "show the roadmap" request would create a **new duplicate result** instead of reusing the existing one (violating the Decisions-table "Never a duplicate" contract and the roadmap requirement that it be a first-class, refreshable, navigable result).
- If instead `isProtectedLocal` defaults absent-policy to *not* protected, then the sensitivity/ordinary-turn gate that `_read_console_roadmap` deliberately enforces for refresh is **simply absent on first arrival** — a roadmap read triggered during a protected/sensitive conversational turn through ordinary delegation would display full card/checklist/provenance content with no confidentiality marking at all, which is exactly the "laundering a newly protected source" failure mode the plan explicitly warns against for this feature family.

Either reading is a real defect; I cannot fully disambiguate which one is live without the (not supplied) Swift definition of `isProtectedLocal` and the caller that decides whether `build_display_payload` is even invoked for sensitive turns — flagged as a coverage limit below, but the asymmetry itself and the untested gap are confirmed directly from the diff.

**Secondary/related:** the first-arrival path reads the timezone via `os.environ.get("JARVIS_TIMEZONE")` directly, while the refresh path uses `runtime.settings.jarvis_timezone`. If these two aren't guaranteed identical, a refresh could change `roadmap_timezone` on an existing card relative to what first-arrival set, affecting "this week" boundary computation (`RoadmapFilter.project`) inconsistently between the two arrivals of the *same* card.

## Reviewed and not finding a blocking issue

- **Spoken-number vs. subject filler parsing (Slice 3.2).** Traced `console_actions._spoken_result_number` and `WorkspaceRecents.spokenNumber` by hand against the new test phrases ("open result number one", "Route one", "One Direction", "the Atlanta one", "one two", "number one two", "first two", "0", "result number 99"). Both implementations correctly keep the ordinal/position grammar narrow and never collapse a subject containing a number word ("Route one", "One Direction") into a position. Refusal cases correctly fall through to `None`/no match rather than guessing.
- **Roadmap Markdown parser (`mcp_servers/mcp_repo/logic.py` `_roadmap_cards`).** Traced the fence (```` ``` ````/`~~~`) and nested-`<details>` depth tracking against the new 30,000+ char / nested-evidence / fenced-example test. Fenced example cards are correctly ignored (never opened as a card because `current is None` short-circuits before the opening-tag check while inside a fence); same-line nested `<details>…</details>` nets back to the correct depth without leaking the nested id as a card boundary. Duplicate-section and unclosed-section handling correctly reports issues rather than silently dropping/merging.
- **MCP self-attestation cross-check (`jarvis/skills/registry.py`).** The new roadmap-specific branch of the `repo_read_file` source-scope validator independently rebuilds the canonical snapshot via `_roadmap_snapshot` and compares it (with `read_at` substituted) against the MCP-returned `roadmap` field, closing the "MCP process cannot attest its own derived fields" gap the plan calls out. Freshness window (`-5..300s`) and size-bound checks are present before trusting the field.
- **Roadmap filter AND/OR semantics, blocker conservatism, timezone week boundaries.** Hand-traced `RoadmapFilter.project`, `blockerEvidence`/`ambiguousBlocker`, and the Monday-start/rolling-7-day logic against the corresponding fixtures in `RoadmapControlsTests`; the AND-across-facets/OR-within-facet behavior, "focus clears conflicting facets", and the explicit-vs-historical blocker exclusion all check out against the traced inputs.
- **Weather context minimizer scoping (`WeatherContextMinimizer`/`_weather_context_call` ContextVar).** The ContextVar is set/reset per invocation in `adapt_to_pipecat`'s try/finally, and the detached-task late-note case relies on `asyncio.create_task` copying the active context at creation time, which is consistent with the one test that exercises cancellation. No process-global registry callback is introduced, satisfying that specific CC7a.4 §6 boundary.
- **Pipeline ordering.** `tests/integration/test_bot_wiring.py`'s updated expected processor order places `WeatherContextMinimizer` right after `LLMUserAggregator` and before `VoiceWorkflowInjector`/`LLM`, matching the `pipeline_steps` list in `build_pipeline`.
- **"Ordinary repo-read refresh stays in place without re-selecting the main stage"** (`AppMessageRouter.display`'s roadmap branch) is explicitly asserted as intended behavior by `RoadmapControlsTests.testActualRouterRefreshRetainsPlacementAndRejectsWrongReplyBeforeApplyingSnapshot`, so the apparent bypass of the generic arrival-notice/select/unread pipeline for roadmap re-arrivals is a deliberate design choice, not an unreviewed regression.

## Coverage limitations

- No tool/filesystem access and no execution: all findings are from static reading of the supplied diff/tests; nothing here was run.
- `DisplayPayload.isProtectedLocal`'s exact definition and the call site that decides whether `build_display_payload` is invoked at all during a sensitive/protected turn are not part of this diff and were not supplied, so Finding 1 cannot be fully disambiguated between "feature silently disabled" and "privacy gate silently absent" — both readings indicate a real gap that should be confirmed against that source before this lands as a clean deployment candidate.
- WS-05 is referenced by the review brief but not described anywhere in the supplied plan excerpt, so I could not check this diff against a WS-05 contract definition beyond confirming the touched files (`registry.py`'s change is scoped to the new roadmap source-verification helper and does not touch self-edit/staging code paths).
- No live-model routing evidence was generated or claimed; `run_ws17_routing_probe`'s live-call path was read for structure only, consistent with the plan's instruction that offline/scripted review is not live routing evidence.
- This review does not constitute release/live acceptance. Required cross-review, exact-candidate verification, and Larry's UI2‑22…25 live acceptance remain open per the plan's own acceptance boundary.
