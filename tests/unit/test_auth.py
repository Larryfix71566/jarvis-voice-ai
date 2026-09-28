"""Client bearer-token storage and CLI contract (Remote Access plan K1)."""
from __future__ import annotations

import hashlib
import re
import sqlite3

import pytest

from jarvis import auth


@pytest.fixture(autouse=True)
def auth_db(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "auth.db"))


def _add(name: str, capsys) -> str:
    assert auth.main(["add", name]) == 0
    return capsys.readouterr().out.strip().splitlines()[0]


def test_minted_token_shape():
    tokens = [auth.mint_token() for _ in range(100)]
    assert all(token.startswith("jvt_") and len(token) == 47 for token in tokens)
    assert all(re.fullmatch(r"jvt_[A-Za-z0-9_-]{43}", token) for token in tokens)
    assert all("=" not in token for token in tokens)


def test_mints_are_unique():
    assert len({auth.mint_token() for _ in range(1000)}) == 1000


def test_hash_token_is_sha256_hex():
    actual = auth.hash_token("jvt_abc")
    assert actual == hashlib.sha256(b"jvt_abc").hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", actual)


@pytest.mark.parametrize("header", [None, "", "   "])
def test_parse_bearer_rejects_missing(header):
    assert auth.parse_bearer(header) is None


@pytest.mark.parametrize("header", [
    "Basic jvt_" + "A" * 43,
    "Token jvt_" + "A" * 43,
    "jvt_" + "A" * 43,
    "Bearer",
    "Bearer jvt_" + "A" * 43 + " extra",
])
def test_parse_bearer_rejects_wrong_scheme_or_shape(header):
    assert auth.parse_bearer(header) is None


@pytest.mark.parametrize("scheme", ["bearer", "BEARER", "BeArEr"])
def test_parse_bearer_accepts_scheme_case_insensitively(scheme):
    token = "jvt_" + "A" * 43
    assert auth.parse_bearer(f"{scheme} {token}") == token


@pytest.mark.parametrize("header", [
    "Bearer  jvt_" + "A" * 43,
    "  Bearer jvt_" + "A" * 43 + "  ",
])
def test_parse_bearer_tolerates_extra_whitespace(header):
    assert auth.parse_bearer(header) == "jvt_" + "A" * 43


def test_parse_bearer_rejects_wrong_prefix():
    assert auth.parse_bearer("Bearer xxx_" + "A" * 43) is None


@pytest.mark.parametrize("token", ["jvt_" + "A" * 42, "jvt_" + "A" * 44, "jvt_"])
def test_parse_bearer_rejects_wrong_length(token):
    assert auth.parse_bearer(f"Bearer {token}") is None


def test_verify_bearer_never_touches_db_for_malformed():
    class RaisingConn:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("malformed token reached the database")

    assert auth.verify_bearer("Bearer jvt_" + "A" * 44, conn=RaisingConn()) is None


def test_verify_bearer_unknown_token(capsys):
    known = _add("known", capsys)
    other = auth.mint_token()
    assert other != known
    assert auth.verify_bearer(f"Bearer {other}") is None


def test_verify_bearer_valid_and_updates_last_used(capsys):
    token = _add("phone", capsys)
    identity = auth.verify_bearer(f"Bearer {token}")
    assert identity == auth.ClientIdentity(name="phone", user_id="larry")
    conn = auth.get_conn()
    row = conn.execute(
        "SELECT created_at, last_used_at FROM client_tokens WHERE name='phone'"
    ).fetchone()
    conn.close()
    assert row["last_used_at"] is not None
    assert row["last_used_at"] >= row["created_at"]


def test_verify_bearer_revoked(capsys):
    token = _add("phone", capsys)
    conn = auth.get_conn()
    conn.execute("UPDATE client_tokens SET revoked_at='2026-09-26T00:00:00Z'")
    conn.commit()
    conn.close()
    assert auth.verify_bearer(f"Bearer {token}") is None


def test_no_plaintext_in_database(capsys):
    token = _add("phone", capsys)
    path = auth.get_conn()
    path.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    path.close()
    db_file = __import__("pathlib").Path(__import__("os").environ["JARVIS_DB_PATH"])
    contents = db_file.read_bytes()
    assert token[4:].encode() not in contents
    assert auth.hash_token(token).encode() in contents


def test_add_duplicate_name_refuses_even_after_revoke(capsys):
    _add("phone", capsys)
    assert auth.main(["add", "phone"]) == 2
    conn = auth.get_conn()
    conn.execute("UPDATE client_tokens SET revoked_at='2026-09-26T00:00:00Z'")
    conn.commit()
    conn.close()
    assert auth.main(["add", "phone"]) == 2
    captured = capsys.readouterr()
    assert "already exists" in captured.err


def test_revoke_unknown_name_refuses(capsys):
    assert auth.main(["revoke", "nope"]) == 2
    assert "no active token named" in capsys.readouterr().err


def test_list_never_prints_a_hash(capsys):
    token = _add("phone", capsys)
    assert auth.main(["list"]) == 0
    output = capsys.readouterr().out
    assert "phone" in output and "larry" in output and "active" in output
    assert auth.hash_token(token) not in output
    assert re.search(r"\b[0-9a-f]{64}\b", output) is None


def test_count_active_excludes_revoked(capsys):
    _add("one", capsys)
    _add("two", capsys)
    _add("three", capsys)
    conn = auth.get_conn()
    conn.execute("UPDATE client_tokens SET revoked_at='2026-09-26T00:00:00Z' WHERE name='two'")
    conn.commit()
    conn.close()
    assert auth.count_active_tokens() == 2


@pytest.mark.parametrize("value,expected", [
    (None, {}), ("", {}), ("  jvt_x  ", {"Authorization": "Bearer jvt_x"}),
])
def test_service_headers(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("JARVIS_SERVICE_TOKEN", raising=False)
    else:
        monkeypatch.setenv("JARVIS_SERVICE_TOKEN", value)
    assert auth.service_headers() == expected


@pytest.mark.parametrize("value,expected", [
    (None, True), ("true", True), ("false", False), ("False", False),
    ("FALSE", False), (" false ", False), ("0", True), ("no", True),
    ("off", True), ("", True),
])
def test_auth_enabled_table(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("JARVIS_AUTH_ENABLED", raising=False)
    else:
        monkeypatch.setenv("JARVIS_AUTH_ENABLED", value)
    assert auth.auth_enabled() is expected
