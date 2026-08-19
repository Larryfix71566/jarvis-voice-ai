# Graph engineering — does it apply to Mortimer?

**Reviewed:** two X posts Larry sent 2026-08-18, each fronting a video and
linking a long-form article that carries the actual method.

- [Anatoli Kopadze, post](https://x.com/AnatoliKopadze/status/2082887253735665905)
  → article: [Graph Engineering explained: what it is, when to use it and when not to](https://x.com/AnatoliKopadze/article/2080668775796314331)
  (video: 40-min talk by the Head of Claude Code — *"85% of our engineers are
  running dozens or hundreds of agents. The way you do it is graph
  engineering."*)
- [Codez, post](https://x.com/0xCodez/status/2079234800766816633)
  → article: [Graph Engineering with Claude: 14-Step roadmap from 0 to graph architect](https://x.com/0xCodez/article/2079165300625330317)
  (video: 1-hour Andrew Ng course on agentic knowledge graphs)

**Scope caveat, stated up front:** this review is of the two ARTICLES, read
in full. The videos themselves were not watched — no transcript was
available. If either video contains material the article omits, this review
does not cover it.

---

## 1. What graph engineering actually says

Both articles teach the same method, in nearly the same words.

**The vocabulary.** A *node* is one bounded job — one agent, one input, one
output. An *edge* is a real data dependency: node A's output feeds node B's
input. Nodes think; edges carry results.

**The fake-edge test** (the core diagnostic). For every "and then" in a
workflow, ask: *does the next step actually read the previous step's
output?* If not, there is no edge — the wait is wasted and the two jobs can
run at once. Both authors claim two or three fake edges hide in almost any
workflow.

**Your linear script is a degenerate graph** — a single unbranching chain,
one arrow in and one out per node. It runs correctly, slowly, and fragilely:
40 sequential steps have 40 points of failure and the latency of all 40
summed, when the real dependencies usually number three to five.

**The diamond** — the one topology that matters: *fan out → reduce →
synthesize*. Split the job, work in parallel, compress with plain code, let
one agent write the answer. Claimed to be the skeleton behind market scans,
code reviews, research reports, and Claude's own `/deep-research`.

**Verification is the whole trick.** Never let the agent that did the work
check the work — models miss most of their own mistakes. The verifier needs
a **clean context**: *"a graph of agents sharing one context is just a
single loop in a costume."* Split checking across distinct lenses
(correctness, currency, source reality) because three different lenses catch
what ten identical ones miss.

**Cost, honestly stated by the authors.** The Bun runtime port — ~535k lines
translated in ~11 days, ~50 workflows, up to 64 concurrent agents — cost
roughly **$165,000** in usage and drew real criticism about whether that
much AI-written code can be safely reviewed.

---

## 2. What Mortimer already has

The single most useful finding: **Mortimer independently implements most of
the hard parts, under different names.** These are not gaps.

| Article concept | Mortimer's existing implementation |
| --- | --- |
| The diamond (fan out → reduce → synthesize) | `jarvis/council/` — proposers fan out, judges score, `select_winner` merges deterministically |
| Worker and verifier must not share context | The council's disjoint proposer/judge rule, enforced per-member by `resolve_members`'s `exclude` |
| Perspective-diverse verification | `PLAN_JUDGE_PROMPT` / `SCOPE_JUDGE_PROMPT` lenses; the shadow-judge tier sampling |
| Tier the models across nodes | Part A model discipline — `model_profile:` per agent, one registry, voice model as dispatcher only |
| Silent node failure must be flagged, not absorbed | `jarvis/toolresult.py`; abstentions recorded explicitly, never silently dropped |
| Isolate nodes so one failure can't poison the graph | `AppWorkspace` git worktrees; `parallel` failure containment |
| **Anchors** — *"some rules must be frozen, the ones an optimizer would be tempted to weaken"* | The self-edit allowlist, validation gates, `config/skills.yaml`, the vault deny-list. "A rule without a backstop is a wish." |

The anchors section is worth re-reading in full. It describes a graph where
every node checks another node, every check passes, and nothing is actually
verified — *"everything is consistent, nothing is verified... it fails
exactly like the single loop did, just later, more expensively, and with far
more green lights on the way down."* That is the same failure Mortimer hit
on 2026-08-18, when a run with all-green tools reported a fabricated access
error. Same disease, arrived at from the opposite direction.

---

## 3. The one real gap: fake edges in the sub-agent loop

**This is the recommendation.** It points at a defect already measured, not
a hypothetical.

Runs `54b62f69` and `9f0684e2` read 9–11 files with every tool call
SUCCEEDING, one file per tool round, until `MAX_TOOL_ITERATIONS` ran out.
Reading eleven independent files is eleven nodes with **zero edges between
them** — a textbook fan-out that `SubAgent._loop` executes as a chain.

Raising `max_iterations` to 15 (already done) treats the symptom. The
fake-edge test names the cause.

Two versions, ascending ambition:

**3a. Concurrent tool batches (cheap).** When the model emits several tool
calls in one assistant turn, execute them with `asyncio.gather` instead of
sequentially. Same iteration count, less wall-clock.

- Caveat [likely]: concurrent calls to the *same* MCP stdio server may
  serialize at the transport layer; calls across different servers won't.
  Measure before assuming a win.
- The D3 failure-constraint injection is already batch-safe (F1), so the
  honesty machinery survives this change.

**3b. Batched reads (the real fix).** A `read_files` tool on `mcp_repo`
taking N paths and returning N results in ONE iteration. This attacks budget
exhaustion directly rather than by raising the ceiling again — the developer
agent is the one agent that reads its way to an answer, and it currently
spends one of its 15 rounds per file.

**3c. Parallel delegation (check first, may already work).** "What's the
weather and what's my next reminder" is two delegations with no edge between
them. Worth verifying whether the pipeline runs concurrent `delegate_task`
calls when the Supervisor emits them together. If it serializes, that is a
direct voice-latency win.

**If any of 3a–3c gets built, ship the fan-in counting rule with it from day
one:** every merge counts its inputs against the number expected and flags
the gap, rather than quietly proceeding on half the data. That is the graph
version of the tool-result honesty discipline, and the articles list its
absence ("silent node failure") as one of three ways graphs break.

---

## 4. What to reject, and why

The articles' own "when NOT to use a graph" section reads like a description
of Mortimer's use case. Kopadze, §8:

- *"The task is small or isolated... the coordination is pure overhead."*
- *"You want to approve every step. A graph's whole point is running wide
  without you, so a tight leash works against it."*
- *"You do not know yet what you are looking for. Exploratory work wants one
  agent you can steer, not a fleet locked into a plan."*
- *"The tell is the fake-edge test. If you cannot find two jobs with no edge
  between them, there is no graph to build. It is a loop, and a loop is fine."*

Mortimer's confirmation gates are a **design decision, not a limitation**,
and this is the article conceding the point.

**Reject specifically:**

- **Self-routing / dynamic workflows** (Codez step 14: describe an objective,
  the model writes its own orchestration script and spawns a fleet). This
  directly contradicts the model-discipline rule that the voice model is a
  dispatcher and never a design model, and the council's founding rule that
  convening is never predictive. Mortimer's routing lives in
  `config/agents.yaml` on purpose — a reviewable data file, not a script the
  model authors at runtime.
- **Fleet-scale anything.** ~$165k for the Bun port is the articles' own
  argument against this for a personal assistant. Kopadze: *"the heavy
  version is for teams with the budget, the caps, and the monitoring."*
- **A graph engine as a component.** There is nothing to build. The two
  patterns worth having (diamond, clean-context verification) already exist
  as the council.

---

## 5. Bottom line

Don't build a graph engine. Steal the **fake-edge test** and apply it to the
two places Mortimer provably runs fake edges — sub-agent tool batches
(§3a/3b) and multi-delegation turns (§3c). Everything else in these articles
that carries judgment, Mortimer already implements under different names,
and the parts it doesn't implement are the parts its design deliberately
rejects.

Kopadze's own closing advice is the right size of takeaway: *"learn the
fake-edge test tonight. Draw your current workflow, find the edges that
carry no data, and delete them."*

---

*Review written 2026-08-18 in a Cowork session, not through Mortimer's own
planning pathway — so it carries no planner attribution footer. The two
source articles were read in full via browser; the videos were not watched.*
