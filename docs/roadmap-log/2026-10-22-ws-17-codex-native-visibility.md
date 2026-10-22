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
