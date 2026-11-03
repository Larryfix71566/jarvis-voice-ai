---
date: 2026-11-03
system: claude
rows: [WS-32]
prs: [275]
---

# WS-32 — Claude independent exact-source review of the roadmap reader repair, 2026-11-03

System: Claude (Claude Code, cloud session, dispatched from Larry's Claude Duet channel).
Workstream: WS-32 (owner `kimi`). Branch: `claude/ws32-independent-review-20261103`.
This entry answers Kimi's open nonauthor review request on #275 (comments of
2026-10-29 01:50 and 02:54 UTC). It records the verdict without editing Kimi's
WS-32 block (§0 C2), the same way Claude recorded its 10-22 WS-28 cross-review.

## Verdict and exact binding

**CHANGES REQUESTED — one blocking finding.** The MCP reader change in
`5c5cb2ee643655716774e05191e3c14c74504b05` is correct within its own file, but
the end-to-end roadmap read it was meant to restore still fails: the host-side
source verifier in `jarvis/skills/registry.py` keeps the generic 256,000-byte
cap for the canonical roadmap and turns every larger roadmap read into
`tool_source_scope_invalid`. The console roadmap refresh therefore still cannot
return a roadmap above 256,000 bytes, on `5c5cb2e` and on current main.

Reviewed bytes are identical at `5c5cb2e` and main `9feb38a58bfa9d2bbb9e520c972a76f2e0e0dfd8`:

| Input | SHA-256 |
| --- | --- |
| `mcp_servers/mcp_repo/logic.py` | `b860e0194f15a01168d971765c4b72b307e9efe5c04bddcd97e89b7aeccc2cb9` |
| `tests/unit/test_roadmap_reader.py` | `92b0f6b7639344fa55963cfddddcc66087c0c8dae7fca460972634eec2b6b9c1` |
| `tests/unit/test_mcp_repo_logic.py` | `dc840b6000688f199e68f72386130619b772b18ec92b1cafd833e6e2fbb8999a` |
| `tests/unit/test_roadmap_event.py` | `280df4f93cf4171a1e7c1296ea78430d60c88bd70e20e496e32f909e992f32cf` |
| `jarvis/skills/registry.py` (consumer, not in WS-32 scope) | `1f453205575d5a3bf16ede0725ccf682402dd6eac1eaff42ea51c0ca1b1f0066` |

## Blocking finding B1 — host verifier still applies the generic cap

`SkillRegistry._repo_source_refs` (`jarvis/skills/registry.py:583–691` on main)
re-verifies every scoped `repo_read_file` result against guarded host reads.
For the canonical roadmap it still requires
`expected.stat().st_size <= REPO_READ_MAX_BYTES` (line 616) and does not import
`ROADMAP_READ_MAX_BYTES`. Any refusal there replaces the result with
`{"ok":false,"error":"tool_source_scope_invalid"}` (lines 740–755).
`_read_console_roadmap` (`jarvis/bot/pipeline.py:476–494`, called at line 2760)
reads `ROADMAP.md` through `call_classified` with an execution scope, so it then
raises `roadmap_snapshot_unavailable`.

Evidence, run in this session:

1. Direct call of `_repo_source_refs` with a real `repo_read_file('ROADMAP.md')`
   body. On `5c5cb2e` (262,336-byte roadmap) and on `9feb38a` (295,531 bytes):
   MCP reader `ok: true` with a snapshot; host verifier `ValueError
   tool_source_scope_invalid`.
2. Registry-level probe reusing the `test_registry_source_policy.py` fixtures
   (`registry_for`, `execution`, pinned `mcp-repo`, `call_classified`): a
   1,100-byte synthetic roadmap card round-trips unchanged; the same card padded
   to 257,100 bytes (above 256,000, below 384 KiB) returns
   `{"ok":false,"error":"tool_source_scope_invalid"}`. The probe was a temporary
   uncommitted test file, deleted after the run.
3. The existing #275 tests did not catch this: `test_roadmap_reader.py` calls
   `logic.repo_read_file` directly, and the registry roadmap tests use a
   ~150-byte fixture.

Not verified: the full native console refresh on a Mac, and whether any caller
other than `_read_console_roadmap` reads the roadmap through a scoped registry
call.

Suggested repair, for the owner to scope: in `_repo_source_refs`, use
`ROADMAP_READ_MAX_BYTES` when `canonical_roadmap` is true and keep
`REPO_READ_MAX_BYTES` everywhere else, plus a registry-level regression with a
canonical roadmap between the two limits (passes) and one above 384 KiB
(refused). This touches `jarvis/skills/registry.py`, which is outside WS-32's
registered scope and carries WS-05 source-classification review, so it needs a
scope amendment or a separate claim before code. Claude has not changed it.

## Checks that passed

- Canonical-only bound: the 384 KiB cap applies only when the resolved path
  relative to the resolved root is exactly `ROADMAP.md`. Probed in a temporary
  repository: `ROADMAP.md` as a symlink to a larger in-repo file is refused at
  the generic cap; `docs/ROADMAP.md` is refused at the generic cap; an alias
  symlink that resolves to the canonical file reads with path `ROADMAP.md` and
  its snapshot, which exposes nothing beyond the canonical file.
- Both guards use the dedicated bound: the pre-read `stat()` check and the
  second raw-read growth check (`logic.py:143–168`). Roadmap logs, search and all
  other paths keep `REPO_READ_MAX_BYTES`.
- Path and secret guards: `resolve_repo_path` still runs first and is
  unchanged; moving the `rel` computation before the size check changes no
  failure mode, because containment is already enforced.
- Ceilings unchanged: `ROADMAP_SNAPSHOT_MAX_BYTES` 512 KiB and the display-event
  ceiling are not touched by the diff.
- Tests: `pytest tests/unit/test_roadmap_reader.py tests/unit/test_mcp_repo_logic.py
  tests/unit/test_roadmap_event.py tests/unit/test_registry_source_policy.py`
  on main `9feb38a`: 158 passed. `python3 scripts/check_roadmap.py`: 0 errors,
  0 warnings.

## Non-blocking observations

- N1. `read_text` loads the whole file before the second raw read checks growth,
  so a file that grows after `stat()` is loaded into memory before it is
  refused. This predates WS-32 and applies to every path.
- N2. `repo_search` (`logic.py:405`) still skips any file above 256,000 bytes, so
  roadmap lines never appear in search results. That matches the registry's
  search verifier (line 682) and WS-32's "all other APIs unchanged" scope; it is
  recorded so nobody reads it as a reader regression.
- N3. A case-variant request such as `roadmap.md` gets the generic cap and no
  snapshot on a case-insensitive filesystem. That fails closed. Not run on APFS.
- N4. Headroom: the roadmap was 259,344 bytes on 10-23 and is 295,531 bytes on
  11-03, against a 393,216-byte cap. At that average rate (about 3.3 KB a day,
  two data points) the cap would be reached in roughly a month. This is a
  projection, not a measurement.

## Remaining action

- kimi: decide the B1 repair path (scope amendment or a new claim covering
  `_repo_source_refs` and its registry test), with WS-05 review of the
  source-classification change.
- larry: approve that scope change; deployment and live acceptance stay separate.
- claude: re-review the exact repair head when it exists.

No implementation, test, fixture, plan or other owner's row was changed by this
review. No deployment, live test or acceptance checkbox is involved.
