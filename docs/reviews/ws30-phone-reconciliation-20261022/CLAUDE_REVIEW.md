# Review: Mortimer phone plan revision 4 (frozen) + revision-5 §13 delta

**Verdict: REVISE** (documentation-level corrections only; no design re-opening needed before S0 claim).

**Review limits:** architecture prose only. I did not inspect source, main `2944080`, candidate head `ebbad57e`, PR #240, hashes, line references, or the controller-plan document. §13's "Evidence at main" table and all SHAs are treated as author claims. Nothing here verifies that the S0 harness, fixtures, or any A/S0 scenario would pass, and S0 as scoped cannot demonstrate production auth, revocation timing, or remote-access properties.

## Disposition of prior review items

- **B1 (reservation-producing item):** satisfied in text. Item 0.2 "Done when" now files the exact table/column/config/host-marker list as a WS-04-coordinated reservation request; 1.1 dependencies require citing approved IDs; A16 audits scope. §13 correctly states S0 cannot close B1.
- **B2 (stale-backup mechanism):** satisfied and correctly strengthened. The author rightly rejected a DB-resident epoch (restored with the snapshot) in favour of a host anchor outside the backup set, with pending/commit/finalize ordering and explicit full-host-rollback limits. One internal contradiction remains (Finding 2).
- **Phone-context / media-listener clarifications:** scheduled as requested (0.3/2.2/A19; 0.2/2.1/A20), excluded from 1.4, and §13 keeps them open.
- **Revision-4 parity matrix:** consistent with existing phases — D1–D4 reuse 3.1/3.2, name owning dependencies, add P01–P04 as obligations not tests, and the matrix does not expand the 1.x packet. No ownership contradiction found; the matrix's "Initial scope" column correctly conditions conversation on "authorized 2.x".

## Prioritized findings

**1. §13 "Evidence and review provenance" + decision table row 1 — same-path collision with frozen #240 (blocks doc integration).**
*Failure:* The delta modifies `docs/plans/MORTIMER_PHONE_ACCESS_PLAN.md`; §13 states main has no phone-plan file and that frozen #240 is "preserved" and revision 5 is "a separate integration candidate." If #240 also adds that path, two PRs introduce the same file: either #240 merges first and the rev-5 PR must rebase onto it, or #240 is superseded and closed unmerged. "Preserve frozen #240; integrate corrected documentation separately" is not executable as written.
*Smallest correction:* Add one sentence: "#240 remains a frozen reference and is closed without merge; revision 5 supersedes it on main" — or the inverse ordering — chosen by the coordinator and recorded in §13 with the resulting plan file SHA.

**2. §4 "Trusted recovery boundary" vs §4 pairing item 6; S0-03/S0-05 — session sign-out collides with global generation.**
*Failure:* The B2 paragraph says every security-authority mutation "including grant **or session** revocation" advances the host anchor, and a global generation change "conservatively invalidates all live remote sessions." Item 6 says "sign out this session" is a "separate, narrower action." Combined, any single-session sign-out would close every peer and force all devices to reauthenticate. S0-03's expected result ("every fake peer closes") is ambiguous for session-scoped revocation, so independent fixture authors cannot write a correct expectation. Also unspecified: whether peers close at pending-mark or at finalize.
*Smallest correction:* Restrict anchor advancement to grant revocation, credential registration/replacement, and authorized restore; record session revocation at the session generation, enforced per request/emit within the five-second bound. State that affected peers close when authority is marked pending, not at finalize. Update S0-03 to expect: session revoke closes only that session's peers; grant revoke closes all.

**3. §13 S0 "Meaningful verification" / "Exit and next claim" — non-tautology is asserted, not mechanised.**
*Failure:* The transition model and the assertions are both test-local artefacts from the same lane; "independently authored" names no independent party; the self-chosen "weaken one rule" mutation only shows the author's model disagrees with the author's own fixture. Crucially, nothing requires production 1.1/1.4 to run against `v1.json`, so a green S0 connects to nothing later ("no automatic promotion" is stated, but no *mandatory reuse* either). Without that, S0 is a specification exercise with no evidential path.
*Smallest correction:* (a) Each S0 vector names the §3/§4/§5 clause it encodes (clause-to-vector map in the fixture); (b) expected results are confirmed by a reviewer other than the model author, recorded in the S0 evidence log; (c) `tests/fixtures/phone_admission_contract/v1.json` is declared the mandatory conformance fixture for the synthetic subparts of A01/A03/A04/A17/A18 in production 1.4, driven against the real admission boundary via an adapter. This makes S0 a reusable oracle rather than disposable.

**4. §13 S0-01/S0-03/S0-05 — missing authority/consume interleavings.**
*Failure:* S0-01 covers duplicate consumes; S0-03 covers revoke-versus-emit. Not covered: ticket issued → grant/session revoked → consume attempted within 30 s (bot's "verify current grant at consume" is the only defence and is untested); ticket issued → ordinary restart → consume (should fail since restart invalidates pending tickets); anchor marked pending while a peer is mid-emit. These are exactly the races §3 claims to close.
*Smallest correction:* Add three sequences to S0-01/S0-03/S0-05 with expected "denied, reason = authority-stale / ticket-invalidated / authority-pending; no emit after pending mark."

**5. §13 claim scope — WS-30 hosting admission-contract tests without WS-04 acknowledgement; suite wording.**
*Failure:* §6 states WS-30 is documentation intake only and implementation extends WS-04. S0 lands a WS-04-domain contract (tickets, revocation, anchor) under a WS-30 roadmap block. The decision table has no WS-04 row for S0 itself, only for production work. Also "Do not run the broader suite … as part of S0" reads as a request to skip repository verification; a new `tests/unit/*.py` file will be collected by any full run regardless.
*Smallest correction:* In the claim text: "S0 is a specification artefact under WS-30; WS-04/WS-17/WS-21 owners notified; confers no ownership of their scopes; production conformance tests move under the WS-04 1.1 claim." Replace the suite sentence with: "S0 claims no broader-suite result; the claim's verifier runs the repository's required checks."

**6. §13 provenance and fixture constants — review anchoring and value sensitivity.**
*Failure:* §13 records #240's SHAs but no revision-5 content hash or candidate head (`ebbad57e` was supplied to me externally), so a new review receipt cannot bind to this text. S0-04 hard-codes 15-second reservation and S0 uses 30 s/5 s from unratified decisions 4/10; expected results written against literal values will break on ratification and could be mistaken for ratification.
*Smallest correction:* Add rev-5 frozen plan SHA-256 and candidate head to §13 at freeze; declare timing values as named fixture constants with the note "expected results are relative to these constants; changing them changes fixtures, not rules."

Lower-priority (not blocking): decision 12 formatting; §13 term "catalog-bound SAYGM" is undefined in this plan — cite the provider-access definition or drop it.

## Decision list

| Actor | Scope | When |
| --- | --- | --- |
| Coordinator | Decide #240 supersede-vs-rebase (F1); record outcome and rev-5 SHA in §13 | Before doc integration |
| Author (codex lane) | Apply F2–F6 text edits; refreeze; record hash | Before new review receipt / doc integration |
| Coordinator + WS-04 owner | Register S0 test-only claim with WS-04/17/21 acknowledgement line; confirm no path overlap | Before any S0 test source is written |
| Independent reviewer (not model author) | Confirm `v1.json` expectations against cited clauses; sign S0 evidence log | During S0, before S0 integration |
| Larry + WS-04 | Origin/RP ID, passkey sync policy, local onboarding method | Before 0.2 reservation request / production 1.1; not S0 |
| WS-04/security owner | Approve reservations and anchored restore contract (B1/B2 proof) | Before production 1.1/1.2 |
| WS-05 + Larry | 0.3 voice disposition with owner/date | Before 1.3; blocked state permitted |
| Controller/provider/WS-20/WS-24 owners | D1–D4 host contracts | Before any parity dispatch; not initial slice |

Once F1–F2 are applied and F3–F6 reflected, the delta is fit for document integration and a bounded S0 claim; none of this requires live setup, and no S0 result should be reported as satisfying any production property.
