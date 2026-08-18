"""Unit tests for jarvis/bot/screen_tool.py
(MORTIMER_SHELL_FIX_AND_SCREEN_VISION_PLAN.md V3).

logic.screen_view/screen_list are injected — no real capture/vision call.
"""

from __future__ import annotations

import pytest

from jarvis.bot.screen_tool import (
    LIST_SCREENS_SCHEMA,
    VIEW_SCREEN_SCHEMA,
    build_list_screens_tool,
    build_view_screen_tool,
)


class TestViewScreenTool:
    async def test_happy_path_returns_answer(self):
        calls = []

        def fake_screen_view(question, display):
            calls.append((question, display))
            return {"answer": "A terminal window.", "display": display,
                    "profile": "claude-sonnet", "low_confidence": False}

        _, handler = build_view_screen_tool(screen_view=fake_screen_view)
        result = await handler({"question": "what's open", "display": 2})
        assert result == "A terminal window."
        assert calls == [("what's open", 2)]

    async def test_defaults_to_display_1(self):
        calls = []

        def fake_screen_view(question, display):
            calls.append(display)
            return {"answer": "ok", "display": display, "profile": "p", "low_confidence": False}

        _, handler = build_view_screen_tool(screen_view=fake_screen_view)
        await handler({"question": "what's open"})
        assert calls == [1]

    async def test_empty_question_is_not_sent_to_logic(self):
        called = []

        def fake_screen_view(question, display):
            called.append(True)
            return {"answer": "x", "display": display, "profile": "p", "low_confidence": False}

        _, handler = build_view_screen_tool(screen_view=fake_screen_view)
        result = await handler({"question": ""})
        assert called == []
        assert "what would you like" in result.lower()

    async def test_error_result_is_relayed_verbatim(self):
        def fake_screen_view(question, display):
            return {"error": "Screen vision is disabled (JARVIS_SCREEN_ENABLED=false)."}

        _, handler = build_view_screen_tool(screen_view=fake_screen_view)
        result = await handler({"question": "what's open"})
        assert "disabled" in result.lower()

    async def test_non_integer_display_falls_back_to_1(self):
        calls = []

        def fake_screen_view(question, display):
            calls.append(display)
            return {"answer": "ok", "display": display, "profile": "p", "low_confidence": False}

        _, handler = build_view_screen_tool(screen_view=fake_screen_view)
        await handler({"question": "what's open", "display": "not-a-number"})
        assert calls == [1]

    def test_schema_shape(self):
        fn = VIEW_SCREEN_SCHEMA["function"]
        assert fn["name"] == "view_screen"
        assert "question" in fn["parameters"]["properties"]
        assert fn["parameters"]["required"] == ["question"]


class TestListScreensTool:
    async def test_happy_path_summarizes_displays(self):
        def fake_screen_list():
            return {"displays": [
                {"index": 1, "resolution": "2560x1440", "main": True},
                {"index": 2, "resolution": "1920x1080", "main": False},
            ]}

        _, handler = build_list_screens_tool(screen_list=fake_screen_list)
        result = await handler({})
        assert "display 1 (main) — 2560x1440" in result
        assert "display 2 — 1920x1080" in result

    async def test_empty_displays_list(self):
        _, handler = build_list_screens_tool(screen_list=lambda: {"displays": []})
        result = await handler({})
        assert "couldn't detect" in result.lower()

    async def test_error_result_is_relayed_verbatim(self):
        _, handler = build_list_screens_tool(
            screen_list=lambda: {"error": "Screen vision is disabled."}
        )
        result = await handler({})
        assert "disabled" in result.lower()

    def test_schema_shape(self):
        fn = LIST_SCREENS_SCHEMA["function"]
        assert fn["name"] == "list_screens"
        assert fn["parameters"]["required"] == []
