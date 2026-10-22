# Native visibility fixture repair

A late hide after the initial fixture show reproduces four failed assertions
in one real WindowServer regression, with zero skips. The old setup also
required the test app to become frontmost before its window existed, despite
the product observer depending on actual window/hidden state.

The test-only repair restores its owned fixture while waiting for real
unhidden/unoccluded visibility and the unchanged observer callback. It retains
the original three-second bound and every assertion in the four original
tests. All five focused tests execute and pass, with zero skips. Application
and observer source are unchanged; no user app is hidden or reconfigured.

[JSON proof](ws17-native-visibility-fixture-2026-10-22.json) pins test bytes,
red patch, executed argv/log hashes and limits. Exact raw records remain local.
The product contract matches the actual state; no callback is synthesized.
Apple documents [restoring windows without foreground activation](https://developer.apple.com/documentation/appkit/nsapplication/unhidewithoutactivation%28%29)
as a separate operation. These focused results do not replace full native and
independent-profile verification, review/CI, installed-build or human/live
acceptance. No checkbox closes here.
