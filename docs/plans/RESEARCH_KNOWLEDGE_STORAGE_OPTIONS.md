# Storing research in the knowledge base — options for Larry's decision

**Status:** DECISION DOC, 2026-09-03. Not an implementation plan; one of
the options below becomes a plan once Larry picks.
**Origin:** Larry: *"I am thinking an extension of the memory graph could
be a knowledge graph that adds any research data for any research we do
for later reference, thoughts?"* — and, after the first answer:
*"separately provide options on the right way to store research as part
of a knowledge base."*
**What is verified here vs. not:** everything about THIS repo is cited
`path:line`. The vault (`mortimer-vault`, a separate package serving
`127.0.0.1:8484`) is NOT a connected folder; its internals — how
`/neighbors` links are formed, the `type` vocabulary it enforces, whether
search is embedding- or FTS-based, what `flush_access` feeds — are
marked **[unverified]**. Connecting that folder resolves every such mark
in one pass and is the first step of whichever option is chosen.

---

## 1. The three stores that exist, and where research goes today

**Facts (`jarvis.memory`).** Short keyed lines
(`user.style.execution.direct`), tiered, rendered into the Supervisor's
cached prefix once per session — 71 facts / 9,818 chars as of today
(`logs/bot.log:388`). Everything here is paid for on every turn's cache
read and capped by tier (`MAX_PREFERENCE_FACTS`, `MAX_PROJECT_FACTS`,
`MAX_CONTEXT_CHARS`, `jarvis/memory.py`). Phase 4 Stage B (unbuilt,
gated) would derive a graph over these keys.

**Curated documents (the vault KB via `mcp_servers/mcp_kb`).** Long-form
markdown, "searched on demand, never auto-injected"
(`mcp_servers/mcp_kb/logic.py:5-7`). Contract as seen from this repo:
`kb_write(type, body, tags, confidence, source_sessions, id?,
expected_hash?, previous_excerpt?)` (`logic.py:103-136`, optimistic
concurrency on update), `kb_search(query, k?, type?, tags?,
confidence_min?)` returning ranked snippets with ids (`:86-96`),
`kb_read(id)`, `kb_neighbors(id)` "documents linked to or from the given
document id" (`:138-140`), `kb_delete` (capture-type only), `kb_flush`
(access-time bookkeeping). Bodies are capped — `kb_digest.py:45`
splits above 3,800 chars because the vault rejects at 4,000
**[vault-side limit; the number is this repo's constant]**. Only the READ
tools are voice-exposed, by design (`mcp_kb/server.py:4-12`, W1); writes
are plain Python calls. Today's only writer: `jarvis/kb_digest.py` at
session end, `type="session-digest"`, `tags=["digest"]`,
`confidence="medium"`, with a Haiku "SKIP if trivial" gate (`:34-41`, `:139`).

**Run log (`jarvis/runlog`, `logs/agents/<date>/<run_id>.jsonl`).** Every
sub-agent run, verbatim: `run_start` (task), each `tool_call` /
`tool_result` (for `web_search`: `{"results":[{"title","url","snippet"}]}`),
`run_end.reply` (the specialist's synthesized answer). Verified on today's
run `95571392…` — two `web_search` results with titles and URLs, and a
reply beginning `**Overview: 350 years of sperm science**`. This is
already durable, already complete, and not searchable as knowledge.

**Where research lands today.**
- Analyst lookups (voice: "tell me about X"): spoken by the Supervisor in
  ≤ 40 words, then nothing. The full answer and every URL sit in the run
  log and are never looked at again.
- The research pathway (site comparison, `POST /api/research/*`):
  `research_save` writes `docs/research/<slug>.md` in the repo through
  the draft-gated `repo_write_file` (`jarvis/admin/server.py:1195-1239`),
  with a provenance footer. `docs/research/` does not exist yet — no
  comparison has ever been saved. Nothing writes it to the KB.

**Why not the memory graph (answering the original question).** The facts
layer is the one store whose every byte is in the cached prefix. A
research finding is 500–4,000 characters with sources; the prefix budget
was raised this week to fit 71 one-line facts. Research there either
inflates the per-turn cache read or is dropped by the tier cap — the
exact failure Stage A instruments. The KB is the layer built for "long,
occasionally relevant, retrieved on demand," and it already has
adjacency. The idea is right; the layer is the KB.

## 2. What "later reference" has to be able to answer

The options are judged against these five queries, all plausible by
voice:

- Q1 *"What did we find about X?"* — recall by topic.
- Q2 *"Where did that come from?"* — sources for a finding.
- Q3 *"Have we looked into this before?"* — dedupe / prior-work check
  before spending a delegation.
- Q4 *"What else is related to X?"* — neighbourhood, the graph question.
- Q5 *"What did we research last week?"* — recency listing.

## 3. Options

### Option A — Write a `research-note` from the run log, deterministically, at run end

**What.** When an analyst run ends and it called `web_search` at least
once, build a KB document with NO LLM call: title = the task, body = the
analyst's `run_end.reply` + a `Sources` section listing every
`tool_result` URL/title (de-duplicated), `type="research-note"`,
`tags=["research", "analyst", <tool names used>]`, `confidence="medium"`,
`source_sessions=[session_id]`. Hook: the run-end path in
`jarvis/agents/base.py` (`subagent_done`, `:768`) or the delegate wrapper
— the same place the run log's `run_end` is written, so the reply and
tool results are in hand. The formal research pathway does the same in
`research_save` alongside the repo file (one extra `kb_write`).

**Gate (deterministic).** Write when `web_search` (or the pathway) was
used AND (≥ 2 tool calls OR reply ≥ 400 chars). One `web_search` with a
short reply is a lookup, not research. Both numbers are knobs.

**Answers.** Q1 yes (`kb_search type=research-note`). Q2 yes — the URLs
are in the body verbatim. Q3 yes (search before delegating; that is a
Supervisor-prompt rule plus a librarian call, cheap). Q5 yes (search
sorted by date, or tags by month). **Q4 only as well as the vault's
`/neighbors` already does it [unverified].**

**Costs.** Build: small — one function, one hook, tests; a `kb_write` per
qualifying run (HTTP to localhost). Run: $0 in LLM; storage ≈ 1–4 KB per
note. Today's session would have produced two notes (sperm history,
Spartanburg history) and skipped the weather.

**Doesn't do.** No synthesis across runs; the note is one specialist's
answer, in that specialist's words (markdown, since the analyst writes
it — fine for a KB body). Trivia that clears the gate is kept
(the vault's access bookkeeping may age it out **[unverified]**).

### Option B — Curate research from the session at teardown, by extending `kb_digest`

**What.** `kb_digest` already reads the transcript at session end and
asks Haiku for a digest or SKIP. Add a second output: research findings
in the session as separate `research-note` documents (question, answer,
what the user did with it). To carry sources, the digest input must
also include the session's analyst run payloads (URLs are not in the
transcript — the Supervisor speaks a summary).

**Answers.** Q1, Q3, Q5 yes. Q2 only with the run-log join (otherwise the
note has no URLs). Q4 as Option A.

**Costs.** Build: medium — prompt work, the run-log join, output parsing
into N documents, tests against the SKIP path. Run: one extra Haiku call
per session with the run payloads in context (a `web_search` result is
1–3K tokens; three lookups ≈ 5–9K input tokens ≈ $0.01/session) —
modest, but it is the only option with a per-session LLM bill.

**Doesn't do.** Anything deterministic: which findings get kept is the
model's call, so a note can be missing or paraphrased. Loses the
specialist's exact wording.

**Relative to A:** better prose, worse provenance and reproducibility,
costs money. Reasonable as a LATER layer over A (a weekly "what did we
learn" digest), not as the primary write path.

### Option C — Index the run log itself; write nothing new

**What.** Point the vault (or a local FTS table in `jarvis.db`) at
`logs/agents/**/*.jsonl` so tool results and replies are searchable as
they are.

**Answers.** Q2 yes (raw URLs). Q1 poorly — hits are chunks of Tavily
output, not answers. Q3/Q5 poorly (every run is a "research", including
weather). Q4 no.

**Costs.** Build: depends on the vault accepting a folder source
**[unverified — a vault change if not]**; the 4,000-char body cap means
splitting every payload. Run: $0.

**Doesn't do.** Turn raw material into knowledge. This is the "we kept
everything" option; it optimises for never losing a URL at the price of
never finding an answer. **Rejected**, but noted because it is the
cheapest thing that could be built and someone will suggest it.

### Option D — Option A plus deliberate linking (the "knowledge graph" shape)

**What.** Same writes as A, plus at write time: (1) `kb_search` the note's
own title against `type=research-note`; link the top-k prior notes
(k = 3), (2) link the session digest that will be written at teardown
(`source_sessions` already carries the session id — whether the vault
turns that into an edge is **[unverified]**), (3) once Phase 4 Stage B
exists, tag the note with the derived entity paths it mentions
(`project.weather`, …) so a fact and its research share a key. How a
link is expressed depends on the vault's model **[unverified]**: if links
are `[[id]]` wikilinks in the body, the writer appends a `Related` line;
if tag-based, shared topic tags; if explicit edges, a field this repo's
client does not expose yet.

**Answers.** Q1–Q3, Q5 as A. **Q4 yes** — `kb_neighbors(note)` walks to
prior notes on the topic, the session it came from, and (later) the
facts it touches.

**Costs.** Build: A + one search per write + the link encoding (small
once the vault model is known); Stage B coupling only if entity links are
wanted. Run: one extra localhost search per note; $0 LLM.

**Doesn't do.** Pay off until there is volume. At the current rate (5
completed council rounds in a month; two research-grade lookups in
today's session) a topic will have a second note to link to in weeks,
not days. The graph is worth building when Q4 has been asked and search
alone failed to answer it — the same evidence gate Stage B uses.

### Option E — Repo files only (status quo for the pathway), indexed by the vault

**What.** Keep `docs/research/*.md` as the research store; have the
vault index that folder **[unverified whether it indexes folders; the
"project documents" Mortimer describes suggest it does]**.

**Answers.** For the formal pathway only: Q1, Q2, Q5 yes; Q3/Q4 as the
vault allows. Analyst lookups — the common case — are not covered at all.

**Costs.** Possibly zero in this repo. **Doesn't do:** the thing that
actually happened today (two analyst lookups, spoken and gone). Fine as a
complement to A for the pathway's long comparisons; not a solution alone.

## 4. Comparison

| | A run-end note | B digest-time curation | C index run log | D = A + links | E repo files |
|---|---|---|---|---|---|
| Q1 recall by topic | yes | yes | weak | yes | pathway only |
| Q2 sources | yes, verbatim | only with run-log join | yes, raw | yes | yes |
| Q3 prior-work check | yes | yes | weak | yes | pathway only |
| Q4 related | vault default [unv.] | vault default [unv.] | no | **yes** | vault default |
| Q5 recency | yes | yes | weak | yes | pathway only |
| LLM cost per session | $0 | ≈ $0.01 | $0 | $0 | $0 |
| Deterministic | yes | no | yes | yes | yes |
| Depends on vault internals | body cap only | body cap only | folder source | link model | folder source |
| Covers analyst lookups | yes | yes | yes | yes | **no** |
| Build size | S | M | S–M | S + unknown | 0–S |

## 5. Recommendation

**A now, E alongside it for the pathway, D when Q4 earns it, B never as
the primary path.**

Concretely: (1) connect `mortimer-vault` so the `[unverified]` marks
resolve — chiefly the link model and whether `source_sessions` is an
edge; (2) plan and build Option A with the deterministic gate and the
`research-note` type, plus the one-line `kb_write` in `research_save`;
(3) add one Supervisor rule — before delegating a research question,
have the librarian `kb_search type=research-note` and, on a hit newer
than 30 days, offer it before spending the delegation (this is Q3, and
it is the only place research storage SAVES money rather than costing
it); (4) hold D behind the Stage B gate pattern: build linking the first
time Larry asks a Q4-shaped question and `kb_search` alone does not
answer it.

**Structured disagreement with the original framing, restated for the
record.** *Reason:* research is long-form with provenance; the memory
layer is short keyed facts in a per-turn cached prefix. *Alternative:*
the KB — already on-demand, already has adjacency, already has a writer
and a content scanner. *Downside of the memory-graph route:* prefix bloat
or tier-cap loss, plus building a second graph on top of an unbuilt
first one. [certain on the layer mismatch; the vault's link model is the
one unknown that would change D's shape, not A's.]

## 6. Open questions for Larry

1. Gate thresholds for A — ≥ 2 tool calls OR ≥ 400-char reply. Too loose
   keeps sports scores; too tight drops one-search answers that were
   worth keeping. Pick, or accept these and tune from what shows up.
2. Should a research-note ever be spoken unprompted ("we looked into this
   on Tuesday")? Recommendation: only via the Q3 rule, never as an
   interjection.
3. Does the vault index a folder today? (Decides E's cost, and whether C
   is even possible — worth knowing even though C is rejected.)
