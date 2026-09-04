"""Unit tests for jarvis/notify.py (gap-closure plan GC9). Fixed argv via
osascript, never a shell -- these are the three adversarial cases GC9
names explicitly."""
from __future__ import annotations

from types import SimpleNamespace

from jarvis import notify


def test_build_argv_escapes_quotes_and_backslashes():
    argv = notify.build_argv('he said "hi" \\ bye')
    assert argv[0] == "osascript"
    assert argv[2] == 'display notification "he said \\"hi\\" \\\\ bye" with title "Mortimer"'


def test_long_message_is_truncated_to_max_chars():
    message = "x" * 600
    argv = notify.build_argv(message)
    # The truncated message is wrapped in quotes inside argv[2]; strip those.
    quoted = argv[2].split("display notification ", 1)[1].split(" with title")[0]
    inner = quoted[1:-1]  # drop the surrounding quotes
    assert len(inner) == notify.NOTIFY_MAX_CHARS


def test_missing_osascript_returns_false_without_raising(monkeypatch):
    def fake_run(*a, **kw):
        raise FileNotFoundError("no such file: osascript")

    monkeypatch.setattr(notify.subprocess, "run", fake_run)
    assert notify.post_notification("hello") is False


def test_post_notification_returns_true_on_zero_exit(monkeypatch):
    monkeypatch.setattr(
        notify.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=0),
    )
    assert notify.post_notification("hello") is True


def test_post_notification_returns_false_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(
        notify.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=1),
    )
    assert notify.post_notification("hello") is False
