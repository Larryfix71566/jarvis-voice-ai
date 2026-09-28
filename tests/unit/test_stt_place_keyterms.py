"""Phase 2 W4 (MORTIMER_VOICE_WORKFLOWS_PLAN.md): Larry's place names are
boosted in speech-to-text, read from his durable place memories. Turn 3513
(2026-09-23) heard "Alfreda, Georgia" for Alpharetta."""

from __future__ import annotations

import jarvis.bot.pipeline as bp

# The live values of these keys on 2026-09-25 (production memories).
FACTS = [
    {"key": "user.location", "content": "User is located in Spartanburg"},
    {"key": "user.location.current", "content": "Spartanburg, SC"},
    {"key": "user.location.home", "content": "Florida, ET"},
    {"key": "user.location.primary", "content": "Spartanburg, SC"},
    {"key": "user.location.rule", "content": "Use CURRENT device location for weather/local queries."},
    {"key": "user.location.secondary", "content": "Florida"},
    {"key": "user.location.work", "content": "Alpharetta, Georgia"},
    {"key": "user.name", "content": "Larry"},
]


def test_durable_places_become_keyterms():
    assert bp.place_keyterms(FACTS) == ["Florida", "Alpharetta", "Georgia", "Spartanburg"]


def test_current_location_and_rule_are_not_read():
    # D-L6: where he is right now never comes from memory, not even as a hint.
    facts = [{"key": "user.location.current", "content": "Savannah, GA"},
             {"key": "user.location", "content": "User is located in Macon"}]
    assert bp.place_keyterms(facts) == []


def test_capped_and_deduplicated():
    facts = [{"key": k, "content": " ".join(f"Place{chr(97 + i)}{k[-4:]}x" for i in range(10))}
             for k in bp.PLACE_KEYTERM_KEYS]
    out = bp.place_keyterms(facts)
    assert len(out) == bp.PLACE_KEYTERM_MAX and len(set(out)) == len(out)


def test_stt_keyterms_adds_places(monkeypatch):
    import jarvis.memory as memory
    monkeypatch.setattr(memory, "list_facts", lambda: FACTS)
    assert bp.stt_keyterms() == bp.STT_KEYTERMS + ["Florida", "Alpharetta", "Georgia", "Spartanburg"]


def test_stt_keyterms_falls_back_to_the_static_list(monkeypatch):
    import jarvis.memory as memory

    def boom():
        raise RuntimeError("database is locked")
    monkeypatch.setattr(memory, "list_facts", boom)
    assert bp.stt_keyterms() == bp.STT_KEYTERMS
