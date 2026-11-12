---
date: 2026-11-12
system: claude
rows: [WS-35]
prs: [335]
---

# WS-35 C10 baseline instructions — Claude's independent review of #335, Claude, 2026-11-12

System: Claude (Claude Code cloud session, Larry's Claude Duet channel). Nonauthor reviewer. The closure plan names Kimi as C10's reviewer. §8 says any system other than the author may review when the named reviewer is busy, and no Kimi review of #335 exists on any branch or open PR as of this entry. Claude did not write #335. This change is documentation only: this entry. It does not change the WS-35 block, which is Codex's scope.

## What was reviewed

[#335](https://github.com/Larryfix71566/jarvis-voice-ai/pull/335), head `073c5ac039a03450c40323d478d48850857663b0`, base `next` at `a1369e223e51cc499c8f942fae95133994a4facb`. All five checks pass at that head.

The substance is `docs/acceptance/ws35-c10-freeze-performance-baseline.md` (75 lines), the procedure for box 810's baseline. The other files are:

- Codex's C10 log and the WS-35 block update.
- #334's contract-review log. #334 is an ancestor of #335.
- `AGENTS.md`, `ORB_SPEC.md` and `mortimer-ui-directions.html`. These are byte-identical to `origin/main` (blobs `d793b665`, `c5cfd6de` and `a990e97a`), so they carry main's docs into `next` and nothing else.

## Claims checked against the freeze `5777e98`

| Claim in the procedure | Source at the freeze | Result |
| --- | --- | --- |
| The three `--filter` test names | `OrbShellFrameTimeTests.swift:109`, `MemoryGraphFrameTimeTests.swift:213`, `SkillsRenderedNavigationBenchmarkTests.swift:139` | match |
| Orb: 1440×220, 10 warm-up + 300 frames, sensitivity crystal p50 > 1.10× empty, budget p95 ≤ 16.7 ms | lines 50, 91, 114, 132–133, 153–156 | match |
| Orb output `.build/interface-fixtures/orb-frame-time.json` under the working directory | lines 146–150 (`currentDirectoryPath`) | match; this is why the procedure runs from the package directory |
| `MORTIMER_SANDBOX_GUEST` bypasses enforcement | line 129 | match |
| Graph: 1440×900; 500 nodes and 2,000 edges; hub degree 220; 48-character labels; 150 pan + 150 zoom; four-node control; gate 33 ms | lines 10–16, 79, 188–196, 226, 247–265 | match |
| Graph output under `macos/MortimerHost/.build/interface-fixtures/P4-frame-time.json` | lines 300–302 | match |
| Skills benchmark emits JSON on stdout | line 302 (`SKILLS_RENDERED_NAVIGATION_JSON=`) | match |
| Four staged attachments | `Stores/AttachmentStore.swift:25` and `:44` | match |
| 8 MiB per image | `jarvis/bot/shared_content.py:19` | match |
| Historical orb p50 4.933 ms, p95 14.150 ms | `docs/acceptance/adaptive-interface/receipts/orb-crystal-glass-2026-09-29.md:21` | match |
| Box 810 thresholds (16.7 ms, 200 ms, 33.3 ms, 10% regression) and box 702's ≤10 MiB | `docs/acceptance/mac-acceptance-2026-11-11.md:104` and `:119` | match |
| C6 probes: p50 and p95 ≤ 1.10× crystal, p95 < 16.7 ms | `ORB_SPEC.md:113–114` | match |
| Nearest-rank p95 (`ceil(0.95n)`) | the orb test's `percentile` (lines 100–103) uses the same rule | consistent |

## Findings

No blocking findings.

- **Nit, who runs §2.** The status line says "Larry runs it on the Mac". §2 says the component probes run "in a separate Codex validation worktree". Whoever runs them, a single sentence naming the operator would remove the ambiguity. The receipt checklist (§5) already records the operator.
- **Not a finding, but relevant.** The three component probes are three of the six tests that fail on GitHub's hosted Intel runner in #338 ([B1 review](2026-11-12-ws-35-b1-claude-review.md)). All three passed on Larry's Mac at `4e58eaa`. So hosted CI results cannot stand in for these probes. The procedure already requires Larry's logged-in Mac session and forbids substituting other evidence.

## Verdict

**APPROVE** at `073c5ac`. Every number, path and test name checked matches the freeze sources. The procedure fails closed: it treats skips, missing output and unmeasured metrics as blockers, not passes. Measurements are not run, and this review certifies none.

Merge notes:

- #335 contains #334, so merging #335 also lands #334's contract-review log.
- #335 conflicts with #340 in `docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md`; it merges cleanly onto `next` by itself. Whichever merges second needs that one dated-progress conflict resolved by its author.
- The baseline capture this procedure describes gates the merge of C1a (#337).

## Unchanged

No source, test, workflow, plan, ROADMAP block or acceptance checkbox was changed. No GitHub review or comment was posted on #335. No benchmark was run; this environment has no Swift toolchain.
