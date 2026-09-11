# Adaptive interface baseline and header progress

Status: implementation in progress; no release acceptance claimed.

## Baseline

Source: `30850f970749b230d5003ea5dfb3ae47e617eb59` (application behavior
from `2ccf66cd7e00b82cf9136d2cd00f42e9bddb90af`, plus interface plan).
The disposable offline Mortimer profile VM ran both existing native suites:

- JarvisKit: 96 tests, zero failures. Log SHA-256
  `249a2a5dacae82fd6ea7ec46fa18aa86835107250149f7bc539cc55bdf3ba4d8`.
- MortimerHost: 39 tests, zero failures. Log SHA-256
  `f60753f8d9be117752a2a6e99cc1d3fe3496d75d75819770f6ba4f092aa93b37`.

Local evidence is retained in sandbox task `66fed310bde6`,
`interface-checks/baseline-results.json` and its named logs. These are
automated correctness baselines, not audio or rendering performance measurements.

## P1 candidate

The header is extracted into a presentation-only `DrawerTabStrip`. Existing
tab bodies, models, ordering, attention calculation and fixed close/pop-out
controls remain in `DrawerView`. Natural-width labels scroll horizontally;
overflow arrows target the nearest hidden tab, and selection/viewport changes
reveal the selected tab. Reduced Motion disables animated arrow scrolling.

Five viewport-policy tests passed alongside the 39 existing host tests before
adding the AppKit rendering fixture. This narrow result does not establish
visual or accessibility acceptance.

The rendering fixture currently fails: an NSHostingView in the sandbox XCTest
process exposes an empty accessibility tree. Correcting its imported protocol
and window lifetime removed compile errors and a test-window teardown crash;
all eight label assertions still fail. Latest check
`p1-header-visible-window` ran 45 tests with eight assertion failures, SHA-256
`a13996ac19b5714e706c43bbb942c9b9c8a13242a3cfe9dba9b0e7b75dca32fc`.
Do not skip these assertions or treat an empty accessibility tree as a pass.
Determine whether the harness needs accessibility activation or whether the
view itself fails before completing P1.

A follow-up activation probe using `AXEnhancedUserInterface` on the XCTest
process returned AX error `-25208`; the eight label assertions remain failing.
Check `p1-header-accessibility-activation` log SHA-256:
`2d0cff0490a429d5c718f1863143558cf073156828b27e018f2f13c8fd6e41ab`.
An actual app-hosted accessibility fixture is the next harness avenue; this
probe does not establish an application accessibility defect or a pass.

## Open gates

### Rendering harness resolution

The wide-header label fixture now passes. In-process
`AXEnhancedUserInterface` activation exposes the SwiftUI nodes. Those nodes
implement the public `accessibilityLabel`/`accessibilityChildren` selectors
without declaring formal protocol conformance, so the fixture reads those
selectors after checking support. Exact expected labels use the existing
uppercase header presentation; all eight complete names remain asserted.
No existing test was removed or skipped. The fixture is still only a
wide-header label check, not interaction or comprehensive VoiceOver acceptance.

Latest full host check with the P3 preview: `p3-console-header-labels`, 51 tests,
zero failures. Log SHA-256:
`b95a7f8d3e0fb8def1dbdd194416fd33ffec238e5b0d33729aa7b6609e4f1a31`.
The earlier failures above remain as diagnostic history, superseded by this run.

- P0 functional screenshots, hardware/performance baseline and safe real
  input/playout observations. Existing simulated amplitude is not evidence.
- P1 rendered/accessibility checks, keyboard and voice selection, narrow and
  detached headers, large text, draft and polling preservation.
- P2 through P6 remain incomplete, including complete backend/profile gates,
  integrated results/graph/monitor behavior and real-device acceptance.
- No candidate has been deployed. This record authorizes no merge or release.

## Narrow selected-label evidence

At source `60a6cda` plus the new test, a native 300-point standalone tab strip
opens with Costs selected. Accessibility frame assertions verify the complete
COSTS text lies inside the scroll viewport after subtracting outer padding,
fixed arrows and control gaps. An empty accessibility tree fails the test.
Full host check `p1-narrow-tab-viewport`: 96 tests, zero failures, no skips;
SHA-256 `4455dd69236e6fea60fa66b32642b1dff6ee684daa37c6bc92c5dc3d6c4b00e7`.
This proves this initial selected-label case only. It does not establish actual
DrawerView chrome sizing, all tab selections, arrow/keyboard/voice interactions,
large text or full VoiceOver acceptance. Those remain pending.

## All mounted header selections at narrow width

A new native header test keeps one SwiftUI header mounted at 300 points and
changes its observable selection through all eight tab keys in forward and
reverse order. At each step it verifies the entire selected label's accessible
frame is inside the scroll viewport, excluding outer padding and fixed overflow
arrows. The original restored-last-tab and wide-header tests remain intact.

Sandbox full host check `p1-all-tab-selections`: 104 tests, zero failures; verifier
16.509 seconds. Log SHA-256:
`8753691b69032bf8f8d251af2d4a6d339770dcda40e4dd5ed284c13abd988e65`.
This proves selection changes in a mounted narrow strip reveal every selected
label without reconstructing the header. It does not prove keyboard/voice event
routing, arrow-button activation, large-text behavior, all tab bodies or detached
drawer chrome. Those requirements remain open independently.

## Overflow arrow activation

The native 300-point header test now invokes actual accessibility press actions
on the right arrow until it disables, then on the left arrow until it disables.
It checks each end label is fully inside the scroll viewport and the selected
Repo tab never changes as a consequence of scrolling. This exercises the actual
ScrollViewReader action and end-of-scroll disabled state, not just policy math.

Full host sandbox check `p1-overflow-actions-fixed-harness`: 105 tests, zero
failures; verifier 20.713 seconds. Log SHA-256:
`a4a50ff3baf7d0b7fb97262f6061aa1949596b279998dc1762272a222652558b`.
The first harness did not compile because macOS exposes the Reduce Motion
environment key as read-only; it was corrected to use the actual system setting
and allow the existing animation to settle. No production change or weakened
assertion was needed. This does not claim a Reduce Motion test, physical pointer
or wheel input, keyboard navigation, or all-tab-body acceptance.
