"""jarvis/repo_map.py — the shared read/cap/skip helper both SubAgent and
UpgradeAgent use (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md G5).
"""

from __future__ import annotations

import jarvis.repo_map as repo_map_module
from jarvis.repo_map import REPO_MAP_MAX_CHARS, load_repo_map_suffix


def test_returns_empty_string_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_map_module, "__file__", str(tmp_path / "jarvis" / "repo_map.py"))
    assert load_repo_map_suffix() == ""


def test_reads_and_wraps_content(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "REPO_MAP.md").write_text("## Map\n- x lives in y\n")
    monkeypatch.setattr(repo_map_module, "__file__", str(tmp_path / "jarvis" / "repo_map.py"))
    suffix = load_repo_map_suffix()
    assert "Repository map" in suffix
    assert "x lives in y" in suffix


def test_truncates_at_cap(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    big = "x" * (REPO_MAP_MAX_CHARS + 500)
    (tmp_path / "docs" / "REPO_MAP.md").write_text(big)
    monkeypatch.setattr(repo_map_module, "__file__", str(tmp_path / "jarvis" / "repo_map.py"))
    suffix = load_repo_map_suffix()
    injected = suffix.split("verify with tools before writing):\n")[1]
    assert len(injected) == REPO_MAP_MAX_CHARS


def test_custom_max_chars_respected(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "REPO_MAP.md").write_text("x" * 100)
    monkeypatch.setattr(repo_map_module, "__file__", str(tmp_path / "jarvis" / "repo_map.py"))
    suffix = load_repo_map_suffix(max_chars=10)
    injected = suffix.split("verify with tools before writing):\n")[1]
    assert len(injected) == 10
