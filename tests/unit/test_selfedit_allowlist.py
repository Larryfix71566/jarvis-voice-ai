"""Unit tests for the self-edit allowlist matcher (plan section 4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.selfedit.allowlist import Allowlist

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "config" / "self_edit_allowlist.json"


@pytest.fixture(scope="module")
def allowlist() -> Allowlist:
    return Allowlist.load(CONFIG)


@pytest.mark.parametrize("path", [
    "web/src/App.tsx",
    "web/src/components/NewPanel.tsx",
    "web/public/icons/panel.png",
    "config/voices.yaml",
    "jarvis/prompts.py",
    "jarvis/skills/new_skill.py",
    "docs/upgrade-notes.md",
    "README.md",
])
def test_allowed_paths(allowlist: Allowlist, path: str) -> None:
    assert allowlist.is_allowed(path), path


@pytest.mark.parametrize("path", [
    # the agent may not edit the editor or the safety gate
    "jarvis/selfedit/service.py",
    "jarvis/agents/upgrade_agent.py",
    ".github/workflows/validate.yml",
    "config/self_edit_allowlist.json",
    "config/upgrade_agent.yaml",
    # anything whose breakage kills the assistant
    "jarvis/wakeword/server.py",
    "jarvis/admin/server.py",
    "jarvis/bot/main.py",
    # dependency changes stay human-driven
    "requirements.txt",
    "requirements-lock.txt",
    "web/package.json",
    "web/package-lock.json",
    # secrets
    ".env",
    ".env.example",
    "web/.env.local",
    # human-only docs
    "DEVIATIONS.md",
    # not on the allow list at all
    "jarvis/cli.py",
    "web/index.html",
    "scripts/run_admin.sh",
    "mcp_servers/mcp_git/logic.py",
])
def test_forbidden_paths(allowlist: Allowlist, path: str) -> None:
    assert not allowlist.is_allowed(path), path


def test_path_traversal_rejected(allowlist: Allowlist) -> None:
    with pytest.raises(ValueError):
        allowlist.is_allowed("web/src/../../etc/passwd")


def test_filter_violations(allowlist: Allowlist) -> None:
    bad = allowlist.filter_violations([
        "web/src/App.tsx", "jarvis/wakeword/server.py", "README.md",
    ])
    assert bad == ["jarvis/wakeword/server.py"]


def test_empty_allow_list_rejected() -> None:
    with pytest.raises(ValueError):
        Allowlist(allow=[], deny=[])
