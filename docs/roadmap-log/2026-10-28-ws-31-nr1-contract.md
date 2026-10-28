---
date: 2026-10-28
system: kimi
rows: [WS-31]
prs: []
---

# WS-31 NR1 no-reference contract implementation

System: Kimi. Workstream: WS-31. Branch: `kimi/ws31-no-reference-contract-20261028`.
Base: `233995cb9fb0f9a5e1f2fd35611b4cfa1b5e0af8`.
Immutable implementation commit: `d2e7a61d46edcc66bbf1eb5746fb3282a14c7efd`.

## Assignment and scope

The matching Owner/Where/Scope claim was present on main. The three implementation paths were absent. The open-PR inventory found no concurrent WS-31 writer. Kimi recorded the required acknowledgment on [PR #280](https://github.com/Larryfix71566/jarvis-voice-ai/pull/280#issuecomment-6457803600).

Only the approved pure stdlib contract, focused test, synthetic fixture, canonical plan, this log, the WS-31 roadmap block and the content-free NR1 receipt changed. Section 11's reviewed contract text was not edited. No existing runtime, admin, agent, App Builder, Skill, provider, sandbox, dependency, configuration, registry, policy, persistence, API, UI or deployment file changed.

## Exact source identity

| Path | Git blob | SHA-256 |
| --- | --- | --- |
| `jarvis/app_build_contract.py` | `7f2c926000b2ac5f6a315b8913d150a6fe876600` | `5036a8bf7a7c517d0a964cbd38267946cd02bd110ee915996ea196f48322b358` |
| `tests/unit/test_app_build_contract.py` | `52aaa8c6780092dbd210207633fc9578d3e4f469` | `dddca6194379fd1dc062a310a67fdd72e2e0432e44a923921cd13c0da95257dc` |
| `tests/fixtures/app_build_contract/new_idea_v1.json` | `3ff48199350544733f51430a5cc8dc74747ca3ea` | `e1585556a00effccbd148d449fbdbda5f375c82237cb9d694800f5c973bdb3ff` |

The fixture is synthetic and is not Larry's selected app request. Its fixed digest oracle was calculated independently with `json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)` encoded as UTF-8 and hashed with SHA-256, before the implementation was written:

- Intent: `87d0db81b7c35eb52b1080e2613e7bfb21ddaff3b8e70fdbaf26c17ffa496add`
- Spec: `eb48b383ba68b7ec9c947c74b6a3d4ee5fb5d2c2908666f9ba88496c260b9cd5`

## NR1-01–10 evidence matrix

| ID | Implementation and focused evidence |
| --- | --- |
| NR1-01 | Synthetic list/filter/export fixture returns `valid_draft`; both routes match the fixed independent intent/spec digests and always return `build_authorized=false`. |
| NR1-02 | Blocking questions return `needs_input`; nonblocking questions remain listed without granting authority. |
| NR1-03 | Unknown reference, path, provider, model, repository, approval, owner, tool and policy fields return content-free `unknown_field` errors. Command-like prose remains inert. |
| NR1-04 | Intent edits with a stale parent digest fail; requirement/oracle/array edits change the spec digest; object key reordering preserves both routes' results. |
| NR1-05 | Missing/duplicate IDs, orphan and reverse-reference mismatches, missing must oracles and no-must inputs fail deterministically. |
| NR1-06 | Exact built-in types, boolean-as-integer rejection, nonfinite/duplicate JSON rejection, unsupported contracts, bounded locations, secret-free errors and insertion-order independence are covered. |
| NR1-07 | Raw/canonical byte caps, depth 8, 4,096 nodes, prose/list/reference boundaries, invalid Unicode/NUL/whitespace, cycles, repeated noncyclic containers and hostile dict/list/str/int subclasses are covered. |
| NR1-08 | Forged approval/owner/tool/policy text never authorizes execution. Raw and mapping routes agree within the independent wire cap; over-cap wire whitespace does not invalidate the equivalent mapping. |
| NR1-09 | Import/call guards record zero file, environment, network, subprocess or SQLite attempts. Static imports are limited to `hashlib`, `json` and `re`; no runtime module is loaded. |
| NR1-10 | Input preservation, deterministic repeats, no retained mutable output aliases, null invalid digests, empty invalid question lists, fixed error order and content-free errors are covered. |

## Validation

- `python -m pytest tests/unit/test_app_build_contract.py -q` using the existing project environment: **81 passed**.
- Independent scratch suite outside the repository: **6 passed**, including **120 key-order permutations** and **500 generated hostile JSON inputs**, with mapping/raw parity and result-shape invariants.
- Full offline unit suite: **7,197 passed, 11 skipped, 215 subtests passed**; 19 existing warnings.
- `python3 scripts/check_roadmap.py`: **0 errors, 0 warnings** before documentation.
- `git diff --check`: passed for the implementation.
- Standard-library `unittest` discovery was not applicable to the pytest-style function tests and discovered zero tests; it is not counted as validation evidence.

## Remaining review and non-claims

Codex must independently review the immutable implementation and hostile/limit cases. Kimi does not approve its own implementation. Repository CI and that nonauthor review remain required at publication.

No real app was selected or created. No model, credential, reference, repository, runtime, service, deployment or publication operation occurred. Digests identify content only; they are not signatures or approval. No acceptance criterion or broader REA/app-building gate closes.
