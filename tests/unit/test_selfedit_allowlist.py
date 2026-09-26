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
    # Larry 2026-08-21 — "the interface thru self-edit could resolve the
    # issue when I ask": a missing agent tool is fixable by voice, which
    # needs the server code AND the two wiring files. The privilege-
    # escalation gate moves to where it always really was — the human
    # merging the PR on GitHub — plus the validation gates before it.
    "mcp_servers/mcp_memory/logic.py",
    "config/agents.yaml",
    "config/mcp_servers.yaml",
    # Model registry split (docs/plans/MORTIMER_MODEL_REGISTRY_SPLIT_PLAN.md
    # D1/D5): the profile POOL is routine via config/** — the loop may add a
    # model on an existing endpoint — because it cannot express a host or a
    # key (D3, a load error). The endpoint map below stays human-only.
    "config/model_profiles.yaml",
])
def test_allowed_paths(allowlist: Allowlist, path: str) -> None:
    assert allowlist.is_allowed(path), path


@pytest.mark.parametrize("path", [
    # Tier 0 (MORTIMER_SELFEDIT_TIERS_PLAN.md): files whose corruption the
    # loop cannot recover from because they ARE the loop.
    "jarvis/selfedit/service.py",
    "jarvis/agents/upgrade_agent.py",
    "jarvis/agents/workspace.py",
    "jarvis/admin/server.py",
    ".github/workflows/validate.yml",
    "config/self_edit_allowlist.json",
    "config/upgrade_agent.yaml",
    # migrations and the vault stay human-only (CLAUDE.md)
    "jarvis/db.py",
    "jarvis/vault.py",
    # the loop's own processes / the CI gate
    "scripts/mortimer.sh",
    "scripts/run_admin.sh",
    "scripts/check_allowlist.py",
    # the deploy script builds, tests and restarts production (2026-09-26)
    "scripts/deploy_main.sh",
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
    # not on any list at all
    "web/index.html",
    "Makefile",
    # still denied even though mcp_servers/config opened up (2026-08-21):
    # the agent's own brain, the enable gate for agent skills, and the
    # allowlist itself remain human-only. The brain's credential half is
    # config/model_endpoints.yaml since the registry split (D5 — it replaced
    # config/upgrade_models.yaml here, which no longer exists).
    "config/model_endpoints.yaml",
    "config/skills.yaml",
    # no Swift gate exists, so a self-edit here would be unvalidated
    "macos/MortimerHost/Package.swift",
])
def test_forbidden_paths(allowlist: Allowlist, path: str) -> None:
    assert not allowlist.is_allowed(path), path
    assert allowlist.tier(path) in ("denied", "unlisted")


@pytest.mark.parametrize("path", [
    # Tier B — the product core, editable with ceremony (Larry 2026-08-31:
    # "if we continue to deny everything we want to do self-edit wise then
    # a self-edit is not useful"). Recoverable by construction: a bad edit
    # lives on a sandbox branch Mortimer cannot merge.
    "jarvis/bot/display.py",
    "jarvis/bot/pipeline.py",
    "jarvis/agents/base.py",
    "jarvis/agents/delegate.py",
    "jarvis/wakeword/server.py",
    "jarvis/memory.py",
    "jarvis/cli.py",
    "scripts/run_bot.sh",
])
def test_core_paths_are_allowed_with_ceremony(allowlist: Allowlist, path: str) -> None:
    assert allowlist.is_allowed(path), path
    assert allowlist.is_core(path), path
    assert allowlist.tier(path) == "core"


def test_routine_outranks_core_and_deny_outranks_both(allowlist: Allowlist) -> None:
    # jarvis/prompts.py matches allow AND core (jarvis/**) → routine.
    assert allowlist.tier("jarvis/prompts.py") == "routine"
    assert not allowlist.is_core("jarvis/prompts.py")
    # jarvis/selfedit/** matches core (jarvis/**) AND deny → denied.
    assert allowlist.tier("jarvis/selfedit/allowlist.py") == "denied"


def test_classify_groups_by_tier(allowlist: Allowlist) -> None:
    groups = allowlist.classify([
        "web/src/App.tsx", "jarvis/bot/display.py", "jarvis/vault.py", "Makefile",
    ])
    assert groups == {
        "routine": ["web/src/App.tsx"],
        "core": ["jarvis/bot/display.py"],
        "denied": ["jarvis/vault.py"],
        "unlisted": ["Makefile"],
    }


class TestExtractPaths:
    """The preview pre-flight finds the files a goal NAMES."""

    def test_finds_slashed_paths_and_source_files(self):
        from jarvis.selfedit.allowlist import extract_paths
        goal = ("Touch jarvis/bot/display.py (merge per-request results), "
                "web/src/displayResults.ts, and DisplayContent.tsx; leave README.md.")
        assert extract_paths(goal) == [
            "jarvis/bot/display.py", "web/src/displayResults.ts",
            "DisplayContent.tsx", "README.md",
        ]

    def test_ignores_versions_urls_and_prose(self):
        from jarvis.selfedit.allowlist import extract_paths
        goal = ("Upgrade to pipecat 1.4 per https://docs.pipecat.ai/x/y.html; "
                "the caption width was 160 → 600. Nothing else.")
        assert extract_paths(goal) == []

    def test_dedupes_and_strips_punctuation(self):
        from jarvis.selfedit.allowlist import extract_paths
        assert extract_paths("edit web/src/App.tsx. Then web/src/App.tsx, again ./docs/a.md.") == [
            "web/src/App.tsx", "docs/a.md",
        ]


def test_path_traversal_rejected(allowlist: Allowlist) -> None:
    with pytest.raises(ValueError):
        allowlist.is_allowed("web/src/../../etc/passwd")


def test_filter_violations(allowlist: Allowlist) -> None:
    bad = allowlist.filter_violations([
        "web/src/App.tsx", "jarvis/vault.py", "README.md",
    ])
    assert bad == ["jarvis/vault.py"]


def test_empty_allow_list_rejected() -> None:
    with pytest.raises(ValueError):
        Allowlist(allow=[], deny=[])
