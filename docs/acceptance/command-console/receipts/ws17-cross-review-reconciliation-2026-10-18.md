# PR #216 Finding 1 Reconciliation — Final Disposition

Source confirmed: `61f701d683d76b3633afc1b060e4a19f20d9339d`. This is a static re-assessment of Finding 1 only, using the previously-omitted caller/property definitions now supplied. No tools, commands, or tests were run by me; the 65 recorder-reported test results are reported as recorder output, not something I executed or independently verified.

## Finding 1 — Disposition: **INVALID** as a blocking issue (field-presence asymmetry itself: CONFIRMED but benign/deliberate)

The original finding bundled two things: (a) a factual observation that first-arrival roadmap display payloads carry no `data_policy`, unlike the refresh path, and (b) two disjunctive blocking-severity hypotheses about what that asymmetry implies. The new evidence resolves both hypotheses.

**(a) The asymmetry is real and intentional, not an oversight.**

`tests/unit/test_roadmap_event.py:51` asserts directly on the ordinary delegation path:
```python
assert 'data_policy' not in delivered  # Projection creates no source grant.
```
This is a deliberate test contract, not an unexamined gap — the comment explicitly names the design rule: the event-stream projection "creates no source grant," distinguishing it from the refresh path's explicit `approved_external` grant.

**(b)(i) "Feature silently disabled on first arrival / dedup breaks" — INVALID.**

`macos/JarvisKit/Sources/JarvisKit/AppMessage.swift`:
```swift
public var isProtectedLocal: Bool {
    guard let dataPolicy else { return false }
    return dataPolicy != "approved_external"
}
```
A missing `dataPolicy` returns `false` (not protected). So a first-arrival payload with no `data_policy` field renders exactly like an `approved_external` one in `WorkspaceResultPane`, and `reuseExistingIdentity`/`refreshRoadmap` do not refuse it. No duplicate-result regression, no silently-disabled `RoadmapView`. This confirms the field absence maps to legacy "local render, trust by construction" semantics (the data came from the agent's own already-validated MCP call chain), not to a new deny-by-default policy — consistent with the distinction the refresh path draws for its own, separately-fetched transport.

**(b)(ii) "Sensitive-turn laundering with no confidentiality marking" — INVALID.**

Two layers independently prevent a sensitive-turn roadmap read from ever reaching the display-payload branch with real content:

- `jarvis/agents/base.py:160` `_tool_result_observation`: when `is_sensitive()` is true, it returns `result[:TOOL_RESULT_EVENT_MAX]` (the plain truncated string) rather than the projected `{"roadmap": ...}` JSON shape that `display.py`'s new branch keys on (`isinstance(data.get("roadmap"), dict)`).
- `jarvis/agents/base.py:1943` `_emit`: when `is_sensitive()` is true, it strips the event down to `{"type","agent","display_name","tool","run_id","ok","latency_ms"}` — both `result` and `arguments` are removed entirely before the event reaches `make_agent_event_handler`'s `on_agent_event`.

`tests/unit/test_roadmap_event.py:129` confirms the composed effect:
```python
agent._emit(events.append, {'type': 'agent_tool_result', 'tool': 'repo_read_file',
                           'arguments': {'path': 'ROADMAP.md'}, 'result': observed})
assert events == [{'type': 'agent_tool_result', 'tool': 'repo_read_file'}]
```
With `arguments`/`result` absent, `jarvis/bot/pipeline.py:669`'s handler calls `build_display_payload(..., arguments={}, result_str="")`. The new `display.py` branch's guard (`data.get("path") == "ROADMAP.md"` on parsed `result_str`) cannot pass against an empty string, so the roadmap card branch never fires during a sensitive turn through this path. The hypothesized "full card content with no confidentiality marking" scenario has no live code path to occur through.

**Conclusion on Finding 1:** the asymmetry is real but is the designed legacy-local-render boundary, not a privacy or functional defect. Both blocking readings from the original review are closed by direct evidence rather than by assumption.

## Secondary timezone concern — remains **UNRESOLVED**

No definition of `runtime.settings.jarvis_timezone` or confirmation that it's sourced from (or kept in sync with) `os.environ.get("JARVIS_TIMEZONE")` was in the supplied snippets. I cannot establish configuration consistency between the two reads from this material, and I'm not asserting a mismatch exists — this stays an open coverage gap, not a confirmed defect.

## Residual coverage limits

- `_tool_result_observation` and `_emit` both gate on `is_sensitive()`; the refresh path (`_read_console_roadmap`) gates on `_voice_is_sensitive()`. These are consistent with each other *within* the path Finding 1 concerns (both base.py gates use the same predicate), so this naming difference does not reopen either closed hypothesis above. Whether `is_sensitive()` and `_voice_is_sensitive()` are equivalent predicates was not established and isn't needed to resolve Finding 1, but it wasn't independently confirmed either.
- All other items in the original review's "Reviewed and not finding a blocking issue" section (spoken-number parsing, Markdown roadmap parser, MCP self-attestation cross-check, filter semantics, weather context minimizer, pipeline ordering, refresh-placement behavior) were not part of this reconciliation request and are unchanged from the original review.
- This remains a static, read-only assessment: no execution, no live calls, no file or tool access, and no merge/deployment action was taken or implied.
