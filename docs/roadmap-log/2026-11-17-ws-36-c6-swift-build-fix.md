---
date: 2026-11-17
system: claude
rows: [WS-36]
prs: []
---

# WS-36 C6: two MortimerHost compile fixes on `next`

Row: WS-36 (Kimi's lane). Plan item: C6 (`docs/plans/MORTIMER_RELEASE_CLOSURE_PLAN.md` §4). These are Kimi's C6 files; Larry approved Claude making this change in his Claude Duet channel on 2026-11-17 at 01:41:09 UTC ("Open the Swift PR"). Reviewer: Kimi.

## Why

The `Swift (macos/MortimerHost)` job is red on `next` at `efffa0a8` (run 43535599810, job 132263718247) with two compile errors, both from C6 (#373):

1. `Console/VoiceWaveView.swift:407:33`: value of type `WaveEngine.Dyn` has no member `g`. `Dyn` declares `cr`, `cg` and `cb` only.
2. `Console/CometOrbRenderer.swift:222:16`: the compiler is unable to type-check this expression in reasonable time.

## What changed

1. `VoiceWaveView.swift:407`: `dyn.g` becomes `dyn.cg`.
2. `CometOrbRenderer.swift:222`: the `arcEnds` closure states its signature, `(index: Int) -> ArcEnd`, and `thinkingSpin` and `angle` are typed `Double`, so the compiler no longer infers the multi-statement closure's type. No value or behaviour changes.

## Evidence and limits

Fix 1 is certain from the struct declaration. Fix 2 is untested: there is no Swift toolchain in Claude's Linux environment, so this PR's own `Swift (macos/MortimerHost)` job is the first build of it. If that job finds a further error, it was hidden behind these two.

## Not fixed here

`validate` on `next` also fails three tests that this PR does not touch:

- `tests/unit/test_agents_yaml_frontend_parity.py`: `test_the_swift_orb_field_has_every_backend_agent` and `test_the_swift_orb_field_invents_no_agents` read `Console/OrbFieldView.swift`, which C6 removed (`1e741c17`). Next actor: kimi.
- `tests/unit/test_plan_manifests.py::test_command_console_manifest_artifacts_exist` still lists `App/ResponseResultRouter.swift`, which C5 removed (`7b2a8063`). Next actor: codex.

The other `validate` failures need Larry's C1b human-only patch. `allowlist` stays red until `next` merges into `main`, because it diffs `next` against `main`.

## Next

kimi: review this PR. larry: merge decision.
