"""Live orchestrator integration tests (plan Phase 2 Tests).

Marked `live`: skipped unless RUN_LIVE=1. Require real API keys in .env
(LLM provider). Spawn real MCP servers; writes go to a temp DB.
"""

import os
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from jarvis.agents.supervisor import Orchestrator
from jarvis.cli import bridge_settings_to_env
from jarvis.config import load_settings
from jarvis.db import get_conn, run_migrations
from jarvis.skills.registry import REPO_ROOT, SkillRegistry

pytestmark = pytest.mark.live


@pytest.fixture
async def stack(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "live.db"))
    run_migrations()
    settings = load_settings()
    bridge_settings_to_env(settings)
    registry = SkillRegistry(REPO_ROOT / "config" / "mcp_servers.yaml")
    await registry.start()

    calls: list[tuple[str, dict]] = []
    original = registry.call

    async def spy(name, arguments, server_names=None):
        calls.append((name, arguments))
        return await original(name, arguments, server_names)

    registry.call = spy
    yield settings, registry, calls
    await registry.stop()


async def test_live_time_question_calls_time_tool(stack):
    settings, registry, calls = stack
    orch = Orchestrator(settings, registry, str(uuid.uuid4()))
    reply = await orch.chat("what time is it?")
    assert reply
    assert any(name == "get_current_time" for name, _ in calls)


async def test_live_note_round_trip(stack):
    settings, registry, calls = stack
    orch = Orchestrator(settings, registry, str(uuid.uuid4()))
    await orch.chat(
        "Save a note titled Smoke Test with body 'the code is swordfish', tag smoke."
    )
    reply = await orch.chat("Search my notes for smoke and tell me the code.")
    names = [name for name, _ in calls]
    assert "create_note" in names
    assert "search_notes" in names
    assert "swordfish" in reply.lower()


async def test_live_set_reminder_writes_row(stack):
    settings, registry, calls = stack
    orch = Orchestrator(settings, registry, str(uuid.uuid4()))
    await orch.chat("Set a reminder to stretch in 2 hours.")
    assert any(name == "set_reminder" for name, _ in calls)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM reminders WHERE message LIKE '%stretch%'"
        ).fetchall()
    assert len(rows) == 1
    due = datetime.fromisoformat(rows[0]["due_at"])
    now = datetime.now(ZoneInfo(settings.jarvis_timezone))
    assert timedelta(hours=1.5) < (due - now) < timedelta(hours=2.5)
