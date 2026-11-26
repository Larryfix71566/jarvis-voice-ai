"""Spoken credential guard (flag-gated, default off). Synthetic values only."""
import asyncio

import pytest
import yaml

from jarvis.bot.sensitive_turn import (
    SensitiveTurn, arm_user_turn, current_sensitive_turn, note_assistant_reply,
)
from jarvis.sensitive import (
    SPOKEN_CREDENTIAL_PLACEHOLDER as PH,
    asks_for_credential, detect_credential, detect_spoken_credential,
    find_spoken_credential_spans, leaves_credential_pending,
    redact_spoken_credentials, spoken_guard_enabled,
)
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

FLAG = "JARVIS_SPOKEN_CREDENTIAL_GUARD_ENABLED"

# (sentence, secrets that must vanish, words that must survive)
POSITIVES = [
    ("my password is hunter2", ["hunter2"], ["my password is"]),
    ("password's hunter2", ["hunter2"], ["password's"]),
    ("My password is hunter2.", ["hunter2"], ["My password is"]),
    ("the PIN is 4729", ["4729"], ["the PIN is"]),
    ("my pin number is four seven two nine", ["four seven", "nine"], ["my pin number is"]),
    ("passcode is 1 2 3 4", ["1 2 3 4"], ["passcode is"]),
    ("security code is 9 9 1", ["9 9 1"], ["security code is"]),
    ("the access code is 55 12", ["55 12"], ["the access code is"]),
    ("the code is 4729", ["4729"], ["the code is"]),
    ("the door code is 4 4 1 2", ["4 4 1 2"], ["the door code is"]),
    ("the code to the garage is 4 4 1 2", ["4 4 1 2"], ["the code to the garage is"]),
    ("the password is h u n t e r", ["h u n t e r"], ["the password is"]),
    ("the password is hotel uniform november tango echo romeo", ["hotel", "romeo"], ["the password is"]),
    ("the wifi password is bluefish", ["bluefish"], ["the wifi password is"]),
    ("the password for my email is bluefish42", ["bluefish42"], ["the password for my email is"]),
    ("my password is capital H unter at sign 2", ["unter", "sign 2", "capital"], ["my password is"]),
    ("set the password to dollar sign money 1", ["dollar", "money 1"], ["set the password to"]),
    ("change my PIN to 1234", ["1234"], ["change my PIN to"]),
    ("the passphrase is correct horse battery staple", ["horse", "staple"], ["the passphrase is"]),
    ("my password is not hunter2 anymore it's bluefish42", ["hunter2", "bluefish42"], ["my password is not"]),
    ("my wifi password is bluefish42, can you text it to my wife",
     ["bluefish42"], [", can you text it to my wife"]),
    ("the password is bluefish42 and can you save it", ["bluefish42"], ["and can you save it"]),
    ("the PIN’s 4729", ["4729"], ["the PIN’s"]),
    ("my login is larry and the password is bluefish42", ["bluefish42"], ["my login is larry"]),
]

NEGATIVES = [
    "the password is wrong", "the password is correct", "the Wi-Fi password is on the fridge",
    "reset my password", "I forgot my password", "change the PIN on my card",
    "what's a good passcode length", "the code is in the repo", "the code is broken",
    "security code review", "pin the window", "call me at 4 pm",
    "set a timer for 4729 seconds", "the code is 200 lines long", "the pin is loose",
    "passwords are 8 chars", "the password is 12 characters long", "my PIN is 4 digits",
    "my zip code is 30022", "the area code is 404", "the error code is 500",
    "the source code is on GitHub", "the password is not working",
    "the password manager is 1Password", "passwords are case sensitive",
    "my password is too short", "my account password is something I need to change",
    # Documented miss: a plain-word value after a stop word is not caught.
    "the password is the name of my dog rex",
]


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(FLAG, "1")


@pytest.fixture
def holder():
    h = SensitiveTurn()
    token = current_sensitive_turn.set(h)
    yield h
    current_sensitive_turn.reset(token)


def test_flag_off_by_default(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    assert not spoken_guard_enabled()
    for text, _, _ in POSITIVES:
        assert find_spoken_credential_spans(text) == []
        assert redact_spoken_credentials(text) == text
        assert not detect_spoken_credential(text)
    assert not leaves_credential_pending("my password is")
    assert not asks_for_credential("What's the PIN?")
    assert find_spoken_credential_spans("4729", pending=True) == []
    h = SensitiveTurn()
    token = current_sensitive_turn.set(h)
    try:
        assert not arm_user_turn("my password is hunter2")
        assert not h.armed
    finally:
        current_sensitive_turn.reset(token)


def test_flag_needs_master_guard(monkeypatch):
    monkeypatch.setenv(FLAG, "yes")
    assert spoken_guard_enabled()
    monkeypatch.setenv("JARVIS_SENSITIVE_GUARD_ENABLED", "false")
    assert not spoken_guard_enabled()


@pytest.mark.parametrize("text,secrets,keep", POSITIVES)
def test_positive(on, text, secrets, keep):
    out = redact_spoken_credentials(text)
    assert PH in out
    for secret in secrets:
        assert secret not in out, out
    for word in keep:
        assert word in out, out
    assert redact_spoken_credentials(out) == out  # idempotent


@pytest.mark.parametrize("text", NEGATIVES)
def test_negative(on, text):
    assert find_spoken_credential_spans(text) == [], text
    assert redact_spoken_credentials(text) == text


def test_typed_assignment_still_caught_by_old_detector():
    assert detect_credential("Password: hunter2x")


def test_bare_code_off(on, monkeypatch):
    monkeypatch.setenv("JARVIS_SPOKEN_CREDENTIAL_BARE_CODE", "off")
    assert find_spoken_credential_spans("the code is 4729") == []
    assert find_spoken_credential_spans("the door code is 4729")
    assert not leaves_credential_pending("the code is")
    assert not asks_for_credential("What's the code?")


def test_word_values_off(on, monkeypatch):
    monkeypatch.setenv("JARVIS_SPOKEN_CREDENTIAL_WORD_VALUES", "0")
    assert find_spoken_credential_spans("the wifi password is bluefish") == []
    assert find_spoken_credential_spans("my password is hunter2")
    assert find_spoken_credential_spans("the password is h u n t e r")
    assert find_spoken_credential_spans("the password is hotel uniform november")


@pytest.mark.parametrize("text", [
    "my password is", "the PIN is...", "okay the door code is",
    "here's my wifi password", "here is the pin", "change my PIN to",
])
def test_leaves_pending(on, text):
    assert leaves_credential_pending(text)


@pytest.mark.parametrize("text", [
    "reset my password", "I forgot my password", "what's my password",
    "change the PIN on my card", "my password is hunter2", "I don't know what my password is",
])
def test_not_pending(on, text):
    assert not leaves_credential_pending(text)


@pytest.mark.parametrize("text", [
    "What's the PIN?", "Can you tell me the wifi password?", "I need the access code.",
    "Please enter your passcode.",
])
def test_asks(on, text):
    assert asks_for_credential(text)


@pytest.mark.parametrize("text", [
    "I kept your password on this Mac.", "Do you want to reset your password?",
    "Your password stayed local.",
])
def test_does_not_ask(on, text):
    assert not asks_for_credential(text)


@pytest.mark.parametrize("text,gone", [
    ("4729", "4729"), ("4 7 2 9", "4 7 2 9"), ("four seven two nine", "four"),
    ("it's hunter two", "hunter"), ("bluefish42", "bluefish42"),
])
def test_pending_redaction(on, text, gone):
    out = redact_spoken_credentials(text, pending=True)
    assert gone not in out and PH in out
    assert redact_spoken_credentials(out, pending=True) == out
    assert redact_spoken_credentials(text) == text  # no pending: untouched


@pytest.mark.parametrize("text", ["never mind", "I don't know", "why do you need it", "no", "um"])
def test_pending_refusals(on, text):
    assert redact_spoken_credentials(text, pending=True) == text


def test_prompt_lifecycle(on, holder):
    assert not arm_user_turn("my password is")
    assert holder.credential_prompted
    holder.clear()
    assert holder.credential_prompted  # outlives the turn boundary
    assert arm_user_turn("4729")
    assert holder.kind == "credential" and holder.account_info
    assert not holder.credential_prompted
    holder.clear()
    assert not arm_user_turn("4729")  # expired after one turn


def test_prompt_expires_after_one_turn(on, holder):
    arm_user_turn("the PIN is")
    assert not arm_user_turn("what time is it")
    assert not arm_user_turn("4729")


def test_assistant_reply_sets_prompt(on, holder):
    note_assistant_reply("What's the PIN?")
    assert holder.credential_prompted
    holder.take_credential_prompt()
    note_assistant_reply("reset my password")
    assert not holder.credential_prompted
    note_assistant_reply("Do you want to reset your password?")
    assert not holder.credential_prompted


def test_arm_user_turn_arms_spoken_credential(on, holder):
    assert arm_user_turn("my password is hunter2")
    assert holder.kind == "credential"


@pytest.mark.parametrize("text,_s,_k", POSITIVES)
def test_idempotent_pending(on, text, _s, _k):
    once = redact_spoken_credentials(text, pending=True)
    assert redact_spoken_credentials(once, pending=True) == once


def test_totality(on):
    for bad in (None, 5, b"x", ""):
        assert find_spoken_credential_spans(bad) == []
        assert redact_spoken_credentials(bad) == bad
        assert not detect_spoken_credential(bad)
        assert not leaves_credential_pending(bad)
        assert not asks_for_credential(bad)


def test_no_new_false_positives(on, holder):
    from tests.unit.test_sensitive import NEGATIVES as FIN_NEG, POSITIVES as FIN_POS
    cases = yaml.safe_load((REPO_ROOT / "tests" / "evals" / "cases.yaml").read_text())
    # One routing-eval case ("...the project wifi password is blueplanet42") IS a
    # spoken password, so the guard correctly catches it; every other one is clean.
    real = [c["input"] for c in cases if "blueplanet42" in c["input"]]
    assert len(real) == 1 and detect_spoken_credential(real[0])
    utterances = [c["input"] for c in cases if c["input"] not in real] + list(FIN_NEG)
    for text in utterances:
        assert find_spoken_credential_spans(text) == [], text
        assert find_spoken_credential_spans(text, pending=False) == []
        holder.clear()
        arm_user_turn(text)
        assert holder.kind != "credential", text
    # financial positives are not spoken credentials either
    for text, _kind in FIN_POS:
        assert find_spoken_credential_spans(text) == [], text


def test_observer_does_not_persist_spoken_password(tmp_path, monkeypatch):
    pytest.importorskip("pipecat")
    from pipecat.frames.frames import (
        TranscriptionFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame,
    )
    from pipecat.observers.base_observer import FramePushed
    from pipecat.processors.frame_processor import FrameDirection

    from jarvis.bot.transcript_log import TranscriptObserver
    from jarvis.db import get_conn, run_migrations

    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "t.db"))
    run_migrations()

    def run(flag):
        if flag:
            monkeypatch.setenv(FLAG, "1")
        else:
            monkeypatch.delenv(FLAG, raising=False)
        with get_conn() as conn:
            conn.execute("DELETE FROM conversations")
        h = SensitiveTurn()
        token = current_sensitive_turn.set(h)
        obs = TranscriptObserver("s1")

        async def push(frame):
            await obs.on_push_frame(FramePushed(
                source=None, destination=None, frame=frame,
                direction=FrameDirection.DOWNSTREAM, timestamp=0))

        async def drive():
            await push(UserStartedSpeakingFrame())
            await push(TranscriptionFrame(text="my password is hunter2", finalized=True,
                                          user_id="u", timestamp="t"))
            await push(UserStoppedSpeakingFrame())
        try:
            asyncio.run(drive())
        finally:
            current_sensitive_turn.reset(token)
        with get_conn() as conn:
            return conn.execute("SELECT content FROM conversations").fetchall()

    assert run(True) == []
    assert len(run(False)) == 1
