"""Direct-tool registration and its log line (jarvis/bot/pipeline.py).

MORTIMER_EVAL_CONFIG_PARITY_PLAN.md item E. Nothing anywhere recorded the
Supervisor calling a DIRECT tool. agent_tool belongs to the sub-agents
(jarvis/agents/base.py) and so never fires on a turn that delegated
nothing — exactly the turn worth seeing. A turn that reached for
ui_control instead of delegating looked, in the logs, identical to a turn
that simply answered.

adapt_to_pipecat was a closure inside build_pipeline until today, which is
why this behaviour had no test; lifting it to module scope is what makes
these possible.
"""

from __future__ import annotations

import logging

import pytest

from jarvis.bot.pipeline import adapt_to_pipecat, register_supervisor_tool


class FakeParams:
    """Stands in for pipecat's FunctionCallParams (D-009)."""

    def __init__(self, arguments):
        self.arguments = arguments
        self.results = []

    async def result_callback(self, result):
        self.results.append(result)


class FakeLLM:
    def __init__(self):
        self.registered = []

    def register_function(self, name, handler):
        self.registered.append((name, handler))


async def test_the_handler_still_gets_arguments_and_returns_via_callback():
    # The locked D-009 contract: (arguments dict) -> confirmation str, with
    # the result delivered through params.result_callback.
    seen = []

    async def handler(arguments):
        seen.append(arguments)
        return "Voice switched to Rachel."

    wrapper = adapt_to_pipecat("set_voice", handler)
    params = FakeParams({"voice": "rachel"})
    await wrapper(params)
    assert seen == [{"voice": "rachel"}]
    assert params.results == ["Voice switched to Rachel."]


async def test_calling_a_direct_tool_is_logged_with_its_name(caplog):
    async def handler(arguments):
        return "ok"

    with caplog.at_level(logging.INFO, logger="jarvis.bot.pipeline"):
        await adapt_to_pipecat("ui_control", handler)(FakeParams({}))
    assert "supervisor_tool tool=ui_control" in caplog.text


async def test_the_log_line_precedes_the_handler_so_a_failure_still_shows(
        caplog):
    # A tool that raises is the case most worth having in the log; logging
    # after the call would lose exactly those.
    async def handler(arguments):
        raise RuntimeError("tool blew up")

    with caplog.at_level(logging.INFO, logger="jarvis.bot.pipeline"):
        with pytest.raises(RuntimeError):
            await adapt_to_pipecat("view_screen", handler)(FakeParams({}))
    assert "supervisor_tool tool=view_screen" in caplog.text


def test_registration_uses_one_spelling_of_the_name():
    # Passing the name twice invites a handler registered under the wrong
    # one, which fails only at call time and only in production.
    llm = FakeLLM()

    async def handler(arguments):
        return "ok"

    register_supervisor_tool(llm, "remember", handler)
    assert [name for name, _ in llm.registered] == ["remember"]


async def test_the_registered_wrapper_logs_the_name_it_was_registered_under(
        caplog):
    llm = FakeLLM()

    async def handler(arguments):
        return "ok"

    register_supervisor_tool(llm, "show_commands", handler)
    _, wrapper = llm.registered[0]
    with caplog.at_level(logging.INFO, logger="jarvis.bot.pipeline"):
        await wrapper(FakeParams({}))
    assert "supervisor_tool tool=show_commands" in caplog.text
