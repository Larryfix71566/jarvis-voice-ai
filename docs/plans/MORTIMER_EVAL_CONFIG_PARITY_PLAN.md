# Eval / production configuration parity

Status: **A–E DONE. F: first parity run recorded 2026-09-05; floors
still unset pending a second run.**

## The problem

`tests/evals/routing_eval.py` does not measure Mortimer. It measures a
harness that shares the base prompt and one tool with production and
differs in everything else.

| | eval (`Orchestrator`) | live (`pipeline.py`) |
|---|---|---|
| system prompt | `SUPERVISOR_PROMPT` only — `supervisor.py:92` | `SUPERVISOR_PROMPT` + `VOICE_ADDENDUM` + `UI_CONTROL_ADDENDUM` + `SCREEN_VISION_ADDENDUM` + `HANDOFF_ADDENDUM` — `pipeline.py:497–515` |
| tools the model sees | `[self._delegate_schema]` — one — `supervisor.py:196` | ten (below) — `pipeline.py:662–676` |
| voice catalog | `"(none configured yet)"` — `supervisor.py:97` | real catalog |

`pipeline.py` never constructs an `Orchestrator`; its only mention of the
name is a comment on line 979. `Orchestrator` is used by `cli.py`, three
test modules, and the eval.

**Why this is not cosmetic.** In the eval the model has exactly one place
to put any intent it wants to act on: `delegate_task`, or nothing. In
production it has nine alternatives competing for the same intent. The
eval therefore cannot observe competing-tool confusion at all, and every
miss it records is "answered instead of delegating" in a world where
delegating was the only option. Tuning `SUPERVISOR_PROMPT` to move the
eval number optimises for a configuration that is never shipped, and can
degrade live routing, which reads three addenda the eval never sees.

## Findings that shape the design

1. **All three kill switches default to ON.** `os.environ.get(NAME, "")`
   with `not in ("false", "0", "no")` means an unset variable enables the
   feature (`pipeline.py:389–415`). Default production is therefore four
   addenda and ten tools: `delegate_task`, `set_voice`, `remember`,
   `cost_summary`, `show_commands` (all unconditional) plus `ui_control`,
   `view_screen`, `list_screens`, `clear_clipboard`, `read_clipboard`
   (flagged, default on).
2. **Routing depends on the schemas and the prompt, not the handlers.**
   What the model sees decides what it picks; a handler only matters once
   a tool is actually called. Splitting schema assembly from handler
   binding is what makes parity reachable without a live transport.
3. **The Orchestrator hard-codes one tool in delegating mode.**
   `_tools_kwarg` returns `[self._delegate_schema]` and `_execute_tool`
   answers anything else with `"Unknown tool ... Use delegate_task."`
   (`supervisor.py:187–196`). This is the real work.
4. **`adapt_to_pipecat` is a single chokepoint** for every direct-tool
   handler (`pipeline.py:472`, used at `615–632`). Production currently
   observes nothing when the Supervisor calls a direct tool instead of
   delegating; one emit there closes that.
5. **`show_commands` is unconditional** while the other five are flagged —
   easy to miss when reconstructing the tool set by hand, which is
   precisely the drift this plan exists to stop.

## Proposed seam

One module holding two pure functions, both taking flags explicitly:

- `build_supervisor_prompt(settings, agent_catalog, voice_catalog, memory_context, *, voice, ui_control, screen, clipboard) -> str`
- `direct_tool_schemas(*, ui_control, screen, clipboard, ...) -> list[dict]`

`pipeline.py` calls both and then binds handlers as it does today. The
eval calls both and binds recording stubs. Neither side reconstructs the
other's configuration by hand, which is the only way this stops drifting
a third time.

## Work items, in order

**A. Extract prompt assembly. — DONE.** `build_supervisor_prompt` now
lives in `jarvis/prompts.py`, beside the strings it assembles, which is
where this module's own docstring always claimed the single source of
truth was. Both callers use it: `pipeline.py` passes `voice=True` plus its
three kill switches, `supervisor.py` passes nothing and every flag
defaults `False`, reproducing its bare prompt. Verified byte-identical
across all sixteen flag combinations, and pinned by eight tests in
`tests/unit/test_prompts.py` — including the old `pipeline.py` expression
transcribed literally, so addendum order or the `"\n"` separator drifting
fails the suite.

**B. Extract tool-schema assembly. — DONE.** `supervisor_tool_schemas`
lives in `jarvis/bot/tool_schemas.py`. Every direct-tool schema turned out
to be a module-level constant its `build_*_tool` factory returns
unchanged, so the menu separates cleanly from the handlers — which is what
makes an offline caller possible at all, since handlers need a live
transport while routing depends only on what the model can see.
`pipeline.py` now maps `to_function_schema` over the shared menu and its
nine schema locals are gone. Verified identical to the old literal list
across all eight switch combinations; nine tests in
`tests/unit/test_tool_schemas.py` pin the order, the contents at every
combination, and that a menu entry IS the object its factory returns, so
the two cannot drift apart again.

A and B are provable no-ops. They were the de-risking step and both are
verified; C onward changes behaviour.

**C. Teach the Orchestrator more than one tool. — DONE.** `extra_tools`
takes `(schema, handler)` PAIRS rather than a schema list plus a separate
handler map, so a caller cannot show the model a tool it cannot answer.
Three things are refused rather than accepted quietly: shadowing
`delegate_task` (a routing eval would score the shadow and report it as a
delegation), a duplicate tool name, and passing extras in direct mode
(accepting and ignoring them would leave the caller believing the model
saw tools it never received). Sync and async handlers both work — every
production handler is async, eval stubs are simpler sync.

It also closes half of item E: `_execute_tool` now emits
`{"type": "supervisor_tool", "tool": ...}` for every tool it runs, and a
raising observer is caught rather than allowed to break the turn. Note
this is the **Orchestrator** half only. Production does not use this class,
so `pipeline.py` still observes nothing when the Supervisor calls a direct
tool; item E remains open for that path.

Empty extras is the default and reproduces the old behaviour, pinned by
the pre-existing `test_only_delegate_tool_is_offered`; nine new tests in
`TestExtraTools` cover the opt-in.

**D. Point the eval at the production configuration. — DONE.**
`EVAL_PROFILE` selects a named profile; `parity` is the default and is
what ships with no kill switch set. An unknown name is fatal rather than
silently defaulted, because a typo that quietly ran `parity` would credit
one configuration's number to another — the exact confusion this plan
exists to end. Every run prints its profile, tool count and addenda above
the result, so a number can never be read without its configuration.

A profile carries `addenda` and `tools` as SEPARATE switches. Four tools
ship even with every kill switch off, so "no addenda" and "no tools" are
different states; folding them together would make `delegate-only`
inexpressible the moment any flag was on.

Stubs answer `"ok"` and the tool sequence is printed under every miss,
sourced from the `supervisor_tool` events item C added rather than from
stub bookkeeping. `CATEGORY_FLOORS` is now scoped by
`CATEGORY_FLOORS_PROFILE`: floors measured under one profile are skipped,
loudly, when another runs. The aggregate threshold still applies.

**E. Production observability. — DONE, both halves.** Item C made the
Orchestrator emit `supervisor_tool`, which is what the eval reads. For the
shipped path, `adapt_to_pipecat` moved from a closure inside
`build_pipeline` to module scope, gained the tool's name, and logs
`supervisor_tool tool=<name>` before dispatch — before, so a tool that
raises is still in the log, which is the case most worth having. Lifting
it out of the closure is also what made it testable at all; that behaviour
had no test because it could not be imported.

`register_supervisor_tool` replaces the ten
`llm.register_function(name, adapt_to_pipecat(handler))` lines so the name
is written once. Passing it twice invites a handler registered under the
wrong spelling, which fails only at call time and only in production.

**F. Re-baseline and set floors. — FIRST RUN DONE 2026-09-05; floors still
unset.** `RUN_LIVE=1`, profile `parity`, model `claude-haiku-4-5`.

    Routing accuracy: 63/70 = 90%
      none        23/23  100%     analyst    5/5  100%
      developer   17/22   77%     scheduler  5/5  100%
      librarian    4/6    67%     systems    5/5  100%
                                  multi      4/4  100%

The aggregate did not move. The composition did, completely.

**Three of the seven old misses now pass**: #26 (darker theme), #30
(Claude's frontier model) and #59 (build status) all delegate correctly
under parity. Every explanation previously offered for those three was
wrong, not merely unproven — they were artifacts of the one-tool harness.

**Two new misses are competing-tool confusion**, which the old eval was
structurally incapable of observing: #6 and #10 both expect `librarian`
and both called the direct `remember` tool instead (#10 called it twice).
Whether the model or the case is wrong is a spec question — the prompt
does say to call `remember` immediately on a durable statement — and it
decides everything about `librarian` at 4/6.

**Two developer misses are worse than routing misses.** #25 asserted the
app registry is empty and #28 asserted no self-edit was running, both
having called no tool at all. Each case gets a fresh Orchestrator, so
their claims about *conversation* history are true; what they invented is
durable SYSTEM state, which lives outside the conversation and can only be
known by asking. Golden Rule 1 covers this in principle and did not fire.
#25 also named the developer specialist to the user, which Rule 4 forbids
and Rule 10's own example licenses — contradiction 1, observed live.

**#56, #66 and #68 asked a clarifying question instead of delegating**,
which is Rule 4 doing exactly what it says against Rule 8's "always
delegated to developer". A sixth contradiction, and the first evidenced by
a run rather than by reading.

**Floors remain unset deliberately: this is n=1.** The pre-parity misses
were byte-identical across two runs, but that was a different
configuration and the property does not transfer.

**The run mutated the machine.** Case 26 POSTed `/api/selfedit/stage` and
`/api/selfedit/run`; case 62 asked to cancel a build. The temp-db
isolation never covered the sidecar — a separate process reached over
HTTP. `isolate_selfedit_service()` now points `JARVIS_ADMIN_URL` at
`127.0.0.1:1` before the registry starts, so children inherit it and the
tool returns its own OFFLINE_ERROR. Opt-OUT via
`EVAL_ALLOW_LIVE_SELFEDIT=1`, so forgetting costs a degraded sub-agent
rather than a real self-edit.

## Decisions (Larry, 2026-09-05)

1. **Configuration: parameterized, defaulting to parity.** One profile
   selector chooses a named configuration; the default is production
   default — `VOICE` + `UI_CONTROL` + `SCREEN_VISION` + `HANDOFF` addenda
   and all ten tools. The configuration is printed above every result, so
   a number can never be read without the config that produced it. The
   selector costs nothing over a fixed choice because A and B take flags
   explicitly anyway, and it is what makes "does this addendum cost
   routing accuracy?" answerable by toggling rather than editing.
2. **Stubs return a neutral `"ok"`, and every tool call is logged.**
   Scoring stays on the delegation set. The diagnostic signal is that the
   model reached for `ui_control` at all, which the log captures whatever
   the stub returns — so the stub's content does not have to be
   production-faithful to be useful, and we are not inventing plausible
   tool results.
*(A third question — whether `set_voice`'s schema embeds the voice catalog
— was checked rather than left open. It does not: `build_set_voice_tool`
returns the module-level `SET_VOICE_SCHEMA` and uses the catalog only
inside the handler, `voice_switch.py:70–92`. The schema side needs no
catalog. The **prompt** side still does: `{voice_catalog}` is interpolated
into `SUPERVISOR_PROMPT`, and the eval passes `"(none configured yet)"`
where production passes `catalog_summary(catalog)`. That gap is real and
work item A covers it.)*

## Expected outcome, stated in advance

**The number will move, and probably down.** Nine additional tools
competing for the same intent is strictly more opportunity to route
elsewhere. That is not a regression — it is the first honest measurement,
and 63/70 was never a measurement of production. Do not compare the two.

## Explicitly out of scope

- The five `SUPERVISOR_PROMPT` self-contradictions. Separate track; they
  are defects on their own terms.
- Any attempt to fix developer routing. There is no evidence yet about why
  it misses, and this plan is what produces that evidence.
