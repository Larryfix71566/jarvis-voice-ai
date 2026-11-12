---
date: 2026-11-12
system: claude
rows: [WS-35]
prs: [338]
---

# WS-35 B1 Swift CI — Claude's independent review of #338, Claude, 2026-11-12

System: Claude (Claude Code cloud session, Larry's Claude Duet channel). Nonauthor reviewer named by the closure plan's B1 row ("Claude, Kimi (reviewers)"). Claude did not write #338. Documentation only: this entry. It does not change the WS-35 block, which is Codex's scope.

## What was reviewed

[#338](https://github.com/Larryfix71566/jarvis-voice-ai/pull/338), draft, head `31e52a54ac7de88e53da98ff6cc324f13ee453b6`, base `next` at `a1369e223e51cc499c8f942fae95133994a4facb`. Hosted run [42957886479](https://github.com/Larryfix71566/jarvis-voice-ai/actions/runs/42957886479) on 2026-11-11, 04:14–04:18 UTC.

The only workflow change is one new `swift-tests` job in `.github/workflows/validate.yml`:

- `runs-on: macos-26-intel`, 45-minute timeout, `contents: read`, `fail-fast: false`.
- Matrix: `macos/JarvisKit`, `macos/MortimerHost`, `ios/MortimerPhoneCore`.
- Xcode 26.3 is pinned through `DEVELOPER_DIR`. A preflight step checks macOS 26 or later, x86_64, the Xcode version and `xctest`.
- For MortimerHost only, a fixture step finds Python 3.12, imports the phone admission and authority modules, builds `PhoneRemoteAuthorityOwner` and exports its paths.
- Then `swift test --package-path <package>`.

`actions/checkout@v7` with `persist-credentials: false` matches the other workflows. The PR also carries the #334/#335 documentation (orb spec, UI directions page, C10 baseline, C0 review log, AGENTS.md, ROADMAP, plan), as its body says.

## Results of the hosted run

| Check | Result | Evidence from the job log |
| --- | --- | --- |
| Swift (macos/JarvisKit) | success | "Executed 239 tests, with 0 failures" |
| Swift (ios/MortimerPhoneCore) | success | "Executed 67 tests, with 1 test skipped and 0 failures" |
| Swift (macos/MortimerHost) | **failure** | compile error, no tests ran |
| validate, allowlist, policy-tests, controller-tests, knowledge-base | success | check runs on the head commit |

The PhoneCore skip is `PhoneResultCommandsProcessTests.testCheckedModelFiveActionsThroughNativeV4ProofSession`, "Requires configured disposable Python/native-owner process fixtures". The fixture step runs for MortimerHost only, so this skip is expected. Codex's B1 log already discloses it.

## The MortimerHost failure

In the MortimerHost job, the toolchain preflight passed, and so did the fixture step (it compiled `PhoneRemoteAuthorityOwner`). The test build then stopped with:

```
macos/MortimerHost/Sources/MortimerHost/Console/SkillsWorkspaceView.swift:380:9: error: the compiler is unable to type-check this expression in reasonable time; try breaking up the expression into distinct sub-expressions
```

The job ended with "Process completed with exit code 1". The other "error" strings in the log are warning context: a `locationManager(_:didFailWithError:)` signature and a deprecated placemark API. They do not fail the build.

Line 380 is the body of `workspaceContent(width:)`. On `next` at `a1369e2`, that expression is one modifier chain on `workspacePresentation(width:)` containing 1 `.background`, 2 `.task`, 14 `.onChange`, 1 `.onAppear` and 1 `.onDisappear`. #338 does not touch this file. It is identical on `main` and `next`, and it was last changed on 2026-09-30 by `51da994`.

What the run shows: this source does not type-check within the compiler's limit on the hosted x86_64 runner with Xcode 26.3. Whether it compiles on Larry's Mac with his toolchain is untested here. A local `swift build --package-path macos/MortimerHost` on that Mac would settle it.

## Verdict

- **The workflow is correct as written.** Every step it adds ran as intended: preflight, fixture preparation, and full suites on the two packages that compile. No changes to `validate.yml` are requested.
- **B1 cannot go green on this PR alone.** It needs a source change in `SkillsWorkspaceView.swift` that splits the chain, for example by moving the `.onChange` group into a separate `ViewModifier` or helper function. That file is outside B1's scope (`.github/workflows/validate.yml`). It needs a Swift compile to verify. Under the closure plan, Claude writes no Swift until B1 is green, so Claude cannot make this fix. Who owns the fix is Larry's call. It could land as its own small PR against `next`, with #338 rerun after it.
- Not a finding: the job's 45-minute timeout leaves room. The failing leg ran about 4 minutes.

## Unchanged

No source, test, workflow, plan, ROADMAP block or acceptance checkbox was changed. No GitHub review or comment was posted on #338.
