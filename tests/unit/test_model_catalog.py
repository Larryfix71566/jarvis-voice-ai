"""The model catalog, and the drift check that was missing (2026-09-05).

The spoken-name mapping used to be prose in two places — rule 8 in
jarvis/prompts.py and the model_profile description in
jarvis/agents/delegate.py — and both had drifted from
config/upgrade_models.yaml:

    rule 8          said `fable`        no such profile
    both locations  said `or-sonnet-5`  no such profile

An unresolvable profile makes the run REFUSE rather than quietly using
another model, so "use Sonnet" failed outright and "use Fable" failed or
not depending on which instruction the model happened to follow. Nothing
caught it because nothing compared the names the model is TOLD to use
against the names that EXIST. That comparison is offline, free and
deterministic, which is why it belongs here rather than in a script.
"""

from __future__ import annotations

import pytest

from jarvis.agents.delegate import build_delegate_tool
from jarvis.model_catalog import (
    load_aliases,
    load_profiles,
    render_model_catalog,
    unknown_alias_targets,
)
from jarvis.prompts import SUPERVISOR_PROMPT

DEAD_NAMES = ("or-sonnet-5",)


def test_every_alias_points_at_a_profile_that_exists():
    # The check whose absence let two dead names sit in the prompt.
    assert unknown_alias_targets(load_aliases(), load_profiles()) == {}


def test_the_two_names_that_were_wrong_are_gone_from_the_prompt():
    for dead in DEAD_NAMES:
        assert dead not in SUPERVISOR_PROMPT
    # `fable` was rule 8's spelling; the registry calls it claude-fable-5.
    assert "claude-fable-5" in render_model_catalog()


def test_the_prompt_no_longer_carries_its_own_mapping():
    # A second copy is what drifted. The prose must point at the rendered
    # list, not restate it.
    assert "{model_catalog}" in SUPERVISOR_PROMPT
    assert "from the model list above" in SUPERVISOR_PROMPT


def test_the_delegate_schema_no_longer_carries_its_own_mapping():
    schema, _handler = build_delegate_tool({})
    described = schema["function"]["parameters"]["properties"]["model_profile"]
    text = described["description"]
    for dead in DEAD_NAMES:
        assert dead not in text
    assert "from the model list in your system" in text


def test_every_profile_appears_in_the_catalog():
    # A profile omitted from the rendered list is a profile the model
    # cannot name — and an omission is how it ends up inventing one
    # instead (case 30 offered "Claude 3.5 Sonnet", which exists nowhere
    # in this registry).
    rendered = render_model_catalog()
    for profile in load_profiles():
        assert str(profile["name"]) in rendered


def test_a_profile_without_a_spoken_name_is_still_listed():
    rendered = render_model_catalog()
    assert "kimi-k2 (no spoken name)" in rendered


def test_tier_and_provider_are_rendered_not_aliased():
    # "frontier" must never become an alias: it is a field, there are five
    # frontier profiles, and hardcoding one would go stale on the next
    # model added.
    assert "frontier" not in load_aliases()
    assert "anthropic, tier frontier" in render_model_catalog()


def test_the_catalog_keeps_registry_order():
    # Traceable to the file a human edits: a diff of one is a diff of the
    # other.
    rendered = [ln.split()[1] for ln in render_model_catalog().splitlines()]
    assert rendered == [str(p["name"]) for p in load_profiles()]


def test_an_alias_naming_a_missing_profile_is_reported():
    bad = {"Ghost": "no-such-profile", "Opus": "claude-opus"}
    profiles = [{"name": "claude-opus"}]
    assert unknown_alias_targets(bad, profiles) == {"Ghost": "no-such-profile"}


@pytest.mark.parametrize("spoken,profile", [
    ("Opus", "claude-opus"),
    ("Fable", "claude-fable-5"),
    ("Sonnet", "claude-sonnet-5"),
    ("Kimi", "kimi-k3"),
    ("Grok", "or-grok-4.6"),
    ("DeepSeek", "or-deepseek-v4-pro"),
])
def test_each_family_resolves_to_the_member_that_was_chosen(spoken, profile):
    # Bare names map to a family with more than one member; which one is a
    # decision, written down rather than inferred.
    assert load_aliases()[spoken] == profile
