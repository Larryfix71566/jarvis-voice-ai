from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).parents[2]


def test_architecture_reference_covers_ownership_boundaries_and_model_routes():
    text = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    for required in (
        "Runtime shape",
        "Trust and data boundaries",
        "Model routes",
        "Voice Supervisor/orchestrator",
        "Research comparison writer",
        "New memory classifier shadow",
        "JARVIS_BACKGROUND_PROFILE",
        "procedure description",
        "JARVIS_VAULT_PATH",
        "Command Console / Atlas",
        "Plan artifact integrity",
    ):
        assert required in text


def test_architecture_reference_is_linked_from_navigation_and_keeps_shadow_explicit():
    assert "ARCHITECTURE.md" in (ROOT / "README.md").read_text(encoding="utf-8")
    assert "ARCHITECTURE.md" in (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "ARCHITECTURE.md" in (ROOT / "docs" / "REPO_MAP.md").read_text(encoding="utf-8")
    shadow = (ROOT / "scripts" / "run_memory_provider_shadow.py").read_text(encoding="utf-8")
    assert 'parser.add_argument("--profile", required=True' in shadow
    assert "--dry-run" in shadow


def test_admin_architecture_endpoint_serves_the_checked_in_source(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "config").mkdir()
    (root / "config" / "self_edit_allowlist.json").write_text(
        '{"allow": ["docs/**"], "core": [], "deny": []}', encoding="utf-8"
    )
    source = "# Architecture\n\nSupervisor and specialist routes.\n"
    (root / "docs" / "ARCHITECTURE.md").write_text(source, encoding="utf-8")
    monkeypatch.setenv("JARVIS_REPO_ROOT", str(root))

    from jarvis.admin.server import app

    response = TestClient(app).get("/api/architecture")
    body = response.json()
    assert response.status_code == 200
    assert body["ok"] is True
    assert body["path"] == "docs/ARCHITECTURE.md"
    assert body["content"] == source
    assert body["truncated"] is False
    assert len(body["sha256"]) == 64
