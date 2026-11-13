---
date: 2026-11-13
system: codex
rows: [WS-35]
prs: []
---

# C5 result carousel

Claim: Codex, `codex/ws35-c5-result-carousel-20261113`, fresh isolated worktree from next `6a7ac28`; reviewer Kimi. Larry explicitly authorized the C4 identity integration as this branch's first commit, then C5 carousel, one draft PR into next. No ROADMAP/closure-plan edit, merge or deploy.

## First commit: identity integration

C4 #366 merged at `343264f`. Current next includes current main and C2 tokens. WorkspaceStore consumes known answer identities before first-arrival routing, applies only higher revisions, preserves UUID/date/filter/pins/selection/scroll/ownership, and marks substantive off-front updates. Replay and completion-only transitions do not mark updated. Router updates existing display stores without re-running presentation, transfer or transcript paths. New answer identities can still use established weather/roadmap semantic reuse.

Tests: `swift test --package-path macos/MortimerHost --filter ComposedWorkspaceIdentityTests`: 3 passed; all five shared contract transitions plus reader/marker/completion/replay assertions. `swift test --package-path macos/MortimerHost --filter ComposedAnswerRouterTests`: 4 passed; actual transport tests cover main reader, supporting owner, changed surface, replay/no inventory effects and no duplicate transcript/reference. Zero skips added. Initial store fixture timestamp compile error and router fixture missing turn attestation were corrected before these passes.

Next: implement carousel A and show-all B with the same set, bounded paging, accessibility/reduction fallbacks and box 196 reuse tests. C6 orb slots and amber stay unchanged. Full suites and hosted Swift validation follow the completed slice. Existing next validate failure is its offline-NLTK lint-command expectation; existing allowlist compares main...next. Both are outside C5 and not fixed here. No final-build/hardware acceptance claimed.
