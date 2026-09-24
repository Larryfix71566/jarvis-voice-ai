"""T2.3 — system_overview() and the flag readers it reuses."""

from __future__ import annotations

import pytest

from jarvis.status import overview as O
from jarvis.status.overview import flags, system_overview

FLAG_NAMES = [
    "JARVIS_UI_CONTROL_ENABLED", "JARVIS_SCREEN_ENABLED", "JARVIS_CLIPBOARD_ENABLED",
    "JARVIS_SPEAKER_GATE_ENABLED", "JARVIS_MEMORY_AUTOMATION_ENABLED",
    "JARVIS_MODEL_ROUTING_ENABLED", "JARVIS_KEY_HEALTH_ENABLED", "JARVIS_GRAPHS_ENABLED",
    "JARVIS_COUNCIL_ENABLED", "JARVIS_STATUS_TOOLS_ENABLED",
    "JARVIS_REGISTRY_SHARED_ENABLED",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in FLAG_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_overview_shape():
    out = system_overview(knowledge=lambda: {"ok": True, "stub": 1})
    assert out["ok"] is True
    agents = {a["name"]: a for a in out["agents"]}
    assert {"scheduler", "librarian", "analyst", "systems", "developer",
            "app_builder"} <= set(agents)
    dev = agents["developer"]
    assert set(dev) == {"name", "display_name", "model_profile", "mcp_servers",
                        "max_iterations"}
    assert dev["model_profile"] == "claude-opus"
    assert dev["max_iterations"] == 25
    assert agents["scheduler"]["max_iterations"] == 5      # the default when absent
    assert "mcp-time" in out["mcp_servers"]
    assert out["workloads"]["developer"] == {"profile": "claude-opus", "route": "direct_api"}
    assert list(out["flags"]) == FLAG_NAMES
    assert out["knowledge"] == {"ok": True, "stub": 1}


def test_flag_defaults():
    f = flags()
    assert f["JARVIS_UI_CONTROL_ENABLED"] == "on"
    assert f["JARVIS_SPEAKER_GATE_ENABLED"] == "off"         # the one default-off switch
    assert f["JARVIS_MEMORY_AUTOMATION_ENABLED"] == "off"
    assert f["JARVIS_MODEL_ROUTING_ENABLED"] == "off"
    assert f["JARVIS_STATUS_TOOLS_ENABLED"] == "on"
    assert f["JARVIS_REGISTRY_SHARED_ENABLED"] == "on"


@pytest.mark.parametrize("name,value,expected", [
    ("JARVIS_UI_CONTROL_ENABLED", "no", "off"),
    ("JARVIS_UI_CONTROL_ENABLED", "off", "on"),           # pipeline.py's exact rule
    ("JARVIS_MEMORY_AUTOMATION_ENABLED", "yes", "on"),
    ("JARVIS_MEMORY_AUTOMATION_ENABLED", "on", "off"),
    ("JARVIS_MODEL_ROUTING_ENABLED", "1", "on"),
    ("JARVIS_MODEL_ROUTING_ENABLED", "true", "off"),      # base.py's exact rule
    ("JARVIS_STATUS_TOOLS_ENABLED", "false", "off"),
    ("JARVIS_GRAPHS_ENABLED", "off", "off"),
    ("JARVIS_REGISTRY_SHARED_ENABLED", "false", "off"),
])
def test_flags_follow_existing_rules(monkeypatch, name, value, expected):
    monkeypatch.setenv(name, value)
    assert flags()[name] == expected


def test_knowledge_overview_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "k.db"))
    out = O.knowledge_overview()
    assert out["ok"] is True
    assert out["memory"]["live"] == 0
    assert set(out) == {"ok", "memory", "procedures", "skills", "workflows"}


def test_sidecar_knowledge_endpoint_uses_overview(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import jarvis.admin.server as srv

    monkeypatch.setattr(O, "knowledge_overview", lambda: {"ok": True, "sentinel": 7})
    assert TestClient(srv.app).get("/api/knowledge").json() == {"ok": True, "sentinel": 7}


def test_pipeline_and_base_call_the_named_readers():
    from pathlib import Path

    root = Path(O.__file__).resolve().parents[2]
    pipeline = (root / "jarvis" / "bot" / "pipeline.py").read_text()
    base = (root / "jarvis" / "agents" / "base.py").read_text()
    assert "ui_control_flag_enabled()" in pipeline
    assert '"JARVIS_UI_CONTROL_ENABLED"' not in pipeline
    assert "memory_automation_enabled()" in pipeline
    assert 'os.environ.get("JARVIS_MODEL_ROUTING_ENABLED") == "1"' not in base.replace(
        'return os.environ.get("JARVIS_MODEL_ROUTING_ENABLED") == "1"', "")
