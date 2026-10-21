# WS-05 / WS-17 integrated verification

Verified preview: [`794a298e3498d1b6e3e4fa47519449f35c06bb3d`](https://github.com/Larryfix71566/jarvis-voice-ai/commit/794a298e3498d1b6e3e4fa47519449f35c06bb3d),
tree `ac0d7de6bc478154e90f035564227879edddb987`.
Related draft PRs [#232](https://github.com/Larryfix71566/jarvis-voice-ai/pull/232)
and [#233](https://github.com/Larryfix71566/jarvis-voice-ai/pull/233).
All twelve original independent checks passed at 05:30 UTC. Owned cleanup and
source/settings/production/prior-asset preservation checks passed. No tests remain
active. This is a verified integration preview, not a merged or deployed release.

## Source and composition

The published `codex/ws05-ws17-preview-794a298` ref was fetched and verified
against the provider's immutable handoff. Actual parent is `1e6add5`; final provider
patches are replayed atop the earlier merge. `b1f07a2` is a declared content input,
not a direct ancestor; `d242ba4` is an ancestor. Provider non-acceptance program
bytes match `b1f07a2`; uncoordinated acceptance paths match `d242ba4`. No conflict
was reconstructed independently. Inspection confirms stop-turn delegation refusal
remains inside provider source-policy and run-log scopes. Both metadata handoffs
and current WS-05 history remain in the preview.

Candidate fingerprint:
`6936380978d675f9f936ef03d7855336119149288f0313f2c1a3f319ea915ceb`.
Protected baseline is `08c0635`; original image, profile, runner, protected fixture
bytes and prepared dependency key are unchanged. Reviewed cleanup source is
`1632afb`; scheduled cleanup remains paused. No scanner exemption, baseline,
check, prerequisite, timeout or assertion was changed.

## Executed checks

Full combined host backend: **6,925 passed, 15 skipped, two subtests passed**,
19 warnings, 244.89s, exit zero. The environment-isolated runner disables dotenv
and live calls; it uses a separate pytest cache. This is a combined-source run,
separate from earlier per-branch checks. Test groups overlap and cannot be summed
as acceptance obligations.

The complete original independent profile ran once, serially after the host suite:

| Original check | Result | Seconds | Log SHA-256 prefix |
|---|---|---:|---|
| backend-imports | PASS | 1.861 | `01ba4719c80b6fe9…` |
| baseline-backend | PASS | 425.279 | `bb8551ead62b1fb7…` |
| backend | PASS | 454.722 | `9f53348f1b633247…` |
| scripted-evals | PASS | 1.92 | `d39ad0e18b8672dd…` |
| latency | PASS | 0.115 | `c192bbb7b228dedb…` |
| knowledge-base | PASS | 3.229 | `9fa0cf112383d08b…` |
| baseline-knowledge-base | PASS | 4.905 | `ec2813e18100ccca…` |
| web | PASS | 31.027 | `f4b7089c49450fee…` |
| native-library | PASS | 88.091 | `226245b95f06456e…` |
| native-app | PASS | 213.253 | `361e7eea5a89a0dc…` |
| baseline-native-library | PASS | 22.885 | `f79a4a50a193966f…` |
| baseline-native-app | PASS | 183.018 | `4c73b68ff1865ef7…` |

Independent candidate backend: **6,728 passed, 11 skipped, two subtests passed**,
59 warnings. Candidate native app: **580 executed, eight prerequisite skips,
zero failures**; JarvisKit: 235 tests, zero failures. Baseline native app: 514
executed, seven prerequisite skips, zero failures. Skips include actual window
capture, connected external displays and active-app prerequisites; they establish
no physical-Mac pass. The latency check uses a synthetic fixture, not live-provider
latency. The 421-test conflict-focused receipt was supplied/read from its owner
and was not independently rerun.

The [JSON receipt](ws05-ws17-integrated-2026-10-21.json) records original command
arguments, full log hashes, source/test manifest, source graph/content proof,
image/profile/runner fingerprints and exact native skip reasons. Raw records and
operational identities stay local. Both standalone PR publication heads had five
CI passes; no combined-source CI or cross-system-review verdict is inferred.
Strict combined-source roadmap validation against explicit main `3061408` has
zero errors and zero warnings. The first lookup lacked `origin/main` in the
provider handoff and warned that branch checks were skipped; using the full main
hash executes the complete check. Publication metadata contracts: 57 passed,
two warnings,3.58s; all 144 checkbox and 29 owner lines are unchanged.

## Open gates

Earlier interrupted VM and non-passing host-native attempts remain in the
[standalone receipt](ws17-acceptance-repair-2026-10-21.md). Actual host capture
failed with SCK-3811 despite permission preflight, and isolation diagnostics had
unchanged nil-NSApp crashes. Read-only host inspection now establishes that an
unlocked, awake interactive desktop is required before a meaningful capture
recheck. Historical failure causation remains unproven. No new Screen Recording
grant or security change is requested; no unchanged retry was performed.

Parent-managed source-review consent remains pending: no source packet was sent
and no review verdict exists. Provider live runtime/account/schema/auth, measured
voice latency/interruption, bounded live consent and overage-disabled confirmation
remain open. Full-context classification is implemented and fails closed, but no
eligible protected/private/local route is selected. Choose and authorize an
eligible route, or keep activation held; never drop or relabel protected context.

No merge, deployment or canonical human checkbox closure. UI2-22/23/24/25 and
dependent UI2-04/09/13 remain open; human/visual and external-display requirements
need their actual observations. After release gates: one short session covers
roadmap/main-window/build truth, multi-turn references, speech versus task stop,
Spartanburg → Atlanta → Spartanburg reuse/opening, and observation versus reviewed
canonical Git readback. Five-day release observation and the separate WS-06 week
require real use and remain open.

This documentation publication preserves standalone runtime/test bytes at
`d242ba4`; integrated source remains the separate frozen preview above. Publication
CI is a separate check. No production records or private content are published.
