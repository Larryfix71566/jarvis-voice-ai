# LLM Council Acceptance Checklist

Manual acceptance for MORTIMER_LLM_COUNCIL_PLAN.md. Run the full stack
(`./scripts/mortimer.sh`) and set at least two `economy`-tier and one
`mid`-tier API key (e.g. `MOONSHOT_API_KEY`) so tier 1 can actually convene.
Tick each line.

## Happy path — no council involvement

- [ ] Give the Upgrade Agent a goal that validates cleanly on the first
      try. Confirm the run completes exactly as before this feature
      existed — no council round appears in `python -m jarvis.council
      --agreement`'s round count, and there is no added latency.

## E1 — automatic escalation on double validation failure

- [ ] Give a goal that reliably fails validation twice (e.g. one that
      edits a file just outside the allowlist alongside an allowed one).
      Confirm: a tier-1 council convenes (all `economy` proposers, all
      `mid` judges); one retry runs with the winning proposal's content
      injected as a `system` message; `council_rounds` has one new row
      with `trigger='E1'`, `tier=1`, and a `winner_profile`.
- [ ] If the retry ALSO fails validation twice, confirm a SECOND council
      convenes at `tier=2` (adds `frontier` proposers, judges become
      `frontier` only — never `mid`, and never the same tier twice).
- [ ] If the tier-2 retry also fails, confirm the session ends and
      reports exactly as a double-failure did before this feature
      existed (no third council — `COUNCIL_MAX_ESCALATIONS=2`).
- [ ] Confirm `council_rounds.retry_validated` is populated (1 or 0) once
      the retry's own `session_validate` call resolves.

## E2 — decline is a recorded fact, not inferred from prose

- [ ] Give a goal that is clearly off-allowlist (e.g. "rewrite the wake
      word detector"). Confirm the agent calls `session_decline` (visible
      in the run's tool-call sequence), not just a prose refusal, and
      that the run ends with `declined=True` in its result.

## E3 — human rejection

- [ ] Start a session, let the agent propose a diff, then click
      "Reject + ask council" in the Edit panel (without validating or
      submitting). Confirm the session reverts to its rollback tag AND a
      council round convenes (`trigger='E3'`), with the winning approach
      shown in the panel. Confirm NO new agent run starts automatically
      — the brief is advisory only until you explicitly start a new run.

## Manual convene

- [ ] With no active session, type a goal into the council's own input
      and click "Convene the council". Confirm a tier-1 round runs
      (`trigger='manual'`) and the winner displays with its
      `select_reason`.
- [ ] Start a session, leave the goal field blank, click "Convene the
      council". Confirm it uses the active session's own goal (shown as
      a placeholder hint in the input).

## Council never authors a diff

- [ ] For every council round above, confirm the winning `content` is
      prose (a plan), never a diff or file contents — the retry that
      follows still goes through the unchanged `edit_propose` →
      `session_validate` → `session_submit` path, authored by one model.

## Score integrity

- [ ] Open a round's detail (`GET /api/council/round/<id>` or the Edit
      panel's score table after a convene). Confirm every proposal has a
      score or an explicit abstention reason — never a blank/missing row.
- [ ] Confirm scores are in the 1.0–10.0 range in tenths; nothing outside
      that range appears as a live number (it should show "abstained").

## Council membership picker (D9)

- [ ] Open "Council membership" in the Edit panel. Confirm a profile with
      a missing API key is shown but its checkbox is disabled.
- [ ] Uncheck all but one profile in a tier. Confirm a warning appears
      ("select at least 2, or none") and "Convene the council" is
      disabled until you either add one back or clear the tier entirely.
- [ ] Reload the page. Confirm your selection persisted
      (`localStorage['mortimer.council.<tier>']`).
- [ ] Confirm `config/upgrade_models.yaml` is unchanged by any picker
      interaction — the picker narrows an existing registry, it never
      writes one.

## Shadow judging (D8.2.1)

- [ ] After several tier-1 escalations/manual convenes, confirm some
      rounds in `council_scores` have `shadow=1` rows from a `frontier`
      judge, and that `council_rounds.winner_profile` always matches
      what the LIVE (`shadow=0`) judges picked, never the shadow judge's
      preference when they differ.

## Offline replay and agreement report (D8.2.2)

- [ ] `python -m jarvis.council --replay <round_id> --judges frontier
      --dry-run`. Confirm it prints live vs. replay winners and scores,
      and that `council_scores`'s row count for that round is unchanged
      afterward.
- [ ] Same command without `--dry-run`. Confirm new `shadow=1` rows
      appear for that round and `council_rounds.winner_label` is
      unchanged.
- [ ] `python -m jarvis.council --agreement`. With fewer than 20 shadowed
      rounds, confirm it reports "insufficient data" and names the exact
      count. Confirm it never recommends a judge-tier change at this
      stage.

## Kill switch

- [ ] Set `JARVIS_COUNCIL_ENABLED=false` in `.env`, restart. Reproduce
      the E1 scenario above. Confirm no council round convenes, no new
      `council_rounds`/`council_scores` rows appear, and the session ends
      exactly as a double-validation-failure did before this feature
      existed. Restore `true` afterward.

## Regression — self-edit loop unaffected when council is idle

- [ ] Confirm a normal, single-attempt successful self-edit run (Edit
      panel: goal → validate → submit → PR) works exactly as before this
      feature — same fields, same PR body, same rollback-tag behavior.
- [ ] Confirm `python -m jarvis.runlog` and the console's Runs panel are
      unaffected — council rounds do not appear there (they are a
      separate table, viewed via `python -m jarvis.council` / the Edit
      panel's council section only).

---

# V2 additions (MORTIMER_LLM_COUNCIL_V2_PLAN.md)

Same setup as above. These items cover V1, V5, V12, and V14 specifically
(V2, V4, V6–V11, V13 are exercised indirectly by the scenarios above and
are otherwise covered by the automated test suite).

## V1 — tier-2 carries the tier-1 winner forward

- [ ] Reproduce the E1 double-escalation scenario (tier-1 retry fails
      validation twice again, forcing tier 2). Confirm the tier-2 round's
      proposal set includes the tier-1 winner's exact content as an extra
      candidate (visible in the round's JSONL payload under
      `logs/council/<date>/<round_id>.jsonl`, marked `"carried": true`),
      alongside the fresh `frontier` proposals — and that this carried
      proposal is excluded from the tier-2 judge pool (its own profile
      never scores itself).

## V5 — non-blocking convene

- [ ] Click "Convene the council" in the Edit panel. Confirm the UI does
      NOT block/spin waiting for the round — the button returns to an
      idle-ish "convening" state immediately and the page stays
      responsive, with the winner card appearing only once the round
      actually finishes (poll interval ~3s).
- [ ] While a convene is in flight, attempt a second "Convene the
      council" (e.g. from a second browser tab). Confirm it is refused
      with "a council round is already in progress".
- [ ] Click "Reject + ask council". Confirm the session reverts (note
      appears) noticeably before the council brief shows up — the revert
      is synchronous, the council result arrives later via polling.

## V12 — round visibility in the UI

- [ ] After any council round has run (E1, E3, or manual), open the
      collapsed "Recent rounds" section at the bottom of the council
      card. Confirm it lists the round(s) with trigger, tier, status,
      winner profile, and a retry-validated indicator (✓/✗/—).
- [ ] Trigger an E1 round (validation fails twice). Without touching the
      CLI, expand "Recent rounds" and confirm the E1 round is visible and
      clicking it loads its score table — this is what makes
      background-agent-triggered rounds reachable from the UI at all.
- [ ] Confirm every `council_rounds` row for a self-edit-workflow round
      has `run_id = NULL` (reserved, not wired up — see CLAUDE.md's LLM
      Council section) — this is expected, not a bug.

## V14 — E2 scope-advisor council

- [ ] Give a goal that is clearly off-allowlist (e.g. "rewrite the wake
      word detector"). Confirm the agent still calls `session_decline`
      (E2's original behavior, unchanged), AND that a tier-1,
      advisory-only council round convenes automatically (`trigger='E2'`
      is not a real trigger value — check the round's `placement='scope'`
      and that it appears in `python -m jarvis.council --agreement`'s
      round count) with the decline reason and allowlist as context.
      Confirm the run's final summary includes a
      "[Council scope advice]" section appended after the decline
      reason.
- [ ] Confirm this scope council does NOT count against
      `COUNCIL_MAX_ESCALATIONS` — reproduce the E1 double-escalation
      scenario in the same overall test session and confirm tier-1 and
      tier-2 E1 escalations still both fire normally.
