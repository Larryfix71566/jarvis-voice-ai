# Reduced-motion scheduling correction

Status: implemented and native-suite tested; P2 and integrated acceptance remain open.

Independent verification of application commit `88e2f07` used candidate fingerprint
`d3b1d39fbcfbd229600957c8a7df29072f5583c08382339fe40db7acc7d9ebb4`,
trusted baseline `68a5ce8`, task `f52430e233ac`, and attempt
`3d529cf1a1f44558b5ec524861e23ec5`. All 12 installed profile checks completed.
Eleven passed; candidate MortimerHost failed. Both backend suites passed within
900 seconds (327.802 and 314.255 verifier seconds). Source remained unchanged.
The failed receipt is retained; it is not a passing full-profile gate.

The candidate failure was `testReducedMotionKeepsVisibleWaveStatic`: the
presentation callback count advanced from 8 to 10 during the static observation
interval. Its visible-window prerequisite passed. Native log SHA-256:
`14775585502e17dbb05a6d756842203011a550c4e2d093b0143b71dee67321ae`.

The adaptive reduced-motion branch now renders its Canvas directly instead of
using a paused animation TimelineView. It has no animation schedule or
visibility-driven sampling. State-driven view updates still supply presentation
and accessibility labels. The normal animation branch retains its visibility
observer, suspension and resume behavior; the legacy rollback path is preserved.
No audio transport, capture, playback, metering, assertions or test timing changed.

## Diagnostic verification

After the independent attempt completed and stopped, its disposable offline VM
was restarted for diagnosis. Only the reviewed wave source was transferred.
These subsequent checks do not replace or modify the earlier failed receipt.

- Initial edit failed compilation due to a missing explicit return in the
  extracted computed property. Corrected before the final run. Log SHA-256:
  `33142eae0d07ca2db48562f2fb69335833aec3f810895919845e74169d608dbb`.
- Next full native run passed the sample-count assertion but failed the
  visible-window prerequisite. A guest assistantd test-keychain dialog was
  observed afterward; this observation alone does not prove causation. Log:
  `29e1e8c8deb6f3ae2722da0191afe043e29c4054e3ecd1ff0882694e8b818cb6`.
- The existing disposable keychain was unlocked, its test timeout set to six
  hours, and the dialog dismissed through CUA. No host keychain or vault changed.
- Final unchanged command: `swift test --package-path macos/MortimerHost`.
  **125 tests passed, zero failures**, 42.167 verifier seconds. Log SHA-256:
  `1fe74ba2ebf7c88d2f20188104210c3dce5d2a4dd51e7d22728e08dd2b342b69`.
  Existing reduced-motion and actual window hide/show tests passed.

Logs remain in host task `work/gui-checks/p2-reduced-motion-static-*`.
The VM desktop setup was completed through CUA during the independent run;
this is not unattended provisioning evidence. Graph interaction, physical audio,
multi-monitor, accessibility/performance acceptance and a new full-profile
receipt for the corrected candidate are still required. No deployment occurred.
