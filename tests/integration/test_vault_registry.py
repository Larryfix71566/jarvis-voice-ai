"""Integration: a vault-injected variable reaches a spawned MCP server
(MORTIMER_CREDENTIAL_VAULT_PLAN.md §4's integration row).

End-to-end path under test: vault file -> inject_env() -> os.environ ->
SkillRegistry._start_server's ${VAR} expansion (jarvis.config.
expand_env_vars) -> the child process's environment. We prove the last
hop by making the variable observable: JARVIS_DB_PATH is stored ONLY in
the vault, mcp-notes is spawned with it via ${JARVIS_DB_PATH}, and the
note it creates must land in the vault-specified database file."""

from __future__ import annotations

import base64
import json
import sqlite3

import pytest
import yaml

import jarvis.vault as vault
from jarvis.skills.registry import SkillRegistry


KEY = base64.b64encode(b"\x07" * 32).decode("ascii")


@pytest.fixture
def vault_env(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_VAULT_KEY", KEY)
    monkeypatch.setenv("JARVIS_VAULT_PATH", str(tmp_path / "secrets.vault"))
    monkeypatch.delenv("JARVIS_VAULT_ENABLED", raising=False)
    return tmp_path


async def test_vault_injected_var_reaches_spawned_mcp_server(
    vault_env, monkeypatch
):
    db_path = vault_env / "vault-supplied.db"

    # The variable exists ONLY in the vault — not in the environment.
    vault.set_secret("JARVIS_DB_PATH", str(db_path))
    monkeypatch.delenv("JARVIS_DB_PATH", raising=False)

    assert vault.inject_env() >= 1
    from jarvis.db import run_migrations

    run_migrations()

    config = {
        "servers": [
            {
                "name": "mcp-notes",
                "command": "python",
                "args": ["-m", "mcp_servers.mcp_notes.server"],
                "env": {"JARVIS_DB_PATH": "${JARVIS_DB_PATH}"},
            }
        ]
    }
    config_path = vault_env / "servers.yaml"
    config_path.write_text(yaml.safe_dump(config))

    reg = SkillRegistry(config_path)
    await reg.start()
    try:
        created = json.loads(await reg.call(
            "create_note",
            {"title": "vault plumbing", "body": "via vault-injected env",
             "tags": "test"},
        ))
        assert "id" in created
    finally:
        await reg.stop()

    # The proof: the child process wrote to the vault-specified DB file.
    assert db_path.exists()
    conn = sqlite3.connect(db_path)
    try:
        titles = [r[0] for r in conn.execute("SELECT title FROM notes")]
    finally:
        conn.close()
    assert "vault plumbing" in titles
