# Acceptance — knowledge framework (MORTIMER_KNOWLEDGE_FRAMEWORK_PLAN.md)

Manual checklist. Not run by pytest. Run after a sidecar/bot restart.

## K3 — Skills

The two properties worth checking by hand are the two that are supposed
to hold by construction. If either fails, stop and say so rather than
working around it.

- [ ] `python -m jarvis.agent_skills --list` shows 4 skills, all `inert`.
- [ ] `python -m jarvis.agent_skills --validate` prints "All SKILL.md
      files are valid" and exits 0.
- [ ] **The registration gate.** With `config/skills.yaml` still
      `enabled: []`, delegate a task that plainly matches one of them
      ("show me the recent commits"). The bot log shows NO
      `skill_injected` line — the skill is on disk and does nothing.
- [ ] Uncomment `git-history-and-status-review` in `config/skills.yaml`,
      restart the bot, ask the same thing. Now `skill_injected
      agent=developer name=git-history-and-status-review` appears, once.
- [ ] **No execution path.** Create `skills/<any-enabled>/scripts/x.sh`.
      Restart. The log carries `skill_bundles_scripts ... scripts are
      NEVER executed`, the injected prompt says the scripts are
      unavailable, and nothing runs. Delete the directory afterwards.
- [ ] `JARVIS_AGENT_SKILLS_ENABLED=false` → no `skill_injected` line for
      any task, and everything else behaves exactly as before.
- [ ] Console → Memory panel shows a `Skills` row reading
      "N enabled of 4 on disk".

### Importing a community skill (the intended workflow)

- [ ] Copy one skill folder into `skills/`. `--list` shows it as
      `inert`. Read its SKILL.md. Only then add its name to
      `config/skills.yaml`, one skill per commit.
- [ ] A skill whose frontmatter violates the standard (bad name charset,
      missing description) shows as `[INVALID]` with the specific
      reasons, and does not prevent the others from loading.

### Promotion from a procedure

- [ ] `python -m jarvis.agent_skills --from-procedure <candidate-id>`
      refuses, naming the status, and explains `--force`.
- [ ] Against an `active` id it writes the folder, says the procedure row
      is unchanged, and says the skill is inert.
- [ ] `python -m jarvis.runlog` still shows that procedure being matched
      afterwards — promotion is a copy, not a move.

## Skill library (MORTIMER_SKILL_LIBRARY_PLAN.md, 2026-08-18)

- [ ] `python -m jarvis.agent_skills --list` shows **5 skills, all
      enabled**. Authored skills ship enabled; the one-at-a-time gate now
      applies to imported skills only.
- [ ] `python -m jarvis.agent_skills --validate` exits 0.
- [ ] `--explain "write a new MCP server for the calendar API"` →
      `mcp-server-authoring` (0.500).
- [ ] `--explain "show me the recent commits"` →
      `git-history-and-status-review`, NOT `mcp-server-authoring`. This is
      the negative that matters: `MAX_INJECTED = 1` means an over-match
      displaces the right skill rather than adding noise.
- [ ] `--explain "what's the plan for today"` → nothing injected.
      (Before `MIN_SHARED_TOKENS`, this scored 0.500 on the word "plan".)
- [ ] After a restart, a delegation that mentions writing an MCP server
      logs `skill_injected agent=developer name=mcp-server-authoring`.
- [ ] After a day of use:
      `grep skill_injected logs/bot.log | awk '{print $NF}' | sort | uniq -c`
      — a skill firing on nearly every run is over-matching, and its
      **body** needs a sharper "when this does not apply" section. Do NOT
      put the anti-trigger in the description: measured 2026-08-18, that
      moves the false positive's score UP, because the negative example's
      own words become matchable tokens.
- [ ] Every sub-agent's system prompt carries the verification taxonomy
      exactly once, whether or not a skill matched.

## Screen-vision diagnostics (Part G)

- [ ] Ask "what's on my second screen". `grep screen_view logs/bot.log`
      shows one line with display, bytes, profile, ms, and an answer
      preview — including for the DIRECT `view_screen` path, which writes
      no run-log row and was previously invisible.
- [ ] A successful capture leaves **no image on disk**: `ls logs/screen/`
      is empty. Tier 2 was deliberately not built.
- [ ] Revoke Screen Recording permission and ask again. The answer names
      the permission, and `logs/screen/<date>/lowconf-*.png` now holds the
      wallpaper frame with a `screen_lowconf_retained` warning in the log.
- [ ] Restore permission. Set `JARVIS_SCREEN_RETENTION_HOURS=0`, restart,
      and confirm the retained image is pruned at startup
      (`screen_logs_pruned` in the log).
- [ ] `JARVIS_SCREEN_ENABLED=false` still suppresses everything.

## K4 — Workflows

- [ ] A task matching a `config/workflows/*.yaml` `when:` logs
      `workflow_injected` exactly once, with the file name.
- [ ] Its `done_when` lines appear in the agent's reasoning about
      whether it finished.
- [ ] `JARVIS_WORKFLOWS_ENABLED=false` silences it entirely.
- [ ] A deliberately malformed workflow file is logged and skipped; the
      others still load.

## Ordering (K3 + K4 together)

- [ ] Find a task that matches a procedure, a skill and a workflow. In
      the run's messages the order is procedure hint → skill reference →
      workflow instruction, and the workflow is the last system message
      before the task. That order is the layer taxonomy — evidence,
      then reference, then requirement.

## K5 — Console visibility

- [ ] `GET /api/knowledge` returns all four layers.
- [ ] `not_reaching_prompt` matches what the bot log reports as dropped.
- [ ] The amber warning line appears when facts are being dropped, and
      disappears when they are not.
