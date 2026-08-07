"""Unit tests for jarvis/wakeword/logic.py — pure gating, no model needed."""

import pytest

from jarvis.wakeword.logic import WakeGate


def test_fires_at_and_above_threshold():
    gate = WakeGate(threshold=0.5, cooldown_s=2.0)
    assert gate.check(0.5, now=100.0) is True


def test_below_threshold_does_not_fire():
    gate = WakeGate(threshold=0.5, cooldown_s=2.0)
    assert gate.check(0.499, now=100.0) is False


def test_cooldown_suppresses_then_allows():
    gate = WakeGate(threshold=0.5, cooldown_s=2.0)
    assert gate.check(0.9, now=0.0) is True
    assert gate.check(0.9, now=1.0) is False  # same utterance, still cooling
    assert gate.check(0.9, now=2.1) is True   # genuinely new utterance


def test_quiet_period_does_not_consume_cooldown():
    gate = WakeGate(threshold=0.5, cooldown_s=2.0)
    assert gate.check(0.1, now=0.0) is False
    assert gate.check(0.9, now=0.5) is True


def test_reset_allows_immediate_refire():
    gate = WakeGate(threshold=0.5, cooldown_s=60.0)
    assert gate.check(0.9, now=0.0) is True
    gate.reset()
    assert gate.check(0.9, now=0.1) is True


def test_invalid_parameters_raise():
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            WakeGate(threshold=bad)
    with pytest.raises(ValueError):
        WakeGate(cooldown_s=-1.0)
