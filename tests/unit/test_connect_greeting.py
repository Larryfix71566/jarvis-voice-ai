"""The connect greeting fires once, only after connect AND pipeline start."""
import asyncio

from jarvis.bot.connect_greeting import ConnectGreeting


def _run(*steps):
    sent = []

    async def send():
        sent.append("greeting")

    async def go():
        g = ConnectGreeting(send)
        for step in steps:
            await getattr(g, step)()
        return g

    g = asyncio.run(go())
    return sent, g


def test_connect_before_start_waits_for_the_pipeline():
    sent, g = _run("client_connected")
    assert sent == [] and not g.sent
    sent, g = _run("client_connected", "pipeline_started")
    assert sent == ["greeting"] and g.sent


def test_start_before_connect_also_greets():
    assert _run("pipeline_started", "client_connected")[0] == ["greeting"]


def test_greets_once_per_session():
    sent, _ = _run("client_connected", "pipeline_started", "client_connected", "pipeline_started")
    assert sent == ["greeting"]


def test_pipeline_start_alone_never_greets():
    assert _run("pipeline_started")[0] == []
