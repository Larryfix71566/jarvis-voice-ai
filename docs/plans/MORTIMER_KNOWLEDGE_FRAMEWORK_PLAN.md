# Mortimer knowledge framework — memory, procedures, skills, workflows

**Status:** APPROVED 2026-08-18. IMPLEMENTED: §1.5 Golden Rules, K1 tiering,
K2 consolidation + volatile firewall, K6 conversion layer. NOT YET BUILT:
K3 skills, K4 workflows, K5 console. Open decisions D3/D4/D6/D7/D8/D9.

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

## 2. The framework — four layers

Larry proposed three categories. Implementation found a fourth already
running: `procedures`. Rather than force it into "skills", it gets its
own layer — because **the four differ in trust, not just in content**,
and collapsing any two forces one trust model onto both.

```
KNOWLEDGE
├── Memory      what is true                observed/stated   declarative
├── Procedures  what worked before          learned from runs evidential
├── Skills      how to do a thing           authored/imported capability
└── Workflows   how it SHOULD be done       authored by Larry normative
```

| | Memory | Procedures | Skills | Workflows |
| --- | --- | --- | --- | --- |
| Origin | extraction, `remember` | `learn_from_run` | authored or imported | Larry |
| Storage | `memories` rows | `procedures` rows | `SKILL.md` folders | config files |
| Trust | asserted | earned (counters) | assumed correct | binding |
| Lifecycle | consolidated | promote/deprecate | versioned files | edited |
| Portable | no | no | **yes** | no |
| Failure mode | stale fact | misleading hint | bad instruction | wrong policy |

### Why procedures must not merge into skills

A procedure is **evidence**: `PROCEDURE_PROMOTE_AFTER` net successes make
it `active`, accumulating failures make it `deprecated`, and it is
explicitly a hint — never a replay. A skill is an **instruction**:
authored once, assumed correct, versioned as a file, portable to another
machine or another agent.

Merge them and one trust model has to win. If authored skills must earn
trust through counters, importing an ecosystem skill becomes useless. If
learned procedures are treated as authoritative, a stale hint becomes a
confident wrong answer — the exact failure §1.5 exists to prevent.

Keeping them separate also frees the word "skill" to mean precisely what
the Agent Skills standard means, with no local redefinition.

### The promotion path (deferred, not designed here)

A procedure with a strong success record is a **candidate** to be
promoted into an authored skill: evidence graduating into capability,
with Larry approving each graduation. Explicitly out of scope for v1 —
noted so it is not accidentally designed against.

---

## 3. K1 — Memory tiering  *(IMPLEMENTED 2026-08-18)*

Facts carry a `tier` classified by DURABILITY, not topic:

| Tier | Cap | Behaviour |
| --- | --- | --- |
| `identity` | none | never dropped; exempt from `MAX_CONTEXT_CHARS` |
| `preference` | `MAX_PREFERENCE_FACTS` | consolidated, not evicted |
| `project` | `MAX_PROJECT_FACTS` | ages out |
| `system` | — | **excluded from the prompt entirely** |

Migration `0012_memory_tiers` backfilled by key prefix; `infer_tier()`
classifies on write and must stay in agreement with it. Both share a
conservative bias: anything unrecognized becomes `project`, never
`identity` (never evicted) and never `system` (hidden).

**Measured result on Larry's store:** 68 system facts stopped competing;
identity is guaranteed. But only ~17 facts now reach the Supervisor —
**tiering decided who competes, not how much room exists.** The
`MAX_CONTEXT_CHARS` budget is now the binding constraint, which is what
makes K2 load-bearing rather than optional.

## 4. K2 — Consolidation  *(IMPLEMENTED 2026-08-18)*

`python -m jarvis.consolidate` REPORTS duplicate clusters and writes
nothing; `--drop <key>...` is the only writing verb. No "merge
everything" command exists, by design.

Three rules enforced by construction, each from a real failure:

1. **Never merge across tiers**; `identity` is excluded entirely.
2. **Clusters are cliques, not connected components.** Transitive
   closure chained 18 unrelated facts on the real store.
3. **`MIN_SHARED_TOKENS = 2`.** The symmetric scorer divides by the
   smaller token set, so a one-token fact matched anything containing
   that word at 1.0. A key-similarity guard was tried first and rejected
   — it also blocked the main use case.

Plus `mixed_content_warning()`: a fact whose CONTENT covers a topic its
KEY doesn't (`user.location` carrying a Fahrenheit preference) is flagged
before any merge.

**Also implemented:** a volatile-state firewall at the write point.
Transient repo snapshots ("19 commits ahead", "47 uncommitted files") are
rejected — Larry: *"these were never the intent of the memory function
in the first place."* Patterns require a countable noun next to the
number, after the first version deleted "Phase 1 committed" as if it
were a snapshot.

---

## 5. K3 — Skills, mirroring the Agent Skills standard

Larry: *"I want our implementation of Skills to mirror what Claude does
for skills so that we could leverage that repository as well."*

Agent Skills became an **open standard on 2025-12-18** (agentskills.io),
supported by 40+ platforms. Mortimer should consume that format
directly rather than invent a parallel one.

### The format

- A folder containing **`SKILL.md`**: YAML frontmatter + Markdown body.
- Required frontmatter: **`name`** (≤64 chars, lowercase/digits/hyphens,
  no XML tags, cannot contain "anthropic"/"claude") and **`description`**
  (≤1024 chars). Optional: `license`, `allowed-tools`, `metadata`,
  `compatibility`.
- Optional sibling folders: `scripts/`, `references/`, `assets/`.
- **Progressive disclosure, three tiers:** name+description at startup
  (~100 tokens each), full body on activation (<5k tokens), reference
  files only on demand.

### Why the standard fits Mortimer specifically

Progressive disclosure solves a problem Mortimer already has. The
Supervisor prompt is 4,631 chars plus 1,623 of addenda plus memory
context, on `claude-haiku-4-5`. A layer costing ~100 tokens per skill
until activated is the right shape for a small dispatcher — and it is
a better design than anything invented locally would have been.

### Security: scripts are the real decision

Skills may bundle executable `scripts/`. Importing a community skill and
running its code is arbitrary code execution from the internet, on
Larry's machine. Consistent with the self-edit allowlist and vault
discipline, the recommendation is **instructions-only by default**:
`SKILL.md` + `references/` are read; `scripts/` is NOT executed without
an explicit per-skill opt-in recorded in config.

### Naming collision (unresolved)

`mcp_servers/*/skill.yaml` already claims the word against `SKILL.md`.
Options: rename MCP manifests to `server.yaml` (touches 11 servers and
`check_skills.py`), or accept the collision with loud documentation.

## 6. K4 — Workflows, seeded from existing memory

A workflow is authored, named, prescriptive, and carries acceptance
criteria — *how work should be done and what "done" means*.

**K4 is not a blank slate.** Scanning the live store found workflows
already accumulating in memory, misfiled as facts because there was
nowhere else to put them:

```
user.style.git_workflow        commit all uncommitted files together before
                               pushing; thorough review before merging to main
user.style.research_first      research alternatives before modifying code
project.mortimer.development.workflow
                               confirm commits explicitly before writes;
                               break large tasks into chunks
user.style.progress_visibility real-time status during execution; will not
                               accept silent waiting
user.location.rule             use CURRENT device location — never default
                               to home or work
```

So workflows are **extracted**, not authored from scratch — which is
also the highest-confidence seed data available, since Larry stated each
one himself.

Design constraints:

1. **Authored, never learned.** Auto-creation from runs is what
   procedures are for.
2. **Guidance, not a state machine.** Injected as prompt context on
   match; never a code path that executes steps. A workflow *executor*
   is explicitly out of scope.
3. **Matching is explicit before clever** — `when:` text plus an
   optional agent list. No embeddings.
4. **`done_when` is the point.** It gives an agent a self-check before
   claiming completion, and Larry something concrete to point at when
   work comes back wrong.

---

## 7. K6 — The conversion layer  *(NEW — Larry 2026-08-18)*

> *"add to the plan a conversion layer to get everything we currently
> have into the right bucket"*

Four layers are worthless if everything stays in bucket one. Today's
inventory, measured:

| Holding | Count | Belongs where |
| --- | --- | --- |
| Facts, `identity` | 6 | Memory (correct) |
| Facts, `preference` | 66 | Memory, minus workflows to extract |
| Facts, `project` | 29 | Memory, minus stale |
| Facts, `system` | 68 | mostly **delete** — re-derivable from the repo |
| Procedures, `active` | 5 | Procedures (correct) |
| Procedures, `candidate` | 20 | Procedures (correct) |
| Procedures, `task_tokens=''` | 14 | **unmatchable by design** — operator cleanup |

### K6.1 Classification pass (report-only)

One command, `python -m jarvis.classify`, that reads every fact and
proposes a destination: `keep-memory`, `-> workflow`, `-> skill`,
`delete-stale`, `needs-review`. Pure detection, same discipline as K2:
**it writes nothing.** Output is a review document Larry reads.

Signals, in order of reliability:
- **`-> workflow`**: imperative/normative language ("must", "always",
  "before", "prefers X before Y") in a `preference` fact that describes
  a PROCESS rather than a taste.
- **`delete-stale`**: `system` tier AND re-derivable from the repo
  (config, branch, file layout) — the volatile firewall already blocks
  the worst class at write time; this catches what predates it.
- **`-> skill`**: expected to be nearly empty. The scan found no
  reusable how-to knowledge in memory; that lives in procedures.
- **`needs-review`**: anything ambiguous. Ambiguity goes to a human,
  never to a default.

### K6.2 Extraction, one bucket at a time

Each destination gets its own explicit command, never a bulk "apply
all": `--extract-workflow <key>` writes a workflow file and archives the
source fact; `--drop <key>` already exists. The 2026-08-18 lesson stands
— a rewriter that is subtly wrong costs more than the mess it fixes.

### K6.3 Archive, never destroy

Converted facts are moved to an `archived` state carrying the id they
became, not deleted. Two reasons: the day's revert showed how expensive
losing content is, and a misclassification must be reversible without
reconstructing text from memory. (During today's cleanup a fact was
over-deleted and had to be restored from truncated console output — the
tail is still incomplete. That must not be the recovery story.)

### K6.4 Order matters

```
1. delete-stale        (biggest win, lowest risk — 68 system facts)
2. extract workflows   (seeds K4 with Larry's own stated rules)
3. consolidate         (K2 on what remains, now much smaller)
4. procedures cleanup  (drop the 14 permanently-unmatchable rows)
5. skills              (import/author — nothing to convert INTO it)
```

Steps 1–3 shrink the memory store by roughly half before any new layer
is built, which is the honest prerequisite: **do not build four buckets
and then pour an unsorted pile into the first one.**

---

## 8. Scope boundaries

**In scope:** four layers, tiering, consolidation, the Agent Skills
format, workflows as injected guidance, the conversion layer, console
visibility.

**Explicitly out of scope:**
- A workflow *executor*. Workflows are prompt context in v1.
- Executing skill `scripts/` without per-skill opt-in.
- Promoting procedures into skills (deferred, §2).
- Embeddings/vector search — the FTS + token-overlap matcher has a
  calibration tool and is adequate.
- Renaming the `procedures` table or module.
- The Developer sub-agent's identity.

## 9. Open decisions

| # | Decision | Recommendation |
| --- | --- | --- |
| D1 | ~~`tier` column vs `kind`~~ | **Resolved** — new column, migration 0012 |
| D2 | ~~Consolidation automatic or manual~~ | **Resolved** — manual (`--consolidate`) |
| D3 | Vocabulary: "procedures" + "skills" both, now that they are separate layers | Keep both; they are genuinely different things |
| D4 | Where workflows inject | Sub-agent prompt for v1 |
| D5 | ~~Prune vs tier the system facts~~ | **Resolved** — tiered; K6.1 proposes deletion |
| D6 | **`skill.yaml` vs `SKILL.md` collision** | Rename MCP manifests to `server.yaml` |
| D7 | **Skill `scripts/` execution** | Instructions-only by default; per-skill opt-in |
| D8 | **"Procedures" vs "Workflows" are close in English** | Consider Precedents / Policies — Larry speaks these aloud |
| D9 | Which agents get skills | Sub-agents first, same reasoning as D4 |
| G1–G4 | Golden Rules follow-ons (§1.5) | Unchanged |

## 10. Sequencing

| Step | Status |
| --- | --- |
| Golden Rules (§1.5) | **done** |
| K1 tiering | **done** |
| K2 consolidation + volatile firewall | **done** |
| **K6 conversion layer** | next — classification report first |
| K4 workflows | after K6.2 supplies the seeds |
| K3 skills | after D6/D7 are decided |
| K5 console visibility | last — it displays whatever settles |

## 11. Approval

§1.5, K1 and K2 are implemented. K3, K4, K5 and K6 are not approved;
D3, D4, D6, D7, D8 and D9 are open for Larry.
