"""Fail-closed bind selection and port parsing."""

from __future__ import annotations

import pytest

from jarvis import auth, bind
from jarvis.db import get_conn, now_iso, run_migrations


def _add_token(token_name="test"):
    token = auth.mint_token()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO client_tokens (user_id, name, token_hash, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("larry", token_name, auth.hash_token(token), now_iso()),
        )
        conn.commit()
    return token


@pytest.fixture
def bind_db(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "bind.db"))
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    monkeypatch.delenv("JARVIS_BIND_HOST", raising=False)
    monkeypatch.delenv("JARVIS_BIND_STRICT", raising=False)
    run_migrations()


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.2.3", "localhost", "LOCALHOST", "::1"])
def test_is_loopback_table(host):
    assert bind.is_loopback(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "100.64.1.2", "192.168.1.10", ""])
def test_non_loopback_table(host):
    assert not bind.is_loopback(host)


def test_default_is_loopback_without_token(bind_db):
    assert bind.resolve_bind_host("test") == "127.0.0.1"


def test_auth_disabled_forces_loopback_even_when_remote_requested(bind_db, monkeypatch, caplog):
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "false")
    monkeypatch.setenv("JARVIS_BIND_HOST", "0.0.0.0")
    assert bind.resolve_bind_host("test") == "127.0.0.1"
    assert "bind_forced_loopback" in caplog.text


def test_remote_bind_without_token_refuses(bind_db, monkeypatch):
    monkeypatch.setenv("JARVIS_BIND_HOST", "100.64.1.2")
    with pytest.raises(bind.BindRefused, match="jarvis.auth add"):
        bind.resolve_bind_host("test")


def test_remote_bind_with_active_token_and_assigned_host_succeeds(bind_db, monkeypatch):
    _add_token()
    monkeypatch.setenv("JARVIS_BIND_HOST", "100.64.1.2")
    monkeypatch.setattr(bind, "_host_is_bindable", lambda _host: True)
    assert bind.resolve_bind_host("test") == "100.64.1.2"


def test_remote_bind_with_revoked_token_refuses(bind_db, monkeypatch):
    _add_token()
    with get_conn() as conn:
        conn.execute("UPDATE client_tokens SET revoked_at = ?", (now_iso(),))
        conn.commit()
    monkeypatch.setenv("JARVIS_BIND_HOST", "100.64.1.2")
    with pytest.raises(bind.BindRefused):
        bind.resolve_bind_host("test")


def test_unassigned_host_falls_back_to_loopback_by_default(bind_db, monkeypatch, caplog):
    _add_token()
    monkeypatch.setenv("JARVIS_BIND_HOST", "100.64.1.2")
    monkeypatch.setattr(bind, "_wait_for_host", lambda _host: False)
    assert bind.resolve_bind_host("test") == "127.0.0.1"
    assert "bind_fell_back_to_loopback" in caplog.text


def test_unassigned_host_refuses_when_strict(bind_db, monkeypatch):
    _add_token()
    monkeypatch.setenv("JARVIS_BIND_HOST", "100.64.1.2")
    monkeypatch.setenv("JARVIS_BIND_STRICT", "true")
    monkeypatch.setattr(bind, "_wait_for_host", lambda _host: False)
    with pytest.raises(bind.BindRefused, match="tailscale status"):
        bind.resolve_bind_host("test")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, 7861), ("", 7861), ("7999", 7999), ("abc", 7861), ("0", 7861), ("70000", 7861)],
)
def test_resolve_port_table(raw, expected, monkeypatch):
    if raw is None:
        monkeypatch.delenv("TEST_PORT", raising=False)
    else:
        monkeypatch.setenv("TEST_PORT", raw)
    assert bind.resolve_port("TEST_PORT", 7861) == expected
