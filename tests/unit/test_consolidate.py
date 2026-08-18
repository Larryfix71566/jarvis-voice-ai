"""Unit tests for jarvis/consolidate.py (K2,
MORTIMER_KNOWLEDGE_FRAMEWORK_PLAN.md).

propose_merges is pure — these tests pass plain dicts and never touch a
database, a model, or the network.
"""

from __future__ import annotations

from jarvis.consolidate import (
    CONSOLIDATABLE_TIERS,
    DUPLICATE_THRESHOLD,
    format_report,
    mixed_content_warning,
    propose_merges,
)


def f(key: str, content: str, tier: str = "preference") -> dict:
    return {"key": key, "content": content, "tier": tier}


class TestClustering:
    def test_near_duplicates_are_grouped(self):
        facts = [
            f("user.style.conciseness", "prefers direct commands and minimal verbosity"),
            f("user.preference.verbosity", "prefers direct commands, minimal verbosity"),
            f("user.style.units", "temperature always in fahrenheit"),
        ]
        props = propose_merges(facts)
        assert len(props) == 1
        assert set(props[0].keys) == {"user.style.conciseness", "user.preference.verbosity"}

    def test_clusters_are_cliques_not_chains(self):
        """REGRESSION: the first implementation used transitive closure and
        chained 18 unrelated facts on Larry's real store — temperature
        units, answer length and permission-asking in one group, because
        each shared generic words with the next. Every member must match
        every other member, so A-B-C only groups if A also matches C."""
        a = f("k.a", "alpha bravo charlie delta")
        b = f("k.b", "alpha bravo charlie echo")      # matches a
        c = f("k.c", "charlie echo foxtrot golf")     # matches b, NOT a
        props = propose_merges([a, b, c])
        for p in props:
            assert not {"k.a", "k.c"} <= set(p.keys), "chained unrelated facts"

    def test_singletons_are_not_proposed(self):
        props = propose_merges([f("k.a", "entirely unique statement here")])
        assert props == []

    def test_below_threshold_is_not_grouped(self):
        props = propose_merges([
            f("k.a", "alpha bravo charlie"),
            f("k.b", "xylophone yankee zulu"),
        ])
        assert props == []


class TestTierSafety:
    def test_never_merges_across_tiers(self):
        """Same words, different tiers — a preference and a project fact
        are not the same fact."""
        props = propose_merges([
            f("user.style.thing", "review the plan before implementing", "preference"),
            f("project.thing", "review the plan before implementing", "project"),
        ])
        assert props == []

    def test_identity_is_never_consolidated(self):
        """identity is small and irreplaceable — hand-review only."""
        assert "identity" not in CONSOLIDATABLE_TIERS
        props = propose_merges([
            f("user.location.home", "Spartanburg South Carolina", "identity"),
            f("user.location.primary", "Spartanburg South Carolina", "identity"),
        ])
        assert props == []

    def test_unknown_tier_is_not_consolidated(self):
        props = propose_merges([
            f("a", "same words repeated here", "mystery"),
            f("b", "same words repeated here", "mystery"),
        ])
        assert props == []


class TestMixedContentWarning:
    def test_catches_preference_hidden_in_a_location_fact(self):
        """The 2026-08-18 worked example: deleting this row by key
        similarity would have silently eaten the Fahrenheit preference."""
        w = mixed_content_warning(
            "user.location", "Spartanburg (prefers Fahrenheit for all displays)"
        )
        assert w is not None
        assert "user.location" in w

    def test_no_warning_when_the_key_advertises_the_topic(self):
        assert mixed_content_warning("user.preference.units", "Fahrenheit") is None

    def test_no_warning_for_plain_content(self):
        assert mixed_content_warning("project.name", "the video editor") is None

    def test_warnings_surface_on_the_proposal(self):
        props = propose_merges([
            f("user.style.a", "weather tables must show fahrenheit units clearly"),
            f("user.style.b", "weather tables must display fahrenheit units clearly"),
        ])
        assert props
        assert any("units" in w for w in props[0].warnings)


class TestReport:
    def test_report_states_nothing_was_changed(self):
        props = propose_merges([
            f("k.a", "alpha bravo charlie delta"),
            f("k.b", "alpha bravo charlie delta echo"),
        ])
        text = format_report(props)
        assert "Nothing has been changed" in text
        assert "--drop" in text

    def test_empty_report_is_explicit(self):
        assert "No duplicate clusters" in format_report([])

    def test_threshold_is_conservative(self):
        """A false merge destroys information; a missed one wastes a slot.
        The threshold sits on the safe side of that asymmetry."""
        assert DUPLICATE_THRESHOLD >= 0.5


class TestSingleWordCoincidence:
    def test_one_shared_word_is_not_a_duplicate(self):
        """REGRESSION, found on Larry's real store: the symmetric scorer
        divides by the SMALLER token set, so the one-token fact
        `user.voice.default: "Jarvis"` scored 1.0 against
        `user.location.path: "/Users/.../jarvis-voice-ai-clean/"` because
        the PATH contains "jarvis"."""
        props = propose_merges([
            f("user.voice.default", "Jarvis", "project"),
            f("user.location.path", "/Users/larryfix/Documents/jarvis-voice-ai-clean/", "project"),
        ])
        assert props == []

    def test_a_bug_report_does_not_merge_with_a_preference(self):
        """Same cause: matched at 1.0 on the word 'fahrenheit' alone."""
        props = propose_merges([
            f("bug.weather_display_celsius",
              "Weather display showing Celsius instead of Fahrenheit", "project"),
            f("user.temperature_unit", "Fahrenheit", "project"),
        ])
        assert props == []

    def test_differently_named_keys_still_merge(self):
        """The rejected key-similarity guard would have blocked this — but
        these ARE the same preference, and this is the main use case."""
        props = propose_merges([
            f("user.style.conciseness",
              "User prefers direct commands and minimal assistant verbosity"),
            f("user.preference.verbosity",
              "Minimal; prefers direct commands and concise responses"),
        ])
        assert len(props) == 1
