"""Unit tests for jarvis/vault.py (MORTIMER_CREDENTIAL_VAULT_PLAN.md).

All tests run with JARVIS_VAULT_KEY set and JARVIS_VAULT_PATH pointed at
tmp_path — keyring is never touched (the env key short-circuits S2's
resolution order before the keychain is consulted)."""

from __future__ import annotations

import base64
import json
import os
import stat

import pytest

import jarvis.vault as vault
from jarvis.vault import VaultError


KEY = base64.b64encode(b"\x01" * 32).decode("ascii")


@pytest.fixture(autouse=True)
def _vault_env(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_VAULT_KEY", KEY)
    monkeypatch.setenv("JARVIS_VAULT_PATH", str(tmp_path / "secrets.vault"))
    monkeypatch.delenv("JARVIS_VAULT_ENABLED", raising=False)
    return tmp_path


# ------------------------------------------------------------------ S1 core


class TestRoundtrip:
    def test_set_get_delete_roundtrip(self):
        vault.set_secret("OPENAI_API_KEY", "sk-test-123")
        vault.set_secret("GMAIL_REFRESH_TOKEN", "tok-456")
        assert vault.get_secret("OPENAI_API_KEY") == "sk-test-123"
        assert set(vault.load_secrets()) == {"OPENAI_API_KEY", "GMAIL_REFRESH_TOKEN"}
        vault.delete_secret("OPENAI_API_KEY")
        assert vault.get_secret("OPENAI_API_KEY") is None
        assert vault.get_secret("GMAIL_REFRESH_TOKEN") == "tok-456"

    def test_reload_is_process_independent(self):
        # A fresh read decrypts from disk — nothing cached in-module.
        vault.set_secret("NAME", "value")
        envelope = json.loads(vault.vault_path().read_text())
        assert envelope["version"] == 1
        assert "ciphertext" in envelope and "nonce" in envelope
        assert "value" not in vault.vault_path().read_text()  # never plaintext
        assert vault.load_secrets() == {"NAME": "value"}

    def test_fresh_nonce_every_write(self):
        vault.set_secret("A", "1")
        nonce1 = json.loads(vault.vault_path().read_text())["nonce"]
        vault.set_secret("B", "2")
        nonce2 = json.loads(vault.vault_path().read_text())["nonce"]
        assert nonce1 != nonce2

    def test_file_mode_is_0600(self):
        vault.set_secret("NAME", "value")
        mode = stat.S_IMODE(os.stat(vault.vault_path()).st_mode)
        assert mode == 0o600

    def test_tampered_ciphertext_raises_with_corruption_message(self):
        vault.set_secret("NAME", "value")
        path = vault.vault_path()
        envelope = json.loads(path.read_text())
        raw = bytearray(base64.b64decode(envelope["ciphertext"]))
        raw[0] ^= 0xFF
        envelope["ciphertext"] = base64.b64encode(bytes(raw)).decode("ascii")
        path.write_text(json.dumps(envelope))
        with pytest.raises(VaultError, match="wrong key or corrupted"):
            vault.load_secrets()

    def test_delete_missing_name_raises(self):
        vault.set_secret("A", "1")
        with pytest.raises(VaultError, match="no secret named B"):
            vault.delete_secret("B")

    def test_empty_value_rejected(self):
        with pytest.raises(VaultError, match="empty value"):
            vault.set_secret("NAME", "")
        with pytest.raises(VaultError, match="empty value"):
            vault.set_secret("NAME", "   ")


# ------------------------------------------------------------------- S2 key


class TestKeyResolution:
    def test_malformed_env_key_raises_no_keyring_fallthrough(self, monkeypatch):
        monkeypatch.setenv("JARVIS_VAULT_KEY", "not-base64!!!")
        # If this ever fell through to keyring, the error would be about
        # the keychain, not base64 — the match pins the S2.1 behavior.
        with pytest.raises(VaultError, match="not valid base64"):
            vault.set_secret("NAME", "value")

    def test_wrong_length_key_raises(self, monkeypatch):
        monkeypatch.setenv(
            "JARVIS_VAULT_KEY", base64.b64encode(b"short").decode("ascii")
        )
        with pytest.raises(VaultError, match="32 bytes"):
            vault.set_secret("NAME", "value")

    def test_wrong_key_fails_authentication(self, monkeypatch):
        vault.set_secret("NAME", "value")
        monkeypatch.setenv(
            "JARVIS_VAULT_KEY", base64.b64encode(b"\x02" * 32).decode("ascii")
        )
        with pytest.raises(VaultError, match="wrong key or corrupted"):
            vault.load_secrets()


# ------------------------------------------------------------- S4 inject_env


class TestInjectEnv:
    def test_injects_missing_names(self, monkeypatch):
        vault.set_secret("SOME_API_KEY", "from-vault")
        monkeypatch.delenv("SOME_API_KEY", raising=False)
        assert vault.inject_env() == 1
        assert os.environ["SOME_API_KEY"] == "from-vault"

    def test_nonempty_env_value_wins(self, monkeypatch):
        vault.set_secret("SOME_API_KEY", "from-vault")
        monkeypatch.setenv("SOME_API_KEY", "from-env")
        assert vault.inject_env() == 0
        assert os.environ["SOME_API_KEY"] == "from-env"

    def test_empty_string_env_value_loses_to_vault(self, monkeypatch):
        # The load-bearing S4 clause: `set -a; . ./.env` exports blank
        # NAME= lines as "" — those must be treated as unset.
        vault.set_secret("SOME_API_KEY", "from-vault")
        monkeypatch.setenv("SOME_API_KEY", "")
        assert vault.inject_env() == 1
        assert os.environ["SOME_API_KEY"] == "from-vault"

    def test_absent_vault_returns_zero_no_error(self):
        assert not vault.vault_path().exists()
        assert vault.inject_env() == 0

    def test_kill_switch_disables_injection(self, monkeypatch):
        vault.set_secret("SOME_API_KEY", "from-vault")
        monkeypatch.delenv("SOME_API_KEY", raising=False)
        monkeypatch.setenv("JARVIS_VAULT_ENABLED", "false")
        assert vault.inject_env() == 0
        assert "SOME_API_KEY" not in os.environ

    def test_present_vault_missing_key_raises_not_falls_back(self, monkeypatch):
        vault.set_secret("SOME_API_KEY", "from-vault")

        # Simulate S6's hard-error row: vault present, key unavailable.
        monkeypatch.delenv("JARVIS_VAULT_KEY", raising=False)

        def _no_key(*_a, **_k):
            return None

        monkeypatch.setattr(vault.keyring, "get_password", _no_key)
        with pytest.raises(VaultError, match="no vault key found"):
            vault.inject_env()


# --------------------------------------------------------------- S5 migrate


ENV_FIXTURE = """\
# Deepgram (speech-to-text)
DEEPGRAM_API_KEY=dg-live-abc
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-live-def
TAVILY_API_KEY=
JARVIS_TIMEZONE=America/New_York
CUSTOM_THING_TOKEN=tok-xyz
# a comment mentioning GITHUB_TOKEN= stays untouched
"""


class TestMigrate:
    def _write_env(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(ENV_FIXTURE)
        return env_file

    def test_matched_names_migrate_and_lines_become_comments(self, _vault_env):
        env_file = self._write_env(_vault_env)
        result = vault.migrate_env_file(env_file)
        assert result["migrated"] == [
            "DEEPGRAM_API_KEY", "OPENAI_API_KEY", "CUSTOM_THING_TOKEN",
        ]
        assert result["skipped"] == ["TAVILY_API_KEY"]

        secrets = vault.load_secrets()
        assert secrets["DEEPGRAM_API_KEY"] == "dg-live-abc"
        assert secrets["OPENAI_API_KEY"] == "sk-live-def"
        assert secrets["CUSTOM_THING_TOKEN"] == "tok-xyz"  # suffix pattern

        text = env_file.read_text()
        assert "dg-live-abc" not in text
        assert "sk-live-def" not in text
        assert "# DEEPGRAM_API_KEY moved to vault" in text
        # No blank NAME= left behind for a migrated name.
        assert "\nDEEPGRAM_API_KEY=" not in text

    def test_unmatched_lines_byte_identical(self, _vault_env):
        env_file = self._write_env(_vault_env)
        vault.migrate_env_file(env_file)
        text = env_file.read_text()
        assert "OPENAI_BASE_URL=https://api.openai.com/v1\n" in text
        assert "JARVIS_TIMEZONE=America/New_York\n" in text
        assert "# a comment mentioning GITHUB_TOKEN= stays untouched\n" in text
        # Empty-valued secret line untouched (skipped, not commented).
        assert "TAVILY_API_KEY=\n" in text

    def test_second_run_is_a_noop(self, _vault_env):
        env_file = self._write_env(_vault_env)
        vault.migrate_env_file(env_file)
        before = env_file.read_text()
        result = vault.migrate_env_file(env_file)
        assert result["migrated"] == []
        assert env_file.read_text() == before

    def test_missing_env_file_raises(self, _vault_env):
        with pytest.raises(VaultError, match="no env file"):
            vault.migrate_env_file(_vault_env / "nope.env")


# ------------------------------------------------------------------- S7 CLI


class TestCli:
    def test_set_via_prompt_and_list_shows_names_not_values(
        self, monkeypatch, capsys
    ):
        monkeypatch.setattr(vault.getpass, "getpass", lambda _prompt: "sk-cli-1")
        assert vault.main(["set", "MY_API_KEY"]) == 0
        assert vault.main(["list"]) == 0
        out = capsys.readouterr().out
        assert "MY_API_KEY" in out
        assert "sk-cli-1" not in out

    def test_get_prints_value(self, monkeypatch, capsys):
        vault.set_secret("MY_API_KEY", "sk-cli-2")
        assert vault.main(["get", "MY_API_KEY"]) == 0
        assert "sk-cli-2" in capsys.readouterr().out

    def test_get_missing_returns_nonzero(self, capsys):
        vault.set_secret("A", "1")
        assert vault.main(["get", "NOPE"]) == 1

    def test_status_reports_counts(self, capsys):
        vault.set_secret("A", "1")
        vault.set_secret("B", "2")
        assert vault.main(["status"]) == 0
        out = capsys.readouterr().out
        assert "2 secret(s)" in out

    def test_vault_error_becomes_exit_code_1(self, monkeypatch, capsys):
        monkeypatch.setenv("JARVIS_VAULT_KEY", "not-base64!!!")
        vault.vault_path().parent.mkdir(parents=True, exist_ok=True)
        vault.vault_path().write_text("{}")
        assert vault.main(["list"]) == 1
        assert "error:" in capsys.readouterr().err


# ------------------------------------------------- S4 call site: load_settings


class TestLoadSettingsCallSite:
    def test_load_settings_sees_vault_injected_key(self, monkeypatch):
        """S4 call site 1: a required key present ONLY in the vault
        satisfies Settings — proof the injection happens before pydantic
        looks at the environment."""
        vault.set_secret("OPENAI_API_KEY", "sk-from-vault")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-x")
        monkeypatch.setenv("ELEVENLABS_API_KEY", "el-x")
        monkeypatch.setenv("TAVILY_API_KEY", "tv-x")

        from jarvis.config import load_settings

        settings = load_settings(env_file=None)
        assert settings.openai_api_key == "sk-from-vault"

    def test_load_settings_env_still_wins_over_vault(self, monkeypatch):
        vault.set_secret("OPENAI_API_KEY", "sk-from-vault")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
        monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-x")
        monkeypatch.setenv("ELEVENLABS_API_KEY", "el-x")
        monkeypatch.setenv("TAVILY_API_KEY", "tv-x")

        from jarvis.config import load_settings

        settings = load_settings(env_file=None)
        assert settings.openai_api_key == "sk-from-env"
