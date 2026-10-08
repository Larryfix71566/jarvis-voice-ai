---
date: 2026-10-07
system: codex
rows: [WS-17]
prs: [173, 195, 197]
---

# Native-owned weather reuse and conversation reading state

Implementation is published by this PR on `codex/ws17-closure-20261007`:
core reuse `6e218cd`/`47f9e05`, measured retention `adf2597`, exact synthetic
thread capture readiness `0a2ff94`, and source-age menu projection `748b1e5`.
The critical post-merge inventory correction remains the frozen #197 review
snapshot (`352ec69`, runtime `065d500`), separate from this increment.
Scope and shared fields/actions were reserved before code in merged #195 and
the bounded `ordinary_turn` reservation; no new model/provider route,
credential, migration, persistent cache, environment/config key, port or
allowlist entry was introduced.

The actual native cache validates canonical UUID/key/revision, source policy,
host turn eligibility, original freshness and capability. Fresh reuse avoids
another fetch/replay; stale refresh keeps identity and reader/Output state.
Ordered references show original source clocks and keep one line per run;
mixed data does not renew its older source. Recents menu, VoiceOver and choices
use source age without changing arrival order/numbers. The measured thread
anchor survives variable-height retention while New/follow behavior remains.

Evidence and limits: [local receipt](../acceptance/command-console/CC7A4_REUSE_2026-10-07.md)
and [machine-readable verification](../acceptance/command-console/CC7A4_LOCAL_VERIFICATION_2026-10-07.json).
Full offline backend: 6,567 passed / 7 skipped / 2 subtests / zero failures.
Frozen native `0a2ff94`: JarvisKit 232 passed; MortimerHost 546 executed /
six existing skips / zero failures, with actual thread and existing protected
window captures passed. The source-age gap was reproduced in the real
Store→menu/VoiceOver/choices path, then its five cases plus existing related
tests passed (45 total). Complete latest-source `748b1e5` verification also passed: JarvisKit 232;
MortimerHost 551 executed / six existing skips / zero failures, including
actual protected-thread capture. All 1,830 source hashes/modes/pins remain
matched. Counts follow XCTest final summaries.

Required exact-source Claude review, clean independent full-profile
comparison, reviewed merge/deployment and Larry's UI2-22…25 remain open.
Automatic approval review rejected transmission of the new six-file #197
correction under the earlier `fee4ac0`-only authorization; no new source was
sent. The previous VM comparison passed all `fee4ac0` candidate checks but
failed baseline Python `host_file_unverified` (7 failures/84 setups), so it is
not a release pass for this source. Production and acceptance checkboxes remain
unchanged. Preserve Claude's earlier increments and Larry's bounded #191
evidence, and keep the thread switch until all four live gates pass.
