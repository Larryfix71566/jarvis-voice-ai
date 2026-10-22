---
date: 2026-10-22
system: codex
rows: [WS-17]
prs: [237]
---

# Native visibility prerequisite — claim only

Registered the explicitly dispatched diagnosis/repair on
`codex/ws17-native-visibility-20261022` from `b97a8b3`, before native code edits.
Synthetic visibility fixtures must establish a real visible/unhidden window
before their original animation/occlusion assertions. Hidden/inactive fixture
failures and focused skips remain non-passing evidence. Test the cause and
retain all assertions; no source-policy, provider, settings, installer or
human-checkbox change is part of this registration.


## Hidden-after-show regression reproduced before repair

Claim #237 merged as `fccb760`. On the registered implementation branch,
a real WindowServer regression establishes a visible synthetic window and its
actual observer, then hides the owned test app after its initial show request.
The original preparation leaves it hidden: one test/four failed assertions/zero
skips. Existing hide/show/miniaturize/detach/animation assertions and observer
source are unchanged. The proposed correction remains test-only and must pass
the original full gate; a focused skip cannot substitute for a pass.


## Restore actual fixture state, preserving product assertions

The fixture checked frontmost activation before creating its window, despite
the observer correctly using visible/unoccluded/unhidden state. A late hide
after the first show left the fixture hidden during its original wait. A real
WindowServer regression reproduces that state with four assertion failures,
zero skips. Preparation now restores only its owned fixture while waiting for
actual OS visibility and the real observer callback, within the unchanged
three-second bound. Initial screen/regular-policy prerequisites remain; the
unnecessary frontmost-app skip is removed. All four original tests retain
every assertion, and all five focused tests now execute and pass with no skips.
No product observer or app runtime code changed. The
[synthetic receipt](../acceptance/command-console/receipts/ws17-native-visibility-fixture-2026-10-22.md)
pins the exact test bytes and red/green evidence; full/review/CI/release gates
remain separate. No human acceptance checkbox closes.


## Deferred hide after initial visibility — bounded follow-up

Combined `636880e` original comparison completed11/12; native581/five prerequisite skips/one visibility failure remains recorded. Three focused traces each passed five cases without skips, but one full-native trace reproduced visible/unhidden to hidden/invisible306ms after initial readiness. New real regression `845cb34` fails three assertions with zero skips after initial visibility and actual hide assertions pass. Test-only `334cf19` requires continuous settling inside the unchanged3s readiness bound, adds a stronger readiness assertion, and preserves all original assertions, negative waits and product source. [Receipt](../acceptance/command-console/receipts/ws17-native-deferred-hide-2026-10-22.md) distinguishes pending green/full/review/CI from live acceptance; no owner or checkbox changes.

Publication `157f195` focused six-case gate failed three initial-visibility assertions in the existing immediate-hide regression, with zero skips; the new deferred-hide case passed. Full original verification was not started. `00fa4a0` applies settled preparation to that remaining positive setup while keeping every original assertion and explicit hide phase. Its current-source focused/full/review/CI gates remain pending.
