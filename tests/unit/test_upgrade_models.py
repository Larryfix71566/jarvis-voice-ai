"""Unit tests for the upgrade planner model registry (config/model_profiles.yaml
joined with config/model_endpoints.yaml; these fixtures use the legacy
single-file shape, which the loader still accepts)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from jarvis.agents import upgrade_agent as ua
from jarvis.selfedit.service import SelfEditService
from tests.sandbox_fakes import FakeRuntime


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


@pytest.fixture
def service(tmp_path: Path) -> SelfEditService:
    """SelfEditService against a throwaway cloned repo (origin/main exists)."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", str(origin))
    work = tmp_path / "work"
    _git(tmp_path, "clone", str(origin), str(work))
    _git(work, "config", "user.email", "t@e.com")
    _git(work, "config", "user.name", "T")
    _git(work, "checkout", "-b", "main")
    (work / "config").mkdir()
    (work / "config/self_edit_allowlist.json").write_text(
        json.dumps({"allow": ["README.md"], "deny": []})
    )
    (work / "config/upgrade_agent.yaml").write_text(yaml.safe_dump(
        {"model": "gpt-4.1-mini", "temperature": 0.2,
         "max_iterations": 1, "max_session_minutes": 30}
    ))
    (work / "README.md").write_text("hello\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "-u", "origin", "main")
    runtime = FakeRuntime(work)
    service = SelfEditService(repo_root=work, github_token=None, runtime_factory=lambda: runtime)
    service.test_runtime = runtime
    return service


REGISTRY = {
    "default": "kimi-k2",
    "profiles": [
        {
            "name": "kimi-k2",
            "label": "Kimi K2.7 Code",
            "provider": "moonshot",
            "model": "kimi-k2.7-code",
            "base_url": "https://api.moonshot.ai/v1",
            "api_key_env": "MOONSHOT_API_KEY",
            "temperature": None,
        },
        {
            "name": "claude-opus",
            "label": "Claude Opus 5",
            "provider": "anthropic",
            "model": "claude-opus-5",
            "base_url": "https://api.anthropic.com/v1/",
            "api_key_env": "ANTHROPIC_API_KEY",
            "temperature": 0.2,
        },
    ],
}


@pytest.fixture
def registry_file(tmp_path: Path) -> Path:
    p = tmp_path / "upgrade_models.yaml"
    p.write_text(yaml.safe_dump(REGISTRY))
    return p


@pytest.fixture(autouse=True)
def clean_profile_env(monkeypatch):
    for var in ("JARVIS_UPGRADE_PROFILE", "JARVIS_UPGRADE_MODELS",
                "MOONSHOT_API_KEY", "ANTHROPIC_API_KEY",
                "JARVIS_UPGRADE_MODEL", "JARVIS_UPGRADE_BASE_URL"):
        monkeypatch.delenv(var, raising=False)


class CapturingClient:
    """OpenAI-SDK stand-in that records completion kwargs."""

    def __init__(self):
        self.requests = []
        self.chat = _Chat(self)


class _Chat:
    def __init__(self, outer):
        self.completions = _Completions(outer)


class _Completions:
    def __init__(self, outer):
        self._outer = outer

    def create(self, **kwargs):
        self._outer.requests.append(kwargs)

        class _Msg:
            content = "done"
            tool_calls = None

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()


def _legacy_agent(service, client, monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_UPGRADE_MODELS", str(tmp_path / "nonexistent.yaml"))
    return ua.UpgradeAgent(
        service,
        config_path=service.repo_root / "config" / "upgrade_agent.yaml",
        client_factory=lambda: client,
    )


def test_legacy_mode_without_registry(service, monkeypatch, tmp_path):
    client = CapturingClient()
    agent = _legacy_agent(service, client, monkeypatch, tmp_path)
    assert agent.profile_name is None
    assert agent.model == "gpt-4.1-mini"
    assert agent.model_label() == "gpt-4.1-mini"
    result = agent.run("change the readme")
    assert result["ok"] is True
    assert client.requests[0]["model"] == "gpt-4.1-mini"
    assert client.requests[0]["temperature"] == 0.2


def test_registry_loads_and_default_resolves(service, registry_file):
    agent = ua.UpgradeAgent(
        service, registry_path=registry_file, client_factory=CapturingClient
    )
    assert agent.profile_name == "kimi-k2"
    assert agent.model == "kimi-k2.7-code"
    assert agent.base_url == "https://api.moonshot.ai/v1"
    assert agent.model_label() == "kimi-k2 (kimi-k2.7-code)"


def test_env_var_overrides_registry_path(service, registry_file, monkeypatch):
    monkeypatch.setenv("JARVIS_UPGRADE_MODELS", str(registry_file))
    agent = ua.UpgradeAgent(service, client_factory=CapturingClient)
    assert agent.profile_name == "kimi-k2"


def test_explicit_profile_beats_env_beats_default(service, registry_file, monkeypatch):
    monkeypatch.setenv("JARVIS_UPGRADE_PROFILE", "claude-opus")
    agent = ua.UpgradeAgent(
        service, registry_path=registry_file, client_factory=CapturingClient
    )
    assert agent.profile_name == "claude-opus"  # env beats default
    agent2 = ua.UpgradeAgent(
        service, registry_path=registry_file, profile="kimi-k2",
        client_factory=CapturingClient,
    )
    assert agent2.profile_name == "kimi-k2"  # explicit beats env


def test_unknown_profile_raises_with_available_names(service, registry_file):
    with pytest.raises(ua.UnknownModelProfileError) as exc:
        ua.UpgradeAgent(
            service, registry_path=registry_file, profile="gpt-99",
            client_factory=CapturingClient,
        )
    assert "claude-opus" in str(exc.value) and "kimi-k2" in str(exc.value)


def test_temperature_null_is_omitted_from_request(service, registry_file):
    client = CapturingClient()
    agent = ua.UpgradeAgent(
        service, registry_path=registry_file, profile="kimi-k2",
        client_factory=lambda: client,
    )
    agent.run("touch the readme")
    assert "temperature" not in client.requests[0]  # D-003: omit entirely


def test_temperature_sent_when_set(service, registry_file):
    client = CapturingClient()
    agent = ua.UpgradeAgent(
        service, registry_path=registry_file, profile="claude-opus",
        client_factory=lambda: client,
    )
    agent.run("touch the readme")
    assert client.requests[0]["temperature"] == 0.2


def test_missing_api_key_fails_fast(service, registry_file):
    agent = ua.UpgradeAgent(service, registry_path=registry_file, profile="kimi-k2")
    assert agent._key_missing and agent._client is None
    result = agent.run("touch the readme")
    assert result["ok"] is False
    assert result["session_started"] is False
    assert "MOONSHOT_API_KEY" in result["summary"]


def test_available_models_reports_key_presence_without_material(
    service, registry_file, monkeypatch
):
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-test-secret")
    models = ua.available_models(registry_file)
    by_name = {m["name"]: m for m in models}
    assert by_name["kimi-k2"]["key_present"] is True
    assert by_name["kimi-k2"]["default"] is True
    assert by_name["claude-opus"]["key_present"] is False
    assert "sk-test-secret" not in json.dumps(models)


def test_missing_registry_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_UPGRADE_MODELS", str(tmp_path / "nope.yaml"))
    registry = ua.load_model_registry()
    assert registry == {"default": None, "profiles": {}}


def test_resolve_profile_errors_when_registry_empty():
    with pytest.raises(ua.UnknownModelProfileError):
        ua.resolve_profile({"default": None, "profiles": {}})
