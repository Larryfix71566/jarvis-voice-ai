# WS-03 review correction evidence — 2026-10-22

Author: Codex. Original source `4699a54a21068f6144b63e70b9021ae85bb6a3a7`.
The original independent verdict remains **REVISE (minor)**, no Critical/High
finding. Its unmodified report is adjacent. These dispositions are author evidence,
not a replacement independent verdict. Follow-up review and final CI remain pending.

| Finding | Correction or bounded disposition |
|---|---|
| M1 | `pytest.ini` sets `asyncio_mode = auto`; all six final-injection drift cases executed and passed in verbose pytest output, Mode.AUTO. No marker change or inferred reviewer approval. |
| M2 | Exact root entries 256/257, YAML events 128/129, depth 4/5, metadata 1024/1025, and refusal before YAML for oversized frontmatter are tested. Within scanner bounds is distinct from schema-valid; depth/event stress fixtures still refuse the closed schema. |
| M3 | Three declared P0 test IDs now assert exact reason codes. Invalid UTF-8 inside delimited frontmatter exercises `skill_encoding_invalid`; bare invalid bytes retain `frontmatter_missing`. |
| M4 | Adjacent tracked-source caller/import inventories record production validation callers, procedure/CLI writer consumers, creator/authoring parse consumers and the sole old script-blocker producer. Static search is not proof about dynamic or external consumers. Focused suites include these paths and direct Skill constructors. |
| L1 | Writer checks parsed mapping equality and full-content delimiter round trip before creating a directory; deliberate serializer corruption refuses. |
| L2 | Exclusive staging file, flush/fsync and atomic no-overwrite hard link prevent partial SKILL.md publication. Fixed error reasons; fault tests cover partial writes, fsync/link failures, preservation of existing resources and a concurrent winner. Empty newly-created package cleanup is nonrecursive and identity-checked. |
| L3 | Lazy body reads use the bounded parser and require matching name/description. FIFO, symlink, invalid controls and identity mismatch refuse. |
| L4 | Registry diagnostics handled before package ordinal attribution; collision tested. |
| L5 | Missing platform flags refuse explicitly; no unsafe fallback. This is not Windows support certification. |
| L6 | Exotic Unicode/control newline delimiter differences remain fail-closed; not normalized. Ordinary LF/CRLF semantics retained. Individual character limits do not override the aggregate 16 KiB UTF-8 frontmatter cap; maximum multibyte fields can refuse, now tested. |
| L7 | Defensive has_scripts declarations retained for manually constructed Skill objects; parser-admitted executable packages remain unsupported. No cleanup-driven capability change. |
| L8 | Reader/writer fdopen failure closes the owned descriptor; catalog shares the parser byte cap; log spacing corrected. |

Historical assertions: only the two script-admission expectations disclosed in the
claim changed. In this correction slice only three P0-created assertion groups were
strengthened, declared before editing in the canonical plan. Frozen workspace and
selection fixtures are unchanged. No acceptance checkbox changed.

## Offline evidence

- Original P0 reproduction: 36 failed / 4 passed; original regression 232 passed.
- Correction red test: 14 failed / 66 passed against pre-correction implementation.
  An initial unguarded FIFO baseline test was interrupted (exit 130); the test now
  fails on the old unbounded read before opening it, so bounded red run completes.
- Correction regression: **346 passed, one dependency deprecation warning**, no skips,
  12 modules: compatibility, agent_skills, catalog, catalog_cli, service, selection,
  injection_boundary, resources, authoring_validation, workspace_fixtures,
  runtime_inventory and subagent. Isolated synthetic paths; no provider inference.
- Six final-injection parametrizations separately passed with verbose Mode.AUTO
  evidence: control/scripts drift across legacy, V2 automatic and V2 explicit
  selection (exact collected IDs retained in adjacent sanitized execution evidence).

Writer scope is atomic file publication in the trusted local authoring directory,
not a transaction against hostile concurrent ancestor replacement or process/power
failure. Cleanup failure returns `skill_write_cleanup_failed`; a fully published
candidate may remain, still disabled and requiring normal inspection/activation.
No recursive cleanup, script execution, dependency install, activation or policy
change. Main's independent WS-20 and WS-17 updates remain preserved.

Full WS-03 acceptance stays **2/12** (historical SW-B/C). Import-review UI, complete
resource adapters, real offline VM/creator evaluation, runtime activation/readback,
rollback and human gates remain separately scoped prerequisites.
