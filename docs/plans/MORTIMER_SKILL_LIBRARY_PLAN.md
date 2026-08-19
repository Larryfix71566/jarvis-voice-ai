# Mortimer skill library — authoring from Claude's skill concepts

**Status:** APPROVED and IMPLEMENTED 2026-08-18. Parts A, B, C, D and G
(Tier 1 + G3) are built and tested. Part E (`console-verification`) and
Part F (`references/`) were deliberately NOT built — see §12 O4/O5.

**One finding during implementation invalidated a work item as written.**
D1 said to put anti-triggers in skill *descriptions*, copying Anthropic's
`morning`. Measured after doing it: adding *"what are you planning to do
next"* to `technical-plan-document`'s description moved that task's score
from **0.000 to 1.000** — precisely backwards. `_overlap_score` divides by
the SMALLER token set, so naming a false positive in the description adds
its exact words to the matchable set. Anthropic's descriptions are read by
a model; Mortimer's are token-matched, and the pattern does not port.

Corrected: anti-triggers live in the skill BODY (never scored), and the
real mechanism is a new `MIN_SHARED_TOKENS = 2` in
`jarvis/agent_skills.py` — same constant, value and reasoning as
`jarvis/consolidate.py`'s. It also fixed a *pre-existing* false positive
the plan had not noticed: "what's the plan for today" scored 0.500 on the
word "plan" alone, above threshold, before any of today's edits.

**Revision 2, 2026-08-18.** Two changes from Larry after the first draft:
(1) authored skills ship **enabled**, not inert (D2); (2) an overlapping
skill is **merged, never duplicated** — which killed the proposed
`verify-before-claiming` skill and turned it into a prompt-layer change
(§5). Plus a new Part G: time-boxed screen-vision diagnostics.

**Author:** drafted 2026-08-18 for Larry, in a Cowork session (not through
Mortimer's own planning pathway).

**Origin.** Larry, 2026-08-18: *"review claude's current skill repository and
provide feedback on the existing skills that could be added to mortimer…
instead of importing the skill from claude let's create our own from the
concepts so that we enhance mortimer 'without tying its hands'."*

**Prior review:** [Meta-prompts for the developer agent](../reviews/meta-prompts-for-the-developer-agent.md)
and [Graph engineering fit](../reviews/graph-engineering-fit-for-mortimer.md).
This plan is the build half of the same conversation.

---

## 1. Evidence

### 1.1 What is actually in Anthropic's repository

Enumerated from [anthropics/skills](https://github.com/anthropics/skills)
`/skills` on 2026-08-18 — 19 skills:

```
academy-guide      algorithmic-art    brand-guidelines   canvas-design
claude-api         discernment-nudge  doc-coauthoring    docx
frontend-design    internal-comms     mcp-builder        pdf
pptx               skill-creator      slack-gif-creator  theme-factory
web-artifacts-builder  webapp-testing  xlsx
```

Three were read in full (`discernment-nudge`, `mcp-builder`,
`webapp-testing`); five more were inspected on local disk (`docx`, `pdf`,
`pptx`, `xlsx`, `skill-creator`) plus four Cowork skills
(`consolidate-memory`, `morning`, `schedule`, `explain-usage`). The
remainder were classified from the repository README's own category list
and skill names only — **that classification is unverified.**

### 1.2 Why importing is the wrong move

Measured from the local copies:

```
docx/SKILL.md    6.9 KB  → invokes python scripts/accept_changes.py, comment.py,
                            merge_runs.py, office/soffice.py, office/validate.py
pptx/SKILL.md   20.8 KB  → invokes python scripts/add_slide.py, clean.py, thumbnail.py
xlsx/SKILL.md    8.6 KB  → invokes python scripts/recalc.py
pdf/            8.1 KB   → ships 8+ scripts
skill-creator/  33.4 KB  → run_eval.py, package_skill.py, quick_validate.py
webapp-testing/          → Playwright scripts, scripts/with_server.py
```

`jarvis/agent_skills.py` has **no execution path by construction**
(`test_module_imports_nothing_that_executes`). An imported script-bound
skill therefore loads several KB of instructions telling an agent to run
programs it cannot run. The loader would flag them unavailable — correct
behavior, zero value delivered.

The deeper reason: a skill's value is proportional to how much it encodes
*its own* environment. These encode Claude Code's (bash, python, unlimited
output). Mortimer's is five sub-agents, MCP tools, two-phase confirmation,
and a 60-word voice output contract.

### 1.3 Current state of Mortimer's skill layer

- Four skills on disk, promoted from active procedures 2026-08-18.
- One enabled (`git-history-and-status-review`), verified firing once:
  run `9f60f6d0`, developer, ok, 22619ms, 1 tool call — in line with three
  comparable pre-skill runs (20.8s/1, 25.5s/2, 22.8s/2). **No latency or
  behavior regression; also no evidence yet of benefit.**
- `MATCH_THRESHOLD = 0.30`, `MAX_INJECTED = 1`,
  `BODY_SOFT_MAX_CHARS = 20_000`.
- `config/skills.yaml` is the registration gate; skills ship inert.
- The loader reads the `SKILL.md` body only. `references/` siblings
  (tier 3 of the standard) are **not read** — see Part F.

---

## 2. Decisions

**D1. Author, never import.** Every skill below is written against
Mortimer's own tools, conventions, and output contract. No skill in this
plan is a copy of an Anthropic skill; each ports a *concept*.
*Alternative considered:* import instruction-only skills and edit them.
*Downside:* they reference tools Mortimer lacks in prose that reads
authoritative, which is the exact shape of the fabrication problem the
Golden Rules exist to prevent.

**D2. New skills authored here ship ENABLED.** *(Larry, 2026-08-18: "since
we are authoring these new skills once built I want them wired and enabled
for use in Mortimer.")* Each Part adds its skill's name to
`config/skills.yaml` as part of the same change.

**This narrows the one-at-a-time rule rather than repealing it.** That rule
exists because a community skill is unreviewed content from a stranger,
possibly carrying scripts. A skill authored in this repository is reviewed
in its own diff before it lands and carries no scripts by D3. The rule
stands, unchanged, for anything imported.

*What this costs, stated plainly:* shipping inert meant a bad match was
caught when Larry chose to enable. Enabling at build time means a bad match
goes live at merge. **Part A's `--explain` therefore stops being a
convenience and becomes the gate** — see D2a.

**D2a. No skill is enabled without recorded match evidence.** Before a name
is added to `config/skills.yaml`, the change must record, in the commit or
the acceptance checklist:

1. two tasks it SHOULD match, with their scores, and
2. two tasks it must NOT match, with their scores below `MATCH_THRESHOLD`.

The negative cases are the ones that matter. `MAX_INJECTED = 1` means an
over-matching skill does not merely add noise — it crowds out the more
specific skill that should have fired.

**D2b. Enabling requires a bot restart.** `load_skills` reads config at
match time, but the sub-agent process holds its own state; a newly enabled
skill will not appear until `./scripts/mortimer.sh` is restarted. Say so in
the acceptance checklist so a "it isn't working" is not misdiagnosed.

**D2c. `config/skills.yaml` stays unwritable by Mortimer.** It is on the
self-edit deny list and `mcp_repo`'s `DENY_WRITE_PATHS`. Enabling is a
human-reviewed commit; the agent still cannot enable capability text for
itself. Unchanged by this decision, and worth not losing.

**D3. No skill bundles `scripts/`.** Not "we won't run them" — they are not
written. A `scripts/` directory in a Mortimer-authored skill would be dead
weight that the loader must warn about forever.

**D4. Build the match-debugging tool first (Part A).** Every other Part's
acceptance criterion is "it matches the right tasks and not the wrong
ones," which cannot be checked today without a live voice run.
*Alternative:* verify by live runs only. *Downside:* a live run costs a
restart and a delegation per check, and gives no score to tune against.

**D5. `references/` support is deferred, not required.** All bodies in this
plan fit under `BODY_SOFT_MAX_CHARS`. Part F states the trigger that would
make it necessary. Building it now would be inventing a requirement.

---

## 3. Design constraints

| Constraint | Holds by | Note |
| --- | --- | --- |
| No execution path | **construction** | `test_module_imports_nothing_that_executes` greps the module source |
| A skill is inert until registered | **construction** | `load_skills` filters on `enabled_names()`; missing config = zero skills |
| Matching never reads bodies | **construction** | `test_matching_never_reads_the_body` |
| Only one skill injected per run | **construction** | `MAX_INJECTED = 1`, `match_skill` returns a single best |
| Skills read as reference, not orders | *discipline* | `as_prompt()` wording; no mechanical backstop — a skill body could still be written imperatively. Part D's review checklist is the mitigation |
| A skill never claims a tool Mortimer lacks | *discipline* | No backstop exists. Part E adds one candidate (see E3) |

That last row is the honest weak point of this plan and is called out again
in §8.

---

## 4. Part A — match-debugging tooling *(prerequisite)*

**A1. `python -m jarvis.agent_skills --explain "<task>"`**

Mirrors `jarvis/procedures.py`'s existing `_explain` (line 469) — same
output shape, same purpose: print every skill's score against a task plus
the shared tokens, so a missed or unwanted match is debuggable without a
voice run. Reuses `_tokens`/`_overlap_score`; adds no second scorer.

Output, one line per skill, sorted by score descending, marking which
would have been injected and whether it is enabled.

**A2. `--explain` must not require the DB.** Skills are files; procedures
are rows. Keep this path DB-free so it works on a fresh checkout.

**Acceptance:**
- `python -m jarvis.agent_skills --explain "show me the recent commits"`
  scores `git-history-and-status-review` above `MATCH_THRESHOLD` and marks
  it `enabled`.
- `python -m jarvis.agent_skills --explain "what is the weather"` shows
  `current-weather-with-fahrenheit` above threshold, marked `inert`.
- New test class `TestExplain` in `tests/unit/test_agent_skills.py`;
  `pytest tests/unit/test_agent_skills.py -q` green.

---

## 5. Part B — verification taxonomy in the **prompt layer**, not a skill

> **Revised 2026-08-18** after Larry: *"if we already have a skill that
> matches a new proposed skill our original should be merged to get the
> best of both without having 2 competing versions."*
>
> Applying that principle killed the original Part B (a
> `verify-before-claiming` skill) and produced a smaller, better change.
> The reasoning is recorded here because it generalizes.

### B0. Why a general skill is architecturally wrong

`MAX_INJECTED = 1`. Only the single highest-scoring skill is injected, so
two skills that both plausibly match are not complementary — they compete,
and the loser contributes nothing.

A *general* discipline skill therefore loses to a *specific* skill exactly
when the specific one fires, and wins only when nothing specific matched.
A verification rule that switches itself off whenever the agent is doing
something particular is worse than absent: it is a rule that goes quiet
precisely when it is most needed.

The overlap is already concrete and already live.
`skills/git-history-and-status-review/SKILL.md` contains, under
"Reporting rules":

- *"Never state a branch's position relative to origin without having seen
  it in `git status --branch` output"*
- *"Give counts, not adjectives"*
- *"If a command fails, say what failed"*

That is the verification taxonomy, scoped to git. Merging a general skill
into it would require the same paragraph copied into all four skills —
four copies of one rule, which is the duplication being objected to.

**So the answer is relocate, not merge.** An always-apply rule belongs
where `GROUNDING_RULE` and `NO_INVENTED_REMEDIATION_RULE` already live:
appended to every sub-agent prompt in `jarvis/prompts.py`, with no
matching involved and nothing that can crowd it out.

### B1. The change

Extend the existing grounding rules in `jarvis/prompts.py` with the
three-category taxonomy ported from `discernment-nudge`:

1. **Facts and figures** — a number, path, branch, or status stated as
   observed. Test: did a tool return it *in this run*?
2. **Reasoning steps** — a cause attributed to an effect. Test: did a tool
   result name that cause in those words?
3. **Missing context** — an assumption the answer had to make because the
   task did not say. Test: say what was assumed.

Same mechanism the D6/D7 rules already use — appended once in `prompts.py`
so the text is stated in exactly one place and reaches every agent.

**B2. What must NOT port.** `discernment-nudge`'s output format ("A few
things worth a second look:" + bullets). Sub-agents have a 60-word
plain-text contract and speak through TTS. The ported behavior is *inline
hedging naming the evidence*, never an appended list.

**B3. Restraint.** Keep it short. `GROUNDING_RULE` and
`NO_INVENTED_REMEDIATION_RULE` are 315 and 238 chars; this addition should
be comparable. It is injected into **every** sub-agent run, so length here
costs more than length in a skill that fires on match.

**B4. Trim the now-redundant skill text.** With the taxonomy always
present, `git-history-and-status-review`'s three general reporting rules
can be shortened to the git-specific one (the `--branch` rule) and the two
generic ones dropped. *Only if* the general rule genuinely covers them —
verify by reading both, and if it does not, leave the skill alone and say
so.

**Acceptance:**
- Addition under ~400 chars; `SUBAGENT_PROMPTS` total per agent grows by
  less than 10%.
- `pytest tests/unit/test_prompts.py -q` green (or the file that asserts
  prompt composition — locate it, do not assume the name).
- A developer run's system prompt contains the taxonomy exactly once,
  regardless of whether a skill matched.

### B5. The general rule this produced *(applies to every future skill)*

**Before authoring a new skill, check it against the existing ones.** Draft
the description, then run `--explain` (Part A) on tasks the existing skills
own. If the draft scores above `MATCH_THRESHOLD` on a task another skill
should win, there is overlap: merge into the existing skill, or sharpen
both descriptions until they separate. Do not add a competing file.

This is the mechanical backstop for Larry's principle — without it, "don't
build overlapping skills" is a wish. It is added to the Part D3 review
checklist as item 7.

---

## 6. Part C — `mcp-server-authoring`

**Concept source:** `mcp-builder`. The one skill in the repository whose
subject matter Mortimer literally performs — 11 MCP servers exist and the
developer agent writes them.

**C1. What ports from the concept:**

- Tool naming: consistent prefixes, action-oriented (`repo_read_file`,
  `runlog_list` — Mortimer already follows this; the skill records it).
- **Actionable error messages** — errors guide toward a fix, with specifics.
- Annotation hints: `readOnlyHint` / `destructiveHint` / `idempotentHint`.
- Bounded responses: paginate and preview rather than dumping payloads.

**C2. What must be rewritten as Mortimer-specific** (this is the
"without tying its hands" content, and it is the majority of the body):

- `logic.py` pure and injectable / `server.py` FastMCP wiring — the
  convention every existing server follows.
- **The `if __name__ == "__main__": mcp.run()` entrypoint.** Omitting it
  makes the process import cleanly, print nothing, and exit 0 — surfacing
  as `McpError: Connection closed` on the *next* server in the list. This
  cost a real debugging session (`mcp_runlog`, C1). The missing stderr
  banner is the tell, not the stack frame.
- `skill.yaml` manifest, kept in sync (`scripts/check_skills.py`).
- Registration in `config/mcp_servers.yaml` and routing in
  `config/agents.yaml` — two files, both required, both easy to forget.
- Results must classify correctly under `jarvis/toolresult.py`'s
  `classify_tool_result`; never invent a second success heuristic.
- Draft→confirm gating via the `actions` table for any write tool.
- `expand_env_vars` leaves unknown `${VAR}` as literal text — do not add
  env entries for optional variables (RC2, the phantom-repo-root bug).

**C3. Explicitly out of the body:** the TypeScript/Node half of
`mcp-builder`, its evaluation-XML format, and its reference-file loading.
Mortimer's servers are Python/FastMCP only.

**Acceptance:**
- `--validate` passes; body under 8,000 chars.
- Match evidence (D2a): **positive** — "write a new MCP server for X",
  "add a tool to mcp-repo"; **negative** — "commit the current changes",
  "show me the recent commits". Scores recorded. The second negative
  matters most: it is the task `git-history-and-status-review` owns, and
  `MAX_INJECTED = 1` means an over-match here silently displaces it.
- Every file path, constant, and tool name in the body verified to exist at
  authoring time (checklist item D3.2).
- Registered in `config/skills.yaml`; fires after restart.

---

## 7. Part D — hardening the four existing skills

Two format patterns observed in Anthropic's skills that the shipped four
lack. Cheap, and they improve skills already on disk.

**D1. Anti-triggers in the description.** `morning`'s description states
*"A question about their day, schedule, or calendar is not by itself a
request for the brief."* Add one such sentence to each of the four.
Highest priority: `technical-plan-document`, already flagged as most likely
to over-match because "plan" appears in many developer requests.

**D2. Declared graceful degradation.** `morning`: *"a missing role is
skipped; the page adapts."* Each skill states what to do when a tool it
names is unavailable — say so plainly rather than inventing a reason.
This is Golden Rule 1 applied at the skill layer.

**D3. A review checklist** at `skills/README.md`, run **before** a name is
added to `config/skills.yaml` — for an authored skill that is at build
time (D2), for an imported one it stays Larry's manual gate:

1. Does it bundle `scripts/`? (Authored: never. Imported: disqualifying
   unless the body is useful without them.)
2. Does every tool it names actually exist in a `skill.yaml`?
3. Is it phrased as reference, not as an order?
4. Does it carry an anti-trigger sentence in the description?
5. Does it say what to do when a tool it names is unavailable?
6. **Match evidence recorded per D2a** — two positive, two negative.
7. **No overlap with an existing skill** (B5): does it score above
   threshold on a task another skill owns? If yes, merge or sharpen —
   never add a competitor. `MAX_INJECTED = 1` means the loser of an
   overlap contributes nothing at all.

**Acceptance:**
- All four descriptions still ≤1024 chars; `--validate` green.
- `--explain "write an implementation plan"` still matches
  `technical-plan-document`; `--explain "what are you planning to do next"`
  no longer does. *(If the second was already below threshold, record that
  — do not claim an improvement that did not occur.)*

---

## 8. Part E — `console-verification` *(lowest priority)*

**Concept source:** `webapp-testing`. Implementation does not port at all
(Playwright scripts). Two ideas do:

**E1. Reconnaissance-then-action.** Look at the current rendered state
before acting on it; do not act on an element you have not confirmed is
there. Maps onto `view_screen` / `screen_list`.

**E2. Bounded inspection.** *"Use bundled scripts as black boxes… they
exist to be called directly rather than ingested into your context
window."* Mortimer's equivalent already exists as `runlog_detail`'s
bounded previews and `payload_path`; the skill states it as a principle.

**E3. Candidate backstop for the §3 weak row.** While authoring this,
consider whether `load_skills` should warn when a skill body names a tool
that is not in any `skill.yaml` — turning "a skill never claims a tool
Mortimer lacks" from discipline into construction. **Not committed to in
this plan** — it needs its own design (substring matching on prose is
error-prone) and is listed as Open Decision O3.

**Deferred rationale:** screen vision is the newest, least-exercised
capability, `_system_profiler_displays` has never been verified against
real multi-monitor hardware, and macOS Screen Recording permission fails
silently. Writing authoritative guidance on top of an unverified capability
is exactly what §9's honesty rule forbids.

---

## 9. Part F — `references/` support *(deferred; trigger stated)*

The standard's tier 3: a skill folder may carry `references/*.md` loaded on
demand. `jarvis/agent_skills.py` reads the `SKILL.md` body only.

**Trigger to build it:** any skill body exceeding ~8,000 chars, OR a second
skill needing the same shared reference material. Neither is true today.

**If built:** a `Skill.reference(name)` accessor reading
`path.parent/"references"/name`, never loaded during matching (the
tier-one property `test_matching_never_reads_the_body` protects), and never
auto-injected — the body must ask for it by name.

---

## 9a. Part G — screen-vision diagnostics *(new, Larry 2026-08-18)*

> *"since computer vision is untested by your measure — I would ask that we
> add what it sees into the logs. not indefinitely, only for a short period
> to give the ability to use for troubleshooting an error in mortimer."*

This **modifies a guarantee Larry previously accepted** — that a screenshot
is "never persisted, never logged." That is why it gets its own Part with
its own decisions rather than being folded in quietly.

### G0. Evidence

- `logs/` is gitignored (`.gitignore` line 32). Nothing here can reach
  GitHub.
- `mcp_screen/logic.py` deletes the temp file in a `finally` (line 270-272)
  and flags `low_confidence` below `MIN_SCREENSHOT_BYTES = 2000` (the
  silent-permission-failure heuristic).
- **The real blind spot:** `jarvis/bot/screen_tool.py`'s direct
  `view_screen` handler returns `result.get("answer")` and nothing else.
  Direct Supervisor tools are not delegations, so **there is no
  `agent_runs` row and no JSONL payload** — the path Larry uses most by
  voice is the one recorded least. The sub-agent `screen_view` path does
  reach the run log.

### G1. Two tiers, deliberately separated

**Tier 1 — text and metadata. Default ON, no expiry.**
Log the vision model's TEXT answer plus: display index, image byte size,
`low_confidence` flag, model/profile used, and latency. Low marginal risk:
the answer already crosses back to the user and, on the sub-agent path,
already lands in the run log. This alone closes the direct-path blind spot
and answers most "why did Mortimer say that" questions.

**Tier 2 — the actual image. Default OFF, self-expiring.**
Persist the captured PNG under `logs/screen/<date>/`.

### G2. "Short period" must be structural, not a promise

A boolean flag left on is how "temporary" becomes permanent. So the switch
is **an absolute deadline, not an on/off**:

```
JARVIS_SCREEN_DEBUG_UNTIL=2026-08-25T00:00:00
```

Past that timestamp, image capture-to-disk stops regardless of anything
else — checked at the single point where the file would be written.
Unparseable or absent means OFF. There is deliberately **no boolean form**
of this variable: a rule without a mechanical backstop is a wish, and
"remember to turn it off" is a wish.

Second backstop: prune `logs/screen/` at bot startup, alongside the
existing run-log prune, with its own much shorter retention
(`JARVIS_SCREEN_RETENTION_HOURS`, default 48) — so even a forgotten
deadline cannot accumulate a screenshot archive.

### G3. Always retain failures, regardless of the deadline

Independent of Tier 2: when a capture comes back `low_confidence: True`,
retain that image. It is a few KB of wallpaper, it is the exact artifact
that diagnoses the silent macOS permission failure, and it is the one case
where an image is nearly certain to contain nothing private. Same
`JARVIS_SCREEN_RETENTION_HOURS` prune applies.

*(This is the highest value-per-risk item in Part G and is worth doing even
if Larry declines Tier 2 entirely.)*

### G4. Risks, stated plainly

- **A screenshot captures whatever is on screen.** Passwords in a manager,
  bank details, health information, private messages — the exact categories
  excluded from Mortimer's memory by rule. A troubleshooting artifact must
  not become the one place they are stored. Nothing in this design prevents
  that; only the short deadline and Larry's awareness of the window do.
- **The counter-argument, which is fair:** every captured screen is
  *already* sent to a cloud vision API — a trade-off Larry accepted
  explicitly. Keeping a copy on his own disk for 48 hours is a smaller
  marginal exposure than the network call he already permits. This is the
  strongest argument for the request and it is a good one.
- **Not mitigated:** if a sensitive window is open during the debug
  window, that frame lands on disk. There is no content filter, and
  building one (OCR-then-redact) would mean sending the image somewhere
  else to classify it — worse, not better.

### G5. Console visibility

While `JARVIS_SCREEN_DEBUG_UNTIL` is in the future, the console shows a
persistent indicator with the expiry date. An always-on capability that is
silently on is the failure mode; the whole point of the deadline is that it
is visible and finite.

**Acceptance:**
- Tier 1: a direct `view_screen` call produces one log line with answer,
  display, bytes, `low_confidence`, model, latency.
- Tier 2 with the deadline in the future: image lands in
  `logs/screen/<date>/`. With the deadline in the past: no file, and one
  log line saying the debug window has expired.
- With the variable unset or malformed: no file, no error.
- Startup prune deletes files older than `JARVIS_SCREEN_RETENTION_HOURS`.
- `low_confidence` retention works with the deadline in the past (G3).
- New tests in `tests/unit/test_mcp_screen_logic.py`; existing tests green.
- `.env.example` documents both variables, including that
  `JARVIS_SCREEN_DEBUG_UNTIL` has no boolean form and why.
- `CLAUDE.md`'s Screen vision section updated — the sentence "never
  persisted, never logged" is now conditionally false and must say so.

---

## 10. Ordering and acceptance

| Order | Part | Why this position |
| --- | --- | --- |
| 1 | A — `--explain` | Every other acceptance criterion depends on it |
| 2 | B — verification taxonomy in prompts | Smallest change, always-on, cannot be crowded out |
| 3 | C — `mcp-server-authoring` | The one genuinely new skill; highest functional value |
| 4 | D — existing-skill hardening | Cheap; improves what is already live |
| 5 | G — screen-vision diagnostics | Unblocks E by making the capability observable |
| 6 | E — `console-verification` | Only after G produces evidence the capability works |
| 7 | F — references | Deferred; trigger not met |

**Net effect of the B revision:** 3 proposed skills became **1 new skill +
1 prompt change + 1 still-deferred**. The library grows from 4 files to 5,
not to 7.

**Whole-plan acceptance:**

1. `python -m pytest tests/unit tests/integration -q` — green except the
   known pre-existing `test_mcp_web_server` network failure.
2. `python -m jarvis.agent_skills --validate` exits 0.
3. `python -m jarvis.agent_skills --list` shows 6 or 7 skills, with every
   skill authored by this plan marked `enabled` (D2).
4. `cd web && npm run build` unaffected (no frontend change in this plan).
5. Match evidence per D2a recorded for each newly enabled skill — two
   positive and two negative cases with scores.
6. Bot restarted (`./scripts/mortimer.sh`), and each new skill observed
   firing at least once: `grep skill_injected logs/bot.log`.
6a. Part G: `grep screen_view logs/bot.log` shows one metadata line per
   capture, and `ls logs/screen/` is empty unless a debug deadline is set.
7. `grep skill_injected logs/bot.log | awk '{print $NF}' | sort | uniq -c`
   reviewed after a day of normal use — a skill firing on nearly every run
   is over-matching and its description needs a sharper anti-trigger.

---

## 11. Out of scope

- Importing any Anthropic skill, verbatim or edited (D1).
- Enabling any IMPORTED skill. `config/skills.yaml` is edited here only to
  register skills authored by this plan (D2); the one-at-a-time manual gate
  stands unchanged for third-party content.
- Any `scripts/` directory in any skill (D3).
- Re-enabling or re-reviewing the four skills already on disk beyond the
  description edits in Part D.
- Changing `MATCH_THRESHOLD`. Part A produces the data that would justify a
  change; changing it before that data exists is guessing.
- The 12 skills in §1.1 classified as no-fit — creative, document,
  enterprise. Their classification is unverified but the cost of being
  wrong is one skipped skill, not a defect.
- Anything from the graph-engineering review (separate document, separate
  decision).

---

## 12. Open decisions — need Larry

**O0. RESOLVED 2026-08-18 — authored skills ship enabled.** See D2/D2a/D2b.
The one-at-a-time gate is narrowed to imported skills only.

**O1. Scope of `verify-before-claiming`.** Written narrowly for the
developer agent, or broadly for every sub-agent? Broad is more useful and
more likely to over-match; `MAX_INJECTED = 1` means a broad match can crowd
out a more specific skill. *Recommendation:* write it broad in content but
rely on the description's anti-trigger to keep it from firing on trivial
lookups.

**O2. Per-skill agent restriction.** Workflows have an `agents:` field;
skills do not — the Agent Skills standard has no such field, and adding one
would be a local extension of a standard chosen precisely to avoid local
extensions. *Options:* (a) accept no restriction, rely on matching;
(b) put it under the standard's optional `metadata:` and honor it in
`match_skill`. *Recommendation:* (a) for now — the standard's shape is
worth more than the control, and no observed problem requires it.

**O3. Tool-existence backstop (E3).** Build it, or leave the §3 weak row as
discipline? *Recommendation:* leave it until a real skill names a
nonexistent tool. Prose-matching for tool names would produce false
positives on ordinary English.

**O4. Does Part E get built at all**, given it rests on an unverified
capability? *Now sequenced after Part G* — G makes the capability
observable, so E becomes answerable with evidence instead of by guess.

**O5. Part G Tier 2 — how long a window, and is it wanted at all?**
Tier 1 (text + metadata) and G3 (retain failed captures) carry almost no
privacy cost and I recommend both unconditionally. Tier 2 (every image on
disk) is the one that trades real exposure for diagnostic completeness.
*Options:* (a) skip Tier 2, rely on Tier 1 + G3; (b) Tier 2 with a 7-day
default deadline; (c) Tier 2 with a 24-hour default.
*Recommendation:* (a) first — run Tier 1 and G3, see whether they actually
explain the failures. Add Tier 2 only if a real failure survives them.
That keeps the strongest guarantee intact until something specific
demands breaking it.

**O6. `JARVIS_SCREEN_RETENTION_HOURS` default.** 48 proposed. The run log
uses 30 *days*; council rounds 180 days. Screenshots deserve the shortest
retention in the system by a wide margin, and 48h is already generous for
"debug the thing that broke this morning."

---

## 13. Risks and what is unverified

- **No evidence skills improve outcomes.** One run (`9f60f6d0`) shows no
  regression. That is all. This plan adds skills on the reasoning that
  authored capability knowledge helps — not on measured benefit.
- **Thresholds are uncalibrated.** `MATCH_THRESHOLD = 0.30` was chosen by
  argument (between a procedure's and a workflow's), not computed from a
  corpus the way `PROCEDURE_MATCH_THRESHOLD` was via `--calibrate`.
- **12 of 19 Anthropic skills were classified without being read.**
- **Enabling at build time moves risk earlier** (D2). Shipping inert meant
  a bad match was caught when Larry chose to enable, after reading. Now a
  bad match goes live at merge, on a threshold that is itself uncalibrated
  (previous bullet). D2a's four recorded cases and acceptance item 7's
  frequency check are the mitigation; neither is as strong as a human
  reading the skill before it takes effect. **This is the main risk the
  plan accepts rather than eliminates.**
- **Prompt-size interaction.** The developer already carries a 4,588-char
  prompt plus up to 8,000 chars of repo map. `mcp-server-authoring` could
  add ~8,000 more on match. The meta-prompts review proposes conditional
  prompt sections to offset this; the two plans should be sequenced
  together if both are approved.

---

## 14. Approval

Nothing in this document has been implemented. On approval, state which
Parts are in scope and how the Open Decisions in §12 resolve.
