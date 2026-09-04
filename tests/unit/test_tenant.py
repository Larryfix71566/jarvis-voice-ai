"""Unit tests for jarvis/tenant.py (gap-closure plan GC8, contract GC-T)."""
from __future__ import annotations

import pytest

from jarvis import tenant


def test_unset_env_returns_default(monkeypatch):
    monkeypatch.delenv(tenant.USER_ID_ENV, raising=False)
    assert tenant.current_user_id() == "local"


def test_empty_env_returns_default(monkeypatch):
    monkeypatch.setenv(tenant.USER_ID_ENV, "   ")
    assert tenant.current_user_id() == "local"


def test_invalid_value_falls_back_to_default_with_warning(monkeypatch, caplog):
    monkeypatch.setenv(tenant.USER_ID_ENV, "Larry")  # uppercase not allowed
    with caplog.at_level("WARNING"):
        assert tenant.current_user_id() == "local"
    assert "tenant_user_id_invalid" in caplog.text


def test_valid_value_is_used_verbatim(monkeypatch):
    monkeypatch.setenv(tenant.USER_ID_ENV, "larry-air")
    assert tenant.current_user_id() == "larry-air"


def test_overlong_value_falls_back_to_default(monkeypatch):
    monkeypatch.setenv(tenant.USER_ID_ENV, "a" * 65)
    assert tenant.current_user_id() == "local"
