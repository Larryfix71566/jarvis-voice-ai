"""Unit tests for AppBuildAgent (MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_
PLAN.md Part D, D1/D7): the SAME UpgradeAgent loop, bound to an
AppWorkspace instead of a SelfEditWorkspace. Reuses test_upgrade_agent.py's
ScriptedClient pattern; what's under test here is specifically the three
things D1/D7 say differ (system prompt, app_build: config section,
JARVIS_APPBUILD_PROFILE env fallback, workflow="appbuild" tagging) — not
the loop mechanics, which test_upgrade_agent.py already covers via the
shared base class.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from jarvis.agents.upgrade_agent import (
    APP_BUILD_SYSTEM_PROMPT,
    APPBUILD_PROFILE_ENV,
    AppBuildAgent,
)
from jarvis.agents.workspace import AppWorkspace
from jarvis.db import get_conn, run_migrations


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "app_build_agent_test.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


@pytest.fixture()
def app_origin(tmp_path: Path) -> Path:
    origin = tmp_path / "remote" / "demo-app.git"
    origin.parent.mkdir(parents=True)
    _git(tmp_path, "init", "--bare", str(origin))
    seed = tmp_path / "seed"
    _git(tmp_path, "clone", str(origin), str(seed))
    _git(seed, "config", "user.email", "t@e.com")
    _git(seed, "config", "user.name", "T")
    _git(seed, "checkout", "-b", "main")
    (seed / "src").mkdir()
    (seed / "src" / "index.js").write_text("console.log(1);\n")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-m", "init")
    _git(seed, "push", "-u", "origin", "main")
    return origin


@pytest.fixture()
def workspace(app_origin: Path, tmp_path: Path) -> AppWorkspace:
    class FakeClient:
        token = "fake-token"
        def _owner(self) -> str:
            return "fake-owner"

    return AppWorkspace(
        "demo-app", github_client=FakeClient(),
        workspaces_dir=tmp_path / "workspaces",
        remote_url=str(app_origin),
    )


@pytest.fixture()
def agent_config_path(tmp_path: Path) -> Path:
    cfg = {
        "model": "fake-model", "temperature": 0.2,
        "max_iterations": 10, "max_session_minutes": 30,
        "app_build": {"max_iterations": 3, "max_session_minutes": 60},
    }
    path = tmp_path / "upgrade_agent.yaml"
    path.write_text(yaml.safe_dump(cfg))
    return path


def _tool_call(name: str, args: dict, call_id: str = "c1") -> SimpleNamespace:
    return SimpleNamespace(
        id=call_id, type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def _response(message: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _msg(content=None, tool_calls=None) -> SimpleNamespace:
    return SimpleNamespace(content=content, tool_calls=tool_calls or [])


class ScriptedClient:
    def __init__(self, messages: list[SimpleNamespace]):
        self._messages = list(messages)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.calls = 0

    def _create(self, **kwargs) -> SimpleNamespace:
        self.calls += 1
        assert self._messages, "scripted client ran out of messages"
        return _response(self._messages.pop(0))


def _agent(workspace: AppWorkspace, client: ScriptedClient, config_path: Path) -> AppBuildAgent:
    return AppBuildAgent(
        workspace, config_path=config_path, client_factory=lambda: client,
    )


def test_uses_app_build_system_prompt(workspace: AppWorkspace, agent_config_path: Path):
    client = ScriptedClient([_msg(content="done")])
    agent = _agent(workspace, client, agent_config_path)
    agent.run("do a small thing")
    assert client.calls == 1
    sent_messages = agent._system_prompt
    assert sent_messages == APP_BUILD_SYSTEM_PROMPT
    assert agent._system_prompt != agent._system_prompt.replace("App-Build", "x")  # sanity


def test_uses_app_build_config_section_loop_bound(workspace: AppWorkspace, agent_config_path: Path):
    # max_iterations for app_build is 3 (vs 10 top-level) — a runaway
    # model hits app_build's bound, not self-edit's.
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("edit_propose", {
            "path": "src/index.js", "new_content": f"console.log({i});\n",
            "rationale": "loop",
        }, call_id=f"c{i}")])
        for i in range(10)
    ])
    agent = _agent(workspace, client, agent_config_path)
    result = agent.run("endless tinkering")
    assert not result["ok"]
    assert "iteration limit" in result["summary"]
    assert client.calls == 3
    assert agent.cfg["max_iterations"] == 3


def test_env_profile_fallback_is_appbuild_specific(
    workspace: AppWorkspace, agent_config_path: Path, monkeypatch,
):
    """D7: JARVIS_APPBUILD_PROFILE is consulted (not JARVIS_UPGRADE_PROFILE)
    when no explicit profile is passed. No registry file exists at this
    config_path's directory, so profile resolution falls through to
    legacy mode either way — this pins that the env var is READ without
    raising, not that it changes the resolved model (that needs a real
    registry, covered by test_subagent-style tests elsewhere)."""
    monkeypatch.setenv(APPBUILD_PROFILE_ENV, "some-profile-name")
    monkeypatch.delenv("JARVIS_UPGRADE_PROFILE", raising=False)
    client = ScriptedClient([_msg(content="done")])
    # No registry_path given -> load_model_registry falls back to the
    # default config/upgrade_models.yaml, which DOES have profiles in this
    # repo, so pass a path to a nonexistent registry to force legacy mode
    # and isolate this test from the real registry contents.
    agent = AppBuildAgent(
        workspace, config_path=agent_config_path,
        registry_path=Path("/nonexistent/registry.yaml"),
        client_factory=lambda: client,
    )
    agent.run("small change")
    assert client.calls == 1  # ran without raising


def test_run_produces_app_build_pr_end_to_end(workspace: AppWorkspace, tmp_path: Path):
    cfg = {
        "model": "fake-model", "temperature": 0.2,
        "max_iterations": 10, "max_session_minutes": 30,
        "app_build": {"max_iterations": 10, "max_session_minutes": 60},
    }
    agent_config_path = tmp_path / "upgrade_agent_more_iters.yaml"
    agent_config_path.write_text(yaml.safe_dump(cfg))
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("edit_propose", {
            "path": "src/index.js", "new_content": "console.log(2);\n",
            "rationale": "bump",
        })]),
        _msg(tool_calls=[_tool_call("session_validate", {})]),
        _msg(tool_calls=[_tool_call("session_submit", {})]),
        _msg(content="Shipped it."),
    ])
    agent = _agent(workspace, client, agent_config_path)
    # AppWorkspace.submit() opens a real PR over HTTP — stub it, same as
    # the workspace-level test does.
    original_start = workspace.start_session
    def _start_and_stub(goal):
        res = original_start(goal)
        workspace._open_pr = lambda title: {"html_url": "https://example.invalid/pr/1"}
        _git(workspace.repo_root, "config", "user.email", "t@e.com")
        _git(workspace.repo_root, "config", "user.name", "T")
        return res
    workspace.start_session = _start_and_stub  # type: ignore[assignment]

    result = agent.run("bump the version")
    assert result["ok"], result
    assert workspace.status()["active"] is False
