# Mortimer knowledge framework — golden rules, memory, skills, workflows

**Status:** DRAFT — §1.5 (Golden Rules) is IMPLEMENTED and tested; §2 onward
(memory tiering, consolidation, vocabulary, workflows) is not approved and
nothing there is built.
**Author:** drafted 2026-08-18 for Larry.
**Origin:** Larry, by voice, 2026-08-18: *"I'm afraid that we're distorting
everything as memory when there should be three separate categories.
Memory which provides context to you and my preferences. Skills, which
should be the way that we remember and store how we complete tasks so
that they can be reused without having to learn that all over. And then
workflows, which should be ways that we want tasks to be done to meet
certain criteria."*

---

## 1. Evidence — the current state, measured

Numbers taken from `data/jarvis.db` and `jarvis/memory.py` on 2026-08-18.

### 1.1 Memory is overflowing, and silently

| Measure | Value |
| --- | --- |
| Rows in `memories` | **180** (179 `kind='fact'`, 1 `kind='summary'`) |
| `MAX_FACTS` (jarvis/memory.py) | 30 |
| `MAX_CONTEXT_CHARS` | 1600 |
| Facts dropped at the cap | **149** |
| Facts dropped at the char budget | **17** |
| Session summary | **dropped entirely** |
| Facts that actually reach the Supervisor | **~14 of 180 (8%)** |
| Rendered context size | 1604 chars (~400 tokens) |

The drops are logged (`memory_context_facts_dropped`) but invisible in
conversation — Mortimer has no idea it is answering from 8% of what it
was told. Real preferences are among the discarded:
`user.style.confirmation_explicit`, `user.frustration_point`,
`user.preference.troubleshooting_directness`,
`user.style.progress_visibility`.

### 1.2 The store is duplicated and undifferentiated

Three separate facts encode "Larry is concise":
`user.preference.verbosity`, `user.style.conciseness`,
`user.style.minimal_explanation`. Four encode plan-display preference.
Key-prefix census of the 179 facts:

| Prefix | Count |
| --- | --- |
| `*.mortimer.*` | 67 |
| `*.style.*` | 45 |
| `*.preference.*` | 20 |
| `*.location.*` | 6 |
| everything else | 41 |

**67 facts are about the system, not about Larry.** Facts about Mortimer's
own configuration are re-derivable from the repo and are competing for
the same 30 slots as durable facts about the user. That is the structural
reason real preferences fall out.

### 1.3 Two of the three layers already exist — under other names

| Larry's concept | Today | Verdict |
| --- | --- | --- |
| **Memory** — context + preferences | `memories` table, `jarvis/memory.py` | Exists; overflowing; no consolidation |
| **Skills** — how a task got done, reusable | `procedures` table (25 rows), `jarvis/procedures.py` | **Exists**, named "procedures" |
| **Workflows** — how a task *should* be done | — | **Does not exist** |

The naming is the confusion. `jarvis/procedures.py` is precisely Larry's
"skills": a procedure is a hint learned from a successful run, matched
against a new task by token overlap and injected as a system message.
CLAUDE.md forbids calling it a "skill" because **`skill` already means an
MCP server** in this codebase (`mcp_servers/*/skill.yaml`). So the word
Larry reaches for is taken, and the thing he wants already exists under a
word he never uses.

### 1.4 What "workflows" would add that neither layer covers

A procedure is **descriptive** — "last time this worked, here's what
happened." It is explicitly a hint, never a replay, and it is learned
automatically from successful runs.

A workflow is **prescriptive** — "this is how I want this kind of task
done, and here's what done looks like." It is authored by Larry, not
learned, and it carries acceptance criteria. Nothing in the system holds
that today: the plan→approve→implement→verify discipline Larry uses on
every change lives entirely in his head and in prose inside plan docs.

---

## 1.5 Golden Rules — why stating a rule wasn't enough (IMPLEMENTED 2026-08-18)

Larry, 2026-08-18: *"I think we need to add Golden Rules to the interface
with the first being: don't lie or fabricate, only respond with factual
verifiable responses."*

**The rule already existed — three times — and fired correctly anyway.**
That is the finding worth keeping.

Verbatim, as they stood before this change:

> **Rule 3:** …If a specialist returns FAILED, say so plainly in one
> sentence **and suggest the fix.**
>
> **Rule 11:** When a delegation returns FAILED, **report the sub-agent's
> stated reason** to the user…
>
> **D6/D7** (every sub-agent prompt): …do not invent remediation steps…

The input those rules received on 2026-08-18 was
`"FAILED: the task could not be completed."` — no reason, no fix. So the
prompt instructed the model to report a reason that did not exist and
suggest a fix it had no basis for. It complied, by generating the most
plausible candidate: *"the codebase access is blocked right now."*

**This was rule-following against an empty input, not rule-breaking.** The
prompt was the proximate cause.

Four compounding conditions, all measured:

| Condition | Evidence |
| --- | --- |
| The rules mandated speculation | Rule 3's "and suggest the fix" |
| No sanctioned way to say "I don't know" | No such rule existed anywhere |
| Small model, large prompt | Supervisor is `claude-haiku-4-5`; 4,631-char prompt, 11 numbered rules, +1,623 chars of addenda, plus memory context |
| Honesty enforced at the tool layer, not the last mile | `classify_tool_result`, all-failed override, pending-draft backstop all live inside the sub-agent loop; the Supervisor's narration to the user passes through no mechanical check |

### What was implemented

- **`GOLDEN_RULES`** in `jarvis/prompts.py`, prepended to `SUPERVISOR_PROMPT`
  by concatenation at definition time (not a format placeholder — static
  text, and concatenation makes it impossible to omit at a call site).
  Three rules: never state unobserved things as fact and "I don't know
  why" is always acceptable; never guess at a cause (access, permissions,
  credentials, connectivity, configuration) the specialist did not state;
  never claim a capability you lack or lack one the specialists cover.
- **Rule 3 no longer mandates a fix.** "and suggest the fix" became
  "Suggest a fix ONLY if the specialist's own result named one."
- **Rule 11 authorizes an absent reason** — "it didn't finish and didn't
  say why" is now an explicitly correct answer.
- These **consolidate** the scattered language rather than adding a
  twelfth instruction; rules 3 and 11 now defer to Golden Rule 1.
- Each rule names its mechanical backstop in a comment above the block.

### The principle to carry forward

**A rule without a backstop is a wish.** Golden Rules earn their place by
being few, first, and paired with enforcement — not by being emphatic.
The backstop that actually fixed the 2026-08-18 incident was mechanical:
`ITERATIONS_EXHAUSTED_MESSAGE` gave the failure a real reason, so there
was nothing left to invent.

### Open decisions

| # | Decision | Recommendation |
| --- | --- | --- |
| G1 | Move Golden Rules to `config/golden_rules.yaml` so they are editable without a code change | Only with a self-edit **deny-list** entry — Mortimer must never be able to rewrite its own governing rules, same rule already applied to the vault and the model registry |
| G2 | Show the Golden Rules in the console | Reasonable with K5's memory visibility work; read-only display first |
| G3 | Mechanically check Supervisor replies claiming access/permission failure against the run's actual tool results | Defer — the vacuum is closed at the source; revisit only if fabrication recurs |
| G4 | Extend Golden Rules to sub-agent prompts too | Likely yes, but measure first: sub-agents already carry D6/D7 and their prompts are shorter |

---

## 2. The proposed framework

Three layers, each with one owner, one storage shape, one lifecycle.

```
KNOWLEDGE
├── Memory     — what is true about Larry and his world   (facts; durable)
├── Skills     — what has worked before                   (learned; evidential)
└── Workflows  — how work should be done, and when it's done  (authored; normative)
```

### K1 — Memory becomes tiered, not just capped

The single flat pool is the root defect. Split by **durability**, not by
topic:

| Tier | Contents | Cap | Eviction |
| --- | --- | --- | --- |
| `identity` | Name, location, role, hard constraints | never dropped | manual only |
| `preference` | How Larry wants to be worked with | generous | consolidated, not evicted |
| `project` | Current work, goals, live context | moderate | ages out |
| `system` | Facts about Mortimer's own config | **excluded from context by default** | prunable wholesale |

`system` is the big win: 67 of 180 rows leave the competition immediately,
and they are the most re-derivable facts in the store — the repo already
says what `config/agents.yaml` contains.

*Open decision D1:* whether `kind` gains these values or a new `tier`
column is added (migration either way).

### K2 — Consolidation, so the store stops growing monotonically

Today a fact is written and never revisited; three phrasings of one
preference all persist and all compete. Add a periodic consolidation pass
(same fire-and-forget shape as `learn_from_run`): cluster near-duplicate
facts within a tier, ask one small model to merge each cluster into a
single canonical fact, keep provenance.

Two rules this must respect, both learned the hard way elsewhere in this
codebase:
- Consolidation **rewrites**, never silently deletes — the merged fact
  carries the ids it replaced, and the originals are archived not dropped.
- It runs off the live path, like the council's shadow judging (V7).

*Open decision D2:* automatic on a schedule, or a manual
`python -m jarvis.memory --consolidate` Larry runs and reviews. Given the
data loss earlier today, manual-first is the conservative read.

### K3 — Skills: keep the machinery, fix the vocabulary

Do **not** rebuild procedures. They work, they are tested, and 25 have
accumulated. The change is naming and visibility:

- Keep the internal identifier `procedures` (tables, module, FTS index)
  to avoid a rename that touches migrations for zero functional gain.
- Introduce **"skill"** as the *user-facing* word in prompts, the console,
  and voice — the way "Mortimer" is user-facing while `jarvis` is
  internal. This is an established pattern in this repo, not a new one.
- Resolve the collision explicitly: MCP servers are **"tool servers"** in
  user-facing language. `skill.yaml` filenames stay as they are.

*Open decision D3:* Larry may prefer the opposite — keep saying
"procedure" out loud and drop "skill" entirely. Cheaper, and avoids
overloading a word that already has a meaning in the repo. Recommend
deciding this before any prompt text changes.

### K4 — Workflows: the genuinely new layer

A workflow is an authored, named recipe with acceptance criteria.

```yaml
# config/workflows/plan-first-change.yaml   (shape illustrative)
name: plan-first-change
when: "any implementation-scale change to Mortimer itself"
steps:
  - Write a plan document under docs/plans/
  - Get Larry's explicit approval before writing code
  - Implement via selfedit_start, never inline drafting
  - Run the full suite; report failures honestly
done_when:
  - "A plan doc exists and was approved"
  - "pytest tests/unit tests/integration is green"
  - "Larry has been told what still needs his machine"
```

Design constraints, inherited from how this codebase already works:

1. **Authored, not learned.** Workflows are config, edited by Larry (or
   drafted by the plan pathway and approved). Never auto-created from
   runs — that is what skills are for.
2. **A workflow is guidance, not a state machine.** Same rule procedures
   live under: injected as prompt context when matched, never a code path
   that executes steps. Building an executor is a much larger project and
   is explicitly out of scope here.
3. **Matching is explicit before it is clever.** v1 matches on the `when:`
   text and an optional agent list. No embeddings.
4. `done_when` is what makes it more than a note: it gives the agent a
   self-check before reporting completion, and gives Larry a concrete
   thing to point at when work comes back wrong.

*Open decision D4:* where workflows are injected — Supervisor prompt
(shapes routing), sub-agent prompt (shapes execution), or both. Sub-agent
is the safer v1: the Supervisor prompt is already long and its budget is
the voice loop's latency.

### K5 — Make the layers visible

The Memory tab currently shows a flat list. Three sections, one per layer,
each with counts, and — critically — **a visible indicator when facts are
being dropped from context**. The 8%-of-180 situation should never again
be discoverable only by reading a log line.

---

## 3. What this fixes, traced to evidence

| Symptom | Layer | Mechanism |
| --- | --- | --- |
| Mortimer forgets stated preferences | K1 + K2 | Preferences stop competing with 67 system facts; duplicates merge |
| Memory grows without bound | K2 | Consolidation makes the store converge |
| "Is that memory or a skill?" | K3 | One word per concept, decided |
| Repeating how work should be done | K4 | Workflows hold it, `done_when` checks it |
| Silent context truncation | K5 | Drops become visible |

---

## 4. Scope boundaries

**In scope:** memory tiering, consolidation, vocabulary decision, the
workflow concept as injected guidance, console visibility.

**Explicitly out of scope:**
- A workflow *executor*. Workflows are prompt context in v1.
- Embeddings/vector search. The FTS + token-overlap matcher is adequate
  and has a calibration tool (`--calibrate`); adding a vector store is a
  separate decision with its own dependency cost.
- Renaming the `procedures` table or module.
- Touching the Developer sub-agent's identity.

---

## 5. Open decisions for Larry

| # | Decision | Recommendation |
| --- | --- | --- |
| D1 | New `tier` column vs. reusing `kind` | New column; `kind` already means fact/summary |
| D2 | Consolidation automatic or manual | Manual first (`--consolidate`), automate once trusted |
| D3 | Say "skill" or keep "procedure" | Decide before prompt edits; "procedure" is cheaper |
| D4 | Where workflows inject | Sub-agent prompt for v1 |
| D5 | Prune the 67 `system` facts outright, or tier and hide them | Tier first, prune after review |

---

## 6. Suggested sequencing

1. **Triage** (no schema change): review and dedupe the existing 180 by
   hand or with a one-off script. Immediate relief.
2. **K1 tiering** + migration. Preferences stop being evicted.
3. **K2 consolidation**, manual command first.
4. **K3 vocabulary**, once D3 is decided.
5. **K4 workflows**, the only genuinely new build.
6. **K5 console**, last — it displays whatever the layers settle into.

Steps 1–2 deliver most of the value and are independently useful if the
rest is never built.

---

## 7. Approval

Not approved. Larry decides D1–D5 and whether the sequencing above is the
right order, before any code is written.
