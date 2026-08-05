"""Unit tests for jarvis/bot/voice_switch.py (plan Phase 5 Tests)."""

import pytest

from jarvis.bot.voice_switch import (
    available_list,
    build_set_voice_tool,
    catalog_summary,
    load_voice_catalog,
    resolve_voice,
)

CATALOG = {
    "default": "rachel",
    "voices": [
        {"id": "rachel", "elevenlabs_voice_id": "EL-RACHEL",
         "label": "Rachel (calm, American female)"},
        {"id": "george", "elevenlabs_voice_id": "EL-GEORGE",
         "label": "George (warm, British male)"},
        {"id": "eric", "elevenlabs_voice_id": "EL-ERIC",
         "label": "Eric (smooth, trustworthy American male)"},
    ],
}


class TestResolution:
    def test_exact_id(self):
        assert resolve_voice("george", CATALOG)["elevenlabs_voice_id"] == "EL-GEORGE"

    def test_id_case_insensitive(self):
        assert resolve_voice("RACHEL", CATALOG)["id"] == "rachel"

    def test_label_substring(self):
        assert resolve_voice("british", CATALOG)["id"] == "george"

    def test_label_substring_case_insensitive(self):
        assert resolve_voice("TRUSTWORTHY", CATALOG)["id"] == "eric"

    def test_unknown_returns_none(self):
        assert resolve_voice("darth vader", CATALOG) is None

    def test_empty_returns_none(self):
        assert resolve_voice("", CATALOG) is None


class TestHandler:
    async def test_pushes_frame_and_confirms(self):
        pushed = []

        async def push(frame):
            pushed.append(frame)

        schema, handler = build_set_voice_tool(push, CATALOG)
        assert schema["function"]["name"] == "set_voice"
        result = await handler({"voice": "george"})
        assert result == "Voice switched to George (warm, British male)."
        assert len(pushed) == 1
        assert pushed[0].settings == {"voice": "EL-GEORGE"}

    async def test_unknown_voice_error_lists_available(self):
        async def push(frame):
            raise AssertionError("must not push")

        _, handler = build_set_voice_tool(push, CATALOG)
        result = await handler({"voice": "morgan"})
        assert "I don't have a voice called 'morgan'" in result
        assert "rachel, george, eric" in result


class TestRepoCatalog:
    def test_voices_yaml_has_at_least_three_voices(self):
        catalog = load_voice_catalog()
        assert len(catalog["voices"]) >= 3
        assert catalog["default"] in {v["id"] for v in catalog["voices"]}
        for v in catalog["voices"]:
            assert v["id"] == v["id"].lower()
            assert " " not in v["id"]
            assert v["elevenlabs_voice_id"] and v["label"]

    def test_summary_format(self):
        assert "- rachel: Rachel (calm, American female)" in catalog_summary(CATALOG)

    def test_available_list(self):
        assert available_list(CATALOG) == "rachel, george, eric"
