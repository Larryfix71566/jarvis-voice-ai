# Eval / production configuration parity

Status: **SCOPE — not approved, no code written.** Drafted 2026-09-05.

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

**A. Extract prompt assembly.** Move `pipeline.py:497–515` behind
`build_supervisor_prompt`. Pin with a test asserting the assembled prompt
is byte-identical to today's for the same flags. Pure refactor.

**B. Extract tool-schema assembly.** Same treatment for
`pipeline.py:662–676`, same byte-identical pinning test. Pure refactor.

A and B are provable no-ops. They are the de-risking step and should land
and be verified before anything below.

**C. Teach the Orchestrator more than one tool.** `_tools_kwarg` takes an
optional extra-schema list; `_execute_tool` consults an optional handler
map before falling through to its current message. Both default empty, so
`cli.py` and the three existing test modules are unaffected.

**D. Point the eval at the production configuration.** Build the prompt
and schemas from A and B, bind stubs that record the tool name and return
a fixed result, print the chosen tool on every case. This is simultaneously
the observability the eval has always lacked: the stub *is* the probe.

**E. Production observability.** Emit the direct tool name in
`adapt_to_pipecat`. Independent of A–D and worth landing on its own.

**F. Re-baseline and set floors.** Run `RUN_LIVE=1` under the declared
configuration, record the per-category table, populate `CATEGORY_FLOORS`
from that observed run.

## Open questions — these need Larry's call, not mine

1. **Which flag configuration is canonical for the eval?** Default-on
   matches production default, but the eval should print the configuration
   it ran under so a number is never orphaned from its config.
2. **What should the stub handlers return?** A stub answering `"ok"` to
   `ui_control` continues the conversation differently than production
   would. For single-turn routing cases this likely does not matter, but it
   is an assumption, not a finding.
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
