"""JARVIS_COMMAND_CONSOLE_ENABLED is read in one place (WS-34 C7-py, contract 2.5).

It used to be read four times with two defaults (off in three places, on in
one), so a default install sent no ``console/hello`` while one handler
behaved as if the console were on.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import jarvis.bot.pipeline as pipeline

SOURCE = Path(pipeline.__file__).read_text(encoding="utf-8")
VAR = "JARVIS_COMMAND_CONSOLE_ENABLED"


def test_unset_and_blank_are_on(monkeypatch):
    monkeypatch.delenv(VAR, raising=False)
    assert pipeline.command_console_flag_enabled() is True
    monkeypatch.setenv(VAR, "")
    assert pipeline.command_console_flag_enabled() is True


@pytest.mark.parametrize("value", ["false", "FALSE", " 0 ", "no", "No"])
def test_false_forms_are_off(monkeypatch, value):
    monkeypatch.setenv(VAR, value)
    assert pipeline.command_console_flag_enabled() is False


@pytest.mark.parametrize("value", ["true", "1", "yes", "TRUE"])
def test_true_forms_are_on(monkeypatch, value):
    monkeypatch.setenv(VAR, value)
    assert pipeline.command_console_flag_enabled() is True


def test_pipeline_has_no_other_read_of_the_variable():
    reads = [m.start() for m in re.finditer(VAR, SOURCE)]
    # The helper's own docstring and its single os.environ read.
    code_reads = [m for m in re.finditer(r'os\.environ\.get\(\s*"' + VAR, SOURCE)]
    assert len(code_reads) == 1, "all reads must go through command_console_flag_enabled()"
    assert reads, "sanity: the helper names the variable"


def test_the_three_former_readers_use_the_helper():
    assert SOURCE.count("command_console_flag_enabled()") >= 3


def test_settings_default_is_on():
    from jarvis.config import Settings
    assert Settings.model_fields["jarvis_command_console_enabled"].default is True
