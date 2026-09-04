# Review — MORTIMER_SECURITY_HARDENING_PLAN.md (T4a)

Reviewed against the repo snapshot `/home/claude/repo`, pipecat 1.4.0 at
`/usr/local/lib/python3.11/dist-packages/pipecat`, and `/home/claude/plans/BRIEF.md`.

Method: the detector in §5 Step 3, `build_child_env` in §5 Step 2a, the
`_read_in_source` regex in §7.2 and the real `Allowlist` matcher were extracted
verbatim and **executed** against inputs the plan did not choose — this repo's
own eval fixtures, its own prose, its own launch scripts, and adversarial
utterances. Sandbox at
`/tmp/claude-0/-home-claude/2ceba6d6-eac3-5a4d-9123-be345652e9e4/scratchpad/sec-review/`.

**Counts: 6 BLOCKER (F1–F6), 11 MAJOR (F7–F17), 6 MINOR (F18–F23).**

---

## Findings

### F1 — The flag is cleared on `UserStoppedSpeakingFrame`, which arrives *after* the turn's transcript and *before* every consumer; 9 of the 11 sites are inert [BLOCKER]

**Where:** §5 Step 6c; D-H4 lifecycle table row "User interrupts mid-turn";
§11 item 2. Repo: `jarvis/bot/transcript_log.py:115–118`.

**What the plan says:**

> ```python
> if isinstance(frame, UserStoppedSpeakingFrame):
>     …
>     # Cleared HERE, before this turn's detection runs below.
>     holder = current_sensitive_turn.get()
>     if holder is not None:
>         holder.clear()
> ```

**Why it's wrong:** `UserStoppedSpeakingFrame` is not the *start* of a user
turn, it is the **end** of one. In pipecat 1.4 the user aggregator appends each
`TranscriptionFrame` as it arrives (`llm_response_universal.py:793` →
`_handle_transcription`, `:1108–1126`) and only then, on turn stop, broadcasts
`UserStoppedSpeakingFrame` (`:1236`) and pushes the aggregation that kicks LLM
inference (`:1216`). So the per-turn order the observer sees is:

`TranscriptionFrame` (arm) → `UserStoppedSpeakingFrame` (**clear**) → LLM runs →
delegations → `LLMFullResponseEndFrame` (assistant print/persist).

The clear lands **between** arming and every consumer except P1/P6, which run
synchronously inside the same `on_push_frame` call. P2, P3, P4, P5, P7, P8, P9,
P10 all read `is_sensitive()` after the flag has already been reset to `False`.

Because `is_sensitive()` is fail-open by design (D-H4), this failure is
completely silent: the tests in §7.3 set the ContextVar by hand and never
reproduce the frame order, so the suite is green while the feature does nothing.

**Evidence:**

- pipecat 1.4.0, `processors/aggregators/llm_response_universal.py`:
  `_on_user_turn_stopped` (`:1225`) → `await self.broadcast_frame(UserStoppedSpeakingFrame)`
  (`:1236`); `_on_user_turn_inference_triggered` (`:1190`) → `segment = await self.push_aggregation()`
  (`:1216`) — the aggregation being pushed is the accumulated `TranscriptionFrame`
  text, so transcripts necessarily precede both.
- This repo's own D-010 note, `jarvis/bot/pipeline.py:676–678`: *"Flux EOT only
  finalizes transcripts, which accumulate harmlessly mid-turn."* Transcripts are
  finalized **during** the turn; the turn closes 2.5 s later
  (`VADParams(stop_secs=2.5)`).
- The existing latency metric confirms the direction: `TranscriptLogger` starts
  its stopwatch on `UserStoppedSpeakingFrame` (`transcript_log.py:58–59`) and
  stops it on `LLMFullResponseEndFrame` (`:64–70`), printing
  `TURN user_end->llm_done`. That metric is only meaningful if user-stop
  precedes the LLM.

**Also broken by the same edit:** `TranscriptLogger.process_frame` has **no**
`StartInterruptionFrame` branch (`transcript_log.py:53–72`), so
`self._assistant_buffer` is never emptied on a barge-in. A partial sensitive
reply therefore survives into the next turn and is flushed by the next
`LLMFullResponseEndFrame` — after the flag was cleared at 6c. The mitigation
makes the leak it was written to prevent *more* likely, not less.

**Fix:** Do not clear on `UserStoppedSpeakingFrame`. Clear on
`UserStartedSpeakingFrame` (the true start-of-turn boundary, and the frame a
barge-in raises first), and additionally clear on `StartInterruptionFrame` in
`TranscriptLogger.process_frame` **after** flushing/discarding
`self._assistant_buffer`. State the frame order explicitly in D-H4 so the
implementer does not have to infer it, and add a §7.3 test that drives the real
sequence `TranscriptionFrame → UserStoppedSpeakingFrame → LLMFullResponseEndFrame`
through a real `TranscriptObserver` + `TranscriptLogger` and asserts the
assistant row is still suppressed.

---

### F2 — The assistant's reply is never scanned, so "what's my balance" leaks the figure into `conversations` and `bot.log` [BLOCKER]

**Where:** §5 Step 6b/6d; D-H6 rows P2/P7; K3 in `/home/claude/plans/BRIEF.md`.

**What the plan says:** Step 6d runs `arm_from_text(text)` on the **user**
transcript only. Step 6b's assistant branch merely reads `is_sensitive()`.
D-H4: *"Finalized user transcription arrives → `detect_financial(text)`."*

**Why it's wrong:** The single most likely way a financial value enters this
system is the assistant *answering* a question that contained no value. "What's
my checking balance?" contains no digits, no keyword+number pair, nothing the
detector can fire on — so the flag never arms and the reply
*"Your checking account balance is $2,431.18."* is printed to `logs/bot.log`
(`transcript_log.py:68`) and INSERTed into `conversations`
(`transcript_log.py:69 → :146`) in plaintext. The memory sweep then folds
`conversations` into long-term memory (`jarvis/memory.py:782`), which is exactly
the pathway the repo already documents as harmful in
`TranscriptObserver.__init__`'s docstring.

**Evidence:**

```
$ python3 -c "... detect_financial('what is my checking balance')"
None
$ python3 -c "... detect_financial('Your checking account balance is $2,431.18 as of today.')"
FinancialMatch(kind='balance', span=(33, 42))
```

The detector *would* catch the reply. Nothing ever hands it the reply.

**Fix:** In Step 6b, before the print/persist branch, call
`arm_from_text(text)` on the assistant text as well (the flag object is
per-session and `arm()` is idempotent), then re-read `is_sensitive()`. Add the
same call to `Orchestrator.chat`'s assistant path (Step 6f, line 153). Add a
D-H6 row making it explicit that **both** roles are scanned, and a §7.1
positive case for a bare assistant-shaped reply.

---

### F3 — The account and balance rules fire on ordinary repo-domain English; every false positive silently deletes a whole turn [BLOCKER]

**Where:** §5 Step 3, `_ACCOUNT_RE` and `_FIN_WORD_RE`; D-H5; R-5; §7.1's
negative set.

**What the plan says:**

> ```python
> _ACCOUNT_RE = re.compile(rf"(?i)\b(?:account|acct|checking|savings)\b" …)
> _FIN_WORD_RE = re.compile(r"(?:(?i:balance|account|owed?|savings|checking|401\s?k|brokerage)|IRA)")
> ```
> §7.1: *"0 false positives and 0 false negatives"*.

**Why it's wrong:** two independent defects.

1. `_FIN_WORD_RE` has **no word boundaries**. `owe` therefore matches inside
   `lower`, `power`, `showed`, `borrowed`, `however`, `allowed`, `followed`,
   `slowed`, `narrowed`, `flowers`, `tower`, `vowel`, `swallowed`; `account`
   matches inside `accounts`/`accounting`; `balance` inside `unbalanced`.
   Any of those within 40 chars of an amount ≥ $100 arms the turn.
2. `checking` and `savings` in `_ACCOUNT_RE` are ordinary verbs/nouns. Any
   6–17 digit run (a unix timestamp, a build id, an order number, a ticket) within
   24 chars of them arms the turn.

This is precisely the defect class this project shipped before — a rule that
keys on shape rather than meaning, whose test passed by luck of word choice.
None of the 36 negatives in §7.1 contains `checking` as a verb, or any word
merely *containing* `owe`.

**Evidence** (extracted `jarvis/sensitive.py`, run verbatim):

```
FinancialMatch(kind='account', span=(20,30))  'checking the run at 1756254000 now'
FinancialMatch(kind='account', span=(19,26))  "I'm checking build 1049322 for errors"
FinancialMatch(kind='account', span=(28,35))  'checking on that, the PR is 1234567'
FinancialMatch(kind='account', span=(16,23))  'checking flight 1234567 status'
FinancialMatch(kind='account', span=(32,39))  'my account, the order number is 8675309'
FinancialMatch(kind='account', span=(25,34))  'my Amazon account, order 112233445 shipped'
FinancialMatch(kind='account', span=(38,44))  'log in to my account, my member id is 998877'
FinancialMatch(kind='account', span=(11,18))  'savings of 1500000 tokens per run'

FinancialMatch(kind='balance', span=(19,25))  'the invoice showed $1,299 for the laptop'
FinancialMatch(kind='balance', span=(23,27))  'I lowered the offer to $250'
FinancialMatch(kind='balance', span=(12,16))  'he borrowed $400 from his brother'
FinancialMatch(kind='balance', span=( 9,13))  'however, $250 is too much for a mouse'
FinancialMatch(kind='balance', span=(18,22))  'the crowd allowed $150 tickets'
FinancialMatch(kind='balance', span=(23,27))  'sales slowed after the $300 hike'
FinancialMatch(kind='balance', span=(17,21))  'the flowers cost $120'
FinancialMatch(kind='balance', span=(23,27))  'she followed up on the $900 invoice'
FinancialMatch(kind='balance', span=(21,27))  'the tower repair was $2,000'
FinancialMatch(kind='balance', span=(27,31))  'vowel training software is $150'
```

12/12 and 11/11 of those fire. Scanning this repo's **own prose**
(`CLAUDE.md`, `README.md`, `DEVIATIONS.md`, `ROADMAP.md`) for words that match
`_FIN_WORD_RE` as a bare substring returns 13 distinct words:
`LOWER, accounting, accounts, allowed, lower, lowering, lowest, narrowed, powers, shadowed, showed, swallowed, windowed`.

The blast radius of one false positive is not "a stray flag": the user's turn
gets **no `conversations` row at all** (§2.2 — "a suppressed turn writes no row
at all, so there is nothing to mark"), the assistant reply gets no row, the
`bot.log` line is replaced, and every run-log payload for that turn becomes
`"<sensitive>"` — for exactly the developer turns most likely to say
"checking build 1049322".

**Fix:** (a) add `\b` boundaries to `_FIN_WORD_RE`:
`r"(?:\b(?i:balance|accounts?|owed?|savings|checking|401\s?k|brokerage)\b|\bIRA\b)"`;
(b) drop the bare verb `checking` from `_ACCOUNT_RE` and require the noun phrase —
`\b(?:account|acct)\s*(?:number|#|no\.?)?\b` and `\b(?:checking|savings)\s+(?:account|acct)\b`;
(c) add every input above to §7.1's negative set and re-run before re-asserting
any 0-FP claim.

---

### F4 — The CLI/text path (P4, P5) never gets a `SensitiveTurn`; Step 6f cites a wiring step that does not exist [BLOCKER]

**Where:** §5 Step 5b, §5 Step 6f, §4 Modify manifest.

**What the plan says:** Step 6f:

> *"`arm_from_text` is a no-op when no `SensitiveTurn` is in context
> (jarvis.cli sets one; see §5 Step 5b)."*

**Why it's wrong:** Step 5b sets `current_sensitive_turn` in
`jarvis/bot/pipeline.py`'s `run_session` and nowhere else. `jarvis/cli.py` is
**not** in §4's 17-file Modify manifest and no step edits it. So in the CLI/text
path `current_sensitive_turn.get()` is `None`, `arm_from_text` returns `False`
at `if holder is None: return False`, `is_sensitive()` is `False`, and the P4/P5
guards are dead code that always takes the persist branch.

This is the path §8 V5 uses to verify the memory gate, so the plan's own
acceptance runs on the one path where suppression is wired to nothing.

**Evidence:**

```
$ grep -n "Supervisor(\|current_sensitive\|Orchestrator" /home/claude/repo/jarvis/cli.py
16:from jarvis.agents.supervisor import Orchestrator
97:            reply = await orchestrator.chat(line)
```
No `SensitiveTurn`, and `jarvis/cli.py` appears nowhere in §4.

**Fix:** Add `jarvis/cli.py` to §4's Modify list and give Step 5 a `5e`:
construct a `SensitiveTurn()` in `jarvis/cli.py:main()` immediately after
`bridge_settings_to_env()` and before the read loop, and call
`current_sensitive_turn.set(...)` on it. (Note the class is `Orchestrator`, not
`Supervisor` — see F16.)

---

### F5 — `RunLogger.start()` writes the delegated task verbatim to `agent_runs.task` and to the JSONL; it is a 12th persistence site the plan misses inside the file it edits [BLOCKER]

**Where:** §1.3's eleven-site table; D-H6; §5 Step 7 (`store.py`).
Repo: `jarvis/runlog/store.py:235–257`.

**What the plan says:** §1.3 is titled *"Where a spoken financial detail
persists today, in plaintext"* and enumerates P8 (`tool_call`), P9
(`tool_result`), P10 (`finish`) as the run-log sites. Step 7 edits exactly
those three.

**Why it's wrong:** `RunLogger.start()` writes `self.task` — the delegation text
the Supervisor composed from the user's utterance — into **both** the JSONL
`run_start` record and the `agent_runs.task` SQLite column. It is the field most
certain to contain the user's words. It is untouched by Step 7.

**Evidence:** `jarvis/runlog/store.py`:

```
240:            self._buffer.append({
241:                "type": "run_start",
…
247:                "task": self.task,
…
250:            self._execute(
251:                "INSERT INTO agent_runs (run_id, session_id, agent, "
252:                "display_name, task, status, started_at, tool_count, model) "
```
and `jarvis/agents/base.py:443–447` — `RunLogger(resolved_run_id, self.name, self.display_name, task, …)` then `runlog.start()`.

The same omission covers `mcp_call` (`store.py:299–317`), whose `error` field is
built from the failing tool's own message (`registry.py:141–160` formats
`f"{tool_name} failed: {error}"`), and `jarvis/procedures.py`'s
`learn_from_run` → `_create_candidate` (`procedures.py:304–321`), which persists
an LLM-written label/description derived from that same task into `procedures`.

**Fix:** Add P12 to D-H6: in `start()`, `task` becomes `SENSITIVE_SENTINEL` in
both the buffer record and the INSERT when `_sensitive()`. Add P13 for
`mcp_call`'s `error`. Note in §10 that `learn_from_run` derives from the task and
must be revisited when P12 lands (or gate it on `_sensitive()` too). Update the
"eleven sites" wording everywhere (§1.3, §1.7, D-H6, §7.3's title, K3 in the
brief).

---

### F6 — A delegated sub-agent runs in a **detached** task that outlives the turn; the flag is cleared while it is still logging [BLOCKER]

**Where:** D-H4 lifecycle ("Assistant turn ends → `clear()` on
`LLMFullResponseEndFrame`"); D-H6 rows P8–P10.
Repo: `jarvis/agents/delegate.py:463–470`, `jarvis/agents/base.py:410–412`.

**What the plan says:** *"Assistant turn ends | `clear()` on
`LLMFullResponseEndFrame` … after the assistant persist/print branch has run"*.

**Why it's wrong:** In this codebase a delegation does **not** finish inside the
turn. `delegate.py:463` — *"Barge-in survival: the WORK runs in a detached
task"* — `run_task = asyncio.create_task(_execute())` at `:470`; the Supervisor
speaks an acknowledgement immediately and `LLMFullResponseEndFrame` fires
seconds-to-minutes before the sub-agent's `tool_call`/`tool_result`/`finish`
land. Clearing the flag at that point means P8–P10 cover only the sliver of the
run that overlaps the acknowledgement — in practice, nothing.

**Evidence:** `jarvis/agents/base.py:410–412`:

> *"(F8: barge-in survival runs delegations as detached tasks, so two concurrent
> `run()` calls can be in flight on one `SubAgent` instance …)"*

and `jarvis/agents/delegate.py:171`: *"…still happens inside the detached task"*.

**Fix:** Do not let a single per-session mutable object carry run-scoped state
across a task that outlives the turn. Either (a) snapshot the flag at
`RunLogger` construction — `RunLogger(..., sensitive=is_sensitive())` — and have
`_sensitive()` read `self._sensitive` rather than the live ContextVar, or (b)
give `run_logger_scope` a companion `sensitive_scope` set in `_execute()` before
detaching. (a) is smaller and matches the existing `model=` field precedent at
`base.py:449`. Either way D-H4's lifecycle table needs a row for
"delegation outlives the turn".

---

### F7 — Step 1 is not "deliberately inert": it breaks `scripts/check_skills.py`, a documented validation gate [MAJOR]

**Where:** §5 Step 1 preamble.

**What the plan says:**

> *"This step is deliberately first and deliberately inert: it changes data that
> nothing reads yet."*

**Why it's wrong:** `scripts/check_skills.py` reads it today and **enforces
presence**, not just shape:

```
102:        for var in m["requires_env"]:
103:            if not env.get(var):
104:                errors.append(f"{dirname}: requires_env {var} is not set")
```

Step 1 adds `JARVIS_UNITS`, `JARVIS_REPO_ROOT` (×2), `GITHUB_OWNER`,
`JARVIS_REGISTRY_REPO`, `JARVIS_REGISTRY_BRANCH`, `JARVIS_UPGRADE_PROFILE`,
`JARVIS_SCREEN_ENABLED`, `JARVIS_SCREEN_RETENTION_HOURS`, `JARVIS_VISION_PROFILE`.
Most are optional-with-a-code-default (`mcp_apps/logic.py:33` defaults to
`"jarvis-voice-ai"`; `:37` to `"mortimer-dev"`; `mcp_screen/logic.py:274`
treats absence as "auto-select"). Any of them unset makes
`python scripts/check_skills.py` print `SKILLS FAIL` — a command CLAUDE.md
line 64 lists as a standard gate.

**Evidence:** `scripts/check_skills.py:102–104` above; CLAUDE.md:64
`python scripts/check_skills.py                          # skill.yaml manifests match servers`.

**Fix:** Either (a) extend Step 1 to teach `check_skills.py` the difference
between *required* and *forwarded-if-present* (e.g. an `optional_env:` key that
`build_child_env` treats identically but the validator does not enforce), or (b)
put the genuinely-optional names in `requires_env_dynamic`-style optional list.
Add `scripts/check_skills.py` to §4's Modify manifest and add
`python scripts/check_skills.py` to Step 1's "test that proves it".

---

### F8 — `test_no_server_reads_an_undeclared_var` detects **zero** of `mcp-screen`'s four variables; the test claimed to be the one that would have caught R-1 misses the only hard case [MAJOR]

**Where:** §7.2 `_read_in_source` / `test_no_server_reads_an_undeclared_var`.

**What the plan says:**

> *"This is the test that would have caught the six under-declared servers in
> plan R-1."*

**Why it's wrong:** the regex only matches a **string literal** immediately
inside the call. This repo's dominant style is a module constant
(`SCREEN_ENABLED_ENV = "JARVIS_SCREEN_ENABLED"` then
`os.environ.get(SCREEN_ENABLED_ENV, …)`). Running the plan's own regex over the
real tree:

```
  mcp_apps       detects ['GITHUB_OWNER', 'GITHUB_TOKEN', 'JARVIS_REGISTRY_BRANCH', 'JARVIS_REGISTRY_REPO']
  mcp_git        detects ['JARVIS_REPO_ROOT']
  mcp_repo       detects ['JARVIS_REPO_ROOT']
  mcp_screen     detects []            <-- all four names missed
  mcp_selfedit   detects ['JARVIS_UPGRADE_PROFILE']   <-- JARVIS_ADMIN_URL missed
  mcp_web        detects ['JARVIS_UNITS', 'TAVILY_API_KEY']
```

So it would have caught 4 of 6, and would have missed `mcp-screen` — the one
the plan itself calls "the hard case" — entirely. A new server written in the
repo's own constant style gets zero coverage from this gate.

**Fix:** Resolve module-level `NAME = "ENV_VAR"` assignments first and
substitute them, or parse with `ast` and follow single-assignment constants.
Concretely: collect `re.findall(r'^([A-Z][A-Z0-9_]*)\s*=\s*["\']([A-Z][A-Z0-9_]+)["\']', src, re.M)`
into a map, then also match `os.environ.get\(\s*([A-Z][A-Z0-9_]*)\s*[,)]` and
translate through it. Assert on the union.

---

### F9 — `.env.example` does not exist in this repo, but two steps and the manifest edit it [MAJOR]

**Where:** §4 Modify (`.env.example`), §5 Step 2c, §5 Step 5d, §6, D-H10.

**What the plan says:** *"In `.env.example`, add under a `# --- security (T4a) ---`
heading …"*

**Why it's wrong:** there is no `.env.example` in the snapshot.

**Evidence:**
```
$ ls /home/claude/repo/.env* ; find /home/claude/repo -maxdepth 2 -name "*.example"
(no output)
$ grep -n "env" /home/claude/repo/.gitignore
6:.env
7:.env.*
8:!.env.example
```
`.gitignore` un-ignores it and `scripts/mortimer.sh:74` tells the user to copy
it, but the file is absent. Per §0.8 (*"If the quoted code is absent entirely,
stop and report"*) the implementer stops on a documentation step.

Relatedly, §6's stated reason is also wrong: *"documented in `.env.example` as
commented-out lines so `scripts/check_env.py` does not begin requiring them"* —
`check_env.py` never reads `.env.example`; its required set is the hardcoded
`REQUIRED_VARS = ["OPENAI_API_KEY", "DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY"]`
(`scripts/check_env.py:22`). Nothing would have started requiring them either way.

**Fix:** Change Steps 2c/5d to *"create `.env.example` if absent, else append"*,
give the file's full intended content, and drop the incorrect `check_env.py`
rationale from §6.

---

### F10 — Two of the enumerated tests fail on first run, and the "60 cases / 0 FP / 0 FN" measurement is off by one [MAJOR]

**Where:** §7.1 `test_counts_match_the_plan`,
`test_redacted_line_carries_no_content`; §4; §7's measurement note; §8 V1; §12.

**What the plan says:**
> `assert len(NEGATIVES) == 35`
> `assert "27 chars withheld" in line`
> *"Final measured result: 60/60 enumerated cases pass, 83/83 including the extra adversarial set"*

**Why it's wrong:** the `NEGATIVES` literal in §7.1 has **36** entries, and
`len("card number 4111111111111111")` is **28**, not 27.

**Evidence:**
```
$ python3  # counting the literal blocks out of the plan file
NEGATIVES entries: 36
POSITIVES entries: 25
$ python3 -c "print(len('card number 4111111111111111'))"
28
```
So the enumerated total is 61, not 60, and both assertions are red the moment
the file is created. The implementer is then forced to make a judgment call
(delete a negative? change the constant?) that §0.4 forbids them to make about
patterns and §0 does not cover for tests.

**Fix:** `assert len(NEGATIVES) == 36`; `assert "28 chars withheld" in line`;
change "60" to "61" in §4, §7's measurement note, §8 V1 and §12.

---

### F11 — The env audit greps only `mcp_servers/`; `mcp-screen` transitively reads `JARVIS_UPGRADE_MODELS` and loses it [MAJOR]

**Where:** §1.2 (*"runtime reads from `grep -rn "os\.environ\|getenv" mcp_servers/`"*),
D-H2's table, R-H1.

**Why it's wrong:** every MCP server imports `jarvis.*` modules, and those read
the environment too. `mcp_servers/mcp_screen/logic.py:66` imports
`jarvis.agents.upgrade_agent.load_model_registry`, which reads
`REGISTRY_PATH_ENV = "JARVIS_UPGRADE_MODELS"` (`upgrade_agent.py:60`, used at
`:218`). That name is in neither `BASE_ENV_KEYS` nor `mcp-screen`'s
`requires_env`, so after scoping an operator who has pointed
`JARVIS_UPGRADE_MODELS` at a non-default registry gets `mcp-screen` silently
resolving the **default** registry — a different profile set, possibly with an
`api_key_env` the child was never granted. The failure surfaces as
"vision is not configured", which is exactly the message D-H2 says it is trying
to avoid.

`run_bot.sh` makes this live rather than theoretical: it does
`set -a; . ./.env; set +a`, so **everything in `.env` is currently in the parent
environment and currently reaches every child**.

**Evidence:**
```
$ grep -n "REGISTRY_PATH_ENV" /home/claude/repo/jarvis/agents/upgrade_agent.py
60:REGISTRY_PATH_ENV = "JARVIS_UPGRADE_MODELS"
218:        path = os.environ.get(REGISTRY_PATH_ENV) or DEFAULT_REGISTRY_PATH
$ sed -n '5,9p' /home/claude/repo/scripts/run_bot.sh
set -a
. ./.env
set +a
```
Sandbox run of the plan's own `build_child_env` against the real
`config/mcp_servers.yaml` with the Step-1 declarations applied:
```
mcp-screen -> ['ANTHROPIC_API_KEY','HOME','JARVIS_DB_PATH','JARVIS_SCREEN_ENABLED',
               'JARVIS_TIMEZONE','JARVIS_VISION_PROFILE','LANG','MOONSHOT_API_KEY',
               'OPENAI_API_KEY','OPENROUTER_API_KEY','PATH','TMPDIR','VIRTUAL_ENV']
```
`JARVIS_UPGRADE_MODELS` absent.

**Fix:** Redo §1.2 as a transitive audit (each server package **plus** every
`jarvis.*` module it imports) and add `JARVIS_UPGRADE_MODELS` to `mcp-screen`'s
`requires_env`. Extend §7.2's `test_no_server_reads_an_undeclared_var` to follow
`from jarvis.… import` in each server package one level deep, or state
explicitly in R-H1 that transitive reads are out of the audit's scope and list
the ones found.

---

### F12 — The four deny entries do not close the self-edit hole: `config/mcp_servers.yaml` re-grants any variable to any server, and it is allow-listed [MAJOR]

**Where:** R-4, D-H9, §8 V7.

**What the plan says:** *"D-H9 therefore adds four deny entries … An assistant
that can widen its own `requires_env`, rewrite the scoping code, add `mcp-web`
to a mail agent, and delete the test that would catch it, is not constrained by
any of the three mechanisms in this plan."*

**Why it's wrong:** the plan itself specifies (Step 2b) that
`config/mcp_servers.yaml`'s `env:` map is applied **after** `build_child_env`
and **overrides it** — *"the `env:` map still wins over everything (it is
applied last)"*. `config/**` is on the allow list and `config/mcp_servers.yaml`
is not on the deny list. So one allowed edit —

```yaml
  - name: mcp-time
    env:
      GITHUB_TOKEN: "${GITHUB_TOKEN}"
      ELEVENLABS_API_KEY: "${ELEVENLABS_API_KEY}"
```

— restores full credential access to any server, with no `skill.yaml` change and
no `registry.py` change. Two further bypasses survive as well.

**Evidence** (real `Allowlist` from `jarvis/selfedit/allowlist.py`, loaded with
the four D-H9 entries appended):

```
denied   jarvis/skills/registry.py
ALLOWED  jarvis/skills/__init__.py        <- package init of the enforcement module
denied   mcp_servers/mcp_web/skill.yaml
denied   config/agents.yaml
denied   tests/unit/test_agent_isolation.py
ALLOWED  tests/conftest.py                <- can collect_ignore the K4 test
ALLOWED  tests/unit/conftest.py
ALLOWED  config/mcp_servers.yaml          <- the env: map override
denied   config/upgrade_models.yaml
```

**Fix:** V7's deny array needs at least three more entries:
`"config/mcp_servers.yaml"`, `"jarvis/skills/__init__.py"` (or replace
`jarvis/skills/registry.py` with `jarvis/skills/**` and re-allow nothing), and
`"tests/conftest.py"` + `"tests/**/conftest.py"`. Update
`test_report_self_edit_exposure`'s `guarded` list to match — it currently checks
only four paths and would print "none — V7 commit is in" while three holes are
open.

---

### F13 — Detection runs per finalized transcript, not per turn; this repo splits one utterance across several, defeating every keyword-context rule [MAJOR]

**Where:** §5 Step 6d; D-H4.

**Why it's wrong:** `arm_from_text(text)` is called on each finalized
`TranscriptionFrame`. This repo's own D-010 records that Deepgram Flux
finalizes transcripts **mid-turn** and that the segments accumulate in the
aggregator. Three of the five detectors (`routing`, `account`, `balance`)
require the keyword and the value in the *same string*. A turn split as
`"my routing number is"` / `"021000021"` matches neither half — and the first
half is printed and INSERTed before the second even arrives.

**Evidence:**
```
detect_financial('my routing number is')          -> None
detect_financial('021000021')                     -> None
detect_financial('my checking account number is') -> None
detect_financial('000123456789')                  -> None
detect_financial('my routing number is 021000021')-> FinancialMatch(kind='routing', …)
```
and `jarvis/bot/pipeline.py:676–678`: *"Flux EOT only finalizes transcripts,
which accumulate harmlessly mid-turn."* Also `DEVIATIONS.md` D-010:
*"the utterance split into two turns … in every early run"*.

**Fix:** Keep a per-turn transcript accumulator on `TranscriptObserver` (reset
on `UserStartedSpeakingFrame`), run `arm_from_text` on the accumulated text, and
**buffer the USER print/persist until turn close** rather than emitting per
segment — otherwise the first segment is already on disk when the second arms
the flag. State this in D-H4 as a lifecycle row.

---

### F14 — `notes` and `reminders` are unenumerated plaintext sinks; §1.3 claims to be complete [MAJOR]

**Where:** §1.3 (*"Where a spoken financial detail persists today, in
plaintext"*), §1.7, D-H6.

**Why it's wrong:** `mcp_notes.create_note` INSERTs `title`/`body` verbatim
into `notes` (`mcp_servers/mcp_notes/logic.py:36`) with **no** scan —
`scan_memory_content` is only wired into `jarvis/memory.py:542/575/606`. The
repo's own routing-eval fixture contains
`"save a note that the project wifi password is blueplanet42"`, so "save a note
that my routing number is 021000021" is squarely in-domain, and the note stays
searchable through `mcp_notes.search_notes`.
Under a sensitive turn nothing stops it: the run-log arguments become
`"<sensitive>"` but the row lands in full.

`reminders` (`mcp_reminders`) has the same shape.

**Evidence:**
```
$ grep -rn "scan_memory_content" /home/claude/repo --include=*.py | grep -v tests
jarvis/memory.py:301 …:542 …:575 …:606
jarvis/bot/remember_tool.py:13   (docstring only)
$ grep -n "INSERT INTO notes" /home/claude/repo/mcp_servers/mcp_notes/logic.py
36:            "INSERT INTO notes (title, body, tags, created_at, updated_at) "
```

**Fix:** Either add P12/P13 rows applying `detect_financial` at
`mcp_notes.create_note`/`update_note` and `mcp_reminders.set_reminder` (a
refusal string, mirroring D-H8), or move them into §2 Non-goals **explicitly**
with the reason, and correct §1.3's claim of completeness and §1.7's
"eleven distinct plaintext locations".

---

### F15 — §1.4 / D-H4's central premise about ContextVars is false, and `Runtime.sensitive_turn` is never read [MAJOR]

**Where:** §1.4, D-H4, §11 item 1.

**What the plan says:**

> *"P1/P2/P6/P7 (transcript) execute in the observer and in a pipeline processor
> — … on a task whose context is not a child of the turn that set the flag."*
> *"So the flag is a small mutable object owned by `Runtime` and read by everyone,
> **plus** a ContextVar … One object, two access paths."*

**Why it's wrong:** there is only **one** access path in the implementation.
Every site in Steps 6 and 7 reads through `is_sensitive()` / `current_turn_id()`
/ `arm_from_text()`, all of which resolve `current_sensitive_turn.get()`.
Nothing anywhere reads `runtime.sensitive_turn`; it exists only to be passed to
`set()` once. So if the stated premise were true, **every transcript site would
read `False` forever** and the whole of K3 would be silently inert — the failure
mode D-H4 was written to prevent.

The premise is in fact false: `run_session` calls `set()` at
`jarvis/bot/pipeline.py:827` before `build_pipeline` (`:833`) and before
`TranscriptObserver` is constructed (`:853`), and `asyncio` copies the current
context into every task created afterwards, so the observer's task does see it.
But an implementer who believes §1.4 will "fix" the non-problem by threading the
object into the constructors, or worse, conclude the plan is broken.

**Fix:** Replace §1.4's second half with the true reason (the object must be
mutable and shared so a *reference* copied into child contexts stays live), and
either (a) actually use `Runtime.sensitive_turn` by passing it to
`TranscriptObserver(...)`/`TranscriptLogger(...)` as a constructor arg — which
also makes F1/F13 easier to fix — or (b) delete the `Runtime` field and say the
ContextVar is the single mechanism. Do not ship both with a false rationale.

---

### F16 — `_resolve_dynamic_env` raises inside `_start_server`, so one typo in a (currently self-editable) `skill.yaml` prevents the bot from starting [MAJOR]

**Where:** D-H2 (*"Any other value is a hard error at registry start
(`ValueError`)"*), §5 Step 2a.

**Why it's wrong:** `build_child_env` calls `_resolve_dynamic_env` unguarded;
`_start_server` calls `build_child_env`; `SkillRegistry.start()` wraps the loop
in `except Exception: await self.stop(); raise` (`registry.py:75–79`). A
`ValueError` therefore propagates out of `start()` and the voice loop never
comes up. That directly contradicts the posture the plan adopts three paragraphs
earlier for a missing variable (*"a degraded server beats a dead voice loop"*)
and the precedent it cites (`mcp_server_env_unresolved` is *"a warning, not a
refusal"*). Until Larry's V7 commit lands, `mcp_servers/*/skill.yaml` is
self-editable, so the assistant can brick its own startup with one typo.

**Evidence:** `jarvis/skills/registry.py:71–79`:
```python
        try:
            for entry in self._server_configs:
                await self._start_server(entry)
        except Exception:
            await self.stop()
            raise
```

**Fix:** Catch `ValueError` in `build_child_env` around the
`_resolve_dynamic_env` call, log `mcp_requires_env_dynamic_invalid server=… error=…`
at ERROR, and continue with base + `requires_env` only. Keep the hard error
where it belongs: a startup-time validation pass over all twelve manifests
(or `scripts/check_skills.py`), not the spawn path.

---

### F17 — D-H4 specifies `turn_id` from `jarvis.runlog.get_run_id()`; the Step 4 source never calls it [MAJOR]

**Where:** D-H4 final paragraph vs. §5 Step 4 `SensitiveTurn.arm` / `arm_from_text`.

**What the plan says:** *"`turn_id` is `jarvis.runlog.get_run_id()` at arm time
when inside a run, else a fresh `uuid.uuid4().hex[:8]`."*

**Why it's wrong:** Step 4's complete file imports only `uuid` and
`contextvars`, and `arm_from_text(text, turn_id=None)` passes `turn_id`
straight through to `arm()`, which falls back to `uuid4().hex[:8]`. No caller in
Steps 5–7 passes a `turn_id`. So `get_run_id()` is never consulted and the
correlation property D-H4 promises does not exist. §0.4 forbids the implementer
from improvising, so this is left dangling.

**Fix:** Either delete the sentence from D-H4, or add to `arm_from_text`:
```python
    if turn_id is None:
        try:
            from jarvis.runlog import get_run_id
            turn_id = get_run_id() or None
        except Exception:
            turn_id = None
```
and say which. (Note the import must be lazy — `jarvis.runlog` importing
`jarvis.bot` is the cycle D-H7 already guards against in the other direction.)

---

### F18 — §8 V4's acceptance depends on Deepgram Flux numeralising spoken digits, which the plan itself says is not guaranteed and which this pipeline cannot configure [MINOR]

**Where:** §8 V4, R-H4.

**Why it's a problem:** V4 tells Larry to *say out loud* "zero zero zero one two
three four five six seven eight nine" and then assert zero rows. If Flux emits
the words rather than `000123456789`, V4 fails through no fault of the
implementation, and there is no knob to fix it: unlike `DeepgramSTTService`
(which exposes `numerals` and `smart_format`, `pipecat/services/deepgram/stt.py:91,98`),
`DeepgramFluxSTTSettings` exposes only `eager_eot_threshold`, `eot_threshold`,
`eot_timeout_ms`, `keyterm`, `min_confidence`, `language_hints`
(`pipecat/services/deepgram/flux/base.py:130–135`).

**Fix:** Add a step 0 to V4: `grep "USER:" logs/bot.log | tail -1` after the
utterance and confirm the transcript contains digits; if it does not, V4 is
**inconclusive**, not failed, and R-H4 is confirmed live. Say so in V4.

---

### F19 — The class is `Orchestrator`, not `Supervisor` [MINOR]

**Where:** §1.3 P4/P5, D-H6, §5 Step 6f, R-H7.

`jarvis/agents/supervisor.py:44` declares `class Orchestrator:`; `jarvis/cli.py:16`
imports `Orchestrator`. The line numbers the plan cites (118, 153, 191–196, 194)
are all correct. Rename in the plan so a `grep "class Supervisor"` does not
send the implementer to §0.8's stop-and-report branch.

---

### F20 — `redacted(role, text)` takes a `role` it never uses [MINOR]

**Where:** §5 Step 4. `def redacted(role: str, text: str) -> str` returns a
string built only from `current_turn_id()` and `len(text)`. Both call sites
(6b, 6d) pass a literal. Drop the parameter or use it; as written a linter with
`ARG001` fails the build and the implementer must decide which way to resolve it.

---

### F21 — `mcp-apps`'s two optional-with-default variables now warn permanently [MINOR]

**Where:** D-H2, §5 Step 1a.

Measured against a realistic environment, Step 1's declarations produce these on
every process start:
```
WARNING mcp_server_env_missing server=mcp-apps var=JARVIS_REGISTRY_REPO
WARNING mcp_server_env_missing server=mcp-apps var=JARVIS_REGISTRY_BRANCH
WARNING mcp_server_env_missing server=mcp-selfedit var=JARVIS_UPGRADE_PROFILE
WARNING mcp_server_env_missing server=mcp-screen var=JARVIS_SCREEN_RETENTION_HOURS
```
All four have code defaults (`mcp_apps/logic.py:33,37`,
`mcp_screen/logic.py:108`, `mcp_selfedit/logic.py:127`). A permanent WARNING for
a deliberately-unset optional is the noise that trains an operator to ignore the
channel that F16 and R-H1 depend on. Same mechanism as `requires_env_dynamic`'s
"absence is normal and silent" rule — apply it here with an `optional_env:` key
(which also fixes F7).

---

### F22 — `BALANCE_MIN_AMOUNT = 100.0` excludes real balances; the knob trades a hard miss for a soft one [MINOR]

**Where:** R-5, D-H5, §6.

Measured:
```
None                                          'my checking account balance is $47.32'
None                                          'the savings account has $12 left'
None                                          'I owe $85 on that card'
None                                          'my brokerage cash balance is $3.10'
None                                          'my balance is $99.99'
FinancialMatch(kind='balance', span=(14,21))  'my balance is $100.00'
```
A $47.32 checking balance is a financial detail by any reading of Larry's
*"sensitive info like financial info"*. The floor exists only because
`_FIN_WORD_RE` has no word boundaries and `account`/`owe` therefore matched
lunch money (R-5's two examples, `"I owe you $20 for lunch"` and
`"my account was charged $8.50"`, are both **verb** uses). Fixing F3's boundary
problem removes most of the pressure for the floor. Recommend: fix F3 first,
then re-measure, then set the floor from the re-measured data (likely much
lower, e.g. `10.0`) rather than from a 100.0 chosen against a broken keyword
rule. §12's checklist item should present that dependency.

---

### F23 — `§7.3`'s `RunLogger` example writes into the real repo's `logs/agents/` [MINOR]

**Where:** §7.3 `test_p8_tool_call_arguments_are_replaced`.

The snippet calls `RunLogger(run_id="t0000001", agent="analyst", task="x", model="m")`
— wrong signature (`display_name` is a required positional) and no `root=`, so
`self._root = Path(".")` and `_write_payload` creates
`./logs/agents/<date>/t0000001.jsonl` under the repo while the assertions read
`tmp_path / log.payload_path`. §7.4 notes this and gives the correction, but the
§7.3 block is still presented as a file to copy. Fix the block itself rather
than correcting it 200 lines later.

---

## What I verified and found correct

- **`${VAR}` expansion still resolves after scoping.** `expand_env_vars`
  (`jarvis/config.py:33–43`) reads the **parent's** `os.environ`, which scoping
  does not touch; only the child's env is restricted. `bridge_settings_to_env`
  still runs first (`registry.py:67`). No `config/mcp_servers.yaml` `env:` entry
  breaks. Confirmed by running `build_child_env` over all twelve real entries.
- **`build_child_env` output for the eleven non-`mcp-screen` servers.**
  `ELEVENLABS_API_KEY` and `DEEPGRAM_API_KEY` reach no child; `GITHUB_TOKEN`
  reaches only `mcp-apps`; `TAVILY_API_KEY` only `mcp-web`. `JARVIS_UNITS`
  reaches `mcp-web` (R-2 handled correctly without amending K2).
- **`requires_env_dynamic` resolution is coherent for `mcp-screen`.**
  `_walk_api_key_envs` over the real `config/upgrade_models.yaml` yields exactly
  `{ANTHROPIC_API_KEY, MOONSHOT_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY}`;
  the `"OPENAI_API_KEY"` literal fallback matches `mcp_screen/logic.py:282`'s
  `prof.get("api_key_env", "OPENAI_API_KEY")`; `vault_names` raises as specified;
  an empty `dynamic` list is a no-op. The R-H8 trade-off (four keys, not one) is
  stated honestly.
- **`_WARNED_MISSING` dedupe works** and `PYTHONPATH` absence is handled by the
  unchanged `registry.py:207`.
- **Path/line citations spot-checked and accurate:** `registry.py:191`
  (`env = dict(os.environ)`), `transcript_log.py:68/69/142/143/146`,
  `supervisor.py:118/153/191–196`, `runlog/store.py:66` (`_DROPPED`),
  `memory.py:301/542/575/606`, `remember_tool.py:19–22`,
  `selfedit/allowlist.py:74–79`, `config/agents.yaml`'s five agents,
  the full allow/deny lists in §1.6, `mcp_apps/skill.yaml:7`,
  `mcp_selfedit/skill.yaml:18`, `mcp_web/skill.yaml:6–7`, and the "line 6"
  claims for `mcp_git`/`mcp_repo`/`mcp_screen`. `jarvis/logging_config.py` is
  indeed 13 lines with no filter hook, and P6/P7 are indeed `print()`.
- **R-5's premise is real:** the roadmap's literal regex does match
  `"I owe you $20 for lunch"` and `"my account was charged $8.50"`.
- **The detector's structural choices that do work.** Card grouping floor of 4
  correctly rejects `555-123-4567`, `123-45-6789`, `35242-1234`, `2026-08-27`,
  `4111-1111`, `+1 205 555 1234`, `+44 7911 123456`, `+81 3 1234 5678`, and
  `version 4111.1111.1111.1111`; a ≥20-digit solid run is rejected; the
  uppercase-only IBAN rule keeps `gpt-5.1`, `462da350`, `97d5cecc`,
  `eleven_flash_v2_5` and lowercase commit SHAs out; `IRA` case-sensitivity
  keeps `"Ira paid me $500 back"` out; `"route 66"`, `"my 401k is up 12%"`,
  `"checking on that balance for you"` and `"my account number is on the
  invoice"` are all correctly negative. All **68** utterances in
  `tests/evals/cases.yaml` are negative — 0 false alarms.
- **The plan's own §7.1 set does pass** against the §5 Step 3 source: 25/25
  positives with the right `kind`, 36/36 negatives, and `detect_financial`
  costs ~3.5 ms on a 24 kB input (matching the plan's 3.34 ms/21.3 kB claim).
- **Only two production writers to `conversations`** exist
  (`transcript_log.py:150`, `supervisor.py:194`) — P3/P4/P5 are complete for
  that table, and `conversations_fts` is trigger-populated, not a separate site.
  The council JSONL (`jarvis/council/council.py:1277,1335`) carries planning
  rounds, not user transcripts, and `mcp_runlog` only calls
  `council_mod.list_rounds`.
- **The import-cycle analysis in Step 6f is correct:** `jarvis/bot/__init__.py`
  is empty and `sensitive_turn` imports only `jarvis.sensitive` (stdlib), so
  `jarvis.agents.supervisor → jarvis.bot.sensitive_turn` terminates.
- **The deny entries that were proposed do match** under the real matcher:
  `jarvis/skills/registry.py`, `mcp_servers/*/skill.yaml` (all twelve),
  `config/agents.yaml`, `tests/unit/test_agent_isolation.py`. R-4's correction
  is right — `jarvis/sensitive.py`, `jarvis/memory.py`,
  `jarvis/bot/sensitive_turn.py` and `jarvis/runlog/store.py` match no allow
  pattern and need no entry.
- **K4's test file is sound as written** and `test_the_sets_have_not_been_quietly_emptied`
  is a genuine guard against the empty-set-passes-trivially failure.
- **Rollback claims hold** for what the plan actually changes: no migration, no
  column, `"<sensitive>"` is shape-compatible with the existing `_DROPPED`
  string sentinel, and both kill switches are single-read-site as described.
