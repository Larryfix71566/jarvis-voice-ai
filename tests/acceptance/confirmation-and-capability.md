# Confirmation & capability — acceptance checklist

MORTIMER_CONFIRMATION_AND_CAPABILITY_PLAN.md. Manual, run against a live
stack (`./scripts/mortimer.sh`) after restarting the bot (prompts/config
are read at boot — this plan changed `jarvis/prompts.py`, `config/
agents.yaml`, and `config/upgrade_models.yaml`). Not run by pytest, except
where an item names a specific automated test/command.

## Part F — frictionless planning + auto-save

- [ ] "Draft a plan for adding calendar sync" (no prior turn, no follow-up
      confirmation) → the developer calls `plan_start` immediately, with
      zero clarifying "should I go ahead?" turns. Voice announces
      completion on its own once the job finishes (`plan_watcher.py`
      polling `/api/plan/job`) — no further user interaction required.
      The display window shows the plan; `docs/plans/<slug>.md` exists on
      disk with the `*Drafted by {profile} ({model}) — {date}.*` footer.
- [ ] Council-mode request ("have the council draft a plan for X") → the
      developer calls `plan_start` with `mode=council` immediately (no
      confirmation gate before drafting starts). Once all candidates are
      in, voice announces "which one? Proposal A drafted by X, Proposal B
      drafted by Y, ..." — this is the ONE required interaction (a real
      choice among candidates, not a confirmation of an action). After
      you choose, the winner auto-saves and voice announces the saved
      path — zero further interaction.
- [ ] A plan run that fails to save (e.g. induce a permission error on
      `docs/plans/`) is announced by voice as a failure naming `plan_adopt`
      as the manual fallback — the display window does NOT show a
      half-finished doc silently as if it succeeded (`test_plan_watcher.py::
      test_done_save_failure_speaks_but_does_not_push_display` covers this
      at the unit level).
- [ ] `plan_adopt` with a `path` outside `docs/plans/**`/`docs/reviews/**`
      (e.g. `config/agents.yaml`) is refused with a boundary error, both
      via voice and confirmed in `tests/unit/test_admin_plan.py::
      test_adopt_rejects_path_outside_docs_plans_and_reviews`.
- [ ] Two plans drafted back-to-back with the same/similar goal (same
      slug) both land on disk — the second gets a `-2` suffix rather than
      silently overwriting the first (`test_single_mode_slug_collision_
      appends_suffix`).
- [ ] `JARVIS_PLAN_WATCHER_ENABLED=false` in `.env`, restart the bot:
      a plan still drafts and auto-saves (the sidecar-side save is
      independent of the watcher), but voice never announces it and the
      display window never auto-opens — `plan_status` by voice is the
      only way to learn it finished.

## Part G — two-phase gate audit

- [ ] "Implement the calendar sync plan" (an existing plan/spec) → the
      developer calls `selfedit_start` with zero confirmation turns; a
      self-edit session begins immediately (branch created, edit loop
      running) — `python -m jarvis.runlog --agent developer` shows the
      run started without any prior "yes go ahead" exchange in the
      transcript.
- [ ] Once the self-edit validates and you say "yes, submit the pull
      request" — the developer calls `selfedit_submit(confirm=true)`
      DIRECTLY, with no re-preview turn (no "here's what I'm about to
      submit, confirm?" round-trip) — this is the eval case added to
      `tests/evals/cases.yaml`; also spot-check the routing eval run
      (`RUN_LIVE=1 python -m tests.evals.routing_eval`, ≥90%) covers it.
- [ ] Ask the developer to submit a PR WITHOUT having said "yes" first —
      the developer does not assert prior confirmation; it either asks
      you directly or calls `selfedit_submit(confirm=false)` to preview
      first (i.e., it does not fabricate a "the user confirmed" task
      framing it never actually heard).
- [ ] "Scaffold a new app called weather-widget" → `app_create` still
      previews (`confirm=false`) before you explicitly say yes — this
      gate was intentionally KEPT (creating a GitHub repo is externally
      visible). Confirming verbally lets developer call
      `app_create(confirm=true)` directly without a second preview.
- [ ] "Build out the weather-widget app" (an existing scaffolded app) →
      `app_build_start` runs with zero confirmation (G1, same reasoning
      as `selfedit_start` — sandboxed `AppWorkspace`). `app_build_submit`
      (opening the PR) still requires your explicit "yes" before the
      developer calls it with `confirm=true`.

## Part H — loud capability degradation

- [ ] With `MOONSHOT_API_KEY` deliberately unset (or an invalid vault
      entry) and `developer`'s `on_profile_fallback: refuse` in
      `config/agents.yaml`: delegate anything to developer → the
      Supervisor reports the delegation was refused, naming the missing
      key and the fix (`python -m jarvis.vault set MOONSHOT_API_KEY` or
      editing `model_profile`) — the developer never silently runs on
      Haiku. Compare against `python -m jarvis.runlog --agent developer`:
      no new run row is created for the refused call.
- [ ] Restore `MOONSHOT_API_KEY`, restart the bot, reconnect: the console
      topbar shows NO capability chip (clean boot, no degraded agents).
- [ ] Temporarily set some conversational agent's `model_profile` to a
      profile with a missing key and leave `on_profile_fallback: warn`
      (the default) — that agent still silently falls back to the voice
      model AND runs normally (unlike refuse mode), but on reconnect the
      console topbar shows an amber `⚠ <agent> degraded` chip; hovering
      it names the assigned vs. resolved model.
- [ ] `python scripts/check_env.py` (or, if the sandbox/keychain check
      fails first, run `check_model_registry()` in isolation per
      `tests/unit/test_check_env_model_registry.py`'s pattern) reports
      one WARN/PASS line per `config/upgrade_models.yaml` profile, plus
      one line per sub-agent with a `model_profile` set — a `refuse`-mode
      agent with a missing key reads "will REFUSE every delegation until
      this is fixed"; a `warn`-mode agent reads "will silently fall back
      to the voice model."
- [ ] H3 registry fix, empirical: with real keys in place, trigger an E1
      escalation (two validation failures + failed repair) or manually
      `POST /api/council/convene` — a round actually forms with
      `proposer_count >= 2` and produces a winner. Confirm via
      `python -m jarvis.council --agreement` or the Edit panel's "Recent
      rounds" list that this is not another zero-proposer no-op round
      (incident 1's second symptom: `gpt-4.1-mini`'s dead key meant the
      economy tier could never actually field a proposer).

## Notes

- The live-only items above (voice interaction, actual key removal,
  actual council convene) cannot be verified from an automated sandbox —
  they require Larry's own machine, real API keys, and a live
  microphone/speaker session.
- Automated coverage for the deterministic parts of Parts F/G/H lives in
  `tests/unit/test_admin_plan.py`, `tests/unit/test_admin_plan_review.py`,
  `tests/unit/test_mcp_selfedit_logic.py`, `tests/unit/test_mcp_apps_logic.py`,
  `tests/unit/test_plan_watcher.py`, `tests/unit/test_display.py`
  (`TestPlanReady`), `tests/unit/test_subagent.py`, `tests/unit/
  test_delegate.py` (`TestProfileFallbackRefusal`), `tests/integration/
  test_bot_wiring.py` (capability report tests), and `tests/unit/
  test_check_env_model_registry.py` — all green as of 2026-08-18.
