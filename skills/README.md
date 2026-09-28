# Skills

Capability knowledge in the [Agent Skills](https://agentskills.io) open
format — a folder with `SKILL.md` (YAML frontmatter + Markdown body).
Mortimer's optional `mortimer.yaml` adds a reviewed step map, declared
capabilities/dependencies and provenance for its native library. It is
descriptive metadata; it does not alter the skill prompt or grant tools.
Loaded by `jarvis/agent_skills.py`, injected into a matching sub-agent run
as one system message.

**Two properties hold by construction, not by policy:**

1. **A skill on disk does nothing.** It loads only if its name is listed
   under `enabled:` in `config/skills.yaml`. Cloning a hundred community
   skills into this directory enables exactly zero of them.
2. **Nothing here is ever executed.** `jarvis/agent_skills.py` imports no
   `subprocess`, `importlib`, `eval`, or `exec`
   (`test_module_imports_nothing_that_executes` greps the source and fails
   if that changes). A bundled `scripts/` directory is detected, reported,
   declared unavailable in the prompt, and never run.

```bash
python -m jarvis.agent_skills --list                    # what is here, what is live
python -m jarvis.agent_skills --validate                # package metadata + exact pins; duplicate YAML keys are refused
python -m jarvis.agent_skills --explain "<a task>"      # scores + what would inject
python -m jarvis.agent_skills --from-procedure <id>     # promote a learned procedure
```

The native Command Console reads the bounded `/api/skills` catalog,
revision-bound `/api/skills/<skill_id>` detail, and authenticated
`/api/skills/<skill_id>/versions` evidence. Versions distinguish manifest
version, package SHA-256, enabled registry pin, and caller-owned candidate
requests; they do not imply activation or expose previous installed revisions.
Readiness remains `unknown` until its dependencies are checked. A Process view
describes reviewed intent; it is not evidence that a run completed those steps.
Run logs record skill selection and instruction-body reads, and the native
Activity view presents those receipts. Generic event writers reject `passed`
step outcomes until a trusted runtime controller/validator receipt exists, so a
successful tool call alone leaves process completion `unknown`. Declared matcher examples
show a schema-checked synthetic request and expected selection only; they do
not execute a skill or model. Voice navigation can open reviewed process steps
and examples; bounded draft handoff opens the native creator review. Voice
cannot publish or activate. Trusted per-step evidence, live draft evaluation,
readiness checks, maintainer-reviewed activation/rollback and Mac runtime acceptance remain unfinished in
the [Skills workspace plan](../docs/plans/MORTIMER_SKILLS_WORKSPACE_IMPLEMENTATION_PLAN.md).

---

## Review checklist

Run this **before** adding a name to `config/skills.yaml`.

For a skill authored in this repository, that means at build time. For an
imported third-party skill it stays a manual gate, one skill at a time, so
each can be judged on its own — that rule is unchanged.

1. **Does it bundle `scripts/`?**
   Authored here: never. Imported: disqualifying unless the body is
   genuinely useful without them, since they will not run.

2. **Does every tool it names actually exist?**
   Check against `mcp_servers/*/skill.yaml`. A skill that instructs an
   agent to call a tool Mortimer does not have invites the agent to
   explain a failure it does not understand.

3. **Is it phrased as reference, not as an order?**
   A skill says how a thing is done. A *workflow* says it must be done
   that way. If the body reads normatively, it belongs in
   `config/workflows/`.

4. **Are trigger boundaries tested?**
   Keep what the skill does in the description; put non-applicable cases
   in the body and positive/negative utterances in fixtures. `MATCH_THRESHOLD`
   is 0.30 and matching is token overlap. Adding anti-trigger words to a
   description makes those same words easier to match and can cause false
   positives, so verify both expected and rejected tasks with `--explain`.

5. **Does it say what to do when a tool it names is unavailable?**
   Without this, an agent facing a missing tool invents a reason. That is
   Golden Rule 1 applied one layer down.

6. **Match evidence recorded** — two tasks it should match and two it must
   not, with scores from `--explain`. The negative cases matter more.

7. **No unreviewed overlap with an existing skill.**
   The legacy matcher injects only its top-scoring skill. The opt-in v2
   selector may add at most one support skill only when both package manifests
   list each other in `compatible_with`, both independently meet the trigger
   threshold and readiness checks, and their combined bodies fit the shared
   16,000-character budget. A one-sided declaration or an undeclared pair is
   a conflict: keep the primary alone. If a draft overlaps an existing skill
   without an explicitly reviewed compatible relationship, merge it or sharpen
   the trigger descriptions; never infer compatibility from wording.

---

## Where a piece of knowledge belongs

Four layers, distinguished by how much they claim:

| Layer | What it is | Where |
| --- | --- | --- |
| Memory | what is true about Larry and his world | `memories` table |
| Procedure | what worked before — learned, carries success counters | `procedures` table |
| **Skill** | **how to do a kind of thing — authored, assumed correct** | **here** |
| Workflow | how Larry requires it be done, with acceptance criteria | `config/workflows/` |

A rule that should apply on *every* run regardless of task is none of
these — it belongs in `jarvis/prompts.py` beside `GROUNDING_RULE`. A
general skill would be crowded out by every specific one (item 7), which
is exactly backwards for a rule meant to always hold.

---

## Current skills

All promoted from `active` procedures on 2026-08-18 except where noted;
see each file's `metadata.source`.

| Skill | Agent | From |
| --- | --- | --- |
| `git-history-and-status-review` | developer | procedure #15 (20✓/6✗) |
| `current-weather-with-fahrenheit` | analyst | procedure #16 (5✓/0✗) |
| `layered-geolocation` | developer | procedure #17 (9✓/4✗) |
| `technical-plan-document` | developer | procedures #18 + #22 (22✓/4✗) |
| `mcp-server-authoring` | developer | authored 2026-08-18 |

`#18` and `#22` were merged rather than shipped as two files — they
covered the same ground, which is item 7 applied before the rule existed.
