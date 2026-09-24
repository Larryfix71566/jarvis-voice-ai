"""The runner import cannot override the exported environment (C6 item 12)."""
import types

from jarvis.bot.bot import _runner_main_preserving_env


def _fake_runner(mutations):
    def importer():
        import os
        for key, value in mutations.items():
            os.environ[key] = value
        return types.SimpleNamespace(main=lambda: "ran")
    return importer


def test_exported_value_survives_the_runner_dotenv(monkeypatch, caplog):
    monkeypatch.setenv("JARVIS_DB_PATH", "/intended/jarvis.db")
    main = _runner_main_preserving_env(_fake_runner({"JARVIS_DB_PATH": "data/jarvis.db"}))
    import os
    assert os.environ["JARVIS_DB_PATH"] == "/intended/jarvis.db"
    assert main() == "ran"
    assert "pipecat_dotenv_override_reverted keys=JARVIS_DB_PATH" in caplog.text


def test_variables_the_import_adds_are_kept(monkeypatch):
    monkeypatch.delenv("JARVIS_ADDED_BY_RUNNER", raising=False)
    _runner_main_preserving_env(_fake_runner({"JARVIS_ADDED_BY_RUNNER": "local"}))
    import os
    assert os.environ.pop("JARVIS_ADDED_BY_RUNNER") == "local"


def test_no_change_logs_nothing(monkeypatch, caplog):
    monkeypatch.setenv("JARVIS_DB_PATH", "/same.db")
    _runner_main_preserving_env(_fake_runner({"JARVIS_DB_PATH": "/same.db"}))
    assert "pipecat_dotenv_override_reverted" not in caplog.text
