"""Larry, 2026-11-24: only account or password info stays on the Mac."""
import pytest

from jarvis.bot.sensitive_turn import (
    SensitiveTurn, arm_from_text, current_sensitive_turn, holds_account_info, is_sensitive,
)
from jarvis.sensitive import detect_credential


@pytest.fixture
def turn():
    holder = SensitiveTurn()
    token = current_sensitive_turn.set(holder)
    try:
        yield holder
    finally:
        current_sensitive_turn.reset(token)


@pytest.mark.parametrize("text", [
    "sk-ant-SYNTHETICSYNTHETICSYNTHETIC0000",
    "AKIASYNTHETIC0000000",
    "ghp_" + "a" * 36,
    "xoxb-1234567890-synthetic",
    "-----BEGIN RSA PRIVATE KEY-----",
    "password: hunter2x",
    "API_KEY=synthetic-value",
])
def test_credential_literals_are_detected(text):
    assert detect_credential(text)


@pytest.mark.parametrize("text", [
    "", "my password is wrong", "what's the secret to good bread", "sk-short", None,
])
def test_talk_about_passwords_is_not_a_credential(text):
    assert not detect_credential(text)


def test_balance_is_sensitive_but_not_account_info(turn):
    assert arm_from_text("Your checking balance is $4,200.00")
    assert is_sensitive() and not holds_account_info()


def test_account_number_is_account_info_and_survives_a_milder_arm(turn):
    assert arm_from_text("account 000123456789")
    assert holds_account_info()
    turn.arm("tool_source_policy")
    assert holds_account_info()
    turn.clear()
    assert not holds_account_info()


def test_credentials_are_only_checked_on_what_the_user_says(turn):
    assert not arm_from_text("password: hunter2x")
    assert not holds_account_info()
    assert arm_from_text("password: hunter2x", credentials=True)
    assert holds_account_info() and turn.kind == "credential"


def test_unwired_context_fails_closed():
    token = current_sensitive_turn.set(None)
    try:
        assert holds_account_info()
    finally:
        current_sensitive_turn.reset(token)


def _resolved(name, adapter, billing):
    from types import SimpleNamespace
    from jarvis.model_routing import AccessRoute
    return SimpleNamespace(route=AccessRoute(name, adapter, billing, None, "approved_external"))


def test_agent_gate_lets_private_turns_through_the_subscription_only(turn):
    from jarvis.agents.base import _protected_turn_blocks
    from jarvis.privacy_policy import DataPolicy
    claude = _resolved("subscription", "subscription_runtime", "subscription")
    codex = _resolved("codex_subscription", "codex_subscription_runtime", "subscription")
    floor = DataPolicy("local_only", "synthetic")
    assert not _protected_turn_blocks(claude, False, floor)
    assert _protected_turn_blocks(codex, False, floor)
    turn.arm("balance")
    assert not _protected_turn_blocks(claude, False)
    assert _protected_turn_blocks(codex, False)
    turn.arm("account")
    assert _protected_turn_blocks(claude, False)
    assert not _protected_turn_blocks(claude, True)
