# Planning pathway — acceptance checklist

MORTIMER_PLANNING_PATHWAY_PLAN.md. Manual, run against a live stack
(`./scripts/mortimer.sh`) with at least two usable model profiles in
`config/upgrade_models.yaml` (key present). Not run by pytest.

- [ ] P1: `config/agents.yaml`'s `developer.timeout_s` is `300`. A
      developer delegation that legitimately runs 90-250s (e.g. "write a
      backend spec for X") no longer times out.
- [ ] P2: "write a backend spec for X and commit it" — the agent's
      spoken/console reply describes the result as a DRAFT awaiting
      confirmation, never as written or committed, even before any
      backstop text is appended. If the model's own wording somehow still
      claims success, the reply ends with
      `[1 draft(s) are awaiting your confirmation — nothing has been
      written yet.]`.
- [ ] P5: after that draft, the side drawer's Output tab shows the FULL
      document content (not just a one-line summary) under
      "Repo — draft create/overwrite {path}", with the amber
      needs-your-confirmation dot lit.
- [ ] P6: "show me the geolocation plan" (or any committed doc) renders
      the file's content in the overlay/popup, titled "Repo — {path}".
- [ ] P3: the Runs panel's expanded detail shows "model: {model}" for a
      new run; `python -m jarvis.runlog --run <id>` shows a `model` line.
      A pre-migration-0011 row shows "—", never blank or a guess.
- [ ] P7 single mode: in the Edit panel's Planning card, pick "single
      model", optionally name a planner, enter a goal, Start. The job
      runs for a couple of minutes without timing out (P1's 300s headroom
      covers this). On completion the card shows the author's name and
      the full plan text.
- [ ] P7 single mode via voice: "have kimi-k3 plan a backend spec for X"
      → developer delegates to `plan_start` (never authors the doc
      itself) → `plan_status` reports drafting, then a finished plan.
- [ ] P7 council mode: pick "council: parallel drafts", enter a goal,
      Start. Candidates appear as tabs/details, each showing its author
      and (when judges were available) an advisory score. Choosing one
      (button or `plan_choose`) completes the round; the round's detail
      view (or `GET /api/council/round/{id}`) still shows every unchosen
      candidate's content — nothing is dropped.
- [ ] P4: the council round view (self-edit escalation rounds AND
      planning rounds alike) shows a roster line above the score table:
      "Proposers: ... · Judges: ... · Shadow: ..." (Shadow segment only
      when shadow rows exist).
- [ ] P7 adoption: "Adopt as draft" (or `plan_adopt` with confirm) creates
      a draft repo write at the expected `docs/plans/<slug>.md` path (or
      a custom path); P5's display shows the FULL adopted content
      INCLUDING the attribution footer
      (`*Drafted by {profile} ({model}) — {date}.*`, plus, for a
      council-chosen plan, "Selected by Larry from N council candidates
      (round {round_id})."). The footer is present on the adopted
      document but absent from every candidate shown before adoption.
- [ ] P7 feeds self-edit: from a finished plan, "Start self-edit with
      this plan" (or `POST /api/selfedit/run` with `plan` set) starts an
      upgrade run whose first planner call includes the plan text.
- [ ] `python -m jarvis.council --agreement` output is unaffected by any
      planning rounds run during this session (rounds_considered excludes
      `workflow="planning"`).
- [ ] `tests/integration/test_registry.py`'s tool count (48) matches the
      live registry — `python -m jarvis.cli` (or the console) shows
      `plan_start`/`plan_status`/`plan_choose`/`plan_adopt` available to
      the developer agent.
- [ ] Full `pytest tests/unit tests/integration` and `cd web && npm run
      build && npm run lint` both clean.
- [ ] `RUN_LIVE=1 python -m tests.evals.routing_eval` still scores >= 90%
      — planning/spec requests route to developer, never answered inline
      by the Supervisor.
