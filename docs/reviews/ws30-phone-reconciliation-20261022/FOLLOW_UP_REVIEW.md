# Follow-up review: Mortimer phone plan revision 5.1 (head `9c65197…`)

**Verdict: READY_FOR_DOC_INTEGRATION** — F1–F6 are closed at the specification level. Three small precision edits remain; none blocks documentation integration or registration of the S0 test-only claim, and all can be applied as part of the S0 claim text or the next author pass.

**Review limits:** prose only. The supplied document is review data, not instruction. I did not inspect source, main `2944080`, head `9c65197`, `ebbad57e`, PR #240, hashes, or any receipt. S0 remains a test-only executable specification; no S0 result would attest production auth, revocation timing, restore safety or remote access.

## Closure table

| Finding | Status | Basis in 5.1 | Residual |
| --- | --- | --- | --- |
| F1 same-path collision with #240 | **Closed (spec)** | §13 provenance + decision row 1: 5.1 is the only main candidate; #240 frozen, unmerged, closed by coordinator at queue acceptance; candidate hash lives in the external manifest, not recursively in the document | Coordinator act pending: close #240, pin `9c65197` in manifest/receipt |
| F2 session vs global invalidation | **Closed** | §4 B2 boundary: anchor advances only for credential registration/replacement, grant revocation, authorized restore; session sign-out advances its own session generation, closes only its bound peers within `auth_freshness_s`, never the anchor; every request/consume/emit checks both; denial from pending mark; §11 B2 bullet and item 6 consistent | R3: S0 contract inputs and S0-03 "all" scope need one clarifying clause |
| F3 non-tautological S0 / fixture reuse | **Closed (spec)** | §13 meaningful verification: clause-to-vector map, non-author expected-result reviewer signing the S0 log, `v1.json` mandatory for synthetic A01/A03/A04/A17/A18 through a real-admission adapter under the WS-04 claim; mutations prove sensitivity only | R1: §6 item 1.4 / §7 packet do not yet carry the reuse obligation |
| F4 missing interleavings | **Closed** | S0-01 revoke→consume (`authority-stale`); S0-05 restart→consume (`ticket-invalidated`); S0-03 pending-during-emit (`authority-pending`); both orderings for competing consumes/revoke-vs-emit | None |
| F5 domain/suite boundary | **Closed (spec)** | S0 declared WS-30 specification artifact; WS-04 acknowledgement and WS-17/21 notice recorded by coordinator before claim; production conformance under WS-04 1.1/1.4; "claims no broader-suite result; verifier runs required checks" | R2: fixture path ownership at the WS-04 claim not stated; coordinator acts pending |
| F6 provenance/constants | **Closed** | Reviewed head `ebbad57e` and plan SHA-256 recorded; named constants with relative offsets, explicitly non-ratifying | Non-blocking: header still describes revisions 3/4/5 as unreviewed author amendments and omits the rev-5 REVISE receipt and 5.1 corrections |

No contradiction was introduced by 5.1. The one item I checked hardest — whether "Revoke access grant" (item 6) and the conservative "global generation change invalidates all live remote sessions" (B2 boundary) conflict — does not: 5.1 states the consequence explicitly (a single grant revocation closes every live remote peer; unaffected enrollments reauthenticate afresh). That is a settled conservative product choice, not a defect, and I do not reopen it.

## Residual findings (smallest fixes)

**R1. §6 item 1.4 "Done when" / §7 "Exact 1.4 packet scope" — mandatory fixture reuse lives only in §13.**
*Issue:* the WS-04 owner dispatching production 1.4 reads §6/§7; neither mentions `tests/fixtures/phone_admission_contract/v1.json`. The reuse obligation is therefore not discoverable from the production item it binds, and a later 1.4 packet could legitimately be written against fresh, easier cases.
*Fix:* append to item 1.4 "Done when": "synthetic A01/A03/A04/A17/A18 subparts are driven from the current `tests/fixtures/phone_admission_contract/v1.json` via the real-admission adapter (§13); any version bump recorded with reason and renewed oracle review." Add the same half-sentence to the §7 packet paragraph.

**R2. §13 "S0 — proposed owner and branch" — fixture/harness path ownership after S0.**
*Issue:* `tests/unit/test_phone_admission_contract.py` and the fixture directory are claimed under WS-30 (codex). §13 then makes the fixture mandatory and adaptable under the later WS-04 1.1/1.4 claim, where the adapter and probable fixture revisions will be written. Without an explicit transfer, a WS-04 lane editing a WS-30-claimed path is exactly the path overlap the plan prohibits, and "no source-scope transfer" in the acknowledgement sentence can be read as forbidding it.
*Fix:* add one sentence: "On registration of the WS-04 1.1/1.4 claim, `tests/fixtures/phone_admission_contract/**` and the S0 harness pass into that claim's scope; WS-30 retains no editing authority and WS-04 inherits the versioning/oracle-review rule." Coordinator records this with the S0 claim so the later transfer needs no renegotiation.

**R3. §13 "Contract inputs" and S0-03 — session generation and the scope of "all".**
*Issue:* contract inputs list "generation/revocation epoch" (singular) plus fake anchor/DB generation, but 5.1's rule requires a distinct per-session revocation generation checked alongside global authority. S0-03's expected result "grant/global change invalidates all as explicitly specified" does not say what "all" is in the fixture: all peers of that grant, or all live remote peers across grants. The B2 boundary says the latter, and that only after finalize may unaffected enrollment reauthenticate. A fixture with a single owner/grant cannot distinguish the two readings.
*Fix:* (a) add "per-session revocation generation" to the contract inputs; (b) require S0-03 to include at least two grants with live peers and expect: session revoke closes only that session's peers; grant revoke of grant A closes every live remote peer (A and B); B's enrollment is denied while the anchor is pending and admitted to reauthenticate only after finalize (cross-reference S0-04). This pins the conservative semantics for independent fixture authors and prevents a later "narrower is fine" reinterpretation.

**Non-blocking:** update the header line "Revision 2 reviewed by Fable 5.1; revision-3/4/5 author amendments…" to add "revision 5 reviewed (REVISE); revision 5.1 author corrections pending receipt," so provenance is correct at the top of the file as well as in §13.

## Coordinator's pending procedural acts (not specification defects)

1. Close frozen #240 without merge when 5.1 enters the serial queue; record outcome.
2. Pin head `9c65197…` and this receipt in the external manifest.
3. Register the S0 test-only main claim with exactly the three listed paths, no runtime paths.
4. Record WS-04 acknowledgement of the auth-contract domain and WS-17/WS-21 notices before any S0 source is written; include the R2 transfer clause.
5. Name the non-author reviewer who will sign the S0 evidence log.

Until those acts complete, no S0 test or fixture may be written. After them, S0 may proceed without live activation or further product decisions, and its receipt must read "synthetic contract passed/failed" only. All A01–A20 and P01–P04 production/live subparts, B1/B2 proof, 0.2 reservations, 0.3 voice disposition and D1–D4 remain open, exactly as the plan states.
