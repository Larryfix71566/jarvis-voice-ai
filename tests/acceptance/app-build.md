# App-build engine — acceptance checklist

Historical engine checklist: VM behavior and remaining gaps are now tracked in
`sandbox/IMPLEMENTATION.md` and `sandbox/VALIDATION.md`. The old host checkout,
candidate-defined commands and concurrent-VM expectations below are superseded.

MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md Part D. Manual, run
against a live stack (`./scripts/mortimer.sh`) with `GITHUB_TOKEN` set
and a real pre-existing test app repo. Not run by pytest. **The bot must
be restarted after this change** — prompt, config, and registered MCP
tools are read at boot.

- [ ] D1: `pytest tests/unit/test_selfedit_service.py tests/unit/
      test_upgrade_agent.py -q` is fully green with no changes needed —
      the Workspace seam refactor is behavior-identical to before it
      landed.
- [ ] D2: ask Mortimer to build something in an app that does not yet
      exist locally under `data/app_workspaces/` — the workspace clones
      on first build. Ask again after a merge on GitHub — the second
      build pulls (`git pull --ff-only`) rather than re-cloning.
- [ ] D2: with an uncommitted change sitting in an existing workspace
      (simulate a crashed prior session), a new `app_build_start` refuses
      synchronously with a clear "not clean" message rather than
      silently overwriting it.
- [ ] D3: an app with no `mortimer.app.yaml` — `app_build_status` (and
      the eventual PR) says explicitly that no checks are defined; the
      build is never described as validated.
- [ ] D3: an app with a `mortimer.app.yaml` whose `test:` command fails
      on purpose — `app_build_submit` refuses with "validation hasn't
      passed."
- [ ] D4: ask for an edit to `.github/workflows/anything.yml` or `.env`
      inside the app — refused with a boundary error, never written.
- [ ] D5: start an app build, then ask an unrelated question that
      delegates to `selfedit_start` in the same session — both run
      concurrently without either refusing the other (separate job
      slots). A second `app_build_start` while one is already running
      IS refused ("already in progress").
- [ ] D6: "build a login page for `<test-app>`" — Mortimer calls
      `app_build_start` for every change, including a single dictated file;
      the retired `app_write_file` returns `sandbox_required`; two-phase confirmation is honored (preview,
      then explicit yes).
- [ ] D7: set `JARVIS_APPBUILD_PROFILE=kimi-k2` and unset
      `JARVIS_UPGRADE_PROFILE` — an app build picks `kimi-k2` while a
      self-edit run in the same session still uses its own default,
      confirming the two profile env vars are independent.
- [ ] D8: no console panel exists for app-build; status is reachable
      only via `app_build_status` (voice) or `GET /api/appbuild/job`.
- [ ] End-to-end (plan §3 item 13): scaffold a small test app
      (`app_create`), draft a one-paragraph plan for it via the planning
      pathway, `app_build_start` with `plan_path` set to that plan,
      `app_build_status` until done, `app_build_submit`, confirm the PR
      appears on GitHub and merge it manually.
- [ ] Full `pytest tests/unit tests/integration -q` clean.
