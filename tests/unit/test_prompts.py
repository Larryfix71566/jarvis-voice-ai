"""Unit tests for jarvis/prompts.py."""

import pytest

from jarvis.prompts import (
    SUBAGENT_PROMPTS,
    SUPERVISOR_PROMPT,
    VOICE_ADDENDUM,
    render_agent_catalog,
    render_voice_catalog,
)


def test_supervisor_prompt_formats_all_placeholders():
    rendered = SUPERVISOR_PROMPT.format(
        jarvis_name="Jarvis",
        user_name="Boss",
        timezone="America/New_York",
        agent_catalog="- scheduler (Scheduler): time stuff",
        voice_catalog="- rachel: Rachel (calm)",
    )
    assert "Jarvis" in rendered
    assert "America/New_York" in rendered
    assert "- scheduler (Scheduler): time stuff" in rendered
    assert "- rachel: Rachel (calm)" in rendered
    assert "{" not in rendered  # no unformatted placeholders remain


def test_supervisor_prompt_locked_rules_present():
    for fragment in ("delegate_task", "set_voice", "acknowledgment", "40 words"):
        assert fragment in SUPERVISOR_PROMPT


def test_voice_addendum_is_plain_prose_rule():
    assert "plain prose" in VOICE_ADDENDUM
    assert "no markdown" in VOICE_ADDENDUM


def test_subagent_prompts_roster_and_contracts():
    assert set(SUBAGENT_PROMPTS) == {"scheduler", "librarian", "analyst", "systems", "developer"}
    for name, prompt in SUBAGENT_PROMPTS.items():
        assert "FAILED:" in prompt, name
    assert "{timezone}" not in SUBAGENT_PROMPTS["scheduler"].format(
        timezone="America/New_York"
    )


def test_render_agent_catalog():
    agents = [{"name": "scheduler", "display_name": "Scheduler",
               "description": "Time and reminders."}]
    assert render_agent_catalog(agents) == "- scheduler (Scheduler): Time and reminders."


def test_render_voice_catalog():
    voices = [{"id": "rachel", "label": "Rachel (calm)"}]
    assert render_voice_catalog(voices) == "- rachel: Rachel (calm)"
