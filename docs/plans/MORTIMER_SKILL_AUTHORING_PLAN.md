# Mortimer skill authoring — the `skill-authoring` skill and the allow-list move

**Status:** DRAFT for Larry's approval, 2026-08-26. Implements roadmap track
**T6, skill-authoring half only** (`docs/plans/MORTIMER_PLATFORM_ROADMAP.md`
§2.6, first two bullets). Gate **G6(a)** and **G6(c)**.

**Author / origin.** The roadmap, §2.6: *"Skill-authoring skill
(`skills/skill-authoring/SKILL.md`): encodes `skills/README.md`'s seven-item
checklist, requires a `python -m jarvis.agent_skills --explain` run with two
positive and two negative utterances before proposing, applies item 7's
merge-or-sharpen rule, and prefers `--from-procedure` when a matching
successful run exists. Its own `--explain` run against `mcp-server-authoring`
and `technical-plan-document` is its first acceptance test."* And: *"Allow-list
change (human commit, C8): `skills/**` moves from deny to allow;
`config/skills.yaml` stays denied, so authoring is possible and enabling
remains Larry's one-at-a-time human act."*

Behind that sits Larry, 2026-08-18, quoted at the top of
`jarvis/agent_skills.py:3-6`: *"I want our implementation of Skills to mirror
what Claude does for skills so that we could leverage that repository as
well"* and *"skills should only be added one at a time so the risk can be
reviewed individually."*

**The Xcode half of T6 is NOT in this plan.** §2.6's remaining two bullets —
the `mortimer.app.yaml` under the Swift app, the build→relaunch sidecar job
with rollback, `xcrun mcpbridge`, and the `macos/**` allow-list change — are
`MORTIMER_XCODE_REBUILD_PLAN.md`, queued 8th (roadmap §8) because they depend
on T1.3 (there must be a Swift app to rebuild). Nothing in this plan touches
`macos/**`, `jarvis/agents/workspace.py`, or `config/mcp_servers.yaml`. Gate
G6(b) — rollback-on-failed-launch — is that plan's, not this one's.

---

## Revision table (findings closed, 2026-08-27)

Every fix below was re-measured against the repo snapshot with the real
scorer / `select_developer_sections` / `discover()` / `explain()`; the
commands and outputs are in §7 and §3.

| Finding | Sev | Section(s) changed | What changed |
|---|---|---|---|
| F1 | BLOCKER | §3 S1, S3; §7 T1/T1b; §7 T2 | Description rewritten (473→391 chars) so it displaces **nothing** — every `technical-plan-document`/`mcp-server-authoring` task and all self-edit vocabulary ("improve Mortimer itself") now score below the winning skill or below threshold. Re-measured in the sandbox; T1/T1b tables replaced; `MATCH_EVIDENCE.silent` gains the four displacement utterances. |
| F2 | BLOCKER | §5 step 9; §7 T1; §8 check 1 | Step 9 runs BEFORE enablement, so `--explain` prints `[inert  ]` and "Nothing would be injected". Step 9 now compares only `score=`/`shared_tokens=`; the pre-enable transcript is added to §7 T1; the `<< INJECTED` / `Would inject:` expectations moved to §8 check 1 (post-enable). |
| F3 | MAJOR | §5 step 1; §4 | Literal allow-list diff replaced by "apply row W0-SKILL of `docs/plans/ALLOWLIST_SEQUENCE.md` and run its verify command" (SEC owns that file, cross-plan resolution §A). Removes the stale `config/agents.yaml` probe row that D-H9 would have flipped. |
| F4 | MAJOR | §1 gap 2 | Corrected the false premise: `mcp_repo`'s `repo_write_file` ALREADY writes `skills/**` today (its deny list is separate — `mcp_servers/mcp_repo/logic.py`, only `config/skills.yaml` — verified). |
| F5 | MAJOR | §3 S1 body, S4; §7 T2; §10 R3 | Corrected the false premise: `propose_edit` writes the live working tree and `load_skills()` re-reads per delegation, so amending an ENABLED skill is live at the next delegation, before validate/PR/merge. New-folder-inert vs enabled-amendment-live now stated distinctly; T2 pins enabled skills' safety headings. |
| F6 | MAJOR | §3 S7; §10 R5; §7 T4 | S7's "a section can only be added" reasoning replaced with the real mechanism: adding vocabulary NARROWS fail-open tasks ("make me a skills library" 3 sections → `['self_development']`). R5 corrected; T4 gains a pinned narrowing test. |
| F7 | MAJOR | §7 T2 | Added `test_no_skill_displaces_another_on_its_own_evidence` (the `MAX_INJECTED = 1` property, stated once); populated `MATCH_EVIDENCE` for `technical-plan-document` and `mcp-server-authoring`; fixed `_scored` docstring, the `StopIteration` default, and a tie-break comment. |
| F8 | MINOR | §7 T6; §8 check 2 | Test-count arithmetic corrected (T3 contributes 7, not 8) and re-totalled after F5/F6/F7 additions; §8 check-2 floor updated. |
| F9 | MINOR | §3 S5; §4; §5 step 7 | Enable-commit references "§5 step 9" → "step 10" (step 9 is verification; step 10 is Larry's enable). |
| F10 | MINOR | §3 S1 body, S12; §7 T7 | "bare three-hyphen line" → "any line that STARTS with three or more hyphens" (a rule, a longer rule, or a `--- a/path` diff header), matching `text.split("\n---", 2)`. |
| F11 | MINOR | §1 scorer table | "40-word stop list" → "44-word (`what/which/who/how` stopped, `why` not)". |
| F12 | MINOR | §1 gap 4, §3 S4, §6 | `SECTION_MATCH_THRESHOLD` :327 → :328; `*.md`-root-only :9 → :10. |
| F13 | MINOR | §8 check 3 | Run `check_allowlist.py` WHILE on the self-edit branch, before merge; on `main` it prints "not enforced". |
| F14 | MINOR | §5 step 2 | "Run these three" → "four"; `grep -c … || true` so a zero count does not abort under `set -e`. |

**Roadmap constraints this plan is bound by.**

| C | How this plan honours it |
|---|---|
| **C1** — backend contract unchanged for the client migration | No sidecar route, no app-message, no MCP tool is added or altered. `TOTAL_TOOLS` is unchanged (§3 S8). |
| **C2** — localhost is the trust boundary | Nothing here binds a socket or listens on anything. |
| **C3** — sensitive tier gated on G3 | Not touched. |
| **C4** — every mutation is draft → confirm | Authoring a skill is a repo write and goes through the existing `selfedit_start` → `selfedit_validate` → `selfedit_submit` two-phase path (§5 step 7). No new write path is created. The roadmap names "skill enable" as one of the C4 mutations; this plan makes enabling a **human git commit**, which is stricter than draft→confirm, not weaker (§3 S5). |
| **C5** — sub-agents act on data, never on windows | The skill instructs no UI action; it names no `ui_control`. |
| **C6** — untrusted content never shares an agent with an outbound channel | No agent's server list changes. `config/agents.yaml` is not touched. |
| **C7** — routing eval ≥ 90 % | No new agent, no Supervisor model change, **no Supervisor prompt change**. The one prompt edit (S7) is inside `DEVELOPER_SECTION_WHEN`, a developer-sub-agent section selector that the roadmap's own §2.6 predecessor (`MORTIMER_DEVELOPER_SECTIONS_AND_VISUAL_VERIFY_PLAN.md` Part A) established explicitly so that "the specialization decision moves to the developer level while Supervisor routing is untouched". Re-run recorded in §8 anyway. |
| **C8** — self-edit allow/deny changes are human commits | §5 step 1 is the literal diff Larry applies by hand, in its own commit, on `main`. No implementer step and no assistant self-edit may write `config/self_edit_allowlist.json`; it is on its own deny list (`config/self_edit_allowlist.json:21`). |
| **C9** — secrets in the vault | No credential is read, written, or named. |
| **C10** — degradation-proof | The skill's complete text is in §3 S1, byte for byte. Every acceptance number in §7 was **measured in the sandbox**, not estimated; the commands and their output are reproduced. No step says "use judgment". |

**Contracts this plan INTRODUCES (consumed by later plans):**

- **S-A — the match-evidence fixture.** `tests/unit/test_skill_match_evidence.py`
  holds `MATCH_EVIDENCE: dict[str, dict[str, list[str]]]`, mapping a skill
  name to `{"fires": [utterance, ...], "silent": [utterance, ...]}`. It is
  the single recorded location for `skills/README.md` item 6. Any later plan
  that adds a skill adds its two positive and two negative utterances here in
  the same PR. Full definition in §7 T2.
- **S-B — `skills/**` is writable by a self-edit; `config/skills.yaml` is
  not.** After §5 step 1, an assistant may author or amend any file under
  `skills/`, and may never enable one. Later plans may rely on both halves.

**Contracts this plan CONSUMES (by doc + section):**

- `docs/plans/MORTIMER_SKILL_LIBRARY_PLAN.md` — the corrected D1 lesson
  (anti-triggers live in the BODY, never the description) and D2/D2a
  (authored skills ship enabled; two positive and two negative `--explain`
  cases are the enable gate). Both are **binding** here; §3 S2 restates the
  mechanism rather than re-deriving it.
- `docs/plans/MORTIMER_PLATFORM_ROADMAP.md` §0 C1–C10, §4 G6, §6 invariants.
- No K1–K8 cross-plan contract from the brief is consumed or deviated from.
  This plan adds no table, no route, no MCP server, no agent, and no token.

---

## Corrections to the roadmap

**None to the roadmap.** Two corrections to the *repository*, both required
before the skill can be written truthfully, because the skill's job is to
encode `skills/README.md`'s checklist and one item of that checklist is
wrong:

**R-1 — `skills/README.md:50` tells an author to put the anti-trigger in the
description. That is the exact thing measured to be backwards.** Item 4 reads
*"**Does the description carry an anti-trigger?** One sentence saying what it
is NOT for."* `MORTIMER_SKILL_LIBRARY_PLAN.md:8-21` records the measurement
that killed it: *"adding 'what are you planning to do next' to
`technical-plan-document`'s description moved that task's score from 0.000 to
1.000 — precisely backwards"*, and `jarvis/agent_skills.py:101-105` carries
the same finding in a code comment beside `MIN_SHARED_TOKENS`. The README
paragraph is a survivor of the pre-correction D1 draft
(`MORTIMER_SKILL_LIBRARY_PLAN.md:378` is the original wording it was copied
from). All five shipped skills already ignore it — none of their descriptions
contains an anti-trigger (`grep -n "^description:" skills/*/SKILL.md`), and
`mcp-server-authoring` and `technical-plan-document` each carry theirs as a
`## When this does not apply` body section. Item 4 is corrected in §5 step 3.

**R-2 — `skills/README.md:59-60` requires match evidence to be "recorded" and
names no location.** Nothing in the repository stores it today; the numbers
from the 2026-08-18 enable gate exist only in a plan document's prose. §3 S9
gives it one file and one shape, and a test that re-measures it on every run.

---

## §0 Binding constraints for the implementing model

1. **You are Claude Sonnet implementing this plan with no access to the
   conversation that produced it. Every decision is already made.** If you
   find yourself choosing between two options, you have found a defect in
   this plan — stop, and report which section is ambiguous.
2. **Do not run `git` in the sandbox.** It leaves `index.lock`. Every commit
   in this plan is Larry's, on the branch named in §5.
3. **Steps 1 and 2 of §5 are Larry's, not yours.** They edit
   `config/self_edit_allowlist.json` and `config/skills.yaml`, both of which
   are on the self-edit deny list. If you are running as a self-edit and your
   diff touches either file, you have violated C8 — remove it.
4. **The skill's text in §3 S1 is literal.** Copy it verbatim, including
   punctuation and the em dashes. Do not "improve" the description: its exact
   token set is what produces the measured scores in §7, and every word was
   chosen against a false positive. Changing one word invalidates the
   acceptance test.
5. **Verify before you claim.** Every "today X does Y" sentence in this plan
   carries a `path:line`. If a citation does not match the file you are
   looking at, the repository has moved on — report the mismatch and stop
   rather than adapting.
6. **No new environment variable, no new numeric constant, no new kill
   switch.** §6 is a table of things that already exist. If your change needs
   a new number, you are building something this plan did not ask for.

---

## §1 What exists today (verified, path:line) and the gap

### The loader and the scorer

| Fact | Where |
|---|---|
| A skill is a folder under `skills/` containing `SKILL.md` (YAML frontmatter + Markdown body), Agent Skills open format. | `jarvis/agent_skills.py:8-15`, `skills/README.md:1-5` |
| `SKILLS_DIR = <repo>/skills`, `SKILLS_CONFIG = <repo>/config/skills.yaml`. | `jarvis/agent_skills.py:72`, `:77` |
| `MATCH_THRESHOLD = 0.30`, `MAX_INJECTED = 1`, `MIN_SHARED_TOKENS = 2`. | `jarvis/agent_skills.py:84`, `:88`, `:106` |
| `NAME_MAX_CHARS = 64`; name regex `^[a-z0-9]+(?:-[a-z0-9]+)*$`; reserved words `anthropic`/`claude`; `DESCRIPTION_MAX_CHARS = 1024`; `BODY_SOFT_MAX_CHARS = 20_000`. | `jarvis/agent_skills.py:109-118` |
| Matching scores the **card** (`f"{name}: {description}"`) only; the body is read lazily on activation. | `jarvis/agent_skills.py:134-143`, `:350-368` |
| The scorer is `jarvis.procedures._overlap_score(a, b) = len(a & b) / min(len(a), len(b))` over `_tokens()` — lowercase `[a-z0-9]+` runs of ≥ 3 chars, minus a 44-word stop list (note: `what`/`which`/`who`/`how` are stopped, `why` is **not** — which is why `why` survives into a card and drove three F1 false fires). | `jarvis/procedures.py:88`, `:109-123`, `:136-145` |
| `match_skill` requires **both** `score >= 0.30` **and** `len(card_tokens & task_tokens) >= 2`; ties broken by highest score; returns at most one skill. | `jarvis/agent_skills.py:358-368` |
| The single injection point: `SubAgent._loop` calls `match_skill(task)` and injects the skill as one system message between the procedure hint and the workflow rule. | `jarvis/agents/base.py:37`, `:528` |
| A skill on disk is inert until its name is listed under `enabled:` in `config/skills.yaml`. Missing config ⇒ nothing enabled. | `jarvis/agent_skills.py:270-289`, `:315-320` |
| `--explain` is deliberately DB-free and is the documented enable gate: *"a skill is not registered in config/skills.yaml without recorded scores for two tasks it should match and two it must not."* | `jarvis/agent_skills.py:465-485` |
| `--from-procedure <ID>` copies (never moves) an `active` procedure row into a `REVIEW ME` skill draft, and deliberately does **not** enable it. Refuses a non-`active` procedure without `--force`. | `jarvis/agent_skills.py:413-459`, `:612-638`, `:379-391` |
| Five skills on disk today, all five enabled. | `skills/`, `config/skills.yaml:24-34` |

### The self-edit gate

| Fact | Where |
|---|---|
| Deny wins over allow; patterns match the full repo-relative POSIX path; `**` crosses segments; a pattern with no slash matches root-level files only. | `jarvis/selfedit/allowlist.py:8-13`, `:75-79` |
| `skills/**` is on the **deny** list today (line 25); `config/skills.yaml` is on it too (line 24); `config/**` is on the allow list (line 5), so the `config/skills.yaml` deny entry is what makes it human-only. | `config/self_edit_allowlist.json:5`, `:24`, `:25` |
| `SelfEditService._check_path` raises `SelfEditError("path is not on the self-edit allowlist: …")` before any write; called by both `read_file` and `propose_edit`. | `jarvis/selfedit/service.py:378-386`, `:188`, `:203` |
| `validate()` runs four checks in order: **allowlist** (re-checks the whole diff vs `origin/main`), **backend import**, **frontend build**, **`pytest tests/unit -q`** (`VALIDATE_PYTEST_TIMEOUT_S = 300`). | `jarvis/selfedit/service.py:391-440` |
| `submit()` refuses unless `_validated_ok` is True, and any new `propose_edit` resets it to False. | `jarvis/selfedit/service.py:443-452`, `:213` |
| CI re-runs the same matcher on `jarvis/self-edit/*` branches only; other branches are exempt because "the allowlist constrains the agent, not the humans". | `scripts/check_allowlist.py:3-6`, `:37-40`, `:56-61` |

### The gap, stated exactly

1. **There is no skill about authoring skills.** `skills/skill-authoring/`
   exists but holds a **9-line stub** whose body is the literal line
   `# Body placeholder` (`skills/skill-authoring/SKILL.md:9`). It is not
   listed in `config/skills.yaml`, so it is inert; `--list` reports it
   `inert`. This plan replaces that file in full. *(Taxonomy item 9: this is
   a MODIFY, not a CREATE — see §4.)*
2. **`skills/**` is denied to the *self-edit* loop**, so the multi-file
   `selfedit_start` path — the one this plan routes authoring through —
   cannot write a skill today. But it is **not** true that "Mortimer cannot
   author a skill at all". `mcp_repo`'s single-file `repo_write_file` **can
   already write `skills/`** today, by voice: `mcp_repo` does not consult
   `config/self_edit_allowlist.json` at all — it carries its **own, separate**
   write deny list (`DENY_WRITE_PATHS`/`DENY_WRITE_SEGMENTS`/`DENY_WRITE_GLOBS`
   in `mcp_servers/mcp_repo/logic.py`), and `skills/**` appears in none of
   them; only `config/skills.yaml` is named there. The developer agent holds
   `mcp-repo` (`config/agents.yaml`, developer `mcp_servers:` list includes
   `mcp-repo`), so `repo_write_file` → `repo_commit_write` reaches
   `skills/<name>/SKILL.md` today. Verified at source, 2026-08-27:
   `_check_write_allowed(resolve_repo_path(root, "skills/brand-new/SKILL.md"), root)`
   passes for `skills/skill-authoring/SKILL.md`, `skills/brand-new/SKILL.md`
   and `skills/README.md`, and refuses `config/skills.yaml` ("not writable
   through this tool (protected configuration)"). What that path lacks is the
   `validate()` gate: it writes one dictated file at a time with no
   frontmatter-conformance or pytest check. This plan's contribution is
   therefore **not** "make authoring possible" — it is "make the *validated,
   multi-file* `selfedit_start` path reach `skills/`, so authoring a whole
   skill goes through the four checks instead of being dictated file by file".
   `write_skill()` (`jarvis/agent_skills.py:379`) remains a library function
   with no MCP tool in front of it.

   **Decision — the `mcp_repo` single-file path stays open.** It is not
   widened by this plan and closing it is out of scope: `repo_write_file`'s
   deny list already protects the one file that matters (`config/skills.yaml`,
   the enable gate), so a dictated single-file skill write is inert exactly
   like a `selfedit_start`-authored one until Larry enables it. The two paths
   converge at the same human gate; the only difference this plan cares about
   is that the multi-file path is validated, which is why the skill body tells
   the agent to *prefer* `selfedit_start` for authoring.
3. **`skills/README.md` item 4 is wrong** (R-1) and item 6 has no storage
   location (R-2).
4. **Measured, and not previously known:** a skill-authoring task selects the
   **wrong developer prompt section**. `select_developer_sections("write a
   new skill for the skill library about running database migrations")`
   returns `['app_development']` — the *app* protocol, which routes toward
   `app_create` and a new private GitHub repo — and **not**
   `self_development`, which is the section that routes to `selfedit_start`.
   Cause: `DEVELOPER_SECTION_WHEN["app_development"]`
   (`jarvis/prompts.py:304-307`) contains `app_write`, which `_tokens()`
   splits into `{app, write}`, so that task shares `{new, write}` = 2 of its
   8 tokens ⇒ `0.250`, exactly `SECTION_MATCH_THRESHOLD`
   (`jarvis/prompts.py:328`, `SECTION_MATCH_THRESHOLD = 0.25`), while
   `self_development` shares only `{write}`
   ⇒ `0.125`. Reproduced in §7 T4. S7 closes it.
5. **`TestShippedSkills` in `tests/unit/test_agent_skills.py:416-436` reads
   the real `skills/` directory**, not a fixture — verified by running
   `discover()` against a deliberately malformed folder (§7 T3). That makes
   it, today and unchanged, the gate that stops a broken `SKILL.md` reaching
   a PR. What it does **not** catch: a frontmatter `name` that disagrees with
   its folder name. Verified: a folder `folder-name-x/` whose frontmatter
   says `name: different-name` parses clean, passes every existing
   assertion, and would sit permanently inert if `config/skills.yaml` named
   the folder. S6 closes it.

---

## §2 Non-goals

- **The Xcode rebuild half of T6.** `mortimer.app.yaml` for the Swift app,
  the build→relaunch sidecar job and its 30 s rollback, `xcrun mcpbridge` in
  `config/mcp_servers.yaml`, ad-hoc signing, and the `macos/**` allow-list
  move are all `MORTIMER_XCODE_REBUILD_PLAN.md` (roadmap §8 item 8), which
  depends on T1.3. Gate G6(b) belongs there. This plan closes G6(a) and
  G6(c) only.
- **No MCP tool for authoring skills.** No `skill_write`, no `skill_explain`.
  Authoring is a repo write and goes through `selfedit_start` like every
  other multi-file change (`jarvis/prompts.py:296`). `TOTAL_TOOLS` is
  unchanged; the routing-eval fixture is unchanged.
- **No change to matching.** `MATCH_THRESHOLD`, `MIN_SHARED_TOKENS`,
  `MAX_INJECTED`, `_overlap_score` and `_tokens` are read, never edited. A
  plan that "fixes" over-matching by moving a threshold would silently change
  every existing skill's behaviour.
- **No per-skill agent restriction.** `MORTIMER_SKILL_LIBRARY_PLAN.md` O2
  left this open with recommendation (a) — accept no restriction. Unchanged
  here; the Agent Skills standard has no such field and adding one is a local
  extension of a standard chosen to avoid local extensions.
- **No automatic promotion.** Nothing in this plan calls
  `--from-procedure` on a schedule or from a watcher. It stays an operator
  command the skill tells an agent to *prefer*, never a trigger.
- **No `references/` or `scripts/` support.** `scripts/` is never executed
  (`jarvis/agent_skills.py:28-44`) and this skill must not bundle one;
  `references/` was deliberately not built
  (`MORTIMER_SKILL_LIBRARY_PLAN.md:3-5`, Part F).
- **The web console is not touched.** No panel shows skills and none is
  added; `web/` is being retired under T1.

---

## §3 Decisions

### S1 — The complete text of `skills/skill-authoring/SKILL.md` is fixed here. Copy it verbatim.

*Why:* C10. A skill is prompt text injected into a sub-agent run; its exact
wording is its behaviour, and its exact **description tokens** are its
matching behaviour. The measured scores in §7 T1 are a property of the token
set below and of nothing else. An implementer who paraphrases produces a
different skill with unmeasured triggering — which under `MAX_INJECTED = 1`
does not merely add noise, it *displaces* the skill that should have won.

Measured on the exact text below with the real `parse_skill`/`discover`,
2026-08-27 (the description was rewritten to close review finding F1 — see
§3 S3 and §7 T1 — and the body gained the F5/F10 corrections): the file is
**11,178 characters / 234 lines**; `parse_skill` returns `problems: []`;
`Skill.body()` returns **10,633 characters**, well inside
`BODY_SOFT_MAX_CHARS = 20_000`; the description is **391 characters**,
inside `DESCRIPTION_MAX_CHARS = 1024`. The body figure is not cosmetic —
see **S12**, and confirm it after transcription with the one-liner in §5
step 3.

````markdown
---
name: skill-authoring
description: Author a SKILL.md for the skill library, or sharpen one that over-matches — frontmatter fields, the seven-point checklist, keeping anti-triggers out of the card, recording measured match evidence from the --explain output before a skill goes live, and promoting a learned procedure with --from-procedure. Use when asked to write, sharpen or promote a skill, a SKILL.md, or the skill library.
metadata:
  source: authored 2026-08-26
  concept_from: MORTIMER_SKILL_AUTHORING_PLAN.md
  agent: developer
---

# Authoring a skill

## When this does not apply

Building or extending an MCP server, or adding a tool to one, is a different
artifact — `mcp-server-authoring` owns it. Writing an implementation plan,
spec or design document is `technical-plan-document`'s. Those two share the
verbs "write" and "author" with this skill and nothing else.

Asking which skills exist, or whether one is live, needs none of this:
`python -m jarvis.agent_skills --list` answers it in one line.

This paragraph is in the BODY on purpose, and that is a rule, not a habit —
see "The description is the whole matching surface" below.

## Prefer promotion when the evidence already exists

Before authoring from scratch, check whether a learned procedure already
describes the thing:

```bash
python -m jarvis.procedures --explain "<the task>" --agent developer
```

If an `active` procedure matches, promote it instead of writing a new file:

```bash
python -m jarvis.agent_skills --from-procedure <id>
```

Promotion is a COPY. The procedure row is kept, keeps its success and
failure counters, and keeps being matched — so an over-eager promotion is
undone by removing a name from `config/skills.yaml`, never by reconstructing
a deleted row. The command refuses a procedure that is not `active`, because
a candidate has not yet cleared its success threshold; `--force` exists and
is almost never the right answer.

What it writes is a DRAFT. The body it generates says `REVIEW ME` and is
built from the procedure's one-line summary. Replace that section with the
real steps before proposing anything. A promoted skill that still says
`REVIEW ME` is not finished.

## The file

`skills/<name>/SKILL.md`, YAML frontmatter and a Markdown body. Nothing
else in the folder: never a `scripts/` directory — Mortimer does not execute
them, and their presence means the skill was written expecting capabilities
it will not get here.

Three hyphens alone on a line open the frontmatter; these fields follow;
three more hyphens close it; the Markdown body starts after that.

```yaml
name: kebab-case-name
description: One sentence of what it is for, then one sentence of when to use it.
metadata:
  source: authored YYYY-MM-DD
  agent: developer
```

**Never write any line that STARTS with three or more hyphens anywhere in
the body** — a horizontal rule (`---`), a longer rule (`----`), or a
unified-diff header (`--- a/path`). `_split_frontmatter` does
`text.split("\n---", 2)`: it splits on the substring `"\n---"`, so the first
match is the frontmatter's closing fence and the SECOND is whatever
three-hyphen line comes next — and everything after it is silently dropped
from the text the agent actually receives. The file on disk still looks
complete, `--validate` still passes, and the agent gets half a skill. Where
you would reach for a horizontal rule, or need to quote a diff, use a `##`
heading, a blank line, or fence the diff and indent it so no body line begins
with `---`.

Hard limits, enforced by `validate_frontmatter`:

- `name` — at most 64 characters, matching `^[a-z0-9]+(-[a-z0-9]+)*$`, and
  it may not contain `anthropic` or `claude` (reserved by the standard).
- `description` — at most 1024 characters. Required.
- Body — under about 20,000 characters. Over that is a warning, and a
  warning fails `tests/unit/test_agent_skills.py`, so treat it as a limit.
- The folder name and the frontmatter `name` MUST be the same string.
  `config/skills.yaml` lists the frontmatter name; if they disagree the
  skill parses cleanly, reports no error, and stays permanently inert.

## The description is the whole matching surface

Matching scores `name: description` — the card — and never the body. It is
token overlap: lowercase runs of letters and digits, three characters or
longer, minus a stop list. The score divides by the SMALLER of the two token
sets, so a short task whose few tokens all appear somewhere in a long
description scores near 1.0.

Three numbers govern the outcome, and none of them is yours to change:
`MATCH_THRESHOLD = 0.30`, `MIN_SHARED_TOKENS = 2`, `MAX_INJECTED = 1`.

**Never put an anti-trigger in the description.** This is the one rule here
that came from a measurement rather than an opinion: adding *"what are you
planning to do next"* to `technical-plan-document`'s description moved that
task's score from 0.000 to **1.000** — precisely backwards, because naming a
false positive adds its exact words to the matchable token set. Anthropic's
skill descriptions are read by a model and the pattern works there; these are
token-matched and it does not port. The anti-trigger goes in a
`## When this does not apply` body section, which is never scored.

What a good description does instead: use the specific nouns of its own
domain, and leave out the generic verbs its neighbours own. Two skills that
both contain "write" and "new" will fight over every task containing both.

## The seven-item checklist

Run this before proposing the skill, not after. It is the same list as
`skills/README.md`, and the two must stay identical.

1. **Does it bundle `scripts/`?** Authored here: never.
2. **Does every tool it names actually exist?** Check against
   `mcp_servers/*/skill.yaml`. A skill that tells an agent to call a tool
   Mortimer does not have invites the agent to explain a failure it does not
   understand.
3. **Is it phrased as reference, not as an order?** A skill says how a thing
   is done. A workflow says it must be done that way. If the body reads
   normatively, it belongs in `config/workflows/`.
4. **Does it carry an anti-trigger — in the BODY, never the description?**
   One `## When this does not apply` section saying what it is not for.
5. **Does it say what to do when a tool it names is unavailable?** Without
   this, an agent facing a missing tool invents a reason.
6. **Match evidence recorded** — two utterances it must fire on and two it
   must stay silent on, added to `MATCH_EVIDENCE` in
   `tests/unit/test_skill_match_evidence.py` in the same change. The
   negative cases matter more.
7. **No overlap with an existing skill.** See below.

## Measure before you propose

Item 6 is a command, not an intention. Run it four times — twice for
utterances this skill must win, twice for utterances another skill must win:

```bash
python -m jarvis.agent_skills --explain "<utterance>"
```

Read three things in the output: the `score`, the `shared_tokens` list, and
the `<< INJECTED` marker. A skill fires only when its score is at least 0.30
AND it shares at least two tokens AND it is the top scorer AND it is enabled.

- A **positive** utterance passes when the line for your skill carries
  `<< INJECTED`.
- A **negative** utterance passes when the line for your skill says `fail`.
  Being second place is not passing — read the `shared_tokens` list and
  remove the shared word from your description.

If a negative case fires, the fix is always the description, never the
threshold. Delete the generic word the two skills share.

Then add the four utterances to `MATCH_EVIDENCE` so the measurement is
re-run on every test run instead of living in someone's memory.

## Item 7 in practice: merge or sharpen, never a competitor

`MAX_INJECTED = 1`. Only the top-scoring skill is ever injected, so two
skills that both match a task are not complementary — they compete, and the
loser contributes nothing at all.

So if a draft scores above threshold on a task another skill owns, there are
exactly two acceptable outcomes:

- **Merge** the draft's content into that skill and ship no new file. This
  is what happened to procedures #18 and #22, which became one
  `technical-plan-document` rather than two files.
- **Sharpen both descriptions** until each wins only its own tasks, and
  record the new measurements.

Shipping a third option — a broad, general-discipline skill — is the case
that looks most reasonable and is most wrong: it loses to every specific
skill and fires only when nothing specific matched. That is why the proposed
`verify-before-claiming` skill does not exist; its content went into
`jarvis/prompts.py`'s `VERIFICATION_TAXONOMY_RULE`, which reaches all five
agents with no matching involved. A rule that must always hold belongs in
the prompt layer, never in a skill.

## What you may write, and the one file you may not

`skills/**` is on the self-edit allowlist: you may create a skill folder,
write its `SKILL.md`, amend an existing one, and update `skills/README.md`.

`config/skills.yaml` is on the **deny** list and always will be. Enabling a
skill is Larry's own act, one at a time, in his own commit. Do not propose an
edit to it and do not ask for it to be added to the allowlist.

Report the state honestly, and the honest state has two cases:

- A **new** skill you just authored is **inert** — its name is not in
  `config/skills.yaml`, so nothing injects it until Larry enables it. Do not
  call it "live". Say: the file is written, the name is not enabled, and
  enabling is his.
- An **amendment to a skill that is already enabled** is **live at the next
  delegation** — the loader re-reads every enabled `SKILL.md` from disk on
  every run, so your edited text is in effect immediately, before any PR.
  Say that plainly; do not claim it is "not yet active". Amending an enabled
  skill's safety-bearing instructions is exactly the change to be most
  careful and most explicit about.

If you attempt it anyway, `SelfEditService` refuses the path with
`path is not on the self-edit allowlist`, `validate()`'s allowlist check
fails the whole session, and CI's `scripts/check_allowlist.py` fails the
branch. Three refusals, not one — do not read a refusal as a bug.

## Before it is finished

```bash
python -m jarvis.agent_skills --validate      # frontmatter conformance
python -m jarvis.agent_skills --list          # on disk, and inert as expected
python -m pytest tests/unit/test_agent_skills.py tests/unit/test_skill_match_evidence.py -q
```

`--validate` exits non-zero if any `SKILL.md` on disk is malformed, and the
unit tests read the real `skills/` directory rather than a fixture, so a
broken file fails the self-edit validation gate before a PR can open. That is
deliberate: it is the mechanical backstop behind every rule above.

## If you cannot run the scorer

If `python -m jarvis.agent_skills --explain` is unavailable — no shell, the
module will not import, the repository tools are not in your list — say so
and stop. Do not propose a skill with estimated scores. The whole enable gate
is the measurement; a skill shipped without it is a guess that displaces a
working skill on some task nobody has thought of yet.
````

### S2 — The description carries no anti-trigger; the body does. This is binding, not stylistic.

*Why:* `MORTIMER_SKILL_LIBRARY_PLAN.md:8-21` is the implemented predecessor
and its correction is binding on this plan by the brief. The mechanism is in
the code comment at `jarvis/agent_skills.py:101-105`. The description in S1
therefore names **no** negative phrase; the words "MCP server",
"implementation plan", "specification" and "document" appear nowhere in it.
They appear in the body's `## When this does not apply`, which
`match_skill` never reads (`jarvis/agent_skills.py:350-368` scores
`skill.card` only; `test_matching_never_reads_the_body` at
`tests/unit/test_agent_skills.py:233` pins it).

Measured consequence, §7 T1: against *"write an implementation plan for the
mail and calendar integration"*, `skill-authoring` shares exactly one token
(`write`) and scores 0.167 — held out by the threshold **and** by
`MIN_SHARED_TOKENS`, two independent bounds.

### S3 — The description was stripped of every generic token that displaced a neighbour. These absences are load-bearing.

*Why:* review finding F1 (BLOCKER) measured the first draft's description
displacing `technical-plan-document` on four ordinary plan-review tasks and
scoring **1.000** on self-edit vocabulary (*"improve Mortimer itself"*).
Under `MAX_INJECTED = 1` a false fire does not add noise — it DISPLACES the
skill that should have won. The rewrite (S1) removed the generic verbs and
generic nouns that caused this and kept the domain nouns that carry the two
positive cases. The full re-measurement is §7 T1/T1b; the 32 card tokens are
`{anti, asked, author, authoring, before, card, checklist, evidence,
explain, fields, frontmatter, goes, keeping, learned, library, live, match,
matches, measured, out, output, over, point, procedure, promote, promoting,
recording, seven, sharpen, skill, triggers, write}`.

An implementer tempted to "tighten" — or "restore a nicer word" — needs to
know which words are deliberate ABSENCES:

| Word | Status | Reason (re-measured 2026-08-27) |
|---|---|---|
| `new`, `tool` | **excluded** | `mcp-server-authoring`'s vocabulary. Their absence is what takes *"add a tool to the mcp-repo server…"* and *"add a new MCP server…"* to **0.000** for `skill-authoring`. |
| `plan`, `specification`, `technical`, `document` | **excluded** | Each is `technical-plan-document`'s own vocabulary — with any second shared verb they produced the four F1 displacements. Now removed. |
| `create`, `draft`, `improve` | **excluded** | Generic verbs F1 proved dangerous: `improve` + `existing` displaced `technical-plan-document` on *"improve the existing spec document"*; `draft` + `review` on *"draft and review the design document"*. Kept only `write`, `sharpen`, `promote`, `author` — see below. |
| `itself`, `mortimer` | **excluded** | The first two words of `DEVELOPER_SECTION_WHEN["self_development"]` — the repo's canonical self-edit phrasing. With both present the first draft scored **1.000** on *"improve Mortimer itself"* and *"improve the name and description"*. Both gone; both tasks now score 0.000. |
| `name`, `description`, `review`, `existing`, `scorer`, `item`, `why` | **excluded** | Each drove an F1 false fire on a coincidental generic phrase (`scorer` → *"explain the scorer to me"* was 1.000; `item` → *"create a new item in the library"* was 0.750). None appears in a positive case, so removing them costs nothing. `item` is why the description says "seven-**point** checklist" while the body heading keeps "seven-item checklist" — the body is never scored. |
| `enabled` | **excluded** | Would fire 1.000 on the status query *"is the skill enabled"* (which `--list` answers). The description says "before a skill **goes live**" instead. |
| `skill`, `library`, `procedure`, `promote`, `evidence`, `match`, `frontmatter`, `explain`, `checklist` | **required** | The domain nouns that carry the two positive cases (`0.375` on `{library, skill, write}`; `0.714` on `{evidence, match, procedure, promote, skill}`). `skill` also appears in the name, so the card carries it twice — harmless, `_tokens` returns a set. |

`write`, `author`, `sharpen`, `promote` are present deliberately: each is a
plausible opening verb, and against a neighbour's utterance each is worth at
most one shared token — which `MIN_SHARED_TOKENS = 2` neutralises on its own
(measured: every `technical-plan-document`/`mcp-server-authoring` task shares
≤ 1 token with the new card, §7 T1).

Three residual fires remain and are ACCEPTED because they displace nothing
(no shipped skill wins them) and each shares a load-bearing domain token:
*"explain why the match never fires"* (`{explain, match}`), *"author a new
review checklist"* (`{author, checklist}`), *"record the evidence and explain
why"* (`{evidence, explain}`). Removing those tokens would break a positive
or drop a real domain noun; injecting `skill-authoring` on these ambiguous
phrasings costs nothing because there was no correct skill to displace.

### S4 — `skills/**` moves from deny to allow; `config/skills.yaml` stays denied. Larry commits it by hand.

*Why:* roadmap §2.6 bullet 2, and C8. The mechanical change is §5 step 1,
now expressed as **row W0-SKILL of `docs/plans/ALLOWLIST_SEQUENCE.md`** (SEC
owns that file — cross-plan resolution §A). The asymmetry is the whole
design: **authoring becomes possible; enabling stays human.** Deny wins over
allow (`jarvis/selfedit/allowlist.py:75-79`), so leaving `config/skills.yaml`
in the deny list keeps it human-only even though `config/**` is allowed.

Two consequences the implementer must not be surprised by — both re-stated
after review finding F5 (MAJOR), which measured the real timing:

- After this change a self-edit may amend **any existing skill**, including
  the already-enabled `mcp-server-authoring`. **An amendment to an
  already-enabled skill is LIVE at the next delegation — before `validate()`,
  before the PR, before the merge.** `propose_edit` does
  `full.write_text(new_content)` straight into the working tree the bot runs
  from (`jarvis/selfedit/service.py:221-223`, `cwd=self.repo_root`), and
  `match_skill` → `load_skills` → `discover` re-reads every enabled
  `SKILL.md` from disk on **every** `SubAgent._loop` with no cache
  (`jarvis/agents/base.py:528`; `load_skills` at `jarvis/agent_skills.py:306`
  calls `discover` unconditionally). So the "gates" are NOT the PR review and
  the pytest check for an enabled-skill amendment — those are downstream of a
  change that is already live. The real gates are **the human merge** and
  **`git checkout` off the session branch**; the mechanical backstop is T2's
  pin on each enabled skill's safety-bearing headings (S9/§7 T2), which turns
  a weakening amendment into a red `pytest` before the PR can open — a check
  that fires *after* the text went live, not before. §10 R3 carries the risk.
  (A **new** skill folder is different: it is inert until Larry enables it,
  because nothing lists its name in `config/skills.yaml` yet.)
- `skills/README.md` also becomes writable (it matches `skills/**`; it does
  **not** match the allow list's `*.md`, which is root-level only per
  `jarvis/selfedit/allowlist.py:10`). That is wanted — the README's "Current
  skills" table has to gain a row whenever a skill is authored.

### S5 — Enabling `skill-authoring` is a separate human commit to `config/skills.yaml`, made after the skill's PR merges.

*Why:* G6(c) is *"A self-edit that authors a skill lands as a PR with
`config/skills.yaml` untouched."* If the enable line rode in the same commit
as the skill, that gate could never be observed. Two commits, in this order:

1. Larry's allow-list commit (§5 step 1) — `config/self_edit_allowlist.json`
   alone.
2. The implementation PR (§5 steps 3–8) — everything else **except**
   `config/skills.yaml`.
3. Larry's enable commit (§5 step 10) — `config/skills.yaml` alone, one added
   line, after he has read the merged `SKILL.md`.

`skills/README.md:8-13` says a skill authored in this repository ships
enabled, because it is reviewed in its own diff. That still holds — step 3
follows step 2 immediately — but "ships enabled" describes the outcome, not a
single commit. The mechanism that makes it *possible* for it to be Larry's
act is that `config/skills.yaml` is unreachable to the assistant, which is
what step 1 preserves.

### S6 — A frontmatter `name` that disagrees with its folder name becomes a test failure.

*Why:* §1 gap 5, measured. Today a mismatch parses clean, produces no
warning, and leaves the skill permanently inert — the single most confusing
possible outcome, because `--list` shows it and `--explain` scores it while
nothing ever injects it. `write_skill()` cannot produce the mismatch
(`jarvis/agent_skills.py:397-401` derives the folder from the name), but a
hand-written or hand-renamed skill can, and this plan is specifically about
hand-written skills. One assertion in `TestShippedSkills` closes it (§7 T3).

*Rejected alternative:* adding the check to `validate_frontmatter()`. That
function is pure and takes a `dict`, not a path — it has no folder to compare
against, and giving it one would break `write_skill`'s pre-flight call at
`jarvis/agent_skills.py:393`.

### S7 — `DEVELOPER_SECTION_WHEN["self_development"]` gains four words: `skill skills library authoring`.

*Why:* §1 gap 4, measured. Today *"write a new skill for the skill library
about running database migrations"* selects `['app_development']` **only** —
the protocol that routes to `app_create` and a new private GitHub repo — and
never `self_development`, the section that routes to `selfedit_start`. An
agent handed only the app protocol for a skill-authoring task is being told
to do the wrong thing with a confirmation gate that does not apply.

The fix is four tokens appended to the hand-authored trigger vocabulary at
`jarvis/prompts.py:308-318`. Measured before/after in §7 T4:

| Utterance | Before | After |
|---|---|---|
| `write a new skill for the skill library about running database migrations` | `['app_development']` | `['app_development', 'self_development']` |
| `promote procedure 17 into a skill and record its match evidence` | `['app_development', 'self_development', 'planning']` | unchanged |
| `add a new MCP server for controlling the thermostat` | `['app_development', 'self_development', 'planning']` | unchanged |
| `write an implementation plan for the mail and calendar integration` | `['planning']` | unchanged |

On the four rows above `app_development` is never *removed*, and
`self_development` is correctly *added* to the first — that much is what the
plan always claimed. But review finding F6 (MAJOR) measured a real side
effect the original reasoning missed: **adding vocabulary to one section
NARROWS any task that previously matched nothing.**
`select_developer_sections` returns `hits` the moment any section matches and
only falls through to the fail-open `return list(DEVELOPER_SECTIONS)` when
`hits` is empty (`jarvis/prompts.py:397-406`). So a task that used to match
no section — and therefore received **all three** — now matches
`self_development` alone and receives **only** it. Measured 2026-08-27 with
the real function:

| Utterance | Before (fail-open) | After (+ 4 words) |
|---|---|---|
| `make me a skills library` | `['app_development', 'self_development', 'planning']` | `['self_development']` |
| `improve the skill library` | `['app_development', 'self_development', 'planning']` | `['self_development']` |
| `what skills do you have` | `['app_development', 'self_development', 'planning']` | `['self_development']` |

This is a **narrowing, not an inclusion**: those three tasks LOSE
`app_development` (its `app_create` two-phase confirmation protocol) and
`planning`. It is the intended reading — a skills-library request is
self-development, not an app — but it is accepted deliberately, not
discovered later, and it is pinned by a test in §7 T4
(`test_a_skills_library_request_is_self_development_only`). Note (measured):
dropping the bare token `library` does **not** avoid it — `_overlap_score`
divides by the smaller set, so a 3-token task sharing one token (`skills`)
already scores 0.333, above `SECTION_MATCH_THRESHOLD = 0.25`. There is no
wording of S7 that both fixes gap 4 and avoids the narrowing.

*Why the vocabulary and not the section text:* the comment at
`jarvis/prompts.py:300-302` establishes that `DEVELOPER_SECTION_WHEN` is
hand-authored and deliberately not derived from the section prose, precisely
so a word can be added for routing without altering what the agent reads.
`test_no_section_text_was_reworded` (referenced in CLAUDE.md's developer-
sections paragraph) pins the prose; this change does not touch it.

### S8 — No MCP tool, no `TOTAL_TOOLS` change, no routing-eval fixture change.

*Why:* roadmap §6 invariant — *"Every new agent-facing capability is added to
`TOTAL_TOOLS` and the routing eval fixture in the same PR."* This plan adds
**no** agent-facing capability. The skill is prompt text selected by an
existing scorer at an existing injection point (`jarvis/agents/base.py:528`);
the allow-list change widens an existing write path. The Supervisor's prompt,
`config/agents.yaml`, and `config/mcp_servers.yaml` are untouched, so no
routing behaviour changes. C7 is satisfied by construction; §8 has Larry run
the eval anyway, because the roadmap says every plan records a score.

### S9 — Match evidence lives in exactly one place: `MATCH_EVIDENCE` in `tests/unit/test_skill_match_evidence.py`.

*Why:* R-2 — `skills/README.md:59` requires evidence "recorded" and names
nowhere. Prose in a plan document is not a record; it cannot fail. The
fixture is the record, the test is the re-measurement, and the skill body
(S1) tells the author to add rows to it. Deliberately, the **scores are not
duplicated into the skill body** — a number written in two places is
taxonomy item 4 waiting to happen. The body says *what to check*; the test
holds *what was measured*.

The test asserts against **every skill folder on disk**, not against
`config/skills.yaml`, so it is independent of whether Larry has enabled a
name yet. That matters: S5 makes enabling a later, separate commit, and a
test that depended on enablement would go red between step 2 and step 3.

### S10 — The seven checklist headlines are pinned identical in `skills/README.md` and the skill body.

*Why:* the roadmap requires the skill to "encode `skills/README.md`'s
seven-item checklist", so the text necessarily exists twice — a skill is
injected into a prompt and cannot link out to a README. Duplication with no
backstop is taxonomy item 4. `test_checklist_headlines_match` (§7 T2) holds
a tuple of the seven exact headline strings and asserts each appears in both
files. If someone edits one, the test names which.

### S11 — Nothing in this plan is behind a kill switch, and that is deliberate.

*Why:* the repo's convention is `JARVIS_<FEATURE>_ENABLED` read in one place.
This plan ships no feature that can misbehave at runtime: a skill is inert
until named in `config/skills.yaml`, and **removing that one line is the kill
switch** — already implemented, already tested
(`tests/unit/test_agent_skills.py:140`). The blanket switch
`JARVIS_AGENT_SKILLS_ENABLED=false` (`jarvis/agent_skills.py:162-171`) still
disables the whole layer. Adding a third would be a fourth thing to
remember. §9 is the rollback procedure.

### S12 — A bare `---` line in a skill BODY silently truncates the injected text. The skill says so, and a test pins it.

*Why:* found while writing this plan, and it very nearly shipped inside it.
`_split_frontmatter` (`jarvis/agent_skills.py:174-184`) does
`text.split("\n---", 2)` and returns `parts[1]` as the body. The first
`"\n---"` is the frontmatter's closing fence; **the second is whatever
three-hyphen line appears next**, and `parts[2]` is discarded. So a body
containing a Markdown horizontal rule — or, as this plan's first draft did,
a fenced YAML example of a `SKILL.md` frontmatter block — loses everything
after it.

Minimal reproduction, run in the sandbox 2026-08-26:

```
>>> _split_frontmatter("---\nname: x\ndescription: y\n---\n\nAAA\n\n---\n\nBBB\n")
('\nname: x\ndescription: y', 'AAA\n')          # 'BBB' is gone
```

Measured on the first draft of §3 S1: the file was 9,859 characters, of
which `Skill.body()` returned **1,910** — the checklist, the measurement
instructions, the merge rule and the allowlist section were all silently
absent from what an agent would have received. `parse_skill` reported
`problems: []`, `--validate` passed, and `--explain` scored it correctly
(matching reads the card, never the body), so **nothing in the existing
system would have caught it.**

Three consequences, all in this plan:

1. §3 S1's `## The file` section presents the frontmatter fields **without**
   the fences and states the rule explicitly — this is a skill about writing
   skills, so the landmine belongs in it.
2. §7 T7 adds one assertion over every skill on disk. It is cheap and it is
   the only mechanical protection that exists.
3. **`jarvis/agent_skills.py` is still not modified.** Fixing
   `_split_frontmatter` to split only on the *first* `"\n---"` would be a
   two-character change and is tempting; it is out of scope here because it
   changes how every existing and every imported skill is parsed, and this
   plan has no way to test that blast radius. §10 R9 records it as accepted
   residual risk and the test makes the failure loud instead of silent.

*Verified after the fix:* the S1 text now contains no bare `---` line in its
body, and `Skill.body()` returns the whole body — see §7 T1's preamble.

---

## §4 Files (create / modify / delete — complete manifest)

Every file touched by any step in §5 appears here, and nothing else.

### Larry commits by hand (C8) — never in an assistant diff

| Path | Action | Step |
|---|---|---|
| `config/self_edit_allowlist.json` | **modify** — `skills/**` deny → allow (row `W0-SKILL` of `docs/plans/ALLOWLIST_SEQUENCE.md`) | §5 step 1 |
| `config/skills.yaml` | **modify** — one line appended under `enabled:` | §5 step 10 |

### The implementation PR

| Path | Action | Step | Notes |
|---|---|---|---|
| `skills/skill-authoring/SKILL.md` | **modify** | §5 step 3 | Exists today as a 9-line stub (`:9` is `# Body placeholder`). Replaced in full with S1's text. **Not a create.** |
| `skills/README.md` | **modify** | §5 step 4 | Item 4 corrected (R-1); item 6 gains its storage location (R-2); "Current skills" table gains a row. |
| `jarvis/prompts.py` | **modify** | §5 step 5 | One string literal in `DEVELOPER_SECTION_WHEN["self_development"]` (S7). |
| `tests/unit/test_skill_match_evidence.py` | **create** | §5 step 6 | S-A, S9, S10. `MATCH_EVIDENCE` also carries `technical-plan-document` and `mcp-server-authoring` (F7); includes the displacement test (F7) and the enabled-skill safety-heading pin (F5). |
| `tests/unit/test_agent_skills.py` | **modify** | §5 step 7 | Additions to `class TestShippedSkills` only: two assertions for S6, the malformed-skill block from §7 T3 (a helper, one real-directory test, one six-case parametrised test), the truncation guard from §7 T7, and a docstring correction — "The four skills promoted…" at `:417` is already wrong (five are shipped; six after this). |
| `tests/unit/test_prompts.py` | **modify** | §5 step 5 | One added class (§7 T4). Existing file; if `select_developer_sections` is not already imported there, add it. |
| `tests/unit/test_selfedit_allowlist.py` | **modify** | §5 step 7 | One added class (§7 T5). Existing file; if `REPO_ROOT` is not defined, use `Path(__file__).resolve().parents[2]`. |
| `docs/REPO_MAP.md` | **modify** | §5 step 8 | Two lines. `grep -n skills docs/REPO_MAP.md` returns only `jarvis/skills/registry.py:55` today — the developer agent's own map does not mention `skills/` or `config/skills.yaml` at all, which is why a self-edit spends iterations rediscovering them. |

### Deleted

None.

### Not touched (asserted, so a diff containing them is a defect)

`config/agents.yaml`, `config/mcp_servers.yaml`, `mcp_servers/**`,
`jarvis/agent_skills.py`, `jarvis/agents/base.py`, `jarvis/selfedit/**`,
`jarvis/procedures.py`, `macos/**`, `web/**`, `tests/evals/**`,
`tests/integration/**`.

`jarvis/agent_skills.py` in particular: the scorer, the thresholds, the
`--explain` output format and `--from-procedure` are all consumed as-is.

---

## §5 Implementation steps, in order

Branch for the implementation PR: **`jarvis/self-edit/skill-authoring`**.
Larry's two hand commits go on **`main`** directly.

### Step 1 — LARRY, on `main`: apply the `skills/**` allow-list move (C8)

This is the C8 statement in full: **`config/self_edit_allowlist.json` is on
its own deny list (`config/self_edit_allowlist.json:21`). No assistant, no
self-edit session, and no step of this plan may write it. Larry applies this
change by hand, commits it alone, and pushes it before the implementation
branch is created.** An implementation diff that contains this file has
violated C8 and must be rejected at review, not fixed up.

**The mechanical edit and its verify command are row `W0-SKILL` of
`docs/plans/ALLOWLIST_SEQUENCE.md`** — the reconciled allow-list and its
ordered commits, owned by `MORTIMER_SECURITY_HARDENING_PLAN.md` / the SEC
task (cross-plan resolution §A). **Do not reproduce a literal unified diff
here:** SEC's W0 commit also adds entries to the same file
(`jarvis/skills/registry.py`, `tests/unit/test_agent_isolation.py`,
`tests/unit/test_requires_env_snapshot.py`), so a hard-coded hunk from this
plan would not apply cleanly after SEC's lands. Row `W0-SKILL` states the
change as add/remove of exact strings:

- **add** `"skills/**"` to the `allow` array;
- **remove** `"skills/**"` from the `deny` array;
- leave `"config/skills.yaml"` in `deny` (untouched).

The two W0 hand commits (SKILL's `skills/**` move and SEC's deny additions)
are **independent and order-free** — they touch disjoint strings and neither
depends on the other's having landed. Run row `W0-SKILL`'s verify command
from `ALLOWLIST_SEQUENCE.md`; the skill-specific outcome it must show is:

```
True  skills/skill-authoring/SKILL.md
True  skills/README.md
True  skills/anything/SKILL.md
False config/skills.yaml
False config/self_edit_allowlist.json
```

(`config/agents.yaml` is deliberately **not** probed here — it stays editable
under the resolution, and D-H9 as first drafted would have denied it; its
state is SEC's concern, not this change's.) If `config/skills.yaml` prints
`True`, the deny entry was removed by mistake — revert and start over. Commit
message: `allowlist: skills/** deny -> allow (T6; config/skills.yaml stays denied)`.

### Step 2 — Implementer: confirm the starting state

Run these four and compare. If any disagrees, stop and report.

```bash
wc -l skills/skill-authoring/SKILL.md              # expect 9
sed -n '9p' skills/skill-authoring/SKILL.md        # expect: # Body placeholder
grep -c skill-authoring config/skills.yaml || true # expect 0 (|| true: a zero count exits 1)
python3 -c "
from jarvis.selfedit.allowlist import Allowlist
al=Allowlist.load('config/self_edit_allowlist.json')
assert al.is_allowed('skills/x/SKILL.md'), 'step 1 has not been committed yet'
assert not al.is_allowed('config/skills.yaml'), 'config/skills.yaml must stay denied'
print('allowlist ok')"
```

A non-zero count from the third command means someone enabled the stub —
stop and report; §7 T1's numbers were measured against a disabled stub being
replaced, not against a live one.

### Step 3 — Replace `skills/skill-authoring/SKILL.md`

Overwrite the file with the fenced block in **§3 S1**, verbatim. Drop the
outer ```` ```markdown ```` fence and its closing fence; the file starts with
`---` on line 1 and ends with the final line of
`## If you cannot run the scorer`.

Then:

```bash
python3 -m jarvis.agent_skills --validate
```

Expected: `All SKILL.md files are valid.` and exit code 0. If it prints
`INVALID`, the frontmatter was mistranscribed — the most likely cause is a
line break inserted into the `description:` value, which YAML will accept
but which changes nothing about scoring, or an unescaped `:` followed by a
space, which YAML will reject. Fix the transcription; do not reword.

Then confirm the body survived transcription **in full** (S12 — this is the
failure mode `--validate` cannot see):

```bash
python3 -c "
from pathlib import Path
from jarvis.agent_skills import parse_skill
p = Path('skills/skill-authoring/SKILL.md')
raw = p.read_text(encoding='utf-8')
s, problems = parse_skill(p)
print('problems:', problems)
print('file chars :', len(raw))
print('body chars :', len(s.body()))
print('desc chars :', len(s.description))
assert len(s.body()) > 9000, 'BODY TRUNCATED — a bare --- line got into the body'
"
```

Expected: `problems: []`, `file chars : 11178`, `body chars : 10633`,
`desc chars : 391`. If `body chars` comes back near 1,900 you have
reintroduced a line starting with `---` into the body — find it and replace
it with a heading. Do not change `_split_frontmatter`.

### Step 4 — Correct `skills/README.md`

Three edits, all literal.

**4a — item 4 (R-1).** Replace lines 50–53:

```diff
-4. **Does the description carry an anti-trigger?**
-   One sentence saying what it is NOT for. `MATCH_THRESHOLD` is 0.30 and
-   matching is token overlap, so a description full of common words will
-   fire on tasks it has no business touching.
+4. **Does it carry an anti-trigger — in the BODY, never the description?**
+   One `## When this does not apply` section saying what it is NOT for.
+   `MATCH_THRESHOLD` is 0.30 and matching is token overlap, so a
+   description full of common words will fire on tasks it has no business
+   touching — but naming the false positive in the description is worse
+   than saying nothing, because it adds those exact words to the matchable
+   set. Measured 2026-08-18: adding "what are you planning to do next" to
+   `technical-plan-document`'s description moved that task's score from
+   0.000 to 1.000. The body is never scored; put it there.
```

**4b — item 6 (R-2).** Replace lines 59–60:

```diff
-6. **Match evidence recorded** — two tasks it should match and two it must
-   not, with scores from `--explain`. The negative cases matter more.
+6. **Match evidence recorded** — two utterances it must fire on and two it
+   must stay silent on, added to `MATCH_EVIDENCE` in
+   `tests/unit/test_skill_match_evidence.py` in the same change, so the
+   measurement is re-run on every test run. The negative cases matter more.
```

**4c — the "Current skills" table.** Add one row at the end of the table,
after the `mcp-server-authoring` row:

```diff
 | `mcp-server-authoring` | developer | authored 2026-08-18 |
+| `skill-authoring` | developer | authored 2026-08-26 |
```

Do **not** change the sentence above the table ("All promoted from `active`
procedures on 2026-08-18 except where noted; see each file's
`metadata.source`") — it already covers an authored skill.

### Step 5 — `jarvis/prompts.py`, one string literal (S7)

At `jarvis/prompts.py:308-318`, inside
`DEVELOPER_SECTION_WHEN["self_development"]`, append four words to the final
string fragment:

```diff
         "fix bug write edit add remove delete rename refactor update "
-        "patch correct repair adjust rework"
+        "patch correct repair adjust rework "
+        # A skill-authoring task measurably selected app_development ONLY
+        # (MORTIMER_SKILL_AUTHORING_PLAN.md S7): app_development's vocabulary
+        # contains "app_write", which _tokens() splits into {app, write}.
+        "skill skills library authoring"
     ),
```

Note the trailing space added to the `rework` line — without it the string
concatenates to `reworkskill` and the fix silently does nothing. Verify:

```bash
python3 -c "
import jarvis.prompts as P
from jarvis.procedures import _tokens
assert 'skill' in _tokens(P.DEVELOPER_SECTION_WHEN['self_development'])
assert 'rework' in _tokens(P.DEVELOPER_SECTION_WHEN['self_development'])
print(P.select_developer_sections('write a new skill for the skill library about running database migrations'))"
```

Expected: `['app_development', 'self_development']`.

Then add `class TestSkillAuthoringSelectsSelfDevelopment` from **§7 T4** to
`tests/unit/test_prompts.py`, following that file's convention of importing
`select_developer_sections` inside each test method.

### Step 6 — Create `tests/unit/test_skill_match_evidence.py`

Full file in **§7 T2**. Write it exactly; the `MATCH_EVIDENCE` literal is the
S-A contract.

### Step 7 — Amend `tests/unit/test_agent_skills.py` and `tests/unit/test_selfedit_allowlist.py`

**7a.** Add `class TestSkillsAreAuthorableButNotEnableable` from **§7 T5** to
`tests/unit/test_selfedit_allowlist.py`. It uses that file's existing
`Allowlist` import and `CONFIG` constant; add no imports.

**7b.** Inside `class TestShippedSkills`
(`tests/unit/test_agent_skills.py:416`), add — in this order — the malformed-
skill block from **§7 T3** (`_shipped_predicate`,
`test_the_real_directory_passes_the_predicate`,
`test_a_malformed_skill_fails_the_validation_gate`), the truncation guard
from **§7 T7**, and the two assertions below (S6), plus the docstring
correction:

```diff
 class TestShippedSkills:
-    """The four skills promoted from active procedures on 2026-08-18."""
+    """The skills actually shipped in this repository, read from disk.
+
+    These read the REAL skills/ directory, not a fixture — which is what
+    makes them the gate SelfEditService.validate()'s pytest check enforces
+    against a malformed SKILL.md written by a self-edit.
+    """
+
+    def test_folder_name_matches_frontmatter_name(self):
+        """A mismatch parses clean, warns about nothing, and leaves the
+        skill permanently inert — config/skills.yaml lists the frontmatter
+        name while a human reads the folder name. Verified 2026-08-26:
+        without this assertion nothing in the suite notices."""
+        for path, skill, _problems in discover():
+            assert skill is not None, f"{path}: unparseable"
+            assert skill.name == path.parent.name, (
+                f"{path}: frontmatter name {skill.name!r} != folder "
+                f"{path.parent.name!r} — the skill would be inert"
+            )
+
+    def test_skill_authoring_is_on_disk(self):
+        on_disk = {s.name for _, s, _ in discover() if s}
+        assert "skill-authoring" in on_disk
```

`discover` is already imported at the top of that file (it is used by
`test_every_shipped_skill_is_valid` at `:420`); add nothing to the imports.

**Do not add an assertion that `skill-authoring` is enabled.** It is not,
until step 10, and the suite must stay green in between (S5).

### Step 8 — `docs/REPO_MAP.md`

Add two lines in the same list style as the existing
`jarvis/skills/registry.py` entry at `:55`:

```
- `skills/<name>/SKILL.md` — authored capability knowledge (Agent Skills
  format). Inert until named in `config/skills.yaml`. Author with the
  `skill-authoring` skill; score with
  `python -m jarvis.agent_skills --explain "<task>"`.
- `config/skills.yaml` — the enable gate. Human-only: on the self-edit
  DENY list, deliberately.
```

### Step 9 — Full local verification, then hand off

```bash
python3 -m jarvis.agent_skills --validate
python3 -m jarvis.agent_skills --list
python3 -m pytest tests/unit -q
```

All three must pass. **`--list` will show `skill-authoring` as `inert` and
that is correct at this step** — its name is not in `config/skills.yaml` yet
(that is step 10, and `config/skills.yaml` is deny-listed, so you cannot
enable it here).

Then run the six acceptance utterances in §7 T1 and compare **only the
`score=` and `shared_tokens=` lines** against §7 T1's tables. **Do NOT expect
`<< INJECTED` or `Would inject: skill-authoring`** — at this step every
`skill-authoring` line reads `[inert  ]` and the final line reads
`Nothing would be injected: the skills above threshold (skill-authoring) are
inert. Enable one in skills.yaml to use it.` — this is §7 T1's pre-enable
transcript, and it is the correct output before Larry's step 10. A
disagreement on the `score=`/`shared_tokens=` numbers means the description
was mistranscribed in step 3 — diff it against §3 S1 rather than adjusting
the table. (The `<< INJECTED` / `Would inject:` expectations belong to §8
check 1, which Larry runs after step 10.)

Report to Larry: the files changed, the six measured scores, and one
sentence saying the skill is written and **not enabled**.

If running as a self-edit: `selfedit_validate`, then `selfedit_submit` with
confirm only after Larry says so. The PR must not contain
`config/skills.yaml` or `config/self_edit_allowlist.json` — that is G6(c).

### Step 10 — LARRY, after the PR merges: enable it (the human act)

Read the merged `skills/skill-authoring/SKILL.md` end to end first — that is
the review the gate exists for. Then, on `main`:

```diff
   # Authored here, 2026-08-18 (MORTIMER_SKILL_LIBRARY_PLAN.md Part C).
   # Skills authored in this repository ship enabled: they are reviewed in
   # their own diff and carry no scripts. The one-at-a-time rule above
   # still governs anything IMPORTED from a third party.
   - mcp-server-authoring
+  # Authored here, 2026-08-26 (MORTIMER_SKILL_AUTHORING_PLAN.md).
+  # Match evidence: tests/unit/test_skill_match_evidence.py::MATCH_EVIDENCE.
+  - skill-authoring
```

Commit message: `skills: enable skill-authoring (reviewed)`. Then confirm:

```bash
python3 -m jarvis.agent_skills --list | grep skill-authoring
python3 -m jarvis.agent_skills --explain "write a new skill for the skill library about running database migrations"
```

The first must print `[enabled ]`; the second must end `Would inject:
skill-authoring`.

---

## §6 Tuning knobs — where every number lives

**This plan introduces no new number and no new environment variable.**
Everything below already exists and is consumed as-is. The table is here so
the implementer can confirm that, and so a later plan knows where to look.

| Value | Default | Single location | Env override | Consumed by |
|---|---|---|---|---|
| `MATCH_THRESHOLD` | `0.30` | `jarvis/agent_skills.py:84` | none | §7 T1 |
| `MIN_SHARED_TOKENS` | `2` | `jarvis/agent_skills.py:106` | none | §7 T1, S2 |
| `MAX_INJECTED` | `1` | `jarvis/agent_skills.py:88` | none | S1 item 7 |
| `NAME_MAX_CHARS` | `64` | `jarvis/agent_skills.py:109` | none | S1 "The file" |
| `DESCRIPTION_MAX_CHARS` | `1024` | `jarvis/agent_skills.py:110` | none | S1 (391 used) |
| `BODY_SOFT_MAX_CHARS` | `20_000` | `jarvis/agent_skills.py:118` | none | S1 |
| `SECTION_MATCH_THRESHOLD` | `0.25` | `jarvis/prompts.py:328` | none | S7 |
| `VALIDATE_PYTEST_TIMEOUT_S` | `300` | `jarvis/selfedit/service.py` | none | §5 step 9 |
| skills layer on/off | on | `jarvis/agent_skills.py:162-171` | `JARVIS_AGENT_SKILLS_ENABLED` | §9 |
| developer sections on/off | on | `jarvis/prompts.py:355-361` | `JARVIS_DEVELOPER_SECTIONS_ENABLED` | §9 |
| per-skill on/off | — | `config/skills.yaml` `enabled:` | none (data, not env) | §9 |

---

## §7 Tests — by file, function, inputs and expected outputs

### T1 — Acceptance: the measured `--explain` numbers (G6(a))

**Re-measured in the sandbox on 2026-08-27** against the exact (F1-rewritten)
description in §3 S1, using the repo's real `discover()`/`match_skill()`/
`explain()`. The transcripts below reproduce the CLI byte for byte.

**Two states matter, and they are different — this is the F2 correction.**
The scores are the same in both, but what `--explain` PRINTS is not:

- **All six enabled** (the state at §8 check 1, *after* Larry's step 10):
  the skill-authoring line reads `[enabled]`, carries `<< INJECTED` when it
  wins, and the last line reads `Would inject: skill-authoring`. This is the
  G6(a) acceptance state and the numbers below are it.
- **Five enabled, skill-authoring on disk but not listed** (the state at §5
  **step 9**, before step 10 — `config/skills.yaml` is deny-listed so the
  implementer *cannot* enable it): the skill-authoring line reads `[inert  ]`
  and the last line reads `Nothing would be injected: … are inert.` The
  pre-enable transcript is reproduced after the enabled ones; §5 step 9
  compares only `score=`/`shared_tokens=` against it, never `<< INJECTED`.

The command is DB-free by construction (`jarvis/agent_skills.py:465-485`: it
calls `discover()` and `enabled_names()` and returns before `main()` reaches
the `from jarvis.db import get_conn` import at `:613`); the runs succeeded
under `env -u JARVIS_DB_PATH` with no database present.

`PASS` in the CLI's own output means *score ≥ 0.30 AND shared ≥ 2*;
`<< INJECTED` means *and it is the top-scoring enabled one*.

**Must fire on two of its own:**

| Utterance | `skill-authoring` score | shared tokens | Winner |
|---|---|---|---|
| `write a new skill for the skill library about running database migrations` | **0.375 PASS** | `['library', 'skill', 'write']` (3) | **skill-authoring** `<< INJECTED` |
| `promote procedure 17 into a skill and record its match evidence` | **0.714 PASS** | `['evidence', 'match', 'procedure', 'promote', 'skill']` (5) | **skill-authoring** `<< INJECTED` |

Runners-up on those two: `mcp-server-authoring` 0.125 / 1 shared and
`technical-plan-document` 0.125 / 1 shared on the first;
`git-history-and-status-review` 0.143 / 1 shared on the second. Every one
fails on both bounds.

**Must NOT fire on two `mcp-server-authoring` utterances:**

| Utterance | `skill-authoring` | Winner |
|---|---|---|
| `add a new MCP server for controlling the thermostat` | **0.000, 0 shared, fail** | mcp-server-authoring 0.500, `['mcp','new','server']` |
| `add a tool to the mcp-repo server that lists untracked files` | **0.000, 0 shared, fail** | mcp-server-authoring 0.500, `['files','mcp','server','tool']` |

**Must NOT fire on two `technical-plan-document` utterances:**

| Utterance | `skill-authoring` | Winner |
|---|---|---|
| `write an implementation plan for the mail and calendar integration` | **0.167, `['write']` (1), fail** | technical-plan-document 0.500, `['implementation','plan','write']` |
| `draft a technical specification for the native macOS client` | **0.000, 0 shared, fail** | technical-plan-document 0.333, `['specification','technical']` |

(The F1 rewrite dropped `draft` from the card, so `skill-authoring` now shares
**zero** tokens with the second row — the runner-up on it is instead
`mcp-server-authoring` at 0.167 on `['draft']`, still far below both bounds.)

Literal CLI transcript for one positive and one negative, as produced:

```
task: 'write a new skill for the skill library about running database migrations'
task tokens (8): ['about', 'database', 'library', 'migrations', 'new', 'running', 'skill', 'write']
threshold: 0.3

[enabled] score=0.375 PASS skill-authoring << INJECTED
          shared_tokens=['library', 'skill', 'write']
[enabled] score=0.125 fail mcp-server-authoring
          shared_tokens=['new']
[enabled] score=0.125 fail technical-plan-document
          shared_tokens=['write']
[enabled] score=0.000 fail current-weather-with-fahrenheit
          shared_tokens=[]
[enabled] score=0.000 fail git-history-and-status-review
          shared_tokens=[]
[enabled] score=0.000 fail layered-geolocation
          shared_tokens=[]

Would inject: skill-authoring
```

```
task: 'add a new MCP server for controlling the thermostat'
task tokens (6): ['add', 'controlling', 'mcp', 'new', 'server', 'thermostat']
threshold: 0.3

[enabled] score=0.500 PASS mcp-server-authoring << INJECTED
          shared_tokens=['mcp', 'new', 'server']
[enabled] score=0.000 fail current-weather-with-fahrenheit
          shared_tokens=[]
[enabled] score=0.000 fail git-history-and-status-review
          shared_tokens=[]
[enabled] score=0.000 fail layered-geolocation
          shared_tokens=[]
[enabled] score=0.000 fail skill-authoring
          shared_tokens=[]
[enabled] score=0.000 fail technical-plan-document
          shared_tokens=[]

Would inject: mcp-server-authoring
```

**Pre-enable transcript — the state at §5 step 9 (F2).** Identical scores,
but `skill-authoring` is `[inert  ]` because its name is not yet in
`config/skills.yaml`, and the final line says nothing is injected. This is
the CORRECT output before Larry's step 10; do not read it as a
mistranscription:

```
task: 'write a new skill for the skill library about running database migrations'
task tokens (8): ['about', 'database', 'library', 'migrations', 'new', 'running', 'skill', 'write']
threshold: 0.3

[inert  ] score=0.375 PASS skill-authoring
          shared_tokens=['library', 'skill', 'write']
[enabled] score=0.125 fail mcp-server-authoring
          shared_tokens=['new']
[enabled] score=0.125 fail technical-plan-document
          shared_tokens=['write']
[enabled] score=0.000 fail current-weather-with-fahrenheit
          shared_tokens=[]
[enabled] score=0.000 fail git-history-and-status-review
          shared_tokens=[]
[enabled] score=0.000 fail layered-geolocation
          shared_tokens=[]

Nothing would be injected: the skills above threshold (skill-authoring) are inert. Enable one in skills.yaml to use it.
```

### T1b — Adversarial battery (not part of G6; recorded as evidence for S3)

Six further negatives, all measured the same way. `skill-authoring` shares at
most **one** token with each, so `MIN_SHARED_TOKENS = 2` holds them out
independently of the threshold:

| Utterance | `skill-authoring` shared | Score |
|---|---|---|
| `write a plan for a new MCP server that reads the calendar` | `['write']` | 0.143 fail |
| `create a new tool for the analyst to look up flight status` | `[]` | 0.000 fail |
| `what's the plan for today` | `[]` | 0.000 fail |
| `author a technical plan document for remote access` | `['author']` | 0.167 fail |
| `show me the git history and what is uncommitted` | `[]` | 0.000 fail |
| `record the evidence from that run in the run log` | `['evidence']` | 0.250 fail |

The last row is the interesting one: 0.250 is below 0.30 *and* one shared
token — two bounds, either alone sufficient. This is why S3 keeps `evidence`
in the description despite the near miss.

**F1 displacement battery (the whole reason the description was rewritten).**
The first draft displaced `technical-plan-document`/`mcp-server-authoring` on
ordinary tasks and scored 1.000 on self-edit vocabulary. Re-measured
2026-08-27 with the real `match_skill` over all six skills — for each, the
winner WITHOUT `skill-authoring` on disk vs WITH it. A pass is "same winner
both ways" (nothing displaced):

| Utterance | winner w/o SA | winner w/ SA | verdict |
|---|---|---|---|
| `review the existing implementation plan before I approve it` | mcp-server-authoring | mcp-server-authoring | no displacement |
| `improve the existing spec document` | technical-plan-document | technical-plan-document | no displacement |
| `draft and review the design document` | technical-plan-document | technical-plan-document | no displacement |
| `author a draft of the remote access plan` | technical-plan-document | technical-plan-document | no displacement |
| `improve Mortimer itself` | None | None (SA 0.000) | no false fire |
| `change Mortimer itself to use a darker theme` | None | None (SA 0.000) | no false fire |
| `improve the name and description` | None | None (SA 0.000) | no false fire |
| `explain why the branch never merged` | None | None (SA 0.000) | no false fire |
| `review the existing workflow and improve it` | None | None (SA 0.000) | no false fire |
| `explain the scorer to me` | None | None (SA 0.000) | no false fire |

Every row that the first draft lost (F1's eight regressions plus its extra
false fires) now passes. The three residual `skill-authoring` fires that
remain (`explain why the match never fires`, `author a new review checklist`,
`record the evidence and explain why`) all have `winner w/o SA = None`, so
they displace nothing — see §3 S3's closing paragraph.

### T2 — `tests/unit/test_skill_match_evidence.py` (create; S-A, S9, S10)

```python
"""Match evidence for every shipped skill, re-measured on every test run.

skills/README.md item 6 requires two utterances a skill must fire on and two
it must stay silent on. Before this file there was nowhere to put them, so
the 2026-08-18 numbers lived only in a plan document's prose — a record that
cannot fail. MATCH_EVIDENCE is that record; this module is the measurement.

Deliberately scored against EVERY skill folder on disk rather than against
config/skills.yaml's enabled list: enabling is a separate human commit
(MORTIMER_SKILL_AUTHORING_PLAN.md S5), and a test that depended on it would
go red between the authoring PR and Larry's enable commit.
"""

from pathlib import Path

from jarvis.agent_skills import (
    MATCH_THRESHOLD,
    MIN_SHARED_TOKENS,
    discover,
)
from jarvis.procedures import _overlap_score, _tokens

REPO_ROOT = Path(__file__).resolve().parents[2]

# name -> {"fires": [...], "silent": [...]}
# "fires"  = this skill is the top-scoring qualifying skill on disk.
# "silent" = this skill does not qualify at all (below threshold, or fewer
#            than MIN_SHARED_TOKENS shared). Second place is NOT silent.
MATCH_EVIDENCE: dict[str, dict[str, list[str]]] = {
    "skill-authoring": {
        "fires": [
            "write a new skill for the skill library about running database migrations",
            "promote procedure 17 into a skill and record its match evidence",
        ],
        # The first four are the G6(a) negatives (two mcp-server-authoring,
        # two technical-plan-document). The last four are the ordinary
        # plan-review / self-edit tasks the FIRST-draft description displaced
        # (review finding F1) — they are the utterances that were actually
        # the problem, so they are recorded here, not just the four that
        # never fired.
        "silent": [
            "add a new MCP server for controlling the thermostat",
            "add a tool to the mcp-repo server that lists untracked files",
            "write an implementation plan for the mail and calendar integration",
            "draft a technical specification for the native macOS client",
            "improve the existing spec document",
            "draft and review the design document",
            "author a draft of the remote access plan",
            "change Mortimer itself to use a darker theme",
        ],
    },
    # F7: the two neighbours skill-authoring must never displace now carry
    # their OWN evidence, so the displacement test below has something to
    # bite on and the grandfathered set shrinks by two.
    "technical-plan-document": {
        "fires": [
            "write an implementation plan for the mail and calendar integration",
            "draft a technical specification for the native macOS client",
        ],
        "silent": [
            "write a new skill for the skill library about running database migrations",
            "add a new MCP server for controlling the thermostat",
        ],
    },
    "mcp-server-authoring": {
        "fires": [
            "add a new MCP server for controlling the thermostat",
            "add a tool to the mcp-repo server that lists untracked files",
        ],
        "silent": [
            "write an implementation plan for the mail and calendar integration",
            "write a new skill for the skill library about running database migrations",
        ],
    },
}

SEVEN_ITEM_HEADLINES = (
    "Does it bundle `scripts/`?",
    "Does every tool it names actually exist?",
    "Is it phrased as reference, not as an order?",
    "Does it carry an anti-trigger — in the BODY, never the description?",
    "Does it say what to do when a tool it names is unavailable?",
    "Match evidence recorded",
    "No overlap with an existing skill",
)


def _scored():
    """Every parsed Skill on disk (None-parse folders dropped)."""
    out = []
    for _path, skill, _problems in discover():
        if skill is not None:
            out.append(skill)
    return out


def _rank(task: str):
    """(score, shared_count, name) rows, best first.

    Tie-break note: this sorts by (-score, name), whereas match_skill keeps
    the FIRST candidate at the top score in discover() (folder-path) order
    (`score > best[0]`, strictly greater — jarvis/agent_skills.py). The two
    agree only because S6 forces every folder name to equal its frontmatter
    name, so discover()'s path order and this name order are the same order.
    Three of F1's original regressions were decided by exactly this tie-break,
    which is why it is spelled out rather than left implicit.
    """
    task_tokens = _tokens(task)
    rows = []
    for skill in _scored():
        card = _tokens(skill.card)
        rows.append((
            _overlap_score(card, task_tokens),
            len(card & task_tokens),
            skill.name,
        ))
    rows.sort(key=lambda r: (-r[0], r[2]))
    return rows


def _qualifies(score: float, shared: int) -> bool:
    return score >= MATCH_THRESHOLD and shared >= MIN_SHARED_TOKENS


class TestMatchEvidence:
    def test_every_named_skill_is_on_disk(self):
        on_disk = {s.name for s in _scored()}
        for name in MATCH_EVIDENCE:
            assert name in on_disk, f"{name} has evidence but no SKILL.md"

    def test_positive_utterances_win(self):
        for name, cases in MATCH_EVIDENCE.items():
            for task in cases["fires"]:
                rows = _rank(task)
                winner = next(
                    (n for score, shared, n in rows if _qualifies(score, shared)),
                    None,
                )
                assert winner == name, (
                    f"{name!r} should win {task!r}; ranking was "
                    f"{[(round(s, 3), sh, n) for s, sh, n in rows[:3]]}"
                )

    def test_negative_utterances_do_not_qualify(self):
        """MAX_INJECTED = 1, so an over-matching skill does not add noise —
        it DISPLACES the skill that should have won. Second place is a
        failure here, not a pass."""
        for name, cases in MATCH_EVIDENCE.items():
            for task in cases["silent"]:
                row = next((r for r in _rank(task) if r[2] == name), None)
                assert row is not None, (
                    f"{name!r} is named in MATCH_EVIDENCE but is not on disk — "
                    "test_every_named_skill_is_on_disk should have caught this"
                )
                score, shared, _ = row
                assert not _qualifies(score, shared), (
                    f"{name!r} qualifies on {task!r} "
                    f"(score={score:.3f}, shared={shared}) — sharpen the "
                    "description; never move the threshold"
                )

    def test_no_skill_displaces_another_on_its_own_evidence(self):
        """The MAX_INJECTED = 1 property, stated once (review finding F7).

        Every 'fires' utterance of every skill must still be won by THAT
        skill with all skills on disk. A per-skill silence test (above) can
        pass while a new skill quietly steals a neighbour's own task; this
        asserts the neighbour still wins it.
        """
        for name, cases in MATCH_EVIDENCE.items():
            for task in cases["fires"]:
                winner = next(
                    (n for score, shared, n in _rank(task)
                     if _qualifies(score, shared)),
                    None,
                )
                assert winner == name, (
                    f"{task!r} should be won by {name!r} but is won by "
                    f"{winner!r} — a description overlaps; merge or sharpen, "
                    "never move the threshold"
                )

    def test_every_shipped_skill_has_evidence_or_is_grandfathered(self):
        """Skills predating this fixture are listed here explicitly rather
        than skipped silently, so the exemption is visible and shrinkable.
        F7 shrank it by two (tpd and mcp-server-authoring now carry
        evidence)."""
        grandfathered = {
            "current-weather-with-fahrenheit",
            "git-history-and-status-review",
            "layered-geolocation",
        }
        for skill in _scored():
            assert skill.name in MATCH_EVIDENCE or skill.name in grandfathered, (
                f"{skill.name} ships with no match evidence — add it to "
                "MATCH_EVIDENCE (skills/README.md item 6)"
            )

    def test_enabled_skills_keep_their_safety_bearing_headings(self):
        """Review finding F5: `skills/**` is writable, `propose_edit` writes
        the live tree, and load_skills re-reads per delegation — so an
        amendment to an ALREADY-ENABLED skill is live before any PR. This is
        the cheap mechanical backstop R3 accepts: a weakening amendment that
        deletes a safety-bearing heading turns this red in validate()'s
        pytest check. Body prose is still not fully pinned; the headings are.
        """
        required = {
            "mcp-server-authoring": [
                "## Writes are two-phase, always",
                "## The entrypoint that has already cost a debugging session",
            ],
        }
        on_disk = {s.name: s for s in _scored()}
        for name, headings in required.items():
            skill = on_disk.get(name)
            assert skill is not None, f"{name} is not on disk"
            body = skill.body()
            for h in headings:
                assert h in body, (
                    f"{name}: safety-bearing heading {h!r} is gone — an "
                    "amendment weakened an enabled skill (F5/R3)"
                )


class TestChecklistIsNotDuplicatedIntoDrift:
    def test_checklist_headlines_match(self):
        """The seven items necessarily exist twice: a skill is injected into
        a prompt and cannot link out to a README. This is the backstop."""
        readme = (REPO_ROOT / "skills" / "README.md").read_text(encoding="utf-8")
        body = (REPO_ROOT / "skills" / "skill-authoring" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        for headline in SEVEN_ITEM_HEADLINES:
            assert headline in readme, f"missing from skills/README.md: {headline}"
            assert headline in body, f"missing from skill-authoring: {headline}"

    def test_the_description_carries_no_anti_trigger(self):
        """MORTIMER_SKILL_LIBRARY_PLAN.md's corrected D1, as a test.

        Naming a false positive in a description adds its exact words to the
        matchable token set — measured 2026-08-18 as 0.000 -> 1.000. These
        are the words this skill's negative cases are made of; none may
        appear in its card.
        """
        skill = next(s for s in _scored() if s.name == "skill-authoring")
        card_tokens = _tokens(skill.card)
        # The first block is the anti-trigger vocabulary (neighbours' nouns).
        # The second is the generic verbs/nouns review finding F1 measured as
        # displacers — including the two self-edit words (`itself`,`mortimer`)
        # that scored the first draft 1.000 on "improve Mortimer itself".
        forbidden = {"plan", "specification", "technical", "document",
                     "tool", "new", "mcp",
                     "itself", "mortimer", "create", "improve", "draft",
                     "scorer", "review", "existing", "enabled", "item"}
        leaked = card_tokens & forbidden
        assert not leaked, (
            f"{sorted(leaked)} leaked into the description — an anti-trigger "
            "or a generic displacer belongs OUT of the card, which is the "
            "whole matching surface (F1)"
        )
```

**Inputs and expected outputs, restated for the implementer:** all eight test
functions (six in `TestMatchEvidence`, two in
`TestChecklistIsNotDuplicatedIntoDrift`) must pass with exit code 0 from the
moment they are written (§5 step 6), through the step-9 verification, and
while `skill-authoring` is still **not enabled** (up to Larry's step 10) —
every one reads the real `skills/` directory, independent of
`config/skills.yaml`, precisely so the suite stays green across that gap (S5).
If `test_negative_utterances_do_not_qualify` or
`test_no_skill_displaces_another_on_its_own_evidence` fails, the description
in step 3 was mistranscribed — do not edit `MATCH_EVIDENCE` to make it pass.

**On the counts:** `skills/README.md` item 6 sets a *minimum* of two positive
and two negative utterances. `skill-authoring` records two positive and
**eight** negative — the four G6(a) negatives plus the four ordinary tasks
its first-draft description displaced (review finding F1), so the fixture
bites on the utterances that were actually the problem. `technical-plan-
document` and `mcp-server-authoring` now each carry the minimum two-and-two
(F7), which is what gives `test_no_skill_displaces_another_on_its_own_evidence`
neighbours to defend. A future skill adding exactly two of each satisfies
both the README and this fixture.

### T3 — The self-edit `validate()` gate on a new `skills/<name>/SKILL.md`

**How `validate()` treats it, check by check** (`jarvis/selfedit/service.py:391-440`):

| Check | Behaviour with a new `skills/<name>/SKILL.md` | Verdict on a **malformed** one |
|---|---|---|
| 1. `allowlist` — `git diff --name-only origin/main` then `Allowlist.filter_violations` | After §5 step 1, `skills/**` is allowed ⇒ the new path passes. | **passes** — malformedness is not a path property |
| 2. `backend_imports` — `python -c "import jarvis, jarvis.config, jarvis.cli"` | Importing `jarvis.agent_skills` does not read any `SKILL.md`; parsing is lazy (`discover()` is called by CLI/tests only). | **passes** |
| 3. `frontend_build` — `npm ci && npm run build` | Unrelated. | **passes** |
| 4. `pytest` — `python -m pytest tests/unit -q`, `VALIDATE_PYTEST_TIMEOUT_S = 300` | `tests/unit/test_agent_skills.py::TestShippedSkills` calls `discover()` on the **real** `skills/` directory (`tests/unit/test_agent_skills.py:419-424`), so it sees the file the session just wrote. | **FAILS** |

`validate()` returns `ok = all(c["ok"] for c in checks)`, and `submit()`
refuses while `_validated_ok` is False (`:443-452`). So **check 4 is the
gate**, and it already exists — this plan adds no fifth check.

**Verified in the sandbox, 2026-08-26.** `discover()` was run against a
`skills/` directory seeded with three deliberately broken folders:

| Probe | `discover()` result | `test_every_shipped_skill_is_valid` |
|---|---|---|
| `broken-probe/SKILL.md` — body text with **no `---` frontmatter fences** | `skill=None`, `problems=['no YAML frontmatter (a SKILL.md must start with ---)']` | **FAIL** (asserts `skill is not None`) |
| `big-probe/SKILL.md` — valid frontmatter, **22,001-character body** | `skill=OK`, `problems=['body is 22001 chars, above the ~20000 guidance …']` | **FAIL** (asserts `not problems`) |
| `folder-name-x/SKILL.md` — valid, but frontmatter `name: different-name` | `skill=OK`, `problems=[]` | **passes** — the gap S6 closes |

Combined verdict printed by the probe: `test_every_shipped_skill_is_valid
would: FAIL`. All three probe folders were removed and the repository
restored afterwards.

**The test that a malformed `SKILL.md` fails validation** — add to
`tests/unit/test_agent_skills.py`, inside `class TestShippedSkills`
(it needs `tmp_path`, so it uses `discover(tmp_path)`, and it asserts the
*same predicate* `test_every_shipped_skill_is_valid` applies to the real
directory — one predicate, two callers, so they cannot disagree):

```python
    @staticmethod
    def _shipped_predicate(found):
        """Exactly what test_every_shipped_skill_is_valid asserts, as a
        function, so the malformed cases below test the real gate and not a
        paraphrase of it."""
        return all(skill is not None and not problems
                   for _path, skill, problems in found)

    def test_the_real_directory_passes_the_predicate(self):
        found = discover()
        assert found
        assert self._shipped_predicate(found)

    @pytest.mark.parametrize("filename,content,why", [
        ("no-frontmatter",
         "name: no-frontmatter\ndescription: no fences\n\n# body\n",
         "no YAML frontmatter"),
        ("bad-yaml",
         "---\nname: bad-yaml\ndescription: [unclosed\n---\n\n# body\n",
         "frontmatter is not valid YAML"),
        ("no-description",
         "---\nname: no-description\n---\n\n# body\n",
         "missing required field: description"),
        ("bad-name",
         "---\nname: Bad_Name\ndescription: uppercase and underscore\n---\n\n# b\n",
         "must be lowercase letters, digits and single hyphens"),
        ("claude-helper",
         "---\nname: claude-helper\ndescription: reserved vendor word\n---\n\n# b\n",
         "reserved word"),
        ("oversized",
         "---\nname: oversized\ndescription: body over the soft cap\n---\n\n"
         + "x " * 11_000,
         "above the ~20000 guidance"),
    ])
    def test_a_malformed_skill_fails_the_validation_gate(
            self, tmp_path, filename, content, why):
        """MORTIMER_SKILL_AUTHORING_PLAN.md §7 T3. Each of these, written
        into skills/ by a self-edit session, must fail check 4 of
        SelfEditService.validate() — which is this predicate."""
        folder = tmp_path / filename
        folder.mkdir()
        (folder / "SKILL.md").write_text(content, encoding="utf-8")
        found = discover(tmp_path)
        assert not self._shipped_predicate(found), (
            f"{filename} should have failed the gate ({why})"
        )
        _path, skill, problems = found[0]
        assert skill is None or problems
```

`pytest` is already imported at the top of `tests/unit/test_agent_skills.py`
(it uses `tmp_path` and `monkeypatch` fixtures throughout); if `import
pytest` is absent, add it.

**Expected:** six parametrised cases, all passing. The `oversized` case is
the one worth understanding — it produces a *valid* `Skill` object with a
non-empty `problems` list, and it is the `not problems` half of the
predicate that catches it (`jarvis/agent_skills.py:253-256`).

### T4 — Developer section selection (S7)

`tests/unit/test_prompts.py` — **verified to exist**. It imports
`select_developer_sections` *inside* each test method
(`tests/unit/test_prompts.py:332` and eight more:
`from jarvis.prompts import select_developer_sections as sel`). Follow that
house convention exactly; do not add a module-level import.

```python
class TestSkillAuthoringSelectsSelfDevelopment:
    """MORTIMER_SKILL_AUTHORING_PLAN.md S7. Measured 2026-08-26: before the
    vocabulary fix, this task selected ['app_development'] alone — the
    protocol that routes to app_create and a NEW PRIVATE GITHUB REPO — and
    never self_development, which is what routes to selfedit_start.
    Cause: app_development's vocabulary contains "app_write", which _tokens()
    splits into {app, write}, so the task shared {new, write} = 2 of its 8
    tokens = 0.250, exactly SECTION_MATCH_THRESHOLD, while self_development
    shared only {write} = 0.125."""

    TASK = ("write a new skill for the skill library about running "
            "database migrations")

    def test_self_development_is_selected(self):
        from jarvis.prompts import select_developer_sections as sel
        assert "self_development" in sel(self.TASK)

    def test_the_other_measured_rows_are_unchanged(self):
        from jarvis.prompts import select_developer_sections as sel
        assert sel(
            "write an implementation plan for the mail and calendar integration"
        ) == ["planning"]
        assert sel(
            "add a new MCP server for controlling the thermostat"
        ) == ["app_development", "self_development", "planning"]

    def test_a_skills_library_request_is_self_development_only(self):
        """Review finding F6: the four added words NARROW any task that used
        to match no section (and therefore received all three) down to
        self_development alone. This is the accepted reading — a skills-library
        request is self-development, not an app — but it is a narrowing, so it
        is pinned here rather than discovered later. Measured 2026-08-27: each
        of these returned ['app_development','self_development','planning']
        before the four words and ['self_development'] after."""
        from jarvis.prompts import select_developer_sections as sel
        assert sel("make me a skills library") == ["self_development"]
        assert sel("improve the skill library") == ["self_development"]
        assert sel("what skills do you have") == ["self_development"]
```

**Measured before/after** (`select_developer_sections`, sandbox 2026-08-26):

```
--- BEFORE
   ['app_development']                                  <- 'write a new skill for the skill library about running database migrations'
   ['app_development', 'self_development', 'planning']  <- 'promote procedure 17 into a skill and record its match evidence'
   ['app_development', 'self_development', 'planning']  <- 'add a new MCP server for controlling the thermostat'
   ['planning']                                         <- 'write an implementation plan for the mail and calendar integration'
--- AFTER (+ 'skill skills library authoring')
   ['app_development', 'self_development']              <- 'write a new skill for the skill library about running database migrations'
   ['app_development', 'self_development', 'planning']  <- 'promote procedure 17 into a skill and record its match evidence'
   ['app_development', 'self_development', 'planning']  <- 'add a new MCP server for controlling the thermostat'
   ['planning']                                         <- 'write an implementation plan for the mail and calendar integration'
```

**The F6 narrowing, measured the same way** (these matched no section
before, so they got all three; now they get one):

```
--- BEFORE
   ['app_development', 'self_development', 'planning']  <- 'make me a skills library'
   ['app_development', 'self_development', 'planning']  <- 'improve the skill library'
   ['app_development', 'self_development', 'planning']  <- 'what skills do you have'
--- AFTER
   ['self_development']  <- 'make me a skills library'
   ['self_development']  <- 'improve the skill library'
   ['self_development']  <- 'what skills do you have'
```

Accepted as the intended reading (S7); `test_a_skills_library_request_is_
self_development_only` pins it so it is a decision, not a surprise.

### T5 — The allow-list asymmetry (G6(c)), as a test

`tests/unit/test_selfedit_allowlist.py` — **verified to exist**, and it
already defines everything this class needs: `from jarvis.selfedit.allowlist
import Allowlist` at `:9`, `REPO_ROOT` at `:11`, and
`CONFIG = REPO_ROOT / "config" / "self_edit_allowlist.json"` at `:12`. Add
one class; add no imports.

```python
class TestSkillsAreAuthorableButNotEnableable:
    """Roadmap T6 / MORTIMER_SKILL_AUTHORING_PLAN.md S4. Authoring becomes
    possible; enabling stays Larry's. Deny wins over allow, which is the
    only reason config/**'s allow entry does not reach config/skills.yaml."""

    def _al(self):
        return Allowlist.load(CONFIG)

    def test_a_skill_file_is_writable(self):
        al = self._al()
        assert al.is_allowed("skills/skill-authoring/SKILL.md")
        assert al.is_allowed("skills/a-brand-new-skill/SKILL.md")
        assert al.is_allowed("skills/README.md")

    def test_the_enable_gate_is_not(self):
        assert not self._al().is_allowed("config/skills.yaml")

    def test_the_allowlist_itself_is_not(self):
        assert not self._al().is_allowed("config/self_edit_allowlist.json")

    def test_filter_violations_names_the_enable_gate(self):
        """The exact code path that rejects an assistant PR touching
        config/skills.yaml: validate()'s check 1 calls this on the whole
        diff vs origin/main (jarvis/selfedit/service.py:398-407)."""
        diff = ["skills/skill-authoring/SKILL.md", "skills/README.md",
                "config/skills.yaml"]
        assert self._al().filter_violations(diff) == ["config/skills.yaml"]
```

If a future refactor has removed `CONFIG`, use
`Allowlist.load(Path(__file__).resolve().parents[2] / "config" /
"self_edit_allowlist.json")`.

### T7 — No shipped skill's body is silently truncated (S12)

Add to `class TestShippedSkills` in `tests/unit/test_agent_skills.py`:

```python
    def test_no_body_is_silently_truncated(self):
        """MORTIMER_SKILL_AUTHORING_PLAN.md S12.

        _split_frontmatter does text.split("\\n---", 2) and returns parts[1]
        as the body. It splits on the SUBSTRING "\\n---", so the first match
        is the frontmatter's closing fence and the SECOND is ANY line that
        STARTS with three or more hyphens — a Markdown horizontal rule
        (`---`), a longer rule (`----`), or a unified-diff header
        (`--- a/path`), the last being very plausible in a skill about
        editing files — and parts[2] is discarded. The file on disk stays
        complete, parse_skill reports no problems, --validate passes, and
        --explain scores it correctly because matching reads the card and
        never the body. Nothing else in this suite can see it.

        Measured 2026-08-26 on this plan's own first draft: 9,859 characters
        on disk, 1,910 delivered.
        """
        for path, skill, _problems in discover():
            assert skill is not None, f"{path}: unparseable"
            parts = path.read_text(encoding="utf-8").split("\n---", 2)
            assert len(parts) < 3 or not parts[2].strip(), (
                f"{path}: a line starting with '---' in the body truncates the "
                f"injected skill there — {len(skill.body())} of "
                f"{len(parts[1]) + len(parts[2])} body chars would reach "
                "the agent. Use a '##' heading instead."
            )
```

**Verified against the five pre-existing skills, 2026-08-26:** none of them
contains a line starting with `---` in its body, so this assertion passes today
(`body()` lengths 2,547 / 2,491 / 2,556 / 5,267 / 3,467, each within 3
characters of the raw text after the frontmatter). It is a regression guard,
not a bug report against them.

### T6 — The full suite

`python3 -m pytest tests/unit -q` must be green. The suite was 1,538 tests
before this plan (CLAUDE.md, 2026-08-25). Count by file, after the review
fixes (F7 added the displacement test, F5 the safety-heading pin, F6 the
narrowing test; F8 corrected T3 to 7 collected, not 8 — `_shipped_predicate`
is a `@staticmethod` and pytest does not collect it):

- `tests/unit/test_skill_match_evidence.py` (create, T2): **8** —
  `TestMatchEvidence` 6 (on-disk, positives-win, negatives-silent,
  no-displacement, evidence-or-grandfathered, safety-headings) +
  `TestChecklistIsNotDuplicatedIntoDrift` 2.
- `tests/unit/test_agent_skills.py` (`TestShippedSkills`): **10** — T3 block
  7 (`test_the_real_directory_passes_the_predicate` 1 +
  `test_a_malformed_skill_fails_the_validation_gate` 6 parametrised;
  `_shipped_predicate` not collected) + S6 2 + T7 1.
- `tests/unit/test_prompts.py` (T4): **3**.
- `tests/unit/test_selfedit_allowlist.py` (T5): **4**.

Total added = 8 + 10 + 3 + 4 = **25**, so the suite goes 1,538 → **1,563**.

---

## §8 Verification Larry runs on his hardware

The sandbox has no Keychain, no network, no Xcode, no microphone, and (in
the snapshot used to write this plan) **no `pytest` installed** — every
pytest-based claim in §7 was verified by executing the same predicates
directly via `discover()`, and is marked as such in T3. Larry runs:

1. **The six acceptance utterances (G6(a)).** **This is where the
   `<< INJECTED` / `Would inject:` expectations live — it runs AFTER step 10,
   when `skill-authoring` is enabled** (F2). Before step 10 the same commands
   print `[inert  ]` / `Nothing would be injected`, which is §7 T1's
   pre-enable transcript and is correct there, not a failure.
   ```bash
   for u in \
     "write a new skill for the skill library about running database migrations" \
     "promote procedure 17 into a skill and record its match evidence" \
     "add a new MCP server for controlling the thermostat" \
     "add a tool to the mcp-repo server that lists untracked files" \
     "write an implementation plan for the mail and calendar integration" \
     "draft a technical specification for the native macOS client"; do
     echo "=== $u"; python -m jarvis.agent_skills --explain "$u" | tail -3
   done
   ```
   Expected last lines, in order: `Would inject: skill-authoring`,
   `Would inject: skill-authoring`, `Would inject: mcp-server-authoring`,
   `Would inject: mcp-server-authoring`,
   `Would inject: technical-plan-document`,
   `Would inject: technical-plan-document`. (On the last utterance
   `skill-authoring` now scores 0.000, not 0.167 — the F1 rewrite dropped
   `draft` — but the winner is unchanged.)
2. **Full unit suite with pytest actually installed:**
   `python -m pytest tests/unit -q` — green, count **≥ 1,563** (1,538
   baseline + 25; see §7 T6).
3. **`python scripts/check_allowlist.py origin/main...HEAD`** — run it
   **while still on** `jarvis/self-edit/skill-authoring`, before merging, and
   it must print `all allowlisted`, exit 0. On `main` (after the merge) it
   prints `check_allowlist: branch 'main' is not a self-edit branch -
   allowlist not enforced` and proves nothing — the check is only meaningful
   on the self-edit branch (`scripts/check_allowlist.py:36-40`).
4. **G6(c), end to end, by voice.** Say: *"write a skill for the developer
   that captures how we review a pull request."* Expected: the developer
   routes through `selfedit_start` (S7), the PR contains files under
   `skills/` and **not** `config/skills.yaml`, and Mortimer's spoken summary
   says the skill is written and not enabled. Then check the PR's file list
   on GitHub.
5. **The refusal path.** Say: *"enable that skill."* Expected: Mortimer
   declines and says enabling is Larry's own commit. If it instead proposes
   an edit to `config/skills.yaml`, `SelfEditService._check_path` refuses
   with `path is not on the self-edit allowlist` — either outcome is
   acceptable; a *successful* edit is not, and would mean step 1's diff was
   applied wrongly.
6. **Routing eval (C7), for the record even though nothing routing-related
   changed:** `RUN_LIVE=1 python -m tests.evals.routing_eval` — record the
   score here. Expected unchanged from the pre-plan baseline; must be ≥ 90 %.
7. **One real authoring session.** Ask for a skill in a domain Mortimer
   actually has, watch that the agent runs `--explain` four times before
   proposing, and read whether its four utterances landed in
   `MATCH_EVIDENCE`. This is the only check of whether the skill's *body*
   works, and no test can substitute for it.

Things that cannot be verified anywhere but on Larry's machine: (4), (5),
(6), (7), and check 3 of `validate()` (`npm ci` needs the network).

---

## §9 Rollback

No data changes anywhere — skills are files, `config/skills.yaml` is config,
and nothing in this plan writes a database row or a migration. Rollback is
therefore purely git plus one line.

| To undo | Action | Effect |
|---|---|---|
| The skill firing at all | Delete the `- skill-authoring` line from `config/skills.yaml` | Instant and total: the file stays on disk and becomes inert (`jarvis/agent_skills.py:315-320`; `test_a_skill_on_disk_is_inert_until_registered`). No restart of anything but the bot. |
| The whole skills layer | `JARVIS_AGENT_SKILLS_ENABLED=false` | `load_skills()` returns `[]` at its single check point (`:162-171`). Pre-existing switch. |
| The S7 prompt change | `JARVIS_DEVELOPER_SECTIONS_ENABLED=false` | Fail-open: every developer section is injected, byte-identical to pre-sections behaviour (`jarvis/prompts.py:385-386`). Blunt but complete. Narrower: revert the four words. |
| Authoring capability | Larry re-applies step 1's diff in reverse: `skills/**` back to `deny` | Immediate; `Allowlist` is loaded per `SelfEditService` construction (`jarvis/selfedit/service.py:104-107`), so the sidecar picks it up on restart. |
| Everything | `git revert` the implementation PR merge commit, then the two hand commits | Restores the 9-line stub and the original allowlist. |

**Rollback ordering matters in exactly one place:** remove the
`config/skills.yaml` line *before* reverting the skill file, or `--list`
reports an enabled name with no folder. `enabled_names()` tolerates it
(`load_skills` just skips), and `test_shipped_skills_start_inert`
(`tests/unit/test_agent_skills.py:430`) asserts against it — so reverting in
the wrong order turns the suite red without breaking the runtime.

---

## §10 Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | The description is paraphrased during transcription and the measured scores stop holding. | medium | An over-matching skill *displaces* the right one on some task (`MAX_INJECTED = 1`) — silent, and only visible in `--explain`. This is exactly what review finding F1 caught in the first draft. | §0 rule 4; T2's `test_negative_utterances_do_not_qualify` **and** `test_no_skill_displaces_another_on_its_own_evidence` (F7) re-measure on every run and name the leaked token; `test_the_description_carries_no_anti_trigger` now blocks all 17 anti-trigger + generic-displacer words (including `itself`/`mortimer`/`scorer`). |
| R2 | A future skill is authored whose description collides with `skill-authoring`. | medium over time | Same displacement, in the other direction. | Item 7 is in the skill body and in the README; T2 forces the new skill's own negatives to be recorded, and one of them will be a `skill-authoring` task if they genuinely overlap. |
| R3 | `skills/**` being writable lets a self-edit weaken an ALREADY-ENABLED skill (e.g. delete `mcp-server-authoring`'s "Writes are two-phase, always" section). | low-medium | **The weakened text is LIVE at the next delegation — before validation and before the PR** (F5): `propose_edit` writes the live working tree and `load_skills` re-reads per delegation. So the window between the amendment and the merge is a window where the enabled skill's degraded text is already reaching agents. | The real gates are **the human merge** and `git checkout` off the session branch — not the pre-PR checks, which are downstream of a change already live. Mechanical backstop: T2's `test_enabled_skills_keep_their_safety_bearing_headings` turns deletion of a pinned safety heading into a red `pytest` (validate() check 4) before the PR can open — it fires *after* the text briefly went live, not before. Accepted residual: body prose other than the pinned headings is not pinned, and the live-before-merge window is inherent to `skills/**` being a per-delegation-reloaded surface (`config/workflows/` shares it). |
| R4 | An agent writes a skill and then tells the user it is live. | medium | A false capability claim — Golden Rule territory. | The skill body's "What you may write, and the one file you may not" says exactly what to report; the mechanical backstop is that `config/skills.yaml` is unreachable, so the claim is checkable in one command (`--list`). §8 check 4 tests it by voice. |
| R5 | S7's four added words **narrow** a task that previously matched no section (and got all three) down to `self_development` alone — losing `app_development`'s `app_create` confirmation protocol and `planning`. | low | A build-shaped skills-library request (e.g. "make me a skills library") no longer carries the app confirmation protocol. Measured on "make me a skills library", "improve the skill library", "what skills do you have" (F6). | This is the intended reading — a skills-library request is self-development, not an app — and is ACCEPTED, not avoidable: `_overlap_score` divides by the smaller set, so even dropping the bare token `library` leaves `skills` scoring 0.333 > `SECTION_MATCH_THRESHOLD`. Pinned as a decision by `test_a_skills_library_request_is_self_development_only` (§7 T4) so it is chosen, not discovered. |
| R6 | `skills/README.md` and the skill body drift apart. | medium over time | The skill teaches a checklist the repo no longer has. | S10 / T2 `test_checklist_headlines_match`, which names the offending headline. |
| R7 | Larry applies step 1 but forgets step 10, or vice versa. | low | Authoring works, nothing is ever enabled (harmless); or the stub is enabled with a `# Body placeholder` body (harmful — it would inject that line). | §5 step 2 refuses to start if the stub is already enabled; §5 step 10 is gated on the PR merging, and its two verification commands print the answer. |
| R8 | The plan's line-number citations go stale before it is implemented. | medium | An implementer patches the wrong line. | §0 rule 5: a citation mismatch is a stop-and-report, not an adaptation. Every diff in §5 is anchored on surrounding text, not on a line number alone. |
| R9 | `_split_frontmatter`'s two-split behaviour (S12) truncates some *future* skill's body — including an imported community skill, where Markdown horizontal rules are common. | **medium-high for imports**, low for authored | Half a skill is injected. Silent: `parse_skill` reports nothing, `--validate` passes, `--explain` scores it correctly because matching reads the card. | T7 makes it a red test the moment the file lands, which is the whole mitigation this plan buys. **Not fixed at the source, deliberately** (S12 point 3): changing `_split_frontmatter` alters how every existing and imported skill parses and this plan cannot test that blast radius. Recommended follow-up for a later plan: split on the first `"\n---"` only, with the five shipped skills' `body()` lengths (2,547 / 2,491 / 2,556 / 5,267 / 3,467, recorded in T7) as the regression baseline. |

---

## §11 Self-audit — the nine-item taxonomy, walked

1. **Multi-consumer contracts named but not typed.** One contract is
   introduced (S-A, `MATCH_EVIDENCE`) and it is typed member by member in
   §7 T2: `dict[str, dict[str, list[str]]]`, keys `"fires"` and `"silent"`,
   with the *predicate* for each spelled out (`fires` = top-scoring
   qualifying skill on disk; `silent` = does not qualify at all — second
   place is explicitly **not** silent). `SEVEN_ITEM_HEADLINES` is a
   `tuple[str, ...]` of seven exact strings, and those same seven strings
   appear in §3 S1's body and §5 step 4a, checked. The `--explain` output
   format is *consumed*, not introduced, and its three load-bearing fields
   (`score`, `shared_tokens`, `<< INJECTED`) are named in the skill body.
2. **Lifecycle left implicit.** Three lifecycles were checked. (a) *On disk
   vs enabled*: stated everywhere it matters — the file survives disabling,
   the skill goes inert, and §9 turns that into the rollback. (b) *Session
   state*: `SelfEditService._validated_ok` is reset by every `propose_edit`
   (`jarvis/selfedit/service.py:213`), so a skill written after validation
   forces re-validation — noted in §7 T3. (c) *Allowlist reload*: `Allowlist`
   is loaded in `SelfEditService.__init__` (`:104-107`), so a change to the
   JSON requires a sidecar restart — stated in §9.
3. **How a value is applied.** Every value has its application site named:
   the description reaches matching via `Skill.card`
   (`jarvis/agent_skills.py:134-136`), not via the body; the four S7 words
   reach selection via `_tokens(DEVELOPER_SECTION_WHEN[name])`
   (`jarvis/prompts.py:394`); the allow-list entry is applied through
   `Allowlist.is_allowed` at `_check_path` (write time) *and*
   `filter_violations` at `validate()` (diff time) — two application sites,
   both named in §7 T5. **The find that this item produced:** the skill's
   body reaches an agent through `Skill.body()`, which is *not* the file's
   text — `_split_frontmatter` returns only the slice between the first two
   `"\n---"` occurrences. Asking "how is this value applied?" of the body is
   what surfaced S12, after the first draft of §3 S1 had already been
   written with a truncating YAML example in it.
4. **Two sections describing the same behaviour differently.** Hunted
   deliberately, three findings. (a) The seven-item checklist necessarily
   exists twice → S10 pins it with a test rather than pretending it does
   not. (b) Match evidence could have lived in both the skill body and the
   fixture → S9 explicitly puts the *numbers* in only one place, and the
   skill body carries no scores at all. (c) `skills/README.md` item 4
   contradicted the code comment at `jarvis/agent_skills.py:101-105` → R-1
   fixes the README rather than letting the skill inherit the contradiction.
5. **Copy and visual states named but unspecified.** No UI. All operator-
   facing copy is literal: the two commit messages (§5 steps 1, 10), the
   comment block added to `config/skills.yaml`, the assertion messages in
   §7 T2/T3/T5, and every line of the skill itself (§3 S1). The expected
   CLI output of every verification command is reproduced exactly.
6. **Initialization timing.** Ordering is stated and the reason given: step 1
   (allowlist) must land before the implementation branch is created, or the
   self-edit session cannot write `skills/`; step 2 refuses to proceed
   otherwise. Step 10 (enable) must land after the PR merges, or G6(c) cannot
   be observed. §9 states the one ordering constraint in rollback. Within a
   process: `Allowlist` at service construction, `discover()` at CLI/test
   call time, `match_skill` at `SubAgent._loop` entry
   (`jarvis/agents/base.py:528`) — the skill is selected once per delegation,
   before the first tool call.
7. **Signatures agreeing across sections; every schema column populated;
   every value derivable.** `MATCH_EVIDENCE`'s two keys are both populated for
   all three named skills by §7 T1/T1b/F7 measurements — `skill-authoring`
   with two `fires` and eight `silent` (the four G6(a) negatives plus the
   four F1 displacers), `technical-plan-document` and `mcp-server-authoring`
   with two and two each. The `skill-authoring` `fires` pair and the first
   four `silent` are the same six utterances as §8 check 1 and G6(a).
   `discover()`,
   `_tokens`, `_overlap_score`, `MATCH_THRESHOLD`, `MIN_SHARED_TOKENS` are
   used with the signatures verified at their cited lines. The `_qualifies`
   helper in T2 is the same predicate as `explain()`'s local `qualifies`
   (`jarvis/agent_skills.py:514-515`) — deliberately mirrored, and if it ever
   drifts the acceptance transcript in T1 stops matching the test.
   `_shipped_predicate` in T3 is one function called by both the real-
   directory test and the malformed cases, so those two cannot disagree.
8. **Judgment left to the implementer.** Swept for the three shapes. No
   "use judgment": every threshold is a number in §6 and every acceptance is
   a measured digit in §7. No "investigate first": step 2 is a decision tree
   (three commands, expected values, "stop and report" on mismatch) and §5
   step 3's failure mode names the two likely mistranscriptions and their
   fixes. No bare "be careful": the security-adjacent change (the allow-list
   move) is a literal diff plus a six-line verification whose exact expected
   output is printed, plus the adversarial cases as tests (§7 T5, and §8
   check 5's refusal path).
9. **Plan drift.** Checked file by file. `skills/skill-authoring/SKILL.md` is
   a **modify**, not a create — the stub exists (verified: 9 lines, `:9` is
   `# Body placeholder`), and §1 gap 1, §4, and §5 step 2 all say so
   consistently. Every file in §5 appears in §4's manifest and nothing else
   does; §4 additionally lists what must **not** appear in the diff. No
   section says "write X" while another says "X exists": `tests/unit/
   test_skill_match_evidence.py` is a create everywhere it is mentioned;
   `tests/unit/test_prompts.py` and `tests/unit/test_selfedit_allowlist.py`
   are treated as existing files gaining a class, and **both were verified
   to exist** — including the exact symbols each added class relies on
   (`select_developer_sections` imported per-method at
   `tests/unit/test_prompts.py:332`; `Allowlist`, `REPO_ROOT` and `CONFIG`
   at `tests/unit/test_selfedit_allowlist.py:9`, `:11`, `:12`). Every test
   in §7 is assigned to exactly one §5 step (T2→step 6, T3/T5/T7→step 7,
   T4→step 5) and §4's manifest rows name the same steps.

**One thing this plan does not verify and says so:** the sandbox snapshot has
no `pytest`, so no test in §7 has been *executed*. Each was instead reduced
to the predicate it asserts and that predicate was run directly (T1 via the
real `--explain` CLI, T3 via `discover()` against seeded broken folders, T4
via `select_developer_sections`). The test bodies themselves are unrun code
and Larry's §8 check 2 is their first real execution.

---

## §12 Approval checklist

Larry ticks these before the implementer starts:

- [ ] **The skill's text** (§3 S1) reads the way you want an agent to be
      taught — particularly `## When this does not apply` and `## What you
      may write, and the one file you may not`.
- [ ] **The description** (§3 S1, S3) — you accept that its exact words are
      load-bearing and that changing one invalidates §7 T1.
- [ ] **The allow-list diff** (§5 step 1) is what you intend: `skills/**`
      writable by a self-edit, `config/skills.yaml` never. You commit it by
      hand (C8).
- [ ] **Enabling stays yours** (§3 S5): a separate commit, after you have
      read the merged `SKILL.md`.
- [ ] **R-1** — you agree `skills/README.md` item 4 is wrong today and
      should be corrected to say the anti-trigger goes in the body.
- [ ] **R-2 / S9** — `tests/unit/test_skill_match_evidence.py` is where
      match evidence lives from now on, and every future skill adds four
      utterances to it.
- [ ] **S7** — you accept the four words added to the developer's
      `self_development` trigger vocabulary, given the measured
      `['app_development']`-only result.
- [ ] **S12 / R9** — you accept that `_split_frontmatter`'s body-truncation
      bug is *guarded* (T7) rather than *fixed* in this plan, and that fixing
      it at the source is a later, separately-tested change.
- [ ] **S11** — no new kill switch; removing one line from
      `config/skills.yaml` is the off switch.
- [ ] **Scope** — the Xcode half of T6 (§2) is a separate plan, after T1.3.
- [ ] Branch name `jarvis/self-edit/skill-authoring` is acceptable.


