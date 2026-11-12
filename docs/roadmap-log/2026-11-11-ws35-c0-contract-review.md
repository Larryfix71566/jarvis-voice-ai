---
date: 2026-11-11
system: codex
rows: [WS-35]
prs: [332]
---

# WS-35: independent C0/C0b contract review

**Verdict: changes requested before C3/C4 consume the contract.** This is a documentation review, not an implementation or live-acceptance pass.

- Reviewed PR #332 at `1f8aca7ee086912d1c9ffddcedbd65af738ca38b`, targeting `next`.
- Source evidence: freeze `5777e98cf1cdbaa65eb13079044693794c071927`. The cited Python and Swift files are unchanged in the review worktree, based on `next` `a1369e223e51cc499c8f942fae95133994a4facb` with main `4a0dd9635227cce51b01fcfcd584b3850ae81042` merged first.
- System/session reference: Codex, `codex/ws35-contract-review-20261111`, Larry's 2026-11-11 release-closure starter-prompt dispatch and explicit approval to follow its review-publication/claim exception.
- Scope: Codex leads contract sections 1 and 4; read sections 0, 6 and 7. Kimi's separate section 2/3/5 review is still required. Larry's five section 7 decisions are retained, not reopened.

## Findings

### R1 (P2): define identity and ordering for layout fallback

Contract section 1.3 line 85 puts `revision` only inside `layout`; section 1.5 line 149 requires a higher revision to replace an existing `answer_id`. Section 1.8 requires unknown or invalid layouts to fall back to legacy content, and section 1.10 explicitly permits the composer to remove `layout` when the answer is too large. It does not remove `answer_id` or define how that fallback updates an existing card.

Concrete case: revision 1 is displayed, then the same answer exceeds the limit and is sent with legacy fields but no layout. The client has no revision with which to satisfy the replacement rule. Dropping the message loses the new result; treating it as new duplicates the card; accepting it unconditionally permits a late fallback to overwrite newer content. This affects the advertised lenient decoder, not only malformed input.

Required clarification: give answer updates an ordering field outside optional layout (or specify an equally unambiguous replacement/fallback rule), including unknown-version and absent-layout cases. Add fixtures for a valid answer followed by a fallback update, replay/out-of-order fallback, and the reverse transition. Identity, pins and placement must remain stable.

### R2 (P2): finish answers for direct-tool-only and no-origin results

Section 1.5 lines 140-145 starts every first result as incomplete and identifies `delegate_done` as its completion point. Existing direct weather (`pipeline.py:1319-1323`), brief (`1373-1374`) and direct display (`1552-1560`) paths send results without a delegated agent run. The direct-tool comment explicitly says there is no agent run. The no-origin watcher case also receives a new answer identity but no terminal rule. These answers cannot rely on `delegate_done` to become complete.

Required clarification: define the completion signal for the foreground request (including multiple direct tools and sequential delegations), immediate/terminal behavior for one-shot background results, and bounded retention after completion. Do not mark a whole request complete merely because its first delegation finishes if another can still start. Add tests for direct-weather-only, brief-only, two sequential direct results, one-shot watcher output and delayed results after request completion. This gives C3 a contract for `complete` rather than leaving clients permanently waiting or independently inventing its meaning.

### R3 (P2): include the transcript-to-result route in the one-surface migration

Section 4.2 lists caption and compact-rail readers to retire, but omits `AppMessageRouter.swift:46-54` -> `ResponseResultRouter.receive` (`ResponseResultRouter.swift:15-58`) -> `DisplayPayload(responseText:timestamp:)` (`AppMessage.swift:245-255`). This route builds result cards from assistant transcript text and forwards them to the display window. It is disabled by the current default thread flag, but remains reachable with layout 2 and `mortimer.interface.conversationThread=false` (`ConversationThreadView.swift:11-28`). Deleting layouts 0 and 1 alone does not retire it.

The section 4.3 first grep misses this dataflow because the subscriber calls its input `entries`, not `conversation.entries`. Its third grep also matches explanatory comments and test fixtures, so its stated allowlist is not an exact executable proof.

Required clarification: assign removal/disablement of this legacy route and treatment of the persisted thread-off preference explicitly to C1a or C5. Include the transcript subscriber/response payload initializer in the audit, distinguish executable consumers from comments/tests, and require a regression with the old preference false: ordinary assistant speech creates no result card and no second-screen transcript. The Log tab remains the approved history exception.

## Verified and retained

- The optional-layout approach can preserve legacy rendering: `DisplayPayload` decodes declared keys and already uses lenient decoding for weather/brief/roadmap. No new message type is necessary.
- The protected callback strips results to seven metadata keys (`base.py:324-335`); `is_sensitive()` fails closed without context (`sensitive_turn.py:79-93`). The contract must preserve these boundaries and the clipboard exception.
- The retired development operation result is `ok: false` (`development_boundary.py:21-26`) and the display formatter rejects it (`display.py:146-147`). The contract correctly avoids building a new approval path on the retired actions table.
- `origin_request_id` is stamped in `_prepare_app_message` immediately before transport serialization (`pipeline.py:2060-2095`), not in each formatter. C3 must capture that trusted identity before composition, or compose after stamping; passing a formatter payload directly will not provide it. Add an end-to-end emitter test, not only a composer test with a manually supplied id.
- Approved palette and system fonts remain as specified. No model, feature flag, runtime setting, protected source or production change was made.

## Validation

- Read current AGENTS, ROADMAP sections 0/2/4, CLAUDE, repository/doc maps, allow-list sequence, closure plan and approved orb spec.
- Checked open PRs into both `next` and `main`: #332 contracts; #333 Claude lane status. Did not modify either branch.
- Compared the cited Python/Swift paths to `5777e98`: no diff.
- Static source inspection only; no runtime implementation exists for this contract yet. Swift, Python integration and live acceptance suites were not run for this docs-only review.
- `python3 scripts/check_roadmap.py`: 0 errors, 0 warnings before edits; rerun after edits below.

## Handoff

Claude: address R1-R3 in #332 and identify the revised head. Kimi: complete the independent contract sections 2/3/5 review. Codex: prepare C10 instructions, then C1a in a separate branch; do not build C4 on the unresolved contract. Larry merges; this review does not authorize a merge or deployment.
