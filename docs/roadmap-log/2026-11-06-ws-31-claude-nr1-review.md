---
date: 2026-11-06
system: claude
rows: [WS-31]
prs: [313]
---

# WS-31 NR1 independent exact-source review — Claude, 2026-11-06

System: Claude (Claude Code cloud session, Larry's Claude Duet channel). Nonauthor reviewer: Claude did not write the NR1 implementation, the plan §11 contract or the NR1-01–10 matrix. Claim: #310, merged as `4a93d022b9ea77d41fc7181863424d4c697e40bb`.

## Target

Kimi's immutable implementation `d2e7a61d46edcc66bbf1eb5746fb3282a14c7efd`, read on main `b084f781d46141d6bce292909344f4ef96384754`, where all three blobs are identical to `d2e7a61`:

| Path | Blob |
| --- | --- |
| `jarvis/app_build_contract.py` | `7f2c926000b2ac5f6a315b8913d150a6fe876600` |
| `tests/unit/test_app_build_contract.py` | `52aaa8c6780092dbd210207633fc9578d3e4f469` |
| `tests/fixtures/app_build_contract/new_idea_v1.json` | `3ff48199350544733f51430a5cc8dc74747ca3ea` |

Contract: `docs/plans/MORTIMER_REA_INTEGRATION_PLAN.md` §11 (NR1 contract definition and NR1-01–10).

## Verdict: CHANGES REQUESTED

One Medium and three Low findings, all in the mapping preflight (`_preflight`). Everything else checked holds. None is a security exposure: NR1 is unwired, has no runtime caller, and `build_authorized` is always false. The findings are departures from explicit §11 clauses.

### F1 (Medium) — preflight error order depends on dict insertion order

§11 says object key order is immaterial, fields are traversed in their documented order, and NR1-10 requires error order independent of dictionary insertion order. `_preflight` walks `value.items()` in insertion order, so preflight errors (text, type, cycle, node and depth limits) come out in whatever order the caller's keys were inserted. The same content gives two different `errors` lists by either route:

- Mapping: fixture with `intent.title = "a\x00"` and `intent.audience = "b\x00"` returns `[title, audience]`; the same object with `intent` keys reversed returns `[audience, title]`.
- Raw JSON: `json.dumps` of those two objects returns different results from `parse_new_app_contract`.
- Node limit: with 4,090 IDs in one list, the first `limit_exceeded` location differs (`acceptance_case_ids[4058]` vs `[4022]`) when `spec` keys are reversed.

The existing `test_fixed_schema_error_order_is_independent_of_dict_insertion_order` covers only validation-phase errors (`unknown_field`, `missing_field`), not preflight errors. Fix direction: for a known schema object, visit its known fields in `_FIELDS` order (then count unknown keys) instead of `value.items()` order; add a preflight-error permutation test.

### F2 (Low) — preflight does not apply the stated error priority

§11: preflight failure chooses "a fixed priority of type/cycle, node/depth limit, then text/size within the currently visited known container". `_preflight` reports in traversal order instead: with `intent.title = "a\x00"` and `intent.audience = 3.5` it returns `[invalid_text title, invalid_type audience]`. Fix direction: apply the priority when recording preflight errors, or document that all preflight errors are reported in schema order and have the contract owner accept that reading.

### F3 (Low) — preflight keeps going after the node budget is spent

§11: preflight "stops after 4,096 total values plus keys". After the budget is spent, `_preflight` adds a `limit_exceeded` for every further node until the 32-error cap, so a 4,090-item ID list returns 31 `limit_exceeded` entries plus the `errors` cap entry. Output stays bounded, so this is Low. Fix direction: stop on the first node-limit error.

### F4 (Low) — the type check can invoke a metaclass comparison hook

§11: reject arbitrary objects "without invoking their conversion, iterator, comparison or serialization hooks". `type(value) not in _ALLOWED_TYPES` compares type objects with `==`, which calls a metaclass `__eq__`: an object whose metaclass defines `__eq__` triggered 6 hook calls (one per allowed type) before being rejected as `invalid_type`. The rejection itself is correct, because every later check uses `type(x) is ...`. Fix direction: test with identity (`any(type(value) is t for t in _ALLOWED_TYPES)`).

## What holds

- Focused suite: `python -m pytest -q --noconftest tests/unit/test_app_build_contract.py` → 81 passed on `b084f78` (Python 3.13, stdlib plus pytest). `--noconftest` because the repository conftest imports runtime dependencies not installed in this container; the module and its tests are stdlib-only.
- NR1-01 digest oracle, recomputed independently from the fixture with my own canonical encoder (sorted keys, compact separators, `ensure_ascii=False`, UTF-8): intent `87d0db81b7c35eb52b1080e2613e7bfb21ddaff3b8e70fdbaf26c17ffa496add`, spec `eb48b383ba68b7ec9c947c74b6a3d4ee5fb5d2c2908666f9ba88496c260b9cd5`. Both match the test constants and the fixture's declared `intent_sha256`.
- NR1-09: under a Python audit hook, the only new imports while loading the module were `hashlib` with its C helpers and the empty `jarvis/__init__.py` (`json` and `re` were already loaded), and repeated parse/validate calls on valid, invalid and duplicate-key input produced no `open`, socket, subprocess, sqlite, environment or import events.
- Raw route: a whitespace envelope one byte over 65,536 returns `limit_exceeded` at `$` while the same mapping validates; at exactly 65,536 bytes it validates. Depth-9 nesting under an unknown key is refused at `$` before parsing.
- Read against §11 with no finding: exact field sets and unknown-field handling; `schema_version` rejects booleans; `mode`, `platform` and `kind` refuse other values as `unsupported_contract`; ID patterns; two-way requirement/case links, orphan cases and missing oracles; `invalid` always has null digests and an empty question list; `needs_input` only with a blocking question; `build_authorized` is a constant false; error locations use only fixed schema names and indices; outputs are built fresh, so there are no aliases into the input.

Not tested here: the full repository suite (repository CI on this PR covers it); Python 3.12, CI's version, for the probes.

## Remaining action

kimi: answer F1–F4 with a fix on a new branch (implementation authorship stays Kimi's); Claude re-reviews the new exact head. larry: merge decisions. Nothing here changes NR1 source, tests or fixture, and no acceptance checkbox changes.
