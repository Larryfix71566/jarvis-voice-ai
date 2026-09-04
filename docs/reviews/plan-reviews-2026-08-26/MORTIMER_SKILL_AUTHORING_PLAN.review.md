# Review — `MORTIMER_SKILL_AUTHORING_PLAN.md` (T6, skill-authoring half)

Reviewed 2026-08-27 against repo snapshot `/home/claude/repo`.
Everything below was **measured**, not read: the plan's §3 S1 skill text was
extracted verbatim (plan lines 251–469), installed into a sandbox copy of
`skills/`, and scored with the repo's own `discover()` / `match_skill()` /
`explain()` and `jarvis.procedures._tokens` / `_overlap_score`.

Sandbox artefacts:
`/tmp/claude-0/-home-claude/2ceba6d6-eac3-5a4d-9123-be345652e9e4/scratchpad/sandbox/skills/`
and `.../rank.py`.

**Counts:** 2 BLOCKER, 5 MAJOR, 7 MINOR.

---

### F1 — The new description **displaces `technical-plan-document` on four ordinary plan-review utterances**, and fires on core self-edit vocabulary. `MAX_INJECTED = 1`, so these are silent losses. [BLOCKER]

**Where:** §3 S1 (the `description:` line), §3 S3 ("Every word of the
description was chosen against a false positive"), §7 T1/T1b, G6(a).

**What the plan says:**
> "§3 S3 — Every word of the description was chosen against a false positive.
> These four are load-bearing." … "`write`, `author`, `draft`, `create`,
> `improve`, `sharpen` are all present deliberately: each is … worth exactly
> one shared token against a neighbour's utterance — which
> `MIN_SHARED_TOKENS = 2` neutralises on its own."

**Why it's wrong:** the author tested six utterances they chose themselves.
The description's 39 card tokens include a large block of *generic* words the
S3 table never examines — `review`, `existing`, `before`, `improve`, `itself`,
`mortimer`, `why`, `never`, `body`, `name`, `description`, `item`, `any`,
`library`, `checklist`. Several of these co-occur in ordinary repo tasks, so
`MIN_SHARED_TOKENS = 2` does **not** neutralise them. Worse, `mortimer` and
`itself` are literally the first two words of
`DEVELOPER_SECTION_WHEN["self_development"]`
(`jarvis/prompts.py:309`) — the repo's own canonical phrasing for a self-edit
request.

**Evidence:** ran the repo's real `match_skill()` over the five shipped skills
with and without the new one (`skills=` seam, so this is the exact production
predicate):

```
'review the existing implementation plan before I approve it'
   before=mcp-server-authoring   after=skill-authoring   REGRESSION   (0.500 vs 0.333)
'improve the existing spec document'
   before=technical-plan-document after=skill-authoring  REGRESSION   (0.500 tie)
'draft and review the design document'
   before=technical-plan-document after=skill-authoring  REGRESSION   (0.500 tie)
'author a draft of the remote access plan'
   before=technical-plan-document after=skill-authoring  REGRESSION   (0.400 tie)
'improve Mortimer itself'                    before=None after=skill-authoring (1.000)
'change Mortimer itself to use a darker theme' before=None after=skill-authoring (0.400)
'explain why the branch never merged'        before=None after=skill-authoring (0.600)
'write a skill for the developer that captures how we review a pull request'
                                             before=None after=skill-authoring (0.429)
```

More false fires, measured the same way (all currently inject nothing):

```
'improve the name and description'        skill-authoring 1.000  ['description','improve','name']
'explain the scorer to me'                skill-authoring 1.000  ['explain','scorer']
'explain why the match never fires'       skill-authoring 0.800  ['explain','match','never','why']
'review the existing workflow and improve it' 0.750 ['existing','improve','review']
'create a new item in the library'        skill-authoring 0.750  ['create','item','library']
'author a new review checklist'           skill-authoring 0.750  ['author','checklist','review']
'record the evidence and explain why'     skill-authoring 0.750  ['evidence','explain','why']
'add a clock panel to Mortimer itself'    skill-authoring 0.400  ['itself','mortimer']
'refactor Mortimer itself to drop the web console' 0.333 ['itself','mortimer']
```

Three of the four `technical-plan-document` losses are **exact score ties**
broken by `match_skill`'s `score > best[0]` (strictly greater, so the first
candidate in `discover()` order wins — `jarvis/agent_skills.py:366`).
`discover()` sorts by folder path, and `skill-authoring` sorts before
`technical-plan-document`. That tie-break is undocumented in the plan and is
load-bearing for three of these regressions.

Note the last entry in the first block: the utterance is **§8 check 4's own
acceptance script** ("write a skill for the developer that captures how we
review a pull request"). It fires at 0.429 largely on `review` + `write` +
`skill` — fine here, but it shows how much of the score comes from generic
verbs rather than domain nouns.

**Fix:** strip the generic tokens and re-measure. A candidate that keeps all
six §7 T1 numbers **identical** while removing every displacement above (391
chars, measured in the same harness):

```
description: Author a SKILL.md for the skill library, or sharpen one that over-matches — frontmatter fields, the seven-item checklist, keeping anti-triggers out of the card, recording measured match evidence from the --explain scorer before a skill is enabled, and promoting a learned procedure with --from-procedure. Use when asked to write, sharpen or promote a skill, a SKILL.md, or the skill library.
```

Measured with that description: the six G6(a) rows are unchanged
(`0.375 / 0.714 / mcp 0.500 / mcp 0.500 / tpd 0.500 / tpd 0.333`), and
`improve the existing spec document`, `draft and review the design document`,
`author a draft of the remote access plan`,
`review the existing implementation plan before I approve it`,
`improve Mortimer itself`, `change Mortimer itself to use a darker theme`,
`explain why the branch never merged`, `improve the name and description`,
`review the existing workflow and improve it` all stop being won by
`skill-authoring`. Whatever wording is finally chosen, §7 T1 must be
re-measured and **`MATCH_EVIDENCE`'s `silent` list must gain at least
`"improve the existing spec document"`, `"draft and review the design
document"`, `"author a draft of the remote access plan"` and `"change
Mortimer itself to use a darker theme"`**, or T2 will keep passing on the
four utterances that were never the problem.

---

### F2 — §5 step 9 tells the implementer to compare `--explain` output "digit for digit" against a transcript that **cannot** be produced at step 9, and to diagnose the mismatch as a mistranscription. [BLOCKER]

**Where:** §5 step 9; §7 T1 (transcript); §3 S5 (enable is step 10).

**What the plan says:**
> "Then run the six acceptance utterances in §7 T1 and compare the printed
> numbers to the table there, digit for digit. A disagreement means the
> description was mistranscribed in step 3 — diff it against §3 S1 rather than
> adjusting the table."

and §7 T1's preamble: "Measured … with all six skills on disk and **all six
enabled**."

**Why it's wrong:** at step 9 the skill is *not* enabled — that is step 10,
and `config/skills.yaml` is on the deny list so the implementer cannot enable
it. `explain()` prints `[inert  ]`, omits `<< INJECTED`, and ends with
"Nothing would be injected". The scores match; the transcript does not. An
implementer told "a disagreement means the description was mistranscribed"
will chase a non-existent bug, or (worse) conclude the skill must be enabled.

**Evidence:** ran the real `explain()` with `skill-authoring` on disk but not
in the enabled list — i.e. exactly the state at step 9:

```
[inert  ] score=0.375 PASS skill-authoring
          shared_tokens=['library', 'skill', 'write']
…
Nothing would be injected: the skills above threshold (skill-authoring) are inert.
```

vs §7 T1's reproduced transcript `[enabled] score=0.375 PASS skill-authoring << INJECTED` / `Would inject: skill-authoring`.

**Fix:** in §5 step 9 replace the instruction with: "compare only the
`score=` and `shared_tokens=` lines; every skill-authoring line will read
`[inert  ]` and the last line will read `Nothing would be injected: the skills
above threshold (skill-authoring) are inert.` — that is the correct output
before Larry's step 10." Add a second expected transcript to §7 T1 showing the
pre-enable form, and move the `<< INJECTED` / `Would inject:` expectations into
§8 check 1 where they belong.

---

### F3 — §5 step 1's "Expected, exactly" block is already wrong once the plan the roadmap sequences *first* has landed. §0 rule 5 then tells Larry to stop. [MAJOR]

**Where:** §5 step 1 (verification block and expected output); cross-plan with
`MORTIMER_SECURITY_HARDENING_PLAN.md` D-H9; roadmap §8 ordering.

**What the plan says:**
> Expected, exactly:
> ```
> True  skills/skill-authoring/SKILL.md
> …
> True  config/agents.yaml
> ```
> and §0 rule 5: "If a citation does not match the file you are looking at …
> report the mismatch and stop rather than adapting."

**Why it's wrong:** `MORTIMER_SECURITY_HARDENING_PLAN.md` D-H9 adds
`"config/agents.yaml"` (plus `jarvis/skills/registry.py`,
`mcp_servers/*/skill.yaml`, `tests/unit/test_agent_isolation.py`) to the
**deny** array, also as Larry's hand commit. The roadmap
(`docs/plans/MORTIMER_PLATFORM_ROADMAP.md:486-497`) sequences that plan
**first** and this plan **fourth**. So by the time step 1 runs,
`config/agents.yaml` is denied and the expected output is wrong on its last
line. The plan gives an explicit remediation only for
`config/skills.yaml` printing `True`; it says nothing about `agents.yaml`.

**Evidence:** applied step 1's diff to the real allowlist and then D-H9's
entries:

```
after step 1 only:                  after step 1 + D-H9:
True  skills/skill-authoring/…      True  skills/skill-authoring/…
True  skills/README.md              True  skills/README.md
True  skills/anything/SKILL.md      True  skills/anything/SKILL.md
False config/skills.yaml            False config/skills.yaml
False config/self_edit_allowlist…   False config/self_edit_allowlist…
True  config/agents.yaml            False config/agents.yaml      <-- differs
```

Neither plan mentions the other; both hand Larry an edit to the same file, and
neither states a merge order for the two hand commits.

**Fix:** (a) drop `config/agents.yaml` from step 1's probe list — it is not
what this change is about — or annotate it `True today, False after
MORTIMER_SECURITY_HARDENING_PLAN.md D-H9; either is acceptable`. (b) add a
sentence to §5 step 1 naming D-H9 and stating that the two hand commits are
independent and order-free, and that step 1's hunk context
(`config/self_edit_allowlist.json` … `requirements*.txt`) is unaffected by
D-H9's additions.

---

### F4 — False premise: "`skills/**` is denied to self-edit, so Mortimer cannot author a skill at all today… The `mcp_repo` write path cannot reach it either (same allowlist family)". `repo_write_file` can already write `skills/`. [MAJOR]

**Where:** §1 "The gap, stated exactly", item 2.

**What the plan says:**
> "**`skills/**` is denied to self-edit**, so Mortimer cannot author a skill at
> all today — by voice or by console. The `mcp_repo` write path cannot reach
> it either (same allowlist family)"

**Why it's wrong:** `mcp_repo` does **not** consult
`config/self_edit_allowlist.json`. It carries its own, entirely separate
write deny list (`mcp_servers/mcp_repo/logic.py:64-81`:
`DENY_WRITE_PATHS`, `DENY_WRITE_SEGMENTS`, `DENY_WRITE_GLOBS`), and `skills/**`
appears in none of them. The developer agent has `mcp-repo`
(`config/agents.yaml:45`), so `repo_write_file` → `repo_commit_write` already
reaches `skills/<name>/SKILL.md` today, by voice.

**Evidence:**

```python
from mcp_servers.mcp_repo import logic as L
L._check_write_allowed(L.resolve_repo_path(root, "skills/brand-new/SKILL.md"), root)
```
```
WRITABLE via mcp_repo: skills/skill-authoring/SKILL.md
WRITABLE via mcp_repo: skills/brand-new/SKILL.md
WRITABLE via mcp_repo: skills/README.md
refused: config/skills.yaml -> config/skills.yaml is not writable through this tool (protected configuration)
```

**Fix:** correct §1 item 2 to: "`skills/**` is denied to the *self-edit* loop,
so the multi-file `selfedit_start` path cannot author a skill. `mcp_repo`'s
single-file `repo_write_file` already can (its deny list is separate —
`mcp_servers/mcp_repo/logic.py:64-76` — and only names `config/skills.yaml`),
which is why authoring today happens one dictated file at a time with no
validation gate." Then decide explicitly whether that second path should stay
open; the plan currently reasons about a write surface that does not exist.

---

### F5 — S4's stated gates for the widening ("PR review, the pytest check, S9's match-evidence test") do not exist at the moment the file changes: `propose_edit` writes into the **live working tree**, and `load_skills()` re-reads from disk on every delegation. [MAJOR]

**Where:** §3 S4 "Two consequences the implementer must not be surprised by";
§10 R3; §3 S1's body paragraph "What you may write, and the one file you may
not".

**What the plan says:**
> "After this change a self-edit may amend **any existing skill**, including
> `mcp-server-authoring`. That widening is intended and its gates are the PR
> review, the `pytest` validation check, and S9's match-evidence test."

and the skill body tells the agent to report "the file is written, the name is
not enabled, and enabling is his."

**Why it's wrong:** two mechanisms combine.

1. `SelfEditService.start_session` does `git checkout -b <branch>` in the
   **same checkout the bot runs from** (`cwd=self.repo_root`,
   `jarvis/selfedit/service.py:172`; `_repo_root()` at `:50-53`), and
   `propose_edit` does `full.write_text(new_content)` directly
   (`jarvis/selfedit/service.py:221-223`). The file is on disk immediately —
   before `validate()`, before `submit()`, before any PR.
2. `match_skill()` → `load_skills()` → `discover()` → `parse_skill()` runs on
   **every** `SubAgent._loop` (`jarvis/agents/base.py:528`) with no cache. So
   the amended text reaches the next delegation with no restart.

Therefore an amendment to an **already-enabled** skill —
`skills/mcp-server-authoring/SKILL.md`, which teaches "Writes are two-phase,
always", "Never invent an `action_id`", "Never add a second success heuristic
anywhere in the tool path" (`skills/mcp-server-authoring/SKILL.md:108-119`) —
takes effect live, unreviewed. The plan's "gates" are all downstream of that.

The skill body's instruction to report "the file is written, the name is not
enabled" is also **false for amendments**: amending an enabled skill needs no
enable act at all. An agent told to say that will make a false capability
statement — the exact Golden-Rule failure R4 is written to prevent.

Precedent, for calibration: `config/workflows/` is already on the allow list
and is also re-read per delegation, so this is not a novel class of hole. But
`jarvis/prompts.py` (the other allow-listed prompt surface) only takes effect
after a restart; `skills/` does not.

**Fix:** (a) change S4's second bullet to state the real gate: "an amendment to
an already-enabled skill is live at the next delegation, before validation and
before the PR — the only gates are the human merge and `git checkout` of the
session branch." (b) In §3 S1's "What you may write" section, replace the
blanket "do not describe a newly authored skill as 'live'" with two cases: a
**new** folder is inert until Larry enables it; an **amendment to an enabled
skill is live immediately**, and must be reported as such. (c) Consider adding
to T2 a pin on the enabled skills' safety-bearing headings (e.g.
`"## Writes are two-phase, always" in mcp-server-authoring's body`), which is
the cheap version of the "body prose is not pinned" residual R3 accepts.

---

### F6 — S7's four added words can **remove** developer prompt sections, including `app_development`'s two-phase confirmation protocol. R5 records the risk in the opposite direction. [MAJOR]

**Where:** §3 S7 ("Only the defective row changes… deliberately
fail-toward-inclusion"), §10 R5, §7 T4.

**What the plan says:**
> "Only the defective row changes. `app_development` is *not* removed from the
> first row: `select_developer_sections` has no `MIN_SHARED_TOKENS` and is
> deliberately fail-toward-inclusion … a spare 1,188-character paragraph costs
> tokens, a missing confirmation protocol costs a wrong write. Removing a
> section is out of scope here."

and R5's impact column: "1,566 wasted characters in the developer's prompt."

**Why it's wrong:** `select_developer_sections` returns `hits` as soon as
**any** section matches and only falls through to the fail-open
`return list(DEVELOPER_SECTIONS)` when `hits` is empty
(`jarvis/prompts.py:392-406`). Adding vocabulary to one section therefore
converts *fail-open* tasks (which previously received **all three** sections)
into single-section hits — a strict **loss** of the other two, including
`app_development`'s `app_create` confirmation protocol.

**Evidence:** simulated the exact S7 string
(`… "patch correct repair adjust rework " "skill skills library authoring"`):

```
'improve the skill library'
   before=['app_development','self_development','planning']  after=['self_development']   LOST: app_development, planning
'make me a skills library'
   before=['app_development','self_development','planning']  after=['self_development']   LOST: app_development, planning
'set up a library of skills'
   before=['app_development','self_development','planning']  after=['self_development']   LOST: app_development, planning
'what skills do you have'
   before=['app_development','self_development','planning']  after=['self_development']   LOST: app_development, planning
'the library needs authoring tools'
   before=['app_development','self_development','planning']  after=['self_development']   LOST: app_development, planning
```

"make me a skills library" is exactly the ambiguous build request for which the
plan argues `app_development` must be kept. All fifteen existing
`select_developer_sections` assertions in `tests/unit/test_prompts.py:326-410`
still pass, so nothing catches it.

**Fix:** three edits, none of them to the four words.

1. Replace S7's "Removing a section is out of scope here" paragraph with the
   real mechanism: *"`select_developer_sections` returns `hits` the moment any
   section matches and only falls through to fail-open when `hits` is empty
   (`jarvis/prompts.py:392-406`). So adding vocabulary to one section
   **narrows** any task that previously matched nothing: 'make me a skills
   library' goes from all three sections to `['self_development']` alone.
   That is the intended reading of a skills-library request — it is
   self-development, not an app — but it is a narrowing, not an
   inclusion."*
2. Correct R5's Impact column from "1,566 wasted characters" to "a
   previously fail-open task loses `app_development` and `planning`;
   measured on 'make me a skills library', 'improve the skill library',
   'what skills do you have'."
3. Add the narrowing to §7 T4 as a *pinned decision*, so it is chosen rather
   than discovered later:

```python
def test_a_skills_library_request_is_self_development_only(self):
    """S7's accepted narrowing: these fell through to fail-open (all three
    sections) before the four words were added."""
    from jarvis.prompts import select_developer_sections as sel
    assert sel("make me a skills library") == ["self_development"]
    assert sel("improve the skill library") == ["self_development"]
```

Note (measured): dropping the bare token `library` from the added vocabulary
does **not** avoid this — `_overlap_score` divides by the smaller set, so on a
3-token task one shared token (`skills`) already scores 0.333, above
`SECTION_MATCH_THRESHOLD`. There is no wording of S7 that both fixes gap 4 and
avoids the narrowing; it has to be accepted explicitly.

---

### F7 — G6(a) and T2's negative test are satisfiable by a skill that displaces `technical-plan-document`; the fixture pins only the four utterances the author picked. [MAJOR]

**Where:** §7 T2 `test_negative_utterances_do_not_qualify`; §7 T1; roadmap
G6(a).

**What the plan says:**
> "`MAX_INJECTED = 1`, so an over-matching skill does not add noise — it
> DISPLACES the skill that should have won. Second place is a failure here,
> not a pass."

**Why it's wrong:** the test only asserts that the *named* skill does not
qualify on the four hand-picked `silent` utterances. It never asserts that the
skill that *should* win still does, and it has no coverage of the neighbouring
skills' own vocabulary beyond those four strings. As F1 shows, the shipped
description passes all four while taking four other `technical-plan-document`
tasks. G6(a) has the identical shape ("does not fire on two … and two …"), so
the gate is met by a skill that regresses matching.

Related smaller holes in the same file:

* `_scored()`'s docstring says it returns `(score, shared_count, name)`; it
  returns `Skill` objects.
* `test_negative_utterances_do_not_qualify` does
  `next(r for r in _rank(task) if r[2] == name)` with no default — a
  `StopIteration` (not an assertion) if the skill is missing from disk.
* `_rank` breaks ties by `(-score, name)`; `match_skill` breaks them by
  `discover()` order (`score > best[0]`). They agree only because S6 forces
  folder name == frontmatter name. Worth a one-line comment, since three of
  F1's regressions are decided by that tie-break.

**Fix:** add a **displacement** test rather than a per-skill silence test:

```python
def test_no_skill_displaces_another_on_its_own_evidence(self):
    """Every 'fires' utterance of every skill must still be won by that
    skill after any new skill is added. This is the MAX_INJECTED = 1
    property, stated once."""
    for name, cases in MATCH_EVIDENCE.items():
        for task in cases["fires"]:
            winner = next((n for s, sh, n in _rank(task) if _qualifies(s, sh)), None)
            assert winner == name, (task, winner)
```

…and populate `MATCH_EVIDENCE` for `technical-plan-document` and
`mcp-server-authoring` in the same PR (the plan already has a
`grandfathered` set; shrinking it by two costs four strings and is what makes
this test bite).

---

### F8 — §7 T3 contributes 7 collected tests, not 8; §8 check 2's pass criterion (`≥ 1,561`) is therefore unreachable. [MINOR]

**Where:** §7 T6; §8 check 2.

**What the plan says:**
> "this plan adds 6 (T2) + 8 (T3: two plus six parametrised) + 2 (T4) + 4 (T5)
> + 2 (§5 step 7) + 1 (T7) = **23**." … "`python -m pytest tests/unit -q` —
> green, count ≥ 1,561."

**Why it's wrong:** T3's three named additions are `_shipped_predicate` (a
`@staticmethod` helper — pytest does not collect a name that does not start
with `test`), `test_the_real_directory_passes_the_predicate` (1) and
`test_a_malformed_skill_fails_the_validation_gate` (6 parametrisations). That
is 7, not 8. Total added = 6 + 7 + 2 + 4 + 2 + 1 = **22**, so the suite goes
1,538 → **1,560**, and `≥ 1,561` fails.

**Evidence:** `CLAUDE.md:115` — "full `pytest tests/unit` (1538 tests) green"
— confirms the baseline. The T3 block is quoted in the plan at lines
1388–1436; `_shipped_predicate` is decorated `@staticmethod`.

**Fix:** change §7 T6 to 22 and §8 check 2 to `≥ 1,560`.

---

### F9 — §3 S5 and §4's manifest say the enable commit is "§5 step 9"; §5's step 9 is the verification step and step 10 is the enable. [MINOR]

**Where:** plan lines 536, 693, 985 vs 1001, 1021.

**What the plan says:**
> §3 S5: "3. Larry's enable commit (**§5 step 9**) — `config/skills.yaml`
> alone" ; §4 manifest: "`config/skills.yaml` | modify … | **§5 step 9**" ;
> §5 step 7: "It is not, until **step 9**".

but §5's headings are "### Step 9 — Full local verification, then hand off"
and "### Step 10 — LARRY, after the PR merges: enable it".

**Why it's wrong:** §0 rule 1 says every decision is already made; a Sonnet
following §4's manifest will look for the enable edit inside step 9, which is
the implementer's step and explicitly must **not** contain
`config/skills.yaml` (G6(c)).

**Fix:** change all three references to "step 10". §7 T2's line 1343 and §10
R7 already say step 10 correctly.

---

### F10 — The skill body's truncation rule is narrower than the code: `_split_frontmatter` splits on the substring `"\n---"`, so **any** line *starting* with three hyphens truncates, not only a "bare three-hyphen line". [MINOR]

**Where:** §3 S1 body, "## The file"; §3 S12; §7 T7.

**What the plan says:**
> "**Never write a bare three-hyphen line anywhere in the body.**
> `_split_frontmatter` splits the file on the first two of them"

**Why it's wrong:** `jarvis/agent_skills.py:179` is
`parts = text.split("\n---", 2)`. That matches `----`, `-----`, `--- BEFORE`,
a diff header `--- a/config/foo.json`, `---text` — anything whose line begins
with three hyphens. A skill body that quotes a unified diff (very plausible for
a skill about editing files, and the *plan itself* quotes six of them)
truncates. The T7 test is correct because it reuses the same `split("\n---",2)`;
only the prose rule understates.

**Evidence:**
```
>>> _split_frontmatter("---\nname: x\ndescription: y\n---\n\nAAA\n\n--- a/f\n\nBBB\n")
('\nname: x\ndescription: y', 'AAA\n')     # everything from '--- a/f' on is gone
```

**Fix:** in §3 S1 and §3 S12 replace "a bare three-hyphen line" with "any line
that **starts** with three or more hyphens — a horizontal rule, a longer rule,
or a unified-diff `--- a/path` header". Same correction in the T7 docstring.

---

### F11 — §1 says "minus a 40-word stop list"; it is 44. [MINOR]

**Where:** §1 "The loader and the scorer" table, row 5.

**Evidence:** `python3 -c "from jarvis.procedures import _STOPWORDS; print(len(_STOPWORDS))"` → `44`.

Relevant beyond pedantry because `why` is **not** a stop word (`what`, `which`,
`who`, `how` are), which is why `why` survives into the card and drives three
of F1's false fires.

**Fix:** "a 44-word stop list (note: `what/which/who/how` are stopped, `why` is
not)".

---

### F12 — `SECTION_MATCH_THRESHOLD` is at `jarvis/prompts.py:328`, not `:327`; `*.md`-is-root-only is documented at `jarvis/selfedit/allowlist.py:10`, not `:9`. [MINOR]

**Where:** §1 gap 4, §3 S4, §6 tuning-knob table.

**Why it matters:** §0 rule 5 makes a citation mismatch a stop-and-report
event. Two off-by-one citations will trigger it needlessly.

**Evidence:** `jarvis/prompts.py:327` is the comment line "# false negative
drops a confirmation protocol. Bias toward inclusion."; `:328` is
`SECTION_MATCH_THRESHOLD = 0.25`. `jarvis/selfedit/allowlist.py:9` is the
`*`/`**` line; `:10` is "A pattern without a slash (e.g. ``*.md``) matches
root-level files only."

**Fix:** correct both.

---

### F13 — §8 check 3's expected output is unobtainable on `main`. [MINOR]

**Where:** §8 check 3.

**What the plan says:**
> "**`python scripts/check_allowlist.py origin/main...HEAD`** on the merged
> self-edit branch — must print `all allowlisted`, exit 0."

**Why it's wrong:** `scripts/check_allowlist.py:36-40` returns 0 early with
`check_allowlist: branch '<x>' is not a self-edit branch - allowlist not
enforced` for any branch not starting with `jarvis/self-edit/`. After the PR
merges, `HEAD` is `main`, so the expected string never appears. The check is
only meaningful while `jarvis/self-edit/skill-authoring` is checked out.

**Fix:** "run it **while still on** `jarvis/self-edit/skill-authoring`, before
merging; on `main` it prints `allowlist not enforced` and proves nothing."

---

### F14 — §5 step 2 says "Run these three" but lists four commands, and `grep -c … # expect 0` exits 1. [MINOR]

**Where:** §5 step 2.

**Why it matters:** C10 forbids leaving the implementer a decision. A
zero-count `grep -c` returns exit status 1; in any `set -e` wrapper the
preflight aborts and the implementer must decide whether that is the failure
the plan meant. The count is also stated three ways (the prose says "A
non-zero count from the third command" — it is the third of four).

**Fix:** "Run these four"; and use
`grep -c skill-authoring config/skills.yaml || true   # expect 0`, with the
prose amended to "the third command".

---

## What I verified and found correct

Measured or opened at source; all of these hold.

1. **The six acceptance numbers in §7 T1 reproduce exactly.** Extracting the
   S1 text verbatim (plan lines 251–469) and scoring it against the five
   shipped skills gives `0.375` / `0.714` / `0.000` / `0.000` / `0.167` /
   `0.167`, with the shared-token lists and winners exactly as tabulated.
2. **The S1 text's own measurements are exact:** 219 lines, **10,389** file
   chars, **9,762** `Skill.body()` chars, **473** description chars,
   `parse_skill` → `problems: []` — all four match the plan digit for digit.
3. **The `_split_frontmatter` truncation bug is real and the fix *was* applied
   to the final text.** `text.split("\n---", 2)` → `parts[1].lstrip("-\n")`;
   the shipped S1 body yields `nparts=2`, so nothing is dropped. The plan's
   minimal repro reproduces character-for-character.
4. **R-1 is real.** `skills/README.md:50-53` still reads "**Does the
   description carry an anti-trigger?** One sentence saying what it is NOT
   for." — contradicting `jarvis/agent_skills.py:101-105` and
   `MORTIMER_SKILL_LIBRARY_PLAN.md:8-21`. Step 4a's `-` block matches the file
   byte for byte, as does 4b's (lines 59-60) and 4c's anchor (line 100).
5. **R-2 is real.** Nothing in the repo stores match evidence today.
6. **S10/T2's `test_checklist_headlines_match` would pass.** All seven
   `SEVEN_ITEM_HEADLINES` strings — including the em dash in item 4 — appear
   in both the S1 body and the post-step-4 README. Checked by string
   containment after applying 4a/4b.
7. **§1 gap 4 is real and correctly diagnosed.** `select_developer_sections
   ("write a new skill for the skill library about running database
   migrations")` → `['app_development']` today (0.250, exactly
   `SECTION_MATCH_THRESHOLD`, on `{new, write}` from `app_write`), and
   `['app_development', 'self_development']` after the four-word addition. The
   trailing-space warning in step 5 is correct and necessary.
8. **The other three T4 rows are unchanged** by S7, and **all fifteen existing
   `select_developer_sections` assertions in `tests/unit/test_prompts.py` still
   pass** after the change (simulated by patching `DEVELOPER_SECTION_WHEN`).
9. **`TestShippedSkills` exists at `tests/unit/test_agent_skills.py:416` and
   does read the real `skills/` directory** (`discover()` with no argument at
   `:420`, `:427`, `:434`); the docstring at `:417` really does say "The four
   skills promoted…" and really is wrong. `validate()` runs
   `python -m pytest tests/unit -q` with `cwd=self.repo_root`
   (`jarvis/selfedit/service.py:428-433`), i.e. against the branch's own
   working tree, so the claim that check 4 is the gate is correct.
10. **All six §7 T3 malformed cases behave as tabulated.** Run through the real
    `discover()`: `no-frontmatter`, `bad-yaml`, `no-description`, `bad-name`,
    `claude-helper` → `skill is None`; `oversized` → valid `Skill` with a
    non-empty `problems` list. The `_shipped_predicate` is False for all six.
11. **S6's gap is real**: folder/frontmatter name mismatch parses clean with
    `problems: []`. The two added assertions also close a second hole the plan
    does not claim — a second folder whose frontmatter reuses an
    already-enabled name (both would load and both would be match-eligible).
12. **The T7 body-length baseline is exact**: 2,547 / 2,491 / 2,556 / 5,267 /
    3,467 for the five shipped skills, each within 3 chars of the raw text
    after the frontmatter, `nparts=2` for all of them.
13. **Deny-wins is real** (`jarvis/selfedit/allowlist.py:77-79`), `skills/**`
    is on the deny list at `config/self_edit_allowlist.json:25`,
    `config/skills.yaml` at `:24`, the allowlist itself at `:21`, `config/**`
    on allow at `:5`. Step 1's two diff hunks match the real file's line
    ranges (`@@ -6,9` and `@@ -21,7`) and context exactly.
14. **T5's three symbols exist where cited**: `Allowlist` at
    `tests/unit/test_selfedit_allowlist.py:9`, `REPO_ROOT` at `:11`, `CONFIG`
    at `:12`. `test_prompts.py:332` really does import
    `select_developer_sections` inside the method.
15. **`--explain` is genuinely DB-free** — `main()` handles `--explain` and
    returns before the `from jarvis.db import get_conn` at `:613`; verified by
    running the CLI with no `JARVIS_DB_PATH` and no database.
16. **The enable gate has exactly one reader.** `enabled_names()`
    (`jarvis/agent_skills.py:270`) is the only consumer of
    `config/skills.yaml`; the admin sidecar's skills endpoint
    (`jarvis/admin/server.py:1291-1303`) is read-only; `write_skill()` and
    `skill_from_procedure()` deliberately do not touch it; `mcp_repo` denies it
    by its own list. No path other than a human commit can add a name — the
    plan's claim holds (but see F5: it is not the same thing as "no unreviewed
    skill text can go live").
17. **The stub is what the plan says it is**: `wc -l` = 9, line 9 is
    `# Body placeholder`, `grep -c skill-authoring config/skills.yaml` = 0.
18. **`docs/REPO_MAP.md`**: `grep -n skills` returns only
    `jarvis/skills/registry.py` at `:55`, as claimed.
19. **The 1,538-test baseline** is confirmed at `CLAUDE.md:115`.
20. **Citation spot-check, all correct**: `jarvis/agent_skills.py` 72, 77, 84,
    88, 101-105, 106, 109-118, 134-143, 162-171, 174-184, 253-256, 350-368,
    379-391, 393-401, 413-459, 465-485, 514-515, 612-638;
    `jarvis/agents/base.py` 37, 528; `jarvis/prompts.py` 300-302, 304-307,
    308-318, 378-383, 385-386, 394; `tests/unit/test_agent_skills.py` 140, 233,
    416-436; `scripts/check_allowlist.py` 3-6, 37-40, 56-61;
    `MORTIMER_SKILL_LIBRARY_PLAN.md` 8-21, 378.
