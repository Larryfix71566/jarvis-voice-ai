---
date: 2026-10-22
system: codex
rows: [WS-20]
prs: [221, 243, 246]
---

# Claude Max bounded documentation review

One official Claude Code request used the existing claude.ai Max subscription,
with tools/MCP/customizations disabled, no model override, no API-key route and
no live benchmark. The runtime reported `claude-opus-5-5`, one turn, success.
Payload SHA-256: `cbd5bdebfd7ae37de4f87c9e406854e482622705a2ff111f6236f7d65176f450`
(44,635 bytes of sanitized project documentation and proposed diff).
This review is of the supplied packet before the corrections below, not an
independent final-source approval, test execution or live acceptance.

## Codex disposition after review

- B-1: corrected the full runbook step to require current-request opening,
  fresh native cache reuse, unread/New notice, supporting-display ownership,
  and the canonical exclusions. Removed timing-only late-result classification.
- B-2: added explicit #210/#216 disposition rows: #222 repair is merged but
  the missing final exact-source cleanup review was recovered from #222’s body,
  independently digest-matched and preserved in the WS-20 evidence index; #223 provides the original #216 review and finding reconciliation while
  preserving its unresolved secondary coverage limits. No code defect is
  invented and no missing evidence is treated as a pass.
- Nonblocking comments: added validation source/hash linkage and handoff-log
  reference; named the implementation-status file; restored missing spaces
  and the cancelled-arrival exclusion.

Codex verified these corrections against the canonical criterion and repository
receipts. No second Claude call or claim of final Claude acceptance is made.
The original report follows unchanged.

---

# WS-20 completion documentation review (packet only)

**Verdict: 2 blocking findings.** The 2/4 count, B1–B4 completion and pending-milestone framing are correct. The UI2-23 runbook text and the treatment of two prior open obligations need correction before this can be called consistent with the canonical sources.

## Blocking findings

### B-1. UI2-23 runbook weakens and omits parts of the canonical criterion
**Location:** `docs/acceptance/ACCEPTANCE_RUNBOOK.md`, hunk `@@ -85,8 +89,11 @@`, step 2.

| Canonical UI2-23 | Proposed runbook | Drift |
|---|---|---|
| The proven current-request result "**opens** from Conversation or another result" | "…may open under Larry's approved October 18 exception" | "May" turns a required behavior into an optional one. A tester could pass a build where the current-request result never opens while reading. |
| "retained cards stay unread and use the existing New notice while reading" | Old line "preserves focus and gives a notice" is removed; nothing replaces it | The unread/New-notice check is dropped. "Verify … the canonical UI2-23 criterion" points to it but no longer states it. |
| "including fresh native weather-cache reuse" | Not mentioned | A named canonical case is missing from the procedure. |
| Unrelated/background, superseded, stale or **cancelled** never take focus | Unchanged earlier line: "a late/background completion stays a card" | "Late" is not a canonical category. A late result for a still-active request should open, so this line contradicts the exception it sits beside. |

**Suggested fix:** "From Conversation or while reading another result, the result proven to answer the still-active explicit request opens (including fresh native weather-cache reuse). Unrelated/background, superseded, stale or cancelled arrivals never take focus; retained cards stay unread and show the existing New notice while reading." Replace "late/background" accordingly and link the dated amendment, as the canonical criterion does.

**Related (non-blocking):** the §11 WS-17 bullet lists "background, stale, superseded and unrelated" and omits **cancelled**.

### B-2. Open obligations #210 and #216 drop out without an explicit disposition
**Locations:**
- Plan header `**Status:**` replacement.
- `IMPLEMENTATION_STATUS.md` new block: "The older cleanup/missing review statements below are historical: subsequent reviewed cleanup and native source verification are linked in §11."

The old header recorded "#210 cleanup findings and missing #216 cross-review remain open obligations." The new header omits them. The status note reclassifies them as historical and says the resolution is linked in §11. §11 has no row naming #210 or #216. Its only nearby evidence is the native compatibility receipt ("records reviewed cleanup and 12 checks at `e9c30b0`"). That receipt does not state that it closes the #210 findings or provides the missing #216 cross-review.

As written, this closes or retires two recorded obligations without traceable evidence, which conflicts with "preserve every existing … decision" and with keeping history intact.

**Suggested fix:** add a §11 row for #210 and #216 with either:
- an exact receipt or review reference showing each is closed, or
- a statement that each remains open under its owner.

If the evidence is not in hand, keep the open-obligation sentence in the header.

## Checks that pass

- **2/4 is a milestone count.** §11 ("count of the four WS-20 checklist bullets, not half-built software") and IMPLEMENTATION_STATUS ("not a software completion percentage") are explicit. The ROADMAP Status points to §11.
- **B1–B4 already complete.** The checklist preamble, ROADMAP Remaining work, plan header and §11 rows B1–B4 agree. No migration is repeated.
- **Decision and live evidence remain pending.** Both checkboxes are untouched and unchecked. The Next step, §11 gate table and closing line keep them open. The decision prompts are labeled "not answers or approvals," and silence is not treated as a decision. Warn-only remains in effect, consistent with plan §7.
- **Other-owner boundaries.** Claude keeps B4 and any CI change, WS-17 keeps #243 and release/install, and WS-03/05 and #240/#245 stay separate. No other-owner row or checkbox is edited. WS-18's accepted scope is preserved and not re-run for paperwork.
- **Other history.** §§9–10 are retained as dated inventories. The 10-18 runbook note is relabeled "(historical)," not deleted. The #246 continuity note is preserved.
- **Acceptance framing.** Source proof is kept separate from installation, physical acceptance and release throughout.

## Should-fix (non-blocking)

1. **Checked claims without a ref (protocol rule 10 / B3).** "A strict local invocation passes on this candidate" (§11 B4 row) and "currently passes" (decision prompt 1) do not name the commit checked. Cite base `636880e` plus #246 `028b44e`, or the candidate head.
2. **Scope sentence understates the change set.** §11 says it "changes only WS-20 documentation and the shared acceptance runbook," but the diff also edits `IMPLEMENTATION_STATUS.md`. That edit is within the authorized scope; the sentence is just inaccurate.
3. **Unreferenced owner confirmations.** "The previous acceptance owner confirmed no active WS-20 edits…" and "The sync owner froze #246" should cite a log entry or PR comment, or be worded as unverified.
4. **Typos.** "then22/23" and "dependent04/09/13" in the §11 WS-17 bullet are missing spaces.

## Evidence limits

- I reviewed only the supplied packet. No SHAs, PR states, CI results, receipts or anchors were checked against the repository or GitHub.
- Unverified: #243 open at `946f655` with five green checks; `#156 → ae70f2c` (the plan also records `ae70f2c` as the #159 deployment refresh, which is plausible but unconfirmed); the merge SHAs for #221, #152, #147, #142, #160, #158 and #191; and that C1–C5 are in §0.
- I did not check that the `#11-ws-20-completion-candidate--2026-10-22` anchors resolve, or that the checker's strict mode passes.
- This is a documentation review only. It grants no acceptance, decision, merge or release, and it does not substitute for Larry's checker-policy choice or owner live evidence.
