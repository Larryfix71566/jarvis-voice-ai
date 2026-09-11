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

## Isolated P1 review artifact

Draft PR #66: https://github.com/Larryfix71566/jarvis-voice-ai/pull/66
Remote commit `fdf1b89d768c1ed9c9b056a61ecd00f30a52f673` has tree
`38d1f111847668bd2ccdcf261af480878503992b`, identical to isolated local commit
`92ff56f25546b72669615f9095478aa2120f8eeb`. The five-file phase preserves the
original tab bodies and view-model ownership, separating later P3/P5 changes.

All 12 installed profile gates passed in independent attempt
`2d8a311c8cc9454499bda7a25cbb9b13`, development task `091a6729bb74`, with
unchanged frozen source `8756eddb4d6e08934c0e36e10f28a3ea17ec1527de5b3f104239bd1b56babf9a`.
Candidate native app: 48 tests, zero failures. Receipt validation checked all
log hashes. The PR remains draft pending GitHub CI and the explicitly listed
manual P1 acceptance. It has not been merged or deployed.

## Enlarged-text probe: acceptance remains open

The strengthened `p1-accessibility-text-measured` sandbox check failed on
2026-09-11: one test, 16 assertions, with every selected control still 32 points
high after applying `.dynamicTypeSize(.accessibility3)`. Log SHA-256:
`50ada9a3c0a56338af49d1555f7d318c77e25f57bb958a166f28676c8d0c02ad`.
The earlier `p1-accessibility-text` pass did not measure enlargement and must
not be used as enlarged-text acceptance evidence.

Apple's EnvironmentValues.dynamicTypeSize documentation explicitly says that
on macOS the value does not affect text size:
https://developer.apple.com/documentation/swiftui/environmentvalues/dynamictypesize
This explains the ineffective fixture, rather than proving that real enlarged
text has been tested. The current ScaledMetric is not evidence of macOS text
scaling support.

Next implementation must provide a real, user-reachable text-size mechanism
(or verify a supported native mechanism), size the strip from that typography,
and test actual label enlargement as well as complete label visibility. A
test-only size injection with no production path is insufficient. Preserve
the failing assertion until the replacement measures that behavior; do not
lower its threshold or mark this requirement accepted. The isolated P1 PR
and its earlier receipt do not include this probe or resolve this gate.

### Real tab typography implementation

DrawerView now exposes a fixed Aa menu with Standard (11pt), Large (16pt)
and Extra large (22pt) tab typography, stored separately from existing drawer
preferences. DrawerTabStrip sizes its actual font and header height from this
value, clamps malformed values, and reveals the selected tab after content
width changes. This changes header typography only, not tab contents.

Offline check `p1-real-tab-text-size` passed the full host suite (107 tests),
30.745 seconds; SHA-256
`9122a9a3e78ed93a6ce93f5806d5b3568dca0141790604c1929f132af07b40a7`.
The enlarged fixture now uses the same 22pt production parameter, retains
the greater-than-32pt control assertion, and checks all eight selected labels
in both directions at a 300pt strip width. This resolves the ineffective
Dynamic Type fixture; it does not establish actual menu interaction, preference
restoration, complete drawer chrome fit, or comprehensive large-text acceptance.
Those remain required, including mounted size changes without selection loss.

### Mounted typography and integrated console checks

`p1-standard-large-console` passed the full native host suite on 2026-09-11,
33.866 seconds, log SHA-256
`d392752419a50689eecb4914f62cc523386f41b951f42fa49c7bfe09bdc8e84e`.
The mounted strip now changes from 11pt to 22pt for every tab in both
directions, retaining selection and asserting the enlarged selected frame
remains completely in the scrolling viewport. Full console fixtures retain
standard typography coverage and add 22pt at all five existing dimensions;
Output, the typography menu, mute and wake controls remain inside the window.
These are offscreen native fixtures, not hardware display or menu-action
acceptance. Actual menu selection and preference restoration remain open.

### Isolated PR CI completion

GitHub check-runs for PR66 head
`fdf1b89d768c1ed9c9b056a61ecd00f30a52f673` were rechecked on 2026-09-11.
All five completed successfully: validate, allowlist, controller-tests,
policy-tests and knowledge-base. This is the isolated original header change;
it does not cover later typography additions or imply manual acceptance.
No merge or deployment was performed.
