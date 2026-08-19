# Meta-prompts as specialized agents — do they fit the Developer?

**Question, Larry 2026-08-18:** *"meta-prompts as specialized agents for use
on specific tasks — can this be leveraged in the developer?"*

**Short answer:** yes, but the useful version is the inverse of what the term
usually implies. The value is not in *generating* prompts — it is in *not
injecting the 60% of the developer's prompt that does not apply to the task
at hand.*

---

## 1. Two different things called "meta-prompting"

| | What it is | Verdict for Mortimer |
| --- | --- | --- |
| **Static specialization** | Pre-authored, task-specific prompt variants selected by matching. Reviewable, diffable, version-controlled. | **Adopt** — mechanism already exists |
| **Dynamic meta-prompting** | A conductor model writes the specialist's system prompt at runtime and spawns it (Suzgun/Kalai pattern; the "self-routing" step in the graph-engineering articles). | **Reject** |

**Why dynamic is rejected** [certain]:

- Contradicts the model-discipline rule (`MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md`
  Part A): the voice model is a dispatcher, never a design/build model.
- A generated prompt cannot be diffed or reviewed. `jarvis/prompts.py` is the
  single source of truth for prompts precisely so a behavior change shows up
  in a commit.
- Violates the anchors principle: a prompt the optimizer authors is exactly
  the rule the optimizer would bend to win. Same objection that makes
  `config/upgrade_models.yaml` and `config/skills.yaml` unwritable by the agent.

**Static specialization already partly exists.** K3 skills (2026-08-18) are
authored, task-matched instruction blocks injected into a sub-agent run —
`technical-plan-document` is literally a task-specialized prompt. The
planning pathway does the same at a coarser grain: `PLAN_AUTHOR_PROMPT`,
`PLAN_REVIEW_PROMPT`, `SCOPE_ADVISOR_PROMPT`, `AppBuildAgent`'s own prompt.

---

## 2. The gap skills cannot close

**Skills can only ADD text. The developer's problem is text that will not go
away.**

Measured 2026-08-18 from `jarvis/prompts.py`:

```
scheduler      1041 chars   (~260 tokens)
librarian       978
analyst         933
systems        1028
developer      4588 chars   (~1147 tokens)  ← 4.4x every other agent
```

Breakdown of the developer prompt by paragraph:

```
   94  identity line
   88  repo read questions
  286  repo writes — two-phase commit/push
 1188  App development — app_create / app_build_start protocol
 1566  Self-development — selfedit_start / validate / submit protocol
  463  planning pathway routing
  342  output contract
  315  GROUNDING_RULE
  238  NO_INVENTED_REMEDIATION_RULE
```

**2,754 of 4,588 chars — 60% — are the two protocol paragraphs**
(app development + self-development). Both are injected when the developer
is asked to read a YAML file. On top sits the repo map (`inject_repo_map:
true`, capped at `REPO_MAP_MAX_CHARS` = 8,000).

So the agent walks into *every* task carrying the full app-scaffolding
confirmation protocol and the full self-edit submission protocol, regardless
of whether either can possibly apply.

---

## 3. Recommended: conditional prompt sections

Split `SUBAGENT_PROMPTS["developer"]` into:

- **A core** — identity, repo reads, output contract, `GROUNDING_RULE`,
  `NO_INVENTED_REMEDIATION_RULE`. Target ~1,100 chars, in line with every
  other agent.
- **Named sections** — `app_development`, `self_development`, `planning` —
  each with a `when:`-style match, injected only when the task matches.

Reuse `jarvis.procedures`'s `_tokens` / `_overlap_score`, the same scorer
workflows and skills already share. One implementation, not a fourth one.

**Properties this preserves:**

- `jarvis/prompts.py` stays the single source of truth — sections are
  literals there, not generated.
- No new agent, so **routing is untouched** and the routing eval is not at
  risk.
- Failure mode is safe by construction: if matching fails, inject everything
  (today's behavior). A miss costs tokens, never capability.

---

## 4. The tempting alternative, and why to argue against it

**Split the developer into multiple agents in `config/agents.yaml`** — a
`reader` and a `builder`, each with its own prompt, model profile, and MCP
subset.

Cheap in code (that file is data, and `model_profile` / `max_iterations` /
`timeout_s` are already per-agent), but it **pays routing accuracy** — the
hardest thing to get back. The Supervisor currently distinguishes five agents
at ≥90% eval accuracy. "Read this config file" vs "implement this plan" is a
far subtler boundary than "weather" vs "git", and every new agent is another
line in the catalog the dispatcher must disambiguate.

Conditional sections buy the same prompt hygiene without touching routing at
all. If sections prove insufficient, agent-splitting remains available —
the reverse is not true.

---

## 5. Honest confidence

- [certain] 60% of the developer prompt is irrelevant on the majority of its
  tasks. This is measured, not inferred.
- [guessing] that this dilution is **causing** failures. The two runs
  actually diagnosed (`54b62f69`, `9f0684e2`) died on `MAX_TOOL_ITERATIONS`,
  not on prompt confusion. No observed failure has been traced to prompt
  bloat.

So this is **risk reduction on a measured inefficiency**, not a fix for a
proven defect — and it should be described that way in any plan, per the
degradation-proof rule about not letting an unverified section read like a
verified one.

**If evidence is wanted first:** the run log already holds it. Compare
developer success rates on tasks that touch the app/self-edit paths against
those that do not (`python -m jarvis.runlog --agent developer`), and check
whether failures cluster where the prompt was most diluted.

---

## 6. Related

- Skills (K3) — `jarvis/agent_skills.py`, the additive half of this idea,
  already shipped.
- [Graph engineering review](graph-engineering-fit-for-mortimer.md) — rejects
  the same dynamic self-routing pattern for the same reasons.

---

*Review written 2026-08-18 in a Cowork session, not through Mortimer's own
planning pathway — so it carries no planner attribution footer. Character
counts measured directly from `jarvis/prompts.py` at commit 313ba43.*
