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


def test_repo_map_under_cap_and_names_phase_modules():
    """GC2 (gap-closure plan, 2026-09-04): the architecture snapshot found
    docs/REPO_MAP.md silent about jarvis/usage_ledger.py, costs_api.py,
    memory_extraction*, kb_digest.py, effort.py, anthropic_shim.py,
    sensitive*, bot/usage_watcher.py, bot/late_result.py, bot/costs_tool.py,
    and mcp_servers/mcp_kb — real, currently-undocumented modules, not
    something owned by a later phase of this plan (jarvis/tenant.py,
    scripts/backup_db.py, scripts/launchd_gen.py are GC7/GC8, Phase B, and
    deliberately not asserted here until they exist). This is the actual
    docs/REPO_MAP.md file in the tree, not a fixture — regenerated from the
    tree, not from memory (§0 binding constraint 10)."""
    from pathlib import Path

    real_map = Path(__file__).resolve().parents[2] / "docs" / "REPO_MAP.md"
    text = real_map.read_text(encoding="utf-8")
    assert len(text) <= REPO_MAP_MAX_CHARS

    suffix = load_repo_map_suffix()
    for name in (
        "usage_ledger", "costs_api", "memory_extraction",
        "memory_extraction_worker", "kb_digest", "effort", "anthropic_shim",
        "sensitive", "bot/sensitive_turn.py", "bot/usage_watcher.py",
        "bot/late_result.py", "bot/costs_tool.py", "mcp_kb",
    ):
        assert name in suffix, name
