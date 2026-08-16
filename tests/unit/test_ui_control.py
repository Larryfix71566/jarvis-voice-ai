"""Unit tests for jarvis/bot/ui_control.py (MORTIMER_VOICE_UI_PLAN.md U1)."""

from __future__ import annotations

import pytest

from jarvis.bot.ui_control import (
    UI_ACTIONS,
    UI_CONTROL_SCHEMA,
    UI_TABS,
    build_ui_control_tool,
    resolve_ui_command,
)


class TestResolve:
    def test_simple_action(self):
        message, reply = resolve_ui_command({"action": "drawer_close"})
        assert message == {"type": "ui", "action": "drawer_close"}
        assert reply == "ok"

    def test_drawer_open_with_optional_tab(self):
        message, reply = resolve_ui_command({"action": "drawer_open", "tab": "runs"})
        assert message == {"type": "ui", "action": "drawer_open", "tab": "runs"}
        assert reply == "ok"

    def test_drawer_open_without_tab_is_valid(self):
        message, reply = resolve_ui_command({"action": "drawer_open"})
        assert message == {"type": "ui", "action": "drawer_open"}
        assert reply == "ok"

    def test_drawer_tab_requires_tab(self):
        message, reply = resolve_ui_command({"action": "drawer_tab"})
        assert message is None
        assert "Which panel" in reply
        assert "memory" in reply  # names the valid options

    def test_every_tab_accepted(self):
        for tab in UI_TABS:
            message, _ = resolve_ui_command({"action": "drawer_tab", "tab": tab})
            assert message == {"type": "ui", "action": "drawer_tab", "tab": tab}

    def test_unknown_action_names_valid_ones(self):
        message, reply = resolve_ui_command({"action": "self_destruct"})
        assert message is None
        assert "self_destruct" in reply
        assert "drawer_open" in reply

    def test_unknown_tab_names_valid_ones(self):
        message, reply = resolve_ui_command({"action": "drawer_tab", "tab": "settings"})
        assert message is None
        assert "settings" in reply
        assert "output" in reply

    def test_tab_ignored_on_non_drawer_action(self):
        # A stray tab on an unambiguous action is dropped, not an error.
        message, reply = resolve_ui_command({"action": "mic_mute", "tab": "runs"})
        assert message == {"type": "ui", "action": "mic_mute"}
        assert reply == "ok-muted"

    def test_mic_mute_returns_ok_muted(self):
        _, reply = resolve_ui_command({"action": "mic_mute"})
        assert reply == "ok-muted"

    def test_tab_case_insensitive(self):
        message, _ = resolve_ui_command({"action": "drawer_tab", "tab": "Runs"})
        assert message == {"type": "ui", "action": "drawer_tab", "tab": "runs"}


class TestSchema:
    def test_schema_enums_match_constants(self):
        props = UI_CONTROL_SCHEMA["function"]["parameters"]["properties"]
        assert set(props["action"]["enum"]) == UI_ACTIONS
        assert set(props["tab"]["enum"]) == UI_TABS

    def test_no_mic_unmute_action(self):
        # U7: deliberately impossible — pinned so nobody "helpfully" adds it.
        assert "mic_unmute" not in UI_ACTIONS
        assert "mic_unmute" in UI_CONTROL_SCHEMA["function"]["description"]


class TestHandler:
    async def test_valid_command_sends_message_and_returns_ok(self):
        sent: list[dict] = []

        async def fake_send(message: dict) -> None:
            sent.append(message)

        _, handler = build_ui_control_tool(fake_send)
        reply = await handler({"action": "drawer_open", "tab": "edit"})
        assert reply == "ok"
        assert sent == [{"type": "ui", "action": "drawer_open", "tab": "edit"}]

    async def test_invalid_command_sends_nothing(self):
        sent: list[dict] = []

        async def fake_send(message: dict) -> None:
            sent.append(message)

        _, handler = build_ui_control_tool(fake_send)
        reply = await handler({"action": "drawer_tab"})
        assert "Which panel" in reply
        assert sent == []
