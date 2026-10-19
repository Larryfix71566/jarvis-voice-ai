# WS-17 current-request foreground: reviewed candidate evidence

Implementation source: `0f2af668028fe75827bb061ba32e5f22a86e6598`, based on
merged claim #225 (`c244963`). The publication adds documentation/evidence only
after that freeze; the runtime/test manifest in the [scrubbed receipt](ws17-current-request-2026-10-19.json)
must remain identical. This records implementation and offline gates; it closes
no UI2, physical-Mac or release acceptance checkbox.

The approved exception opens only the answer proven to belong to the still-active
explicit request, including from another result. Background, unknown, cancelled,
superseded and duplicate arrivals retain focus. Supporting-display ownership and
independent Atlas/Skills/Workflow/Memory navigation remain protected. Native
weather UUID, original fetch time, expiry and source/privacy guards are preserved.

The same synthetic two-city SDK/transport/router/store witness fails two
second-city assertions on unchanged `c244963` runtime and passes the candidate.
This distinguishes the new approved policy from the former no-jump behavior.
The temporary baseline test overlay was removed. Additional regressions cover
actual synchronous frame/function dispatch, upstream speaking echoes, copied
boundaries, reused runners, detached children, cancellation/reordering and one
foreground winner; cached Spartanburg → Atlanta → Spartanburg retains identity.

## Verification

The supported independent verifier completed all **12 original ordered checks**
on candidate fingerprint
`1055551a180438004174512325ab3e0e7196e10f7c224e414ba7b63ca5adc917`
against approved baseline `08c0635`. Its `source_commit` field denotes that
protected baseline; it is not the candidate's implementation revision. Profile
and runner fingerprints, actual commands and per-log hashes are in the receipt.
The verifier checked frozen source after execution and validated receipt/log
hashes. Both newly owned clones were removed; existing assets were preserved.

| Check | Result |
|---|---|
| Baseline / candidate backend unit suites | 6,280 / 6,606 passed; 11 existing skips each |
| Scripted evals / latency / web build | 13 evals passed; latency budgets and build passed |
| Baseline / candidate knowledge-base suites | 17 passed each |
| Baseline / candidate native libraries | 227 / 235 executed; zero failures |
| Baseline / candidate native apps | 514 / 572 executed; seven / eight prerequisite skips; zero failures |
| Local candidate Python unit + integration | 6,803 passed; 15 existing skips; zero failures |
| Local native app / library | 572 / 235 executed; five app prerequisite skips; zero failures |

Local native files are byte-identical between tested `6d777eb` and `0f2af66`.
VM capture/display/activation skips and local display/activation skips are
limitations, not passes. Local capture regressions executed with their original
privacy assertions. Earlier failed runs are retained: the XCTest execution-
sandbox abort reproduces on baseline, and all five dotenv-contaminated Python
failures reproduce on baseline. Process-only isolation resolves those environment
issues. Two incomplete STT mocks were aligned with the actual FrameProcessor API;
no assertion, runtime check, skip list, timeout or budget was weakened.

## Independent source review

Claude Code 2.1.291 / `claude-sonnet-5` completed the full source/test static
review and a bounded reconciliation on unchanged `0f2af66`, with tools/MCP/hooks
and persistence disabled. Original reports and failed/blocked attempts remain
local; the receipt preserves report/packet hashes and dispositions.

1. **INVALID:** alleged non-string `.split` crash. Existing
   `is_real_user_message` requires nonempty string content before selection;
   actual imported helper/pipeline probes reject six non-string cases without
   exception or authority and accept the matching string control.
2. **NON-BLOCKING:** clearing foreground eligibility on uncorrelatable final
   input is deliberately conservative. A possible new input cannot leave a
   prior token eligible; valid new input recovers, while foreign/unknown control
   envelopes cannot revoke a good binding. Reduced auto-open availability on
   noisy or malformed finals remains a UX tradeoff for live observation.
3. **NON-BLOCKING:** matching backend/native versions are needed for the new
   attestation behavior. The backend emits `console/turn`; native advertises
   the host-only inventory marker; backend gates the additive cache argument.
   Mixed versions preserve legacy/card behavior; compatibility tests do not
   establish a coordinated-release or live pass.
4. **NON-BLOCKING:** historical heuristic test helpers are no longer used for
   router eligibility. Optional cleanup is not an added release requirement.

Final reviewer verdict: **No blocking findings.** The reviewer ran no tests and
relied on supplied source and synthetic probe evidence. The second pass was
bounded finding reconciliation, not a full second review. The native contract
probe compiles the exact production class and JSONValue, without instantiating
the renderer/router; full caller-chain tests are separate evidence. No physical
Mac, installed-build, CI, deployment or daily-driver acceptance is inferred.
