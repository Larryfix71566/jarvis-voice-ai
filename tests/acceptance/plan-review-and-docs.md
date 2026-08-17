# Plan review + document consolidation — acceptance checklist

MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md. Manual, run against a live stack
(`./scripts/mortimer.sh`) with at least two usable model profiles in
`config/upgrade_models.yaml` (key present), including `claude-fable-5`
(R7). Not run by pytest, except where a §4 item names a specific
automated test/command.

- [ ] T1: `tests/unit/test_upgrade_agent.py` has the autouse `_isolated_db`
      fixture. Two consecutive `pytest tests/unit -q` runs add ZERO rows
      to `data/jarvis.db`'s `council_rounds` (compare
      `SELECT COUNT(*) FROM council_rounds` before/after both runs).
- [ ] T2 (one-time operator step — run AFTER T1 has landed, never wired
      into startup): clean up the pre-existing junk rows this test
      pollution left behind —
      ```sql
      DELETE FROM council_scores WHERE round_id IN
        (SELECT round_id FROM council_rounds WHERE status='too_small'
         AND goal IN ('validate me', 'rewrite the wake word detector'));
      DELETE FROM council_rounds WHERE status='too_small'
        AND goal IN ('validate me', 'rewrite the wake word detector');
      ```
      Run once via `sqlite3 data/jarvis.db` (or Python's `sqlite3`
      module, since this repo's containers may not ship the `sqlite3`
      CLI). Verify `council_rounds` no longer contains any `too_small`
      row with those two goals.
- [ ] Re-run the exact failure that motivated this plan: "have Fable 5
      review the geolocation plan and report gaps" →
      - STT surfaces the word "Fable" (R8's keyterm boosting) rather than
        "table five"/"Clyde's frontier model".
      - The Supervisor delegates to developer without ever saying "I
        can't", "I don't have access", or similar (R6's rule-8 sentence).
      - developer calls `plan_start` with
        `review_path=docs/plans/GEOLOCATION_DEVELOPMENT_PLAN.md` and
        profile `claude-fable-5` (R7) — never authors/reviews the
        document itself in the conversation.
      - `plan_status` reports drafting, then a finished review; the
        summary says "review", not "plan" (R5).
      - Adopting (`plan_adopt` / "Adopt as draft") lands at
        `docs/reviews/…` with the reviewer footer
        (`*Review by {profile} ({model}) — {date}. Reviewed:
        {review_path}.*`).
- [ ] Council-mode review: in the Edit panel's Planning card, set the
      "review an existing document" path, pick "council: parallel
      drafts", Start. Every usable profile produces a PARALLEL review
      (not a plan); judges score them advisorily; you choose one. The
      round's detail view (or `GET /api/council/round/{id}`) still shows
      every unchosen review's content — nothing is dropped. Adopting the
      chosen review appends both the reviewer footer AND, for
      council mode, "Selected by Larry from N council candidates
      (round {round_id})."
- [ ] `plan_start` with a nonexistent or denied `review_path` (e.g. a
      typo'd path, or `.env`) refuses SYNCHRONOUSLY with the read error
      — the job never transitions to "running", and no planner call is
      ever made (verified in `tests/unit/test_admin_plan_review.py`).
- [ ] A document over `PLAN_REVIEW_DOC_MAX_CHARS` (60,000 chars) reviews
      with the truncation notice
      ("… (truncated for review — flag this truncation in your
      verdict)") present in the injected content — unit-tested in
      `tests/unit/test_admin_plan_review.py`, not exercised live.
- [ ] `git log --follow docs/plans/implemented/MORTIMER_LLM_COUNCIL_PLAN.md`
      shows the file's pre-move commit history (D1/D2 moves used `git mv`,
      not delete+recreate). Spot-check at least one more moved file the
      same way, e.g.
      `git log --follow docs/plans/GEOLOCATION_DEVELOPMENT_PLAN.md`.
- [ ] No root-level `*_PLAN.md` remains (`ls *.md` at repo root shows only
      `README.md`, `CLAUDE.md`, `DEVIATIONS.md`, `ROADMAP.md`).
      `jarvis/docs/` does not exist. `docs/README.md` exists and matches
      D3's skeleton. `docs/plans/`, `docs/plans/implemented/`, and
      `docs/reviews/` all exist (the last may be empty until a review is
      first adopted).
- [ ] `CLAUDE.md` contains no stale path to a moved document — grep for
      each of the 19 moved filenames plus the 2 geolocation docs; every
      hit is prefixed with its new `docs/plans/...` location, not a bare
      filename implying repo-root.
- [ ] Two consecutive `pytest tests/unit -q` runs add ZERO rows to
      `data/jarvis.db`'s `council_rounds` (same check as T1, repeated
      here per §4's own list — count before == count after both runs).
- [ ] `python -m jarvis.council --agreement` is unaffected by review
      rounds — `placement="review"` rides the existing
      `workflow="planning"` exclusion from `compute_agreement`'s corpus,
      same as plan-authoring rounds.
- [ ] Overlay resize (W1): corner-drag (bottom-right, 14×14px handle)
      resizes the plan/review display window beyond the 40vw/40vh default
      up to the `0.9×innerWidth` / `0.85×innerHeight` clamp. The resized
      size survives a page reload (`localStorage['mortimer.display.size']`
      holds `{"w": n, "h": n}`). A window that has never been resized
      still opens at the 40vw/40vh default. Shrinking the browser window
      after a resize re-clamps the stored size instead of letting it
      overflow. The resize handle is hidden below 860px viewport width.
      The wave/satellites read visibly through the more translucent
      background (`rgba(4, 9, 12, 0.35)` + `blur(12px)`). The popped-out
      `⧉` second-window `DisplayContent` still fills 100% of that window
      on an OS-level resize.
- [ ] `tests/evals/cases.yaml` (loaded by `tests/evals/routing_eval.py`)
      contains R6's 3 new developer cases: "have Fable five review the
      geolocation plan and report gaps", "use Claude's frontier model to
      critique the backend spec", "get kimi to check the development plan
      for problems" — all expect `developer`.
- [ ] `RUN_LIVE=1 python -m tests.evals.routing_eval` still scores >= 90%
      including the three new cases (live — not run by this
      implementation pass; needs real API keys).
- [ ] `tests/integration/test_registry.py`'s tool count (48) still
      matches the live registry — `plan_start` gained a parameter, not a
      new tool.
- [ ] Full `pytest tests/unit tests/integration` and `cd web && npm run
      build && npm run lint` both clean.
