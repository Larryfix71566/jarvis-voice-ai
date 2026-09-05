"""The Supervisor's visible tool menu (jarvis/bot/tool_schemas.py).

MORTIMER_EVAL_CONFIG_PARITY_PLAN.md item B. The menu was a literal list
inside build_pipeline, so the only other thing that needed it — the
Orchestrator the routing eval drives — reconstructed it as a single tool
and scored routing in a one-tool world for as long as the eval existed.

These pin the extraction as a no-op: the order, the contents at every
flag combination, and the fact that a schema in the menu is the very
object its build_*_tool factory hands back, so the two cannot drift.
"""

from __future__ import annotations

import itertools

import pytest

from jarvis.bot.costs_tool import COST_SUMMARY_SCHEMA, build_cost_summary_tool
from jarvis.bot.handoff_tools import (
    CLEAR_CLIPBOARD_SCHEMA,
    READ_CLIPBOARD_SCHEMA,
    SHOW_COMMANDS_SCHEMA,
)
from jarvis.bot.remember_tool import REMEMBER_SCHEMA
from jarvis.bot.screen_tool import LIST_SCREENS_SCHEMA, VIEW_SCREEN_SCHEMA
from jarvis.bot.tool_schemas import supervisor_tool_schemas
from jarvis.bot.ui_control import UI_CONTROL_SCHEMA
from jarvis.bot.voice_switch import SET_VOICE_SCHEMA

DELEGATE = {"type": "function", "function": {"name": "delegate_task"}}


def _names(**flags):
    return [s["function"]["name"] for s in supervisor_tool_schemas(DELEGATE, **flags)]


def test_the_default_menu_is_the_five_unconditional_tools():
    assert _names() == [
        "delegate_task", "set_voice", "remember", "cost_summary",
        "show_commands",
    ]


def test_everything_on_reproduces_the_list_pipeline_py_built():
    # Transcribed from the literal pipeline.py used to build. Order is
    # load-bearing: a reordered tool list is a different prompt to the
    # model even when the contents match.
    assert supervisor_tool_schemas(
        DELEGATE, ui_control=True, screen=True, clipboard=True
    ) == [
        DELEGATE,
        SET_VOICE_SCHEMA,
        REMEMBER_SCHEMA,
        COST_SUMMARY_SCHEMA,
        UI_CONTROL_SCHEMA,
        VIEW_SCREEN_SCHEMA,
        LIST_SCREENS_SCHEMA,
        SHOW_COMMANDS_SCHEMA,
        CLEAR_CLIPBOARD_SCHEMA,
        READ_CLIPBOARD_SCHEMA,
    ]


def test_show_commands_ships_even_with_every_switch_off():
    # H3/H6: show_commands always registers; only the clipboard half is
    # gated. This is the one an ad-hoc reconstruction of the menu drops.
    assert "show_commands" in _names()
    assert "clear_clipboard" not in _names()


@pytest.mark.parametrize(
    "flag,added",
    [
        ("ui_control", ["ui_control"]),
        ("screen", ["view_screen", "list_screens"]),
        ("clipboard", ["clear_clipboard", "read_clipboard"]),
    ],
)
def test_each_switch_adds_exactly_its_own_tools(flag, added):
    base = _names()
    assert sorted(set(_names(**{flag: True})) - set(base)) == sorted(added)


def test_a_disabled_tool_is_absent_not_merely_last():
    # The model cannot call what it cannot see; "off" has to mean gone.
    off = _names(ui_control=False, screen=False, clipboard=False)
    for name in ("ui_control", "view_screen", "list_screens",
                 "clear_clipboard", "read_clipboard"):
        assert name not in off


def test_every_combination_keeps_a_stable_relative_order():
    canonical = supervisor_tool_schemas(
        DELEGATE, ui_control=True, screen=True, clipboard=True
    )
    rank = {id(s): i for i, s in enumerate(canonical)}
    for u, sc, c in itertools.product([False, True], repeat=3):
        got = supervisor_tool_schemas(
            DELEGATE, ui_control=u, screen=sc, clipboard=c
        )
        ranks = [rank[id(s)] for s in got]
        assert ranks == sorted(ranks), (u, sc, c)


def test_the_menu_holds_the_object_the_factory_returns():
    # If the menu ever held a copy, a schema could be edited in one place
    # and stale in the other — which is the class of drift this module
    # exists to end.
    schema, _handler = build_cost_summary_tool()
    assert schema is COST_SUMMARY_SCHEMA
    assert supervisor_tool_schemas(DELEGATE)[3] is COST_SUMMARY_SCHEMA


def test_the_menu_can_omit_delegate_task_for_a_caller_that_owns_it():
    # The Orchestrator builds its own delegate schema from the live
    # sub-agent roster; handing it a second one would show the model two.
    names = [s["function"]["name"]
             for s in supervisor_tool_schemas(
                 None, ui_control=True, screen=True, clipboard=True)]
    assert "delegate_task" not in names
    assert names == [
        "set_voice", "remember", "cost_summary", "ui_control",
        "view_screen", "list_screens", "show_commands",
        "clear_clipboard", "read_clipboard",
    ]


def test_omitting_delegate_task_changes_nothing_else_about_the_order():
    with_it = supervisor_tool_schemas(DELEGATE, ui_control=True, screen=True,
                                      clipboard=True)
    without = supervisor_tool_schemas(None, ui_control=True, screen=True,
                                      clipboard=True)
    assert without == with_it[1:]
