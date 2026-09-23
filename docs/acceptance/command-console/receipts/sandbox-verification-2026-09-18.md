# Sandbox verification receipt — 2026-09-18

This receipt records automated evidence from the release-review worktree at
HEAD `b224c84` with additional uncommitted sandbox changes present. It is
implementation evidence only; it is not the independent exact-candidate,
physical-display, provider, rollback, or daily-driver receipt required for
release closure.

## Commands and results

| Check | Result |
| --- | --- |
| `UV_CACHE_DIR=/private/tmp/jarvis-uv-cache uv run --with-requirements requirements-lock.txt pytest -q` | 2,611 passed / 4 skipped; 2 subtests passed |
| `swift test --package-path macos/JarvisKit` | 190 passed / 0 failures |
| `swift test --package-path macos/MortimerHost` | 241 passed / 0 failures |
| `swift test --package-path macos/MortimerHost --filter ContentPanelTests` | 15 passed / 0 failures |
| `pytest -q tests/unit/test_plan_manifests.py` | 7 passed / 0 failures |
| `git diff --check` | passed |

The complete MortimerHost run also regenerated the graph-performance receipt:

- p50: 9.198 ms
- p95: 11.414 ms
- maximum: 25.842 ms
- gate: p95 <= 33 ms, passed

## Behaviors covered by the latest sandbox changes

- CoreAudio startup is off the main actor, so a slow device negotiation does
  not freeze the Command Console during reconnect.
- Pinned display panels remain outside the default one-to-four-result stage;
  unpinned overflow is retired first and an all-pinned inventory refuses a new
  copy instead of evicting user content.
- Exact repeated window payloads reuse the existing panel and workspace owner.
  Distinct sections from one Developer `run_id` still append to one outer
  panel and retain distinct workspace history rows.
- The plan manifest covers the landed source, fixture, test, probe and
  acceptance artifacts for both active plans.

## Still open

The latest physical reconnect attempt did not settle at `READY VOICE`; the
receipt is `candidate-reconnect-attempt-2026-09-18.md`. Multi-display role and
unplug/reconnect behavior, OS share-picker delivery, VoiceOver, provider-backed
inbound content, rollback, deployment hashes, and the five-day daily-driver
period remain open release gates. Memory B6 remains in staged shadow mode until
the Mac rollout has reversible writes and redacted benefit/cost/error monitoring.
