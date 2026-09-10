"""Unit tests for jarvis/bot/keyhealth_notice.py (gap-closure plan GC5,
2026-09-04). tick_once is exercised directly (never via start()/asyncio
sleeps) with fake agents carrying name/model_unusable/model_unusable_detail
-- the same shape as jarvis.agents.base.SubAgent's properties."""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from jarvis.bot.keyhealth_notice import KeyHealthNotice
from jarvis.prompts import KEYHEALTH_RECOVERED_TEMPLATE, KEYHEALTH_TEMPLATE


@dataclass
class FakeAgent:
    name: str
    model_unusable: bool = False
    model_unusable_detail: str = ""


def _notice(agents, connected=True, injected=None):
    injected = injected if injected is not None else []

    async def inject(text: str) -> None:
        injected.append(text)

    return KeyHealthNotice(inject=inject, agents=agents, is_connected=lambda: connected), injected


@pytest.mark.asyncio
async def test_disconnected_never_injects():
    agent = FakeAgent("weather", model_unusable=True, model_unusable_detail="HTTP 401")
    notice, injected = _notice([agent], connected=False)

    await notice.tick_once()

    assert injected == []


@pytest.mark.asyncio
async def test_one_unusable_injects_once_with_name_and_detail():
    agent = FakeAgent("weather", model_unusable=True, model_unusable_detail="HTTP 401 unauthorized")
    notice, injected = _notice([agent])

    await notice.tick_once()

    assert len(injected) == 1
    assert "weather" in injected[0]
    assert "HTTP 401 unauthorized" in injected[0]
    assert injected[0] == KEYHEALTH_TEMPLATE.format(agents="weather", detail="HTTP 401 unauthorized")


@pytest.mark.asyncio
async def test_same_unusable_state_does_not_reinject():
    agent = FakeAgent("weather", model_unusable=True, model_unusable_detail="HTTP 401")
    notice, injected = _notice([agent])

    await notice.tick_once()
    await notice.tick_once()
    await notice.tick_once()

    assert len(injected) == 1


@pytest.mark.asyncio
async def test_recovery_injects_recovered_template_once():
    agent = FakeAgent("weather", model_unusable=True, model_unusable_detail="HTTP 401")
    notice, injected = _notice([agent])
    await notice.tick_once()
    assert len(injected) == 1

    agent.model_unusable = False
    await notice.tick_once()
    await notice.tick_once()  # already recovered -- must not inject again

    assert len(injected) == 2
    assert injected[1] == KEYHEALTH_RECOVERED_TEMPLATE


@pytest.mark.asyncio
async def test_multiple_unusable_agents_all_named_in_one_injection():
    agents = [
        FakeAgent("weather", model_unusable=True, model_unusable_detail="HTTP 401"),
        FakeAgent("news", model_unusable=True, model_unusable_detail="HTTP 429"),
        FakeAgent("calendar", model_unusable=False),
    ]
    notice, injected = _notice(agents)

    await notice.tick_once()

    assert len(injected) == 1
    assert "weather" in injected[0]
    assert "news" in injected[0]
    assert "calendar" not in injected[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("recovering", [False, True])
async def test_failed_announcement_retries_without_duplicate(recovering, caplog):
    agent = FakeAgent("weather", True, "HTTP 401")
    notice, injected = _notice([agent])
    if recovering:
        await notice.tick_once()
        agent.model_unusable = False
    original = notice._inject

    async def failed(text):
        raise RuntimeError("private transport details")

    notice._inject = failed
    await notice.tick_once()
    assert "RuntimeError" in caplog.text
    assert "private transport details" not in caplog.text
    notice._inject = original
    await notice.tick_once()
    await notice.tick_once()
    assert len(injected) == (2 if recovering else 1)
    if recovering:
        assert injected[-1] == KEYHEALTH_RECOVERED_TEMPLATE


@pytest.mark.asyncio
async def test_cancellation_is_not_swallowed():
    import asyncio

    async def cancelled(text):
        raise asyncio.CancelledError

    notice = KeyHealthNotice(cancelled, [FakeAgent("weather", True, "401")], lambda: True)
    with pytest.raises(asyncio.CancelledError):
        await notice.tick_once()
