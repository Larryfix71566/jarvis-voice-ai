from __future__ import annotations

import pytest

from jarvis.bot.model_route_tool import handle_model_route


@pytest.mark.asyncio
async def test_voice_route_tool_requires_confirmation_for_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "voice.db"))
    draft_text = await handle_model_route({
        "workload": "developer", "profile": "claude-opus", "route": "direct_api",
        "confirm": False,
    })
    assert "draft" in draft_text.lower()
    assert "confirm" in draft_text.lower()


@pytest.mark.asyncio
async def test_voice_route_tool_rejects_unknown_choice(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "voice.db"))
    result = await handle_model_route({
        "workload": "missing", "profile": "claude-opus", "route": "direct_api",
        "confirm": False,
    })
    assert "could not change" in result.lower()
