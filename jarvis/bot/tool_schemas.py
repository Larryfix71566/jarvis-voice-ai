"""The Supervisor's visible tool menu, assembled in one place.

MORTIMER_EVAL_CONFIG_PARITY_PLAN.md item B. The menu used to exist only
as a literal list inside `build_pipeline` (jarvis/bot/pipeline.py), so
anything else wanting to know what the Supervisor can see had to
reconstruct it by hand — and the one thing that did, the Orchestrator the
routing eval drives, exposed a single tool instead of ten and nobody
noticed for as long as the eval has existed.

Every schema here is a module-level constant that its `build_*_tool`
factory returns unchanged, so the menu is separable from the handlers.
That matters: the handlers need a live transport and a session, while
routing depends only on what the model can SEE. An offline caller can
therefore ask for production's exact menu and bind whatever handlers it
likes.

Two things are load-bearing and pinned by tests:

* **Order.** It reproduces the list `pipeline.py` built, because a
  reordered tool list is a different prompt to the model even when the
  contents match.
* **`show_commands` is unconditional.** The other five optional tools sit
  behind kill switches; this one does not, and reconstructing the menu by
  hand is exactly how that gets missed (H3/H6 — show_commands always
  registers, while only the clipboard half is gated).
"""

from __future__ import annotations

from jarvis.bot.costs_tool import COST_SUMMARY_SCHEMA
from jarvis.bot.handoff_tools import (
    CLEAR_CLIPBOARD_SCHEMA,
    READ_CLIPBOARD_SCHEMA,
    SHOW_COMMANDS_SCHEMA,
)
from jarvis.bot.remember_tool import REMEMBER_SCHEMA
from jarvis.bot.screen_tool import LIST_SCREENS_SCHEMA, VIEW_SCREEN_SCHEMA
from jarvis.bot.ui_control import UI_CONTROL_SCHEMA
from jarvis.bot.voice_switch import SET_VOICE_SCHEMA


def supervisor_tool_schemas(
    delegate_schema: dict | None,
    *,
    ui_control: bool = False,
    screen: bool = False,
    clipboard: bool = False,
) -> list[dict]:
    """OpenAI-style tool schemas the Supervisor sees, for one configuration.

    `delegate_schema` is passed in rather than imported: it is built from
    the live sub-agent roster (the `agent_name` enum), so it is the one
    entry that cannot be a constant. Pass None to get the menu WITHOUT it —
    for a caller that already owns its own delegate schema and would
    otherwise end up showing the model two of them. The rest of the order
    is unchanged either way.

    The flags are the same kill switches that decide registration, so a
    caller cannot show the model a tool it did not register — or register
    one it did not describe in the prompt.
    """
    schemas: list[dict] = [
        *( [delegate_schema] if delegate_schema is not None else [] ),
        SET_VOICE_SCHEMA,
        REMEMBER_SCHEMA,
        COST_SUMMARY_SCHEMA,
    ]
    if ui_control:
        schemas.append(UI_CONTROL_SCHEMA)
    if screen:
        schemas.append(VIEW_SCREEN_SCHEMA)
        schemas.append(LIST_SCREENS_SCHEMA)
    # Unconditional on purpose — see the module docstring.
    schemas.append(SHOW_COMMANDS_SCHEMA)
    if clipboard:
        schemas.append(CLEAR_CLIPBOARD_SCHEMA)
        schemas.append(READ_CLIPBOARD_SCHEMA)
    return schemas
