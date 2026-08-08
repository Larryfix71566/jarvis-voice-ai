"""Unit tests for the Upgrade Agent contract (plan section 3.5).

The LLM is faked with a scripted client; what is under test is the agent's
side of the contract: closed toolset, loop bounds, the single-repair rule,
and that off-allowlist goals cannot produce edits.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from jarvis.agents.upgrade_agent import TOOL_SPECS, UpgradeAgent
from jarvis.selfedit.service import SelfEditService

ALLOWLIST = {"allow": ["web/src/**"], "deny": ["jarvis/**"]}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


@pytest.fixture()
def service(tmp_path: Path) -> SelfEditService:
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", str(origin))
    work = tmp_path / "work"
    _git(tmp_path, "clone", str(origin), str(work))
    _git(work, "config", "user.email", "t@e.com")
    _git(work, "config", "user.name", "T")
    _git(work, "checkout", "-b", "main")
    (work / "web/src").mkdir(parents=True)
    (work / "web/src/App.tsx").write_text("export default 1;\n")
    (work / "config").mkdir()
    (work / "config/self_edit_allowlist.json").write_text(json.dumps(ALLOWLIST))
    cfg = {
        "model": "fake-model", "temperature": 0.2,
        "max_iterations": 6, "max_session_minutes": 30,
    }
    (work / "config/upgrade_agent.yaml").write_text(yaml.safe_dump(cfg))
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "-u", "origin", "main")
    return SelfEditService(repo_root=work, github_token=None)


def _tool_call(name: str, args: dict, call_id: str = "c1") -> SimpleNamespace:
    return SimpleNamespace(
        id=call_id, type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def _response(message: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class ScriptedClient:
    """Plays back a list of messages, one per completion call."""

    def __init__(self, messages: list[SimpleNamespace]):
        self._messages = list(messages)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.calls = 0

    def _create(self, **_kwargs) -> SimpleNamespace:
        self.calls += 1
        assert self._messages, "scripted client ran out of messages"
        return _response(self._messages.pop(0))


def _msg(content=None, tool_calls=None) -> SimpleNamespace:
    return SimpleNamespace(content=content, tool_calls=tool_calls or [])


def _agent(service: SelfEditService, client: ScriptedClient) -> UpgradeAgent:
    return UpgradeAgent(
        service,
        config_path=service.repo_root / "config/upgrade_agent.yaml",
        client_factory=lambda: client,
    )


def test_toolset_is_closed() -> None:
    names = {t["function"]["name"] for t in TOOL_SPECS}
    assert names == {"file_read", "edit_propose", "session_validate", "session_submit"}


def test_unknown_tool_refused(service: SelfEditService) -> None:
    agent = _agent(service, ScriptedClient([_msg(content="done")]))
    result = agent._dispatch("shell", {"cmd": "rm -rf /"})
    assert not result["ok"]


def test_off_allowlist_goal_cannot_edit(service: SelfEditService) -> None:
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("edit_propose", {
            "path": "jarvis/wakeword.py", "new_content": "x=1\n",
            "rationale": "rewrite",
        })]),
        _msg(content="That path requires human development; I declined."),
    ])
    agent = _agent(service, client)
    result = agent.run("rewrite the wake word detector")
    assert result["ok"]  # agent finished by declining
    assert "declined" in result["summary"].lower() or "human" in result["summary"].lower()
    assert not (service.repo_root / "jarvis/wakeword.py").exists()


def test_iteration_bound_stops_runaway(service: SelfEditService) -> None:
    # The fake model keeps proposing the same edit forever.
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("edit_propose", {
            "path": "web/src/App.tsx", "new_content": f"export default {i};\n",
            "rationale": "loop",
        }, call_id=f"c{i}")])
        for i in range(50)
    ])
    agent = _agent(service, client)
    result = agent.run("endless tinkering")
    assert not result["ok"]
    assert "iteration limit" in result["summary"]
    assert client.calls == agent.cfg["max_iterations"]


def test_double_validation_failure_ends_session(service: SelfEditService) -> None:
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("session_validate", {}, "v1")]),
        _msg(tool_calls=[_tool_call("session_validate", {}, "v2")]),
    ])
    # Dirty a forbidden file so validation can never pass.
    agent = _agent(service, client)
    service.start_session("doomed")
    (service.repo_root / "jarvis").mkdir(exist_ok=True)
    (service.repo_root / "jarvis/x.py").write_text("bad\n")
    result = agent.run("validate me")
    assert not result["ok"]
    assert "validation failed twice" in result["summary"]
