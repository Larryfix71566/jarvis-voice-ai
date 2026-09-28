"""Unit tests for jarvis/tenant.py (gap-closure plan GC8, contract GC-T)."""
from __future__ import annotations

from jarvis import tenant


def test_unset_env_returns_default(monkeypatch):
    monkeypatch.delenv(tenant.USER_ID_ENV, raising=False)
    assert tenant.current_user_id() == "local"


def test_empty_env_returns_default(monkeypatch):
    monkeypatch.setenv(tenant.USER_ID_ENV, "   ")
    assert tenant.current_user_id() == "local"


def test_invalid_value_falls_back_to_default_with_warning(monkeypatch, caplog):
    canary = "PRIVATE_TENANT_ID_CANARY"
    monkeypatch.setenv(tenant.USER_ID_ENV, canary)  # uppercase not allowed
    with caplog.at_level("WARNING"):
        assert tenant.current_user_id() == "local"
    assert "tenant_user_id_invalid" in caplog.text
    assert canary not in caplog.text


def test_valid_value_is_used_verbatim(monkeypatch):
    monkeypatch.setenv(tenant.USER_ID_ENV, "larry-air")
    assert tenant.current_user_id() == "larry-air"


def test_overlong_value_falls_back_to_default(monkeypatch):
    monkeypatch.setenv(tenant.USER_ID_ENV, "a" * 65)
    assert tenant.current_user_id() == "local"


def test_user_id_scope_overrides_and_restores_process_default(monkeypatch):
    monkeypatch.setenv(tenant.USER_ID_ENV, "process-owner")
    with tenant.user_id_scope("request-owner"):
        assert tenant.current_user_id() == "request-owner"
    assert tenant.current_user_id() == "process-owner"


def test_user_id_scope_rejects_invalid_authenticated_identity():
    import pytest

    with (
        pytest.raises(ValueError, match="invalid authenticated user identifier"),
        tenant.user_id_scope("INVALID"),
    ):
        pass
