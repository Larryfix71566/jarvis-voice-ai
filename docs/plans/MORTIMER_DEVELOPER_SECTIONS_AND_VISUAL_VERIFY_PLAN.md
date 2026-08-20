# Mortimer — Developer Prompt Sections & Visual Verification

**Status: APPROVED by Larry 2026-08-19 — IMPLEMENTED (except B4.2)**
Author: Claude, 2026-08-19. Requested by Larry.

---

## 0. Why

Two problems, arrived at from opposite directions in the same conversation.

**Problem 1 — the developer's prompt carries text that doesn't apply.**
Measured 2026-08-19:

```
developer own prompt          4,034 chars
  app development             1,188
  self-development            1,566   ← 68% of its own text, two paragraphs
  planning                      463
  core (identity/reads/output)  ~817
shared AGENT_DISCIPLINE         546
```

Both protocol paragraphs are injected on *every* developer run, including
"read this YAML file." The 2026-08-18 `AGENT_DISCIPLINE` consolidation cut
the *shared* rules 1,216 → 546 and left this untouched — so the remaining
prompt-space problem is now entirely the developer's own text.

Larry's framing, which this plan adopts: **do the specialization at the
developer level, leave Supervisor routing exactly as it is today.** That
gets the benefit of specialized agents without touching the routing eval,
which is the expensive thing to get back once lost.

**Problem 2 — the self-edit validation gates cannot see the screen.**
`web/src/**` and `web/public/**` are on the self-edit allowlist; the
interface is the *primary* self-edit target by design. All four validation
gates (allowlist, backend import, frontend build, pytest) prove the code
compiles, imports, and passes tests. **None of them can tell whether the
console still looks right or is usable.** Every glass change made on
2026-08-18 would have passed all four while rendering as anything at all.

Larry: *"I like giving screen vision to all aspects of the interface, I feel
like that makes sense."*

---

## 1. The correction that shapes Part B

**A screenshot taken during `validate()` is the wrong artifact, and this
plan does not build one.**

`screen_view` (`mcp_servers/mcp_screen/logic.py`) captures a **physical
display** via `screencapture`. Self-edit validation runs in the admin
sidecar against a sandbox branch that is *not what is currently rendering
on screen*. A capture at that moment photographs whatever console happens
to be running — almost always the pre-change one. It would produce a green
check that means nothing, which is worse than no check at all.

The correct artifact would be a headless render of the branch's build.
Verified 2026-08-19: **no headless browser exists in this repo** — neither
Playwright nor Puppeteer appears in `requirements.txt` or
`web/package.json`. Adding one is a real project (new dependency, a CI
runner that can run it, and a console that needs a live bot to connect to
before anything meaningful renders). It is explicitly **out of scope** here
and should not be inferred as a follow-up commitment.

What *is* buildable now, and is what Larry actually asked for: give
Mortimer the ability to **look at its own running interface and report
honestly on it**, at the moment when the branch is genuinely on screen —
after Larry pulls and runs it. That is a verification step with a human in
the loop, not a gate. It reuses the existing screen-vision path entirely.

Naming discipline: this is called a **visual check**, never a "gate."
The four things in `validate()` are gates — they block. This does not
block, and the vocabulary must not suggest it does.

---

## PART A — Conditional prompt sections at the developer level

### A1. Split the developer prompt into a core plus named sections

`jarvis/prompts.py` gains, replacing the single `developer` string:

```python
DEVELOPER_CORE = "..."        # identity, repo reads, write two-phase, output contract
DEVELOPER_SECTIONS: dict[str, str] = {
    "app_development":  "...",   # the existing 1,188-char paragraph, verbatim
    "self_development": "...",   # the existing 1,566-char paragraph, verbatim
    "planning":         "...",   # the existing   463-char paragraph, verbatim
}
```

**The section text is moved verbatim, not rewritten.** This plan changes
*when* text is injected, never *what it says*. Any rewording is a separate
change with its own review — mixing the two would make a behavioral
regression indistinguishable from a selection bug.

`SUBAGENT_PROMPTS["developer"]` continues to exist and equals
`DEVELOPER_CORE + all sections`, so every existing caller and test that
reads it keeps working and the fail-open path below has something to
return.

**Assembly order is fixed and must not vary between the full prompt and a
selected one**, or the two stop being byte-comparable and A5's kill-switch
test cannot be written:

```
DEVELOPER_CORE
  + each selected section, in DEVELOPER_SECTIONS declaration order
  + "\n" + AGENT_DISCIPLINE
  + repo-map suffix (when inject_repo_map)
```

Sections are joined by `"\n\n"`, matching how the paragraphs are separated
in the prompt today.

Verified 2026-08-19: the developer prompt contains **no `{}` format
placeholders** (only `scheduler` uses `{timezone}`), so
`base.py`'s `.format(timezone=...)` at line 220 applies harmlessly to the
assembled result. No escaping work is needed.

### A2. A pure selector

New in `jarvis/prompts.py` (pure — no DB, no network, no model):

```python
def select_developer_sections(task: str) -> list[str]:
    """Which DEVELOPER_SECTIONS apply to `task`. Fail-open: ambiguity
    returns every section, which is today's behavior exactly."""
```

Mechanics, deliberately boring:

- Reuse `jarvis.procedures`'s `_tokens` / `_overlap_score`. **One scorer in
  this codebase, not a second one** — the same rule that made
  `agent_skills.MIN_SHARED_TOKENS` reuse `consolidate.py`'s value.
- Each section carries a hand-authored `when:` token set, stored beside it
  in `prompts.py`. Not derived from the section text: the self-development
  paragraph contains the word "app" and would pull app tasks in.
- `SECTION_MATCH_THRESHOLD = 0.25`, **deliberately lower** than a skill's
  0.30 or a workflow's 0.35, because the cost asymmetry is inverted here.
  A false positive costs ~1,200 wasted characters. A false negative drops
  a confirmation protocol. Bias toward inclusion.
- **Multiple sections may be selected.** Unlike skills (`MAX_INJECTED = 1`)
  there is no competition — a task can legitimately be both a plan and a
  self-edit, and both paragraphs should be present.
- If *no* section scores above threshold, return **all** sections. A task
  the selector doesn't recognize gets today's prompt, unchanged.
- **No `MIN_SHARED_TOKENS` guard here, deliberately** — and this is a
  considered deviation from `agent_skills.py`, not an oversight. There,
  `MAX_INJECTED = 1` means a coincidental single-token match *displaces*
  the skill that should have won, so the guard prevents real loss. Here
  sections don't compete and a coincidental match costs ~1,200 wasted
  characters. "What's the plan for today" pulling in the planning section
  is an acceptable outcome; dropping a confirmation protocol is not.

### A3. Wire it at the one place per-run text is already chosen

`jarvis/agents/base.py` line 296 currently does:

```python
{"role": "system", "content": self._system_prompt},
```

It becomes a call to a new `self._system_prompt_for(task)`, which returns
`self._system_prompt` unchanged for every agent except `developer`, and for
`developer` assembles core + selected sections + the same
`AGENT_DISCIPLINE` and repo-map suffix `__init__` already appends.

This is the right seam because `_loop` is **already** where the other three
"what text does this run get" decisions happen — procedure hint (line 307),
skill (line 333), workflow (line 352). Section selection joins them rather
than inventing a fourth mechanism in a different file.

`__init__` keeps doing the `.format()` and repo-map read exactly once per
boot; only assembly moves per-run. No new file reads per delegation.

Concretely, `__init__` stores three things on `self` instead of one
pre-joined string: the formatted core, the formatted sections dict, and
the repo-map suffix (empty when absent). `.format(timezone=...)` is applied
to each piece at construction, exactly as it is applied to the whole string
today — verified safe because the developer prompt has no placeholders, so
this is a no-op for it and unchanged for every other agent.

### A4. Kill switch

`JARVIS_DEVELOPER_SECTIONS_ENABLED=false` → `select_developer_sections`
returns all sections. Enforced at exactly one point, inside the selector.
Disabling it restores today's behavior byte for byte.

### A5. Tests (`tests/unit/test_prompts.py`, extending `TestAgentDiscipline`)

| Test | Pins |
|---|---|
| `test_full_prompt_is_core_plus_every_section` | the reassembly identity — no text lost in the split |
| `test_a_self_edit_task_gets_the_self_development_section` | positive case |
| `test_an_app_task_gets_the_app_section` | positive case |
| `test_a_plain_repo_read_gets_neither_protocol` | the actual saving |
| `test_an_unrecognized_task_gets_every_section` | **fail-open** |
| `test_a_task_that_is_both_gets_both_sections` | no `MAX_INJECTED`-style competition |
| `test_the_kill_switch_restores_the_full_prompt` | byte equality with today |
| `test_no_section_text_was_reworded` | each section is a substring of the pre-split prompt |

### A6. Expected outcome

Typical developer task: **4,034 → ~1,300–2,000 chars** of own text. Both
protocols present in full when they apply. Supervisor routing, the routing
eval, `config/agents.yaml`, and the agent catalog are all untouched.

---

## PART B — Visual verification of interface changes

### B0. What is already true, and why no new strictness is needed

Recorded here because it was the finding that redirected this part.
Self-development is already **structurally** far stricter than app
development, enforced in config rather than prompt wording:

| | self-edit | app-build |
|---|---|---|
| boundary | **allowlist**, 9 paths, + 25 deny patterns that always win | **deny-list**, 4 patterns; everything else writable |
| validation | 4 fixed gates | whatever `mortimer.app.yaml` declares; "none" is legal |
| landing | sandbox branch + rollback tag, PR only, human merges | PR |

A separate self-development *sub-agent* with sterner prompt rules would add
routing surface and no safety: the boundary is enforced by which tool is
called (`selfedit_start` → `SelfEditWorkspace` + allowlist;
`app_build_start` → `AppWorkspace` + deny-list), and calling the wrong one
targets a different repository rather than relaxing a gate. Per this
codebase's own discipline — *a rule without a backstop is a wish* — the
backstop already exists. **Part B therefore adds sight, not rules.**

### B1. `visual_intent` — one authored sentence, recorded on the session

When a self-edit session proposes an edit touching `web/src/**` or
`web/public/**`, `SelfEditService` records a single sentence stating **what
should look different**, authored by the agent at propose time.

This is the difference between a useful check and a vibe check. A vision
model asked "does this look right?" has no reference and will produce
agreeable prose. Asked "is the side drawer translucent, with the desktop
visible through it?" it can be wrong in a way that is *detectable*.

- Stored on the session alongside the existing per-path `rationale`.
- **Absent is a legal state and is reported as such** — "no visual intent
  stated," never a fabricated question. Same discipline as `AppWorkspace`'s
  "no checks defined."
- Non-visual edits never record one and never prompt for one.

### B2. `POST /api/selfedit/verify-appearance` (admin sidecar)

New endpoint on the sidecar, and a `verify_appearance` tool on
`mcp_selfedit` (thin HTTP client, same convention as its other tools —
`tests/integration/test_registry.py`'s `TOTAL_TOOLS` **57 → 58**; 57
verified 2026-08-19, not assumed from CLAUDE.md, which still records the
pre-`mcp_screen` count of 55).

Behavior, in order, stopping at the first failure:

1. **Confirm what is running.** Read the repo's current branch
   (`git rev-parse --abbrev-ref HEAD`, argument list, never a shell — the
   `SelfEditService._git` convention). If it is not the session's sandbox
   branch, **refuse** and say which branch is checked out. A pass claimed
   against the wrong code is precisely the failure mode Part B exists to
   avoid.

   The endpoint accepts `branch_override: bool = False`. A merged PR leaves
   Larry on `main` *with* the changes, and refusing there would be wrong —
   so the mismatch is refusable, not fatal, and the user in the loop is the
   authority, as everywhere else in this system. The override must be
   passed explicitly by the caller and the result **always states which
   branch was actually checked out**, so an overridden pass is never
   indistinguishable from a matched one.
2. **State the assumption explicitly in the result**: this confirms the
   branch, *not* that the browser has reloaded since. Under `npm run dev`
   Vite hot-reloads so the two coincide; against a stale production build
   they do not. The result says so every time rather than relying on the
   reader to remember.
3. **Refuse when `visual_intent` is absent**, naming that as the reason.
4. Call the existing `mcp_screen.logic.screen_view` with a question built
   from `visual_intent` plus a fixed suffix asking for anything unreadable,
   clipped, or overlapping.
5. Return the model's text answer verbatim, the display index, and
   `low_confidence` when the capture heuristic fired.

**This does not block anything.** It cannot be called from `validate()` and
must not be added to the checks list.

### B3. The PR body flags visual changes

`SelfEditService._open_pr` (line 302) currently lists changed paths with
rationales. It gains, when any changed path matches `web/src/**` or
`web/public/**`:

```
### Visual change — run the branch before merging

Intended appearance: <visual_intent>

The four validation checks cannot see the screen. Run this branch and
say "check your appearance" to have Mortimer look at the result.
```

When `visual_intent` is absent the block still appears, with the intent
line replaced by *"No intended appearance was stated — describe what should
look different before verifying."* The warning is the useful half; omitting
it because the agent failed to author a sentence would hide a visual change
precisely when the agent was least careful about it.

Cheap, honest, and useful even if B2 is never invoked.

### B4. Broaden screen vision across the interface

Larry: *"screen vision to all aspects of the interface."* Two concrete
gaps today:

- **B4.1 — reach.** `mcp_screen` is wired only to `systems` and
  `developer` in `config/agents.yaml`. Add nothing here without a stated
  reason; the direct Supervisor `view_screen` tool already covers voice,
  which is the path used most. **No change proposed — recorded so the
  decision is visible rather than overlooked.**
- **B4.2 — multiple displays, unverified.** Mortimer's interface now spans
  up to three native windows (console, display, drawer), placeable across
  screens. `_system_profiler_displays` **has never been verified against
  real multi-monitor hardware**, and `screen_view(display=N)` is untested
  beyond display 1. This is a verification task on Larry's machine, not a
  build task: with the drawer popped to a second screen, `screen_list`
  must report both, and `view_screen` must be able to reach the drawer.
  Until that runs, any claim that Mortimer can see "the whole interface"
  is unsupported and must not be made in prompts or docs.

### B5. Tests

| Test | Pins |
|---|---|
| `test_verify_refuses_when_branch_does_not_match` | the wrong-code failure mode |
| `test_branch_override_proceeds_but_names_the_branch` | an overridden pass is never mistaken for a matched one |
| `test_verify_refuses_when_no_visual_intent` | absent is reported, never invented |
| `test_the_question_contains_the_recorded_intent` | not a generic "does this look ok" |
| `test_low_confidence_is_surfaced_not_swallowed` | the permission-failure path |
| `test_pr_body_flags_web_paths` | B3, with and without `visual_intent` |
| `test_verify_is_not_in_the_validate_checks_list` | it is a check, never a gate |

Screen capture and the vision client are injected seams
(`capture_fn` / `client_factory`, already parameters of `screen_view`), so
none of this needs a display or an API key in CI.

---

## 2. What this plan deliberately does not do

- **No headless render.** Named in §1 with the reason. Not a follow-up.
- **No new sub-agent, no `config/agents.yaml` change, no routing change.**
  Part A's whole point is leaving the Supervisor alone.
- **No rewording of the moved section text** (A1).
- **No stricter self-edit rules.** B0 records why: the strictness is
  already structural, and prompt rules would add none.
- **No screenshot inside `validate()`.** Explicitly forbidden by B2 and
  pinned by a test.
- **No retention change.** Screen captures keep the existing 48-hour
  `JARVIS_SCREEN_RETENTION_HOURS` policy and the low-confidence-only image
  retention from the skill-library plan's Part G. This plan adds no new
  category of stored image.

## 3. Acceptance

1. `pytest tests/unit tests/integration -q` green.
2. `python -m tests.evals.routing_eval` ≥ 90% — **must be run**, even
   though no routing changed, because Part A alters what the developer
   sees and the eval is the only measurement of routing health.
3. A developer task that is a plain repo read shows a measurably shorter
   system prompt in the run log; a self-edit task shows the full
   self-development section.
4. `JARVIS_DEVELOPER_SECTIONS_ENABLED=false` restores the prompt byte for
   byte.
5. A self-edit touching `web/src/**` produces a PR body carrying the
   visual-change block.
6. B4.2 multi-display verification run on Larry's machine, verdict
   recorded in this file — **PASS/FAIL, not assumed.**

## 4. Approval

Larry approves before any code is written or run.

- [x] Part A — conditional developer prompt sections
- [x] Part B — visual verification (B1, B2, B3, B5)
- [ ] B4.2 — multi-display verification on real hardware **(needs Larry's Mac)**

## Deviations from the plan as written

**A2 gained a recognised-read path.** As specified — fail-open only — a plain
repo read matched no section and received all three, so acceptance criterion 3
("a plain repo read shows a measurably shorter system prompt") FAILED and the
saving existed only on tasks that already matched. The fix distinguishes
UNRECOGNISED (fail-open, unchanged) from RECOGNISED-AS-A-READ (core only).

That opened a real hazard the plan had not considered: *"read the file and fix
the bug"* looks like a read and is a self-edit. Every mutation verb — fix,
write, edit, add, remove, rename, refactor, update, patch — therefore lives in
`self_development`'s vocabulary, so anything that could write matches a section
before it can reach the core-only path.
`test_a_read_that_could_write_keeps_the_protocol` pins three variants.

Measured after: plain read 813 chars (was 4,033), self-edit 2,380, app 2,002,
plan+implement 2,844, unrecognised 4,033.
