---
date: 2026-11-13
system: codex
rows: [WS-35]
prs: [370]
---

# C5 result carousel

Claim: Codex, `codex/ws35-c5-result-carousel-20261113`, fresh isolated worktree from next `6a7ac28`; reviewer Kimi. Larry explicitly authorized the C4 identity integration as this branch's first commit, then C5 carousel, one draft PR into next. No ROADMAP/closure-plan edit, merge or deploy.

## First commit: identity integration

C4 #366 merged at `343264f`. Current next includes current main and C2 tokens. WorkspaceStore consumes known answer identities before first-arrival routing, applies only higher revisions, preserves UUID/date/filter/pins/selection/scroll/ownership, and marks substantive off-front updates. Replay and completion-only transitions do not mark updated. Router updates existing display stores without re-running presentation, transfer or transcript paths. New answer identities can still use established weather/roadmap semantic reuse.

Tests: `swift test --package-path macos/MortimerHost --filter ComposedWorkspaceIdentityTests`: 3 passed; all five shared contract transitions plus reader/marker/completion/replay assertions. `swift test --package-path macos/MortimerHost --filter ComposedAnswerRouterTests`: 4 passed; actual transport tests cover main reader, supporting owner, changed surface, replay/no inventory effects and no duplicate transcript/reference. Zero skips added. Initial store fixture timestamp compile error and router fixture missing turn attestation were corrected before these passes.

Next: implement carousel A and show-all B with the same set, bounded paging, accessibility/reduction fallbacks and box 196 reuse tests. C6 orb slots and amber stay unchanged. Full suites and hosted Swift validation follow the completed slice. Existing next validate failure is its offline-NLTK lint-command expectation; existing allowlist compares main...next. Both are outside C5 and not fixed here. No final-build/hardware acceptance claimed.

## Carousel and transcript retirement

A and B share one pinned-first recent-ten inventory. Explicitly open/comparison Older readers remain temporary members so changing modes never discards an open card (acceptance 195); navigating away removes that temporary slot, not history or Output. Paging stops at either end, with keyboard/VoiceOver controls and textual unread/updated/pinned state. Reduced motion or transparency uses the opaque flat path. Only the front mounts a full renderer; neighbours are metadata previews. The main console keeps its single action row; B and standalone cards expose their own actions. Supporting-display ownership/grid and protected-local sharing restrictions remain unchanged.

The transcript no longer embeds result cards/arrival notice or manufactures result payloads from speech. Retired ResponseResultRouter, the old preference helpers and presentResponse/updateResponse paths. Larry separately approved removal of JarvisKit's obsolete DisplayPayload(responseText:timestamp:) initializer and its direct-test migration; those two Kit files are the only source/test exception outside the C5 file list. Host decoded fixture helper avoids reintroducing that initializer.

Box 196 regressions cover original weather, Atlanta, original again as two identities, fresh-cache reuse/reference-only transcript, and stale refresh with a new composer ID retaining the original workspace identity. Native UI revision test retains actual scroll position and first responder across layout-to-fallback update. Protected content is mounted and asserted separately in the carousel; transcript-only window capture compares different private bodies and a public-transcript removal positive control, so empty captures cannot falsely prove privacy.

Initial full Host run exposed duplicate console actions and obsolete compact-mode assertions. The carousel now suppresses its action row within the console. The compact test retains both stored preference values and scroll assertions, but uses a genuinely scrollable result instead of expecting offset 240 on a one-line result that C5 now actually renders. Initial capture waits for retired inline cards were migrated without timeouts or added skips. Wide screenshot inspection caught clipped/overlapping preview labels; lateral previews were bounded instead of relying on native 3D transforms. These are local implementation/verification findings, not acceptance-box claims.

Latest fetched base remains next `6a7ac289babee8da959706c16f9cc58abe1a44a6`. Main advanced with docs-only daily batch #368 to `61c25b3`; per Larry's explicit fresh-next and no ROADMAP/plan changes instruction, that separate main-to-next synchronization is not included in C5. No changes to AppTheme/amber, C6 orb slots, SkillsWorkspaceView, harness model, deployment or production.

## Final local verification

- `swift test --package-path macos/JarvisKit`: 261 tests, 0 failures, 0 skips (`/tmp/c5-kit-full-final.log`).
- `swift test --package-path macos/MortimerHost`: 659 total, 0 failures, 7 existing skips. Host631/3 dual-display skips; authority28/4 optional offline owner-harness skips (`/tmp/c5-host-full-final.log`). Both final full commands exit0. No test skips or timeout increases added.
- All9 ConsoleActionBar and all3 CompactConversation tests passed after integration fixes. Native rendering/revision/privacy regressions included in final full suite.
- `git diff --check` clean; retired source grep empty under Host/Kit Sources.
- Inspected wide, flat narrow, and integrated720 native screenshots. Wide SHA256 `2171957289613a6b3d5b0521a4f2131f607bacc1f47cc749a46af8d464cbb054`; integrated `eade6f5d6ddf3340642f3caf14f5c0831d2f85e2978117fa00e4adfcc24176bd`; flat motion/transparency `c7312d82d5087647fa45c07a2608658b9f2d57a208ae6e747c599611ab97012c`. Fixtures generated in the package's .build/interface-fixtures directory, not committed binary artifacts.

Next actor: Kimi independent review. Hosted B1 Swift must pass on the published exact head; draft publication is not readiness or acceptance. Final-build hardware/VoiceOver/Instruments GPU acceptance remains unclaimed. Base next hosted Swift is green (run43501487086), but that is not evidence for the new C5 head.

Published draft: [#370](https://github.com/Larryfix71566/jarvis-voice-ai/pull/370), base next, source commit `7b2a806`. Final staged check removed one redundant blank line at EOF only; no executable source change after tests. Exact-head hosted checks remain pending at publication.
