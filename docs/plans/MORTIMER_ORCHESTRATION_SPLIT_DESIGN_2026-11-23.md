# Splitting orchestration from Mortimer's voice model: design (2026-11-23)

Asked by Larry, 2026-11-23 19:18 UTC: "splitting the orchastrator from the voice, is that feasible? I think if it is we get better orchastration by using different more capable models for decision making?" Then at 19:19 UTC: "Write the design".

Design only: no repo change, no PR. Code read at `origin/next` **a469553** (the #409 WS-41 merge, which includes #407 WS-40).
Every claim carries a file:line, a measurement, or is marked **untested** with what would test it.
Builds on, and does not redo: `mortimer/voice-streaming-investigation-2026-11-23.md` (the "streaming note") and `mortimer/model-selection-test-plan-2026-11-23.md` (the "test plan").
Companion files: `mortimer/orchestration-split-2026-11-23/orchestrator_latency.py` (timing script), `orchestrator_prompt.txt` (the prompt it used), `run1.json` (raw results).

---

## 0. Answer

**Yes, it's feasible, and I'd build option B: a thin `hand_off` tool on the voice model, and a new text-only `orchestration` workload that picks the agent, writes the brief and sets the model, whose decision the host then runs through the existing `delegate_task` handler.**

- **Why B:** every routing decision moves to a stronger model, while every host guard that checks those decisions today (unknown agent, earned continuation, retry guard, duplicate run, explicit-model resolution, weather scope, workflow result hook) keeps running unchanged, because the orchestrator's output goes through the same handler. The orchestrator is text-only, so it needs no native tool receipt and can never call a tool itself.
- **Main cost:** one extra subscription call per hand-off, and about **2.1 s** more (Opus 5.5 medium, p50, measured here) before the specialist starts. That's 1.7 s for Sonnet 5.5, so the stronger model costs only ~0.5 s over the voice model's own class.
- **The voice gate isn't hit by that time, with one dependency.** Delegated first audio should come from the spoken "one moment" line said before the hand-off. On the current build that line is dropped (streaming note §2), so the streaming/acknowledgement fix has to land first, or the extra time is heard as silence.
- **Option C** (the orchestrator owns the whole job, asynchronously, with WS-38's retry loop and done-check) is where this ends up. B is its first step, not a detour.
- **Quick win, separate:** move the working agents from `claude-sonnet-5` to `claude-sonnet-5-5` (§7). Config only, but read finding F1 first: it affects every tool-using workload on the subscription.

Three things found on the way that matter to any of this:

| | Finding | Evidence | Status |
|---|---|---|---|
| F1 | **One tool receipt can cover only one (model, tool menu) pair per process.** `_validate_native_receipt` reads one file named by one env var and requires its `model`, `tool_names` and schema hash to equal the request's. The voice and every tool-using agent run in the same bot process with different menus, so at most one of them can pass. | jarvis/subscription_tools.py:133-151 (one path from `JARVIS_SUBSCRIPTION_TOOL_CAPABILITY_RECEIPT`, :136; exact `model` :147; exact `tool_names` :151); jarvis/model_routing.py:847-862 builds every tool workload's client on that same check | Code read. **Untested live.** Test: deploy with the voice receipt set, ask something that delegates to scheduler, and look for "native tool acceptance does not match this request". If confirmed, a receipt store keyed by (model, menu digest) is a prerequisite for delegated work on the subscription build at all, split or no split. |
| F2 | **The `effort:` settings in config/agents.yaml do nothing on the subscription route.** The routed provider is `"subscription"`, and effort only applies when the provider is `"anthropic"`. The native tool client would also refuse `extra_body` if it got one. So every agent runs at the CLI's default effort. | jarvis/model_routing.py:746-748; jarvis/effort.py:94; jarvis/subscription_tools.py:576; agents.yaml `effort: low` on scheduler and systems (lines 27, 116) | Code read. Matters for §7 and for any per-role effort choice. Fix belongs with the test plan's P3 (`--effort` in the argv). |
| F3 | **A delegated run holds the voice model's native session open, and that session has a 120 s deadline fixed when it starts.** Developer runs may take 300 s. | jarvis/bot/subscription_llm.py:196 (`timeout_s=120.0`); jarvis/subscription_tools.py:227-228 (deadline set at construction), :410 (gateway reads bounded by it); config/agents.yaml:133 (developer `timeout_s: 300`) | Code read. **Untested** whether a developer run over ~120 s ends the voice turn. Test: a delegated developer task known to take 3 minutes, then check the bot log for a gateway timeout. Option C removes the problem; B leaves it as it is today. |

---

## 1. Today: how a voice turn becomes a delegated job

```
 Larry speaks
     |
     v
 VAD -> Deepgram STT -> VoiceWorkflowInjector (regex guidance)          pipeline.py:2143
     |
     v
+---------------------------------------------------------------+
| VOICE MODEL  (voice_supervisor = claude-sonnet-5-5)            |   model_access.yaml voice_supervisor
| one prompt holds persona AND routing rules                    |   prompts.py:81-93, pipeline.py:1894
|                                                                |
|  decides: answer / direct tool / delegate                     |
|  writes:  agent_name  (enum of 6 agents)                      |   delegate.py:441
|           task        (self-contained brief)                  |   delegate.py:442-449
|           model_profile (only if Larry named one)             |   delegate.py:468-488
|           continuation / findings_path                        |   delegate.py:451-467
|  says:    "One moment..." (rule 1)                            |   prompts.py:81
+---------------------------------------------------------------+
     | delegate_task(...)                           pipeline.py:1979
     v
 HOST GUARDS (code, not model)
   weather scope                                    pipeline.py:1757-1761
   workflow result hook                             voice_workflows.py:256
   unknown agent -> refuse                          delegate.py:560-564
   named model resolved or REFUSED                  delegate.py:577-591
   continuation must be earned                      delegate.py:595
   retry guard on a reworded failed task            delegate.py:602-650
   duplicate pending run -> ALREADY RUNNING         delegate.py:688-694
     |
     v
 SPECIALIST  (SubAgent.run, its own CLI process, its own model)    delegate.py:750-757
   scheduler / librarian / analyst / systems = claude-sonnet-5
   developer / app_builder = claude-opus (Opus 5)
     |
     v  result string (FAILED/REFUSED/NEEDS-INPUT tags)             delegate.py:766-836
 VOICE MODEL speaks the result (same native session, still open)   subscription_llm.py:216-233
```

What the voice model decides on every delegated turn:

1. Whether to delegate at all, or answer, or use a direct tool (`local_weather`, `system_status`, `view_screen`, `ui_control` and the rest, pipeline.py:2042-2066).
2. Which of the six agents (config/agents.yaml).
3. The brief. The schema says "fully self-contained; sub-agents cannot see this conversation" (delegate.py:435-437), so the brief is the only thing the specialist knows about the request.
4. How to split a multi-part request (rule 2, prompts.py:82).
5. What to do after a FAILED result (rule 11, prompts.py:91), and when to re-delegate for a missing detail (rule 13, :93).
6. Routing confirmations with the right `action_id` or `staging_id` (rule 9, :89).
7. Passing a model name only when Larry said one (rule 8, :88).

How much of the voice prompt that takes: rules 2, 3, 4, 8, 9, 11 and 13 are 7,027 characters, and the six agent descriptions another 3,439 (measured from prompts.py and agents.yaml at a469553). The whole exported voice prompt was 18,035 characters (streaming note §5). So roughly 58% of what the voice model reads each turn is routing. (Rule 8 also holds a few non-routing sentences on view changes and result selection.)

**Where it went wrong.** Nov 18, 9:51 PM ET, voice model then Haiku 4.5 (request-resolution note `docs/reviews/2026-11-19-request-resolution-design-note.md` §3; weather self-edit thread notes):

- It added "which is Alpharetta" to the analyst's brief, which rule 11 forbids ("never add details the user did not say"). The weather guard refused it four times, correctly.
- It then briefed the developer to loosen that guard and "start a self-edit". The developer read six files over 79 s and refused: the premise was false.

Both were orchestration decisions made by the model chosen for speed. The specialist (Opus 5) caught the second one, but only after a full run.

**What I can't claim:** the voice model is now Sonnet 5.5, not Haiku 4.5 (model_access.yaml `voice_supervisor`). Whether Sonnet 5.5 repeats these mistakes is **untested**. The test plan's Stage B routing eval (86 cases, 3 runs) measures exactly that, and should run on Sonnet 5.5 voice before anyone claims the split fixes a live problem. The case for the split doesn't rest on it, though: whatever model wins voice is picked for speed, and the routing decisions above don't need speed.

---

## 2. What moves and what stays

| Decision | Today | After the split |
|---|---|---|
| Answer, direct tool, ask a question, or hand off | voice | **voice** (needs to be fast; direct tools are the fast path) |
| Spoken acknowledgement before work | voice | **voice** |
| Which agent(s), how to split a multi-part ask | voice | **orchestrator** |
| The brief, using only Larry's words | voice | **orchestrator** |
| `model_profile` when Larry names a model | voice | **orchestrator** (host still resolves or refuses, delegate.py:577-591) |
| Confirmation routing (`action_id`, `staging_id`), continuation, `findings_path` | voice | **orchestrator** (needs the conversation tail and the last result, see §3 B) |
| Every host guard in §1 | host | **host, unchanged** |
| Speaking the result | voice | **voice** |
| After FAILED: report, ask, never reword-and-retry | voice (rule 11) | B: voice still reports; C: orchestrator decides the next attempt under the WS-38 ledger |

---

## 3. Options

### Option A: second opinion on the brief

The voice model keeps `delegate_task` exactly as today. Before the specialist runs, the host sends Larry's words plus the voice model's `agent_name` and `task` to an orchestrator model, which returns `approve`, `rewrite` (a new brief), `reroute` (another agent) or `ask_user`.

```
 voice --delegate_task(agent, brief)--> [orchestrator reviews] --approve/rewrite/reroute--> host guards --> specialist
                                              |
                                              +--ask_user--> back to voice
```

- **Latency on delegated turns:** + one orchestrator call before the specialist starts (same size as B, §4).
- **Quota per hand-off:** one extra call. The voice model still writes the full brief too, so the brief is written twice.
- **Failure modes:** the reviewer sees the voice model's brief first and may anchor on it (**untested**; a routing eval comparing A's corrected picks with B's fresh picks would show it). Two models own one decision, so a disagreement needs a rule for who wins. The voice prompt keeps all its routing rules.
- **Code:** a hook inside the `delegate_task` handler before `agent.run`, a new workload, a prompt. Smallest of the three, roughly 300-450 lines with tests (estimate from reading the code, not from building it).

### Option B: thin hand-off plus a text orchestrator (pick)

The voice model gets `hand_off` instead of `delegate_task`. Its only argument is an optional one-line `note` (what Larry wants, in the voice model's words). The host supplies the facts the voice model can't be trusted to restate: Larry's exact transcript for this turn (`runtime.voice_state.user_text`, already passed to the delegate tool at pipeline.py:1538), the last few turns, and the last delegated results. The orchestrator returns JSON. The host runs each step through the existing `delegate_task` handler, in parallel where steps are independent, and returns the combined result to the voice model to speak.

```
 Larry: "save a note that the plumber comes Tuesday and remind me Monday night to move the car"
     |
     v
+-------------------------+
| VOICE (fast, Sonnet 5.5)|  says "One moment."  then  hand_off(note="note + reminder")
+-------------------------+
     |                       host attaches: exact transcript, last turns, last results
     v
+--------------------------------------------+
| ORCHESTRATOR (text only, Opus 5.5 medium)  |  no tools, cannot act
| returns:                                   |
| {"steps":[                                 |
|   {"agent_name":"librarian","task":"Save a note: the plumber comes Tuesday.","model_profile":null},
|   {"agent_name":"scheduler","task":"Remind the user Monday night to move the car.","model_profile":null}],
|  "ask_user":null}                          |
+--------------------------------------------+
     |  each step -> existing delegate_task handler (all host guards run)
     v
 librarian ----+
               +--> combined result --> VOICE speaks it
 scheduler ----+
```

(The JSON above is what Sonnet 5.5 and Opus 5.5 actually returned for that sentence in the timing run, give or take wording; both split it into the two agents in all 9 tries.)

- **Latency on delegated turns:** + 2.1 s p50 (Opus 5.5 medium) or 1.7 s (Sonnet 5.5) between the hand-off and the specialist starting (§4). First audio is the acknowledgement, which the voice model says before calling `hand_off`, so the 2.5 s delegated gate is met or missed by the voice model, not the orchestrator. That holds only once the acknowledgement is actually spoken (streaming note §2 and §6.1).
- **Quota per hand-off:** one orchestrator call. Measured here: about 95-120 output tokens per decision on an ~11.3k-character system prompt (~3k tokens), which the CLI caches across calls. Against that, the voice model stops writing the brief, and its prompt loses most of the ~10.5k characters of routing (§1). Relative to a specialist run (several rounds, each with tool schemas and growing context) the orchestrator call is small; the exact ratio is **untested** and the test plan's 5-hour utilisation reading (Stage A) is how to measure it.
- **Failure modes and what handles them:**
  - *Orchestrator times out, errors, or returns bad JSON:* the hand-off returns `FAILED[transient: orchestrator_unavailable]` and the voice model says so. One retry for a transient error; **no silent fallback to the voice model's own pick**, for the same reason agents use `on_profile_fallback: refuse` (base.py:493-503) and routes have `fallback_routes: []`. In the timing run 1 of 54 decisions came back unparseable (§4), so this path is real, not theoretical.
  - *Orchestrator adds a detail Larry didn't say:* same risk as today, with a stronger model. The host can check cheaply that every proper noun in a brief appears in the transcript or the last results (WS-38's "Larry's own words" check, request-resolution note §8). **Untested** how often it fires.
  - *Orchestrator picks an agent outside the roster or a model Larry didn't name:* the existing handler refuses (delegate.py:560-564, 577-591).
  - *Privacy:* the orchestrator sees Larry's words and, for confirmations and continuations, earlier results. It must pass the same `assert_route_allowed` check on the turn's policy that the voice service does (subscription_llm.py:180). On the subscription both are Claude `approved_external`, so nothing new leaves the Mac that the voice model doesn't already see.
  - *Voice hands off when it should have used a direct tool, or vice versa:* still a voice decision, but a much smaller one. The routing eval's `none` category (23 cases) and direct-tool cases measure it.
- **Code** (estimate from reading, not building):

| Piece | Where | Rough size |
|---|---|---|
| `orchestration` workload, `capabilities: [text]`, route `subscription`, `privacy: approved_external`, `priority: interactive`, `fallback_routes: []` | config/model_access.yaml (workloads + `subscription_defaults`) | ~10 lines |
| `claude-opus-5-5` profile (and later `claude-fable-5-2`) | config/model_profiles.yaml | ~10 lines each |
| Orchestrator: prompt built from the agent catalog plus the routing rules moved out of the voice prompt; call through the text route (`SubscriptionTextClient`, jarvis/subscription.py:271-278 argv: `--print`, `--tools ""`); strict JSON schema check; host-side "only Larry's words" check | new `jarvis/agents/orchestration.py` | 200-300 |
| `hand_off` tool: build the orchestrator input from host state, run steps through the existing handler, append a code-written provenance line (`[routed by <model>: librarian, scheduler]`, same idea as F9's `[ran on …]`, delegate.py:766-771) | jarvis/agents/delegate.py | 100-150 |
| Voice prompt: rules 2, 4, 8, 9, 11, 13 cut down to "answer, use a direct tool, ask, or hand off"; agent catalog replaced by one line per capability area | jarvis/prompts.py | net shrink |
| Register `hand_off` instead of `delegate_task` behind a flag (`JARVIS_ORCHESTRATOR_ENABLED`, default off until accepted) | jarvis/bot/pipeline.py:1979, jarvis/bot/tool_schemas.py:47 | 20-40 |
| New voice tool receipt: the voice menu changes, which invalidates the receipt (API-removal thread notes; subscription_tools.py:151-154) | Mac, `scripts/verify_claude_voice_capability.py` once it lands | one run |
| Tests: JSON validation, refusal paths, guard pass-through, multi-step, provenance line, flag off = today's behaviour byte for byte | tests/unit | 250-350 |
| Evals: routing_eval scores the orchestrator's `agent_name` choices on the same cases.yaml; a voice-side eval scores hand off vs direct vs answer | tests/evals/routing_eval.py, cases.yaml | 80-150 |

  Total roughly 700-1,000 changed lines with tests. The orchestrator being text-only is deliberate: it needs no native tool receipt (F1 doesn't bite it), it can never execute anything itself, and it opens Codex (`gpt-6.2-astra`) as a candidate, since the Codex route is text-only (model_access.yaml `codex_subscription.capabilities: [text]`).

### Option C: the orchestrator owns the job

`hand_off` returns at once ("on it"). The orchestrator runs the request in the background: dispatches, reads results, decides the next attempt under WS-38's attempt ledger (3B), runs the done-check (4C), and delivers the answer through the existing late-delivery path (delegate.py:874-950 and the outbox at :332-339). The voice model is free to talk about something else meanwhile.

```
 voice --"One moment." + hand_off--> returns "accepted" at once; voice turn ends
                                         |
                                         v
                         ORCHESTRATOR LOOP (background)
                     +--> decide step --> host guards --> specialist
                     |          ^                             |
                     |          +--- classify failure (2A) <--+
                     |               transient: retry once
                     |               approach: new approach, ledger budget (3B)
                     |               policy: stop and ask
                     +--> done-check against Larry's words (4C)
                                         |
                                         v
                late delivery --> voice speaks the result when it lands
```

- **Latency:** the voice turn ends fastest of the three (no waiting on the specialist), and F3 goes away because no voice session is held open. Time to the answer is B's plus any retries.
- **Quota per hand-off:** B's call plus one per further attempt and one per model done-check. Bounded by the ledger's try budget (request-resolution note §7).
- **Failure modes:** the conversation contract changes: answers arrive later, possibly after Larry has moved on, so the late-delivery wording and the "don't start it again" control text (delegate.py:545) carry more weight. A loop that runs a write, send or self-edit must stop for Larry; that needs per-tool side-effect classes, which don't exist yet (request-resolution note §7, "Side effects end the loop").
- **Code:** B, plus WS-38 3B (ledger), side-effect classes and 4C. The request-resolution note sizes 3B as M-L and 4C as M. Not buildable before those land.

The request-resolution note rejected a host-run loop (3A) because "the host doesn't know the alternatives; it would guess, or need a model, which makes it a second supervisor" (§7, 3A row), and listed 3B's weakness as "still relies on the supervisor model to pick a good next approach". The orchestrator in B is that second supervisor, on a stronger model. So B makes 3B better when it lands, and C is B plus 3B plus 4C.

---

## 4. Measurements: how long an orchestrator decision takes

Run here, 2026-11-23 ~19:40-19:50 UTC, from this cloud container through its proxy, Claude Code CLI **2.1.330** (not Mortimer's pinned 2.1.291), on this session's subscription login with no API key, fresh process per call (the text route's shape), Mortimer's isolation env. System prompt: the real agent catalog plus the voice prompt's routing rules plus a JSON output contract, 11,344 characters (`orchestrator_prompt.txt`). Input: a two-line conversation tail plus the utterance. Six delegated utterances (five from the test plan's Appendix B delegated list or close to it, one two-part request), 3 reps each, shuffled across configs, one warm-up discarded. Times are from process spawn to the CLI's `result` event, i.e. start-up included.

| Config | n | Start-up p50 | Decision p50 | p90 (approx.) | Max | CLI's own API time p50 | Output tokens p50 | JSON parsed | Agent(s) as expected |
|---|---|---|---|---|---|---|---|---|---|
| Sonnet 5.5, default effort | 18 | 478 ms | **1.67 s** | 2.32 s | 2.48 s | 1.16 s | 95 | 18/18 | 18/18 |
| Opus 5.5, `--effort low` | 18 | 470 ms | **1.97 s** | 2.40 s | 2.59 s | 1.47 s | 102 | 18/18 | 18/18 |
| Opus 5.5, `--effort medium` | 18 | 469 ms | **2.14 s** | 2.62 s | 3.33 s | 1.62 s | 121 | 17/18 | 17/18 |

The two-part request (librarian + scheduler) is the slow one on every config: Sonnet 5.5 1.60-2.48 s, Opus low 1.86-2.59 s, Opus medium 2.58-3.33 s (3 tries each, all split correctly).

What the numbers say:

- An orchestrator decision costs about **2 s** on Opus 5.5 and **1.7 s** on Sonnet 5.5, from process start. About 0.47 s of each is CLI start-up, which the streaming note's pre-start trick (a CLI process started ahead and kept waiting) cuts to ~30 ms on the Mac (streaming note §3). With that, Opus 5.5 medium would be ~1.7 s and Sonnet ~1.2 s [likely; not measured with pre-start here].
- Opus over Sonnet costs ~0.3 s (low) to ~0.5 s (medium) at p50. That's the price of the stronger model, and it's small next to a specialist run.
- The one failure: Opus 5.5 medium, "why did the last weather lookup fail", wrote one sentence of prose ("Troubleshooting goes to the developer.") and then valid JSON with the right agent. The script's strict parser rejected it. So the host must either pull the first JSON object out of the reply or refuse and say so; either way it's a real case for the bad-JSON path in §3 B, not a hypothetical. A stricter output contract in the prompt is the cheap first fix [likely; untested].
- None of the picks were wrong, but six easy utterances say nothing about routing accuracy (see caveats).

Fable 5.2 was **not** run: the test plan (§0.7, §4.1) says Fable may draw usage credits instead of plan limits depending on the plan, and that has to be checked on Larry's `/model` screen first (Stage 0). Anthropic labels Fable 5.2 "Moderate" latency, the same label as Opus 5.5 (test plan §2.1), so I'd expect it in the same range, but that's **untested**.

Caveats: n = 3 per (config, utterance), 18 per config, so differences under ~300 ms are noise. Agent picks were scored against one expected answer per utterance, which is a smoke check that the JSON contract works, not a routing-accuracy result. Six easy utterances can't separate Sonnet from Opus on routing quality; the 86-case routing eval can.

---

## 5. Pick: B now, grown into C

| | A. Second opinion | **B. Hand-off + text orchestrator** | C. Orchestrator owns the job |
|---|---|---|---|
| Who decides routing | voice, then checked | **orchestrator** | orchestrator |
| Added time before the specialist starts | one call | **one call (~2.1 s Opus 5.5 medium)** | one call, plus retries later |
| Extra quota per hand-off | one call, brief written twice | **one call** | one call plus loop calls |
| Voice prompt | unchanged | **~half smaller** | ~half smaller |
| Host guards | unchanged | **unchanged, same handler** | unchanged, plus ledger |
| Needs WS-38 3B/4C first | no | **no** | yes |
| Needs the spoken acknowledgement fixed first | yes | **yes** | yes |
| Rough size | 300-450 lines | **700-1,000 lines** | B + WS-38 3B + 4C |

**Why B over A:** A keeps the routing rules on the fast model and pays for two models to write one brief. B moves the decision cleanly and the host keeps every check it has.

**Why B before C:** C depends on work that isn't built (3B ledger, side-effect classes, 4C). B is the part of C that's useful on its own, and none of it is thrown away when C comes.

**Orchestrator model:** start on **Opus 5.5 at medium** (`claude-opus-5-5`). It runs on the pinned CLI 2.1.291 (streaming note §4; API-removal thread checked the binary's strings), so no CLI bump is needed, and it's the test plan's planner candidate that is usable today. Move to Fable 5.2 only if the test plan's §5 corpus or a routing eval shows a gain and Stage 0 shows it draws plan limits, not usage credits. Fable 5.2 needs CLI ≥ 2.1.321 and new receipts (test plan §2.1). [likely] Opus at `low` is a fallback if quota turns out to be the constraint; it measured 2.0 s here.

**Main cost, in one line:** about 2.1 s more before work starts on every hand-off, plus one Opus call of subscription quota each time.

**Order of work:**
1. Confirm or clear F1 (one live test). If confirmed, a keyed receipt store first, because without it delegated work can't run on the subscription build at all.
2. The streaming note's acknowledgement fix (its §2, small, owned by the voice-receipt / API-removal work).
3. B behind its flag, with the routing eval pointed at the orchestrator (needs the test plan's H1 adapter, `Orchestrator(client_factory=...)`, jarvis/agents/supervisor.py:59-115, which today refuses a subscription client, :115-123).
4. Live: `scripts/latency_probe.py --budget` on a 40-turn session (test plan Appendix B), plus the 86-case routing eval, flag on vs off.
5. C when WS-38 3B and 4C land.

---

## 6. How it fits the daily model-sync check (WS-41, #409) and the test plan

**WS-41.**
- Detect: `pins.py` scans every model ID in tracked `config/**/*.yaml` (jarvis/model_sync/pins.py:1-3, `scan_config`). The new `orchestration` workload's profile is picked up with no WS-41 change, and `propose.py` would open a PR editing that ID like any other.
- Certify: today only the voice role has a role gate (`voice_bench`, jarvis/model_sync/certify.py:49-66, 159-164); every other role gets the exact-ID probe and a manual receipt step (:98-103). An orchestrator role should get its own gate before a PR is proposed: the orchestrator decision latency (this note's script, p90 under a budget Larry sets, e.g. 4 s) and the routing eval on cases.yaml through the orchestrator (≥ 90%, the existing exit gate, tests/evals/routing_eval.py:30). That's a `roles: ["orchestrator"]` branch in `certify.py`, ~40 lines, plus H1.
- The voice role's gate gets simpler: once routing leaves the voice prompt, a new voice candidate needs latency plus "hand off or not" accuracy, not full agent routing.

**Test plan.**
- It has three roles: voice, planner, council (§0.1). The split adds a fourth, **orchestrator**: text only, interactive, latency-bound (unlike the planner's 300 s), judged on routing.
- Candidates: the planner list (`claude-fable-5-2`, `claude-opus-5-5`, `gpt-6.2-astra`) plus `claude-sonnet-5-5` as the speed baseline. Astra is possible because the orchestrator is text only; its decision latency through `codex exec` is **untested**.
- New stage, "Stage O": `orchestrator_latency.py` for latency (this note), then Stage B's routing eval (86 cases × 3 runs) scored on the orchestrator's picks. The best-fit rule is the test plan's §3, with the orchestrator's hard gates being routing ≥ 90% and the three known-miss cases ≥ 2/3, and its tie-break being quota, as for orchestration roles there.
- Stage A and Stage C are unchanged. Stage C's delegated turns then measure the whole chain with the orchestrator in it.

---

## 7. Quick win: working agents from Sonnet 5 to Sonnet 5.5

Separate from the split; can go first.

- **What changes:** in config/model_access.yaml, `profile: claude-sonnet-5` → `claude-sonnet-5-5` for `scheduler`, `librarian`, `analyst`, `systems`, and the text workloads `memory`, `background`, `research_synthesis`. With routing on, these workload entries win over agents.yaml (base.py:455-462, "Saved workload selections must win"); change agents.yaml's `model_profile` lines too so the startup default matches.
- **Leave out:** `council` (its member choice is the test plan's §6 job, and the council enforces one vote per model identity) and `memory_shadow` (public-fixture twin of `memory`; change it together with `memory` or not at all).
- **Works on the pinned CLI:** 2.1.291 knows `claude-sonnet-5-5` (streaming note §4, live; API-removal notes, binary strings).
- **Tests:** tests/unit/test_model_floor.py only forbids Haiku for agents and requires the `claude-sonnet-5` profile to exist (:35, :108-123), so keep that profile in the registry and the floor tests pass.
- **Receipts:** a tool workload's receipt binds its model (subscription_tools.py:147), so each changed tool agent needs a new receipt. With F1 as it stands, only one of them can be active at a time anyway.
- **Not a change in effort:** because of F2, agents.yaml's `effort: low/medium` lines don't apply on the subscription, before or after this.
- **What I can't claim:** that Sonnet 5.5 does Mortimer's agent work better than Sonnet 5, or how its quota weight compares. Both are **untested**. Neither model retires soon: the deprecations fixture lists Sonnet 5 "not sooner than June 30, 2027" (tests/fixtures/model_sync/anthropic-model-deprecations.md:91), so this is about capability, not a deadline.
- **Same shape, bigger:** `developer`, `app_builder` and `vision` run `claude-opus` = Opus 5 (model_profiles.yaml:78-82). Moving them to Opus 5.5 is the same kind of edit, but developer runs self-edits, so I'd do it after the Sonnet move has been used for a few days.
- **Size:** ~10 config lines, one PR.

---

## 8. Not verified

- F1, F2 and F3 are code reads, not live runs. Each has its test in the table in §0.
- All timings come from a cloud container on CLI 2.1.330, not Larry's Mac on 2.1.291. The Mac run of `orchestrator_latency.py` (§9) settles the numbers for his setup.
- Whether Sonnet 5.5 as the voice model still makes the routing mistakes Haiku 4.5 made on Nov 18.
- Routing accuracy of any orchestrator model on the 86-case eval (needs H1).
- Fable 5.2 and `gpt-6.2-astra` as orchestrators: not run.
- Quota per hand-off as a share of the 5-hour window.
- How often an orchestrator brief would add a detail Larry didn't say, and whether a host proper-noun check catches it.
- The code sizes in §3 are estimates from reading the code.

---

## 9. Running the timing on the Mac

From the test plan's bench folder (`~/mortimer-bench`, test plan §8.1):

1. Download `mortimer/orchestration-split-2026-11-23/orchestrator_latency.py` and `orchestrator_prompt.txt` (if they land as `.txt`, use those names):
   ```bash
   mv ~/Downloads/orchestrator_latency.py ~/Downloads/orchestrator_prompt.txt ~/mortimer-bench/
   ```
2. Run it (about 5 minutes, 54 small calls of subscription quota, never an API key). The script calls `claude` on your PATH; put the bench CLI first if you want the side-by-side one:
   ```bash
   cd ~/mortimer-bench
   env -u ANTHROPIC_API_KEY python3 orchestrator_latency.py \
     --system-file orchestrator_prompt.txt \
     --configs claude-sonnet-5-5,claude-opus-5-5:low,claude-opus-5-5:medium \
     --reps 3 --out ~/mortimer-bench/orchestrator-latency.json
   ```
3. Send the JSON.

---

## 10. Decisions for Larry

1. Build option B (hand-off plus a text orchestrator), behind a flag, after the acknowledgement fix?
2. Orchestrator model to start: Opus 5.5 at medium, or wait for Fable 5.2 (CLI bump plus the usage-credit check)?
3. Run the one live test for F1 now? It decides whether a receipt store comes before everything else.
4. Quick win: Sonnet 5 → 5.5 for the four agents and three text workloads now, as its own small PR?
