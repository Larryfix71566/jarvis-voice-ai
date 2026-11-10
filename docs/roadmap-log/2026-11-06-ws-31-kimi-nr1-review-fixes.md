---
date: 2026-11-06
system: kimi
rows: [WS-31]
prs: [315]
---

# WS-31 NR1 review fixes F1–F4 — Kimi, 2026-11-06

System: Kimi (Kimi agent session, Larry's Mortimer project channel). Implementation author: Kimi authored the NR1 implementation at `d2e7a61` and owns this fix; Claude's independent review (2026-11-06, `docs/roadmap-log/2026-11-06-ws-31-claude-nr1-review.md`) requested changes F1–F4; Claude did not coauthor this fix and re-reviews the new exact head.

## Target and base

Branch `kimi/ws31-nr1-review-fixes-20261106`, created from current main `c7cc1181ad2de0eb5b5b3ec19cc696768cca288f` (freshness checked: all three NR1 blobs unchanged from `d2e7a61` on main). Code and tests landed at exact head `2d150902366ddd4909c8112f4f3d46bddc4fa3dc`:

| Path | Blob |
| --- | --- |
| `jarvis/app_build_contract.py` | `40309e3b393b789df12b49c11867163990d674c9` |
| `tests/unit/test_app_build_contract.py` | `3cfa157ab50efafee9198acf7a66205424dd666f` |
| `tests/fixtures/app_build_contract/new_idea_v1.json` | `3ff48199350544733f51430a5cc8dc74747ca3ea` (unchanged) |

The PR adds only WS-31 documentation (ROADMAP WS-31 block, this log, REA plan dated progress) on top of that head. The §11 contract text is unchanged.

## Finding → fix mapping (all in `_preflight` / new `_preflight_known_object`)

- **F1 (Medium) — error order followed dict insertion order.** Known-container preflight now partitions items into present known fields and unknown keys (`type(key) is str and key in fields`), visits known fields in their documented `_FIELDS` order, and counts unknown keys afterwards (one `unknown_field` per containing object; unknown-key values are not traversed). §11: fields traversed in documented order; object key order immaterial; NR1-10.
- **F2 (Low) — no error priority.** Each known field's recursion collects into its own segment buffer; segments are stable-sorted by `_PREFLIGHT_PRIORITY` (`invalid_type` 0, `limit_exceeded` 1, everything else 2) and flushed atomically into the parent, giving the §11 priority of type/cycle, node/depth limit, then text/size within the currently visited known container. The global 32-error cap semantics are unchanged (the same `_pending() <= _MAX_ERRORS` guard as before governs every append).
- **F3 (Low) — preflight kept emitting after the node budget.** Node-tick failure now sets `state.node_limit_hit`, appends one `limit_exceeded` at the current location, and stops all further traversal and unknown-key counting. The 4,090-item hostile list now yields exactly one `limit_exceeded` instead of 31 plus the cap entry.
- **F4 (Low) — type check could call a metaclass `__eq__`.** `type(value) not in _ALLOWED_TYPES` replaced with `any(type(value) is allowed for allowed in _ALLOWED_TYPES)`; identity comparison only, no conversion, iterator, comparison or serialization hook is invoked.

## Tests added (four, appended after the existing 81)

1. `test_preflight_error_order_is_independent_of_dict_insertion_order` (F1): reversed-key mapping and raw-JSON routes produce identical documented-order `invalid_text` errors; the node-limit permutation case (4,090-item `acceptance_case_ids`, reversed spec dict) produces identical results on both routes with the limit location inside `$.spec.requirements[0].acceptance_case_ids[`.
2. `test_preflight_error_priority_is_type_then_limit_then_text` (F2): `invalid_type` precedes `invalid_text`, and `limit_exceeded` (nested-depth constraints) precedes `invalid_text` within the same known container.
3. `test_node_limit_produces_exactly_one_limit_exceeded` (F3): the 4,090-item case yields exactly one error, `limit_exceeded`.
4. `test_type_check_never_invokes_metaclass_comparison_hooks` (F4): a `HostileObject` whose metaclass counts `__eq__` calls is rejected as `invalid_type` with zero hook calls recorded.

## Validation

- Focused suite `pytest tests/unit/test_app_build_contract.py -q`: **85 passed** (81 existing unchanged + 4 new).
- Mutation check: each of the four new tests fails against the pre-fix module, so each binds its finding.
- NR1-01 digests recomputed and unchanged: intent `87d0db81b7c35eb52b1080e2613e7bfb21ddaff3b8e70fdbaf26c17ffa496add`, spec `eb48b383ba68b7ec9c947c74b6a3d4ee5fb5d2c2908666f9ba88496c260b9cd5`.
- Full offline unit suite `pytest tests/unit -q` runs on repository CI against the PR head; the fixing sandbox cannot hold the full tree (same division as Claude's review, which also relied on repository CI for the full suite).

## Scope and non-claims

Changed only `jarvis/app_build_contract.py`, `tests/unit/test_app_build_contract.py`, the ROADMAP WS-31 block, this log entry and the REA plan's dated progress. The fixture, the §11 contract text, module limits (`_MAX_BYTES`/`_MAX_DEPTH`/`_MAX_NODES`/`_MAX_ERRORS`/`_MAX_PROSE`), imports (stdlib `hashlib`/`json`/`re` only), result shape and always-false `build_authorized` are unchanged. No runtime wiring, caller, dependency/config/registry/policy, persistence, model call, credentials, service or deployment change. No acceptance checkbox ticked; NR1 remains unwired with no runtime identifier reserved. Next: Claude re-reviews the exact PR head; Larry merges.
