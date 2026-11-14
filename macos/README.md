# macos/

- **`JarvisKit/`** — the shared client package (this plan,
  `MORTIMER_NATIVE_CLIENT_CORE_PLAN.md`). The single implementation of the
  voice session, the admin sidecar API, and the wake-word path.
- **`MortimerHost/`** — the G1(b) debug harness that T1.3 grows into the
  real native app.

**Self-edit eligibility** (2026-09-07,
`docs/archive/plans/MORTIMER_SELFEDIT_AUTHORING_PLAN.md` SE5). The Swift
**sources** of `JarvisKit/` and `MortimerHost/` are editable by self-edit
as routine paths: a changed package is gated by `swift build` and
`swift test` run in the session worktree, and the PR is flagged SWIFT
CHANGE. Everything else under `macos/` stays human-only —
`Package.swift`, `Package.resolved`, plists, entitlements and `scripts/`
— because a dependency, signing or
packaging change is not something a gate can validate.

A merged Swift change does nothing until the app is rebuilt:

    cd macos/MortimerHost && scripts/bundle.sh

That rebuild is the human's, by design — it is the one manual step in the
self-edit loop.
