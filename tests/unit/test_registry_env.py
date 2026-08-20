"""MORTIMER_ENV_BRIDGE_PLAN.md — `.env` is not `os.environ`.

`RUN_LIVE=1 python -m tests.evals.routing_eval` crashed every set_reminder
with `ZoneInfoNotFoundError: 'No time zone found with key
${JARVIS_TIMEZONE}'` — the literal placeholder, reaching a child process as
its timezone.

The cause was not a missing value. `.env` line 32 sets
JARVIS_TIMEZONE=America/New_York and `ZoneInfo('America/New_York')` resolves
fine. `.env` is a FILE; `os.environ` is a PROCESS, and pydantic-settings
reads the file into a Settings object without touching the environment.
`bridge_settings_to_env` was the thing that copied it across, and it had to
be REMEMBERED: pipeline.py, cli.py and test_orchestrator_live.py remembered;
routing_eval.py did not.

These tests exist because that class of bug was made three times on
2026-08-19 — twice in credential probes reading OPENAI_BASE_URL from
os.environ, once here — and every time the symptom pointed somewhere other
than the cause.

No child processes are spawned: `_start_server` is stubbed.
"""

from __future__ import annotations

import os

import pytest

from jarvis.skills.registry import SkillRegistry


@pytest.fixture()
def config_file(tmp_path):
    path = tmp_path / "servers.yaml"
    path.write_text(
        "servers:\n"
        "  - name: mcp-test\n"
        "    command: python\n"
        "    args: [\"-c\", \"pass\"]\n"
        "    env:\n"
        "      JARVIS_TIMEZONE: \"${JARVIS_TIMEZONE}\"\n"
        "      MISSING_ONE: \"${NOT_SET_ANYWHERE_AT_ALL}\"\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def captured(monkeypatch, config_file):
    """Start the registry with _start_server stubbed, capturing the env each
    child WOULD have received."""
    seen: list[dict] = []

    async def fake_start_server(self, entry):
        env = dict(os.environ)
        from jarvis.config import expand_env_vars
        for key, value in (entry.get("env") or {}).items():
            env[key] = expand_env_vars(str(value))
        seen.append(env)

    monkeypatch.setattr(SkillRegistry, "_start_server", fake_start_server)
    return seen


class TestBridge:
    async def test_start_bridges_settings_into_the_environment(
            self, monkeypatch, config_file, captured):
        """E1 — THE test. A registry started with no prior bridge call must
        still give its children a real timezone. This is exactly what
        routing_eval did, and what crashed."""
        monkeypatch.delenv("JARVIS_TIMEZONE", raising=False)
        registry = SkillRegistry(config_file)
        await registry.start()
        assert os.environ.get("JARVIS_TIMEZONE")
        assert "${" not in os.environ["JARVIS_TIMEZONE"]

    async def test_an_explicit_env_var_still_wins(
            self, monkeypatch, config_file, captured):
        """setdefault, never assignment: a real environment variable is the
        CI/override channel and must keep winning. This is also what makes
        the bridge idempotent, which is why cli.py and pipeline.py keep
        their own calls."""
        monkeypatch.setenv("JARVIS_TIMEZONE", "Europe/Berlin")
        registry = SkillRegistry(config_file)
        await registry.start()
        assert os.environ["JARVIS_TIMEZONE"] == "Europe/Berlin"

    async def test_bridging_twice_changes_nothing(self, monkeypatch):
        from jarvis.config import bridge_settings_to_env
        monkeypatch.setenv("JARVIS_TIMEZONE", "Europe/Berlin")
        bridge_settings_to_env()
        bridge_settings_to_env()
        assert os.environ["JARVIS_TIMEZONE"] == "Europe/Berlin"

    def test_a_broken_settings_object_does_not_raise(self, monkeypatch):
        """Best-effort: one unbuildable Settings must not turn a stale env
        entry into a bot that will not start."""
        import jarvis.config as cfg
        monkeypatch.setattr(
            cfg, "load_settings",
            lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        cfg.bridge_settings_to_env()  # must not raise


class TestUnresolvedPlaceholder:
    async def test_an_unresolved_var_is_logged_with_its_name(
            self, monkeypatch, config_file, caplog):
        """E2 — expand_env_vars leaves ${VAR} literal BY DESIGN, and that
        design is relied on elsewhere. The failure was that nothing said so:
        the only symptom was a ZoneInfoNotFoundError five frames deep inside
        a subprocess."""
        monkeypatch.delenv("NOT_SET_ANYWHERE_AT_ALL", raising=False)
        registry = SkillRegistry(config_file)
        with caplog.at_level("WARNING", logger="jarvis.skills.registry"):
            try:
                await registry.start()
            except Exception:  # noqa: BLE001 — a real spawn may fail here
                pass
        warnings = [r.message for r in caplog.records
                    if "mcp_server_env_unresolved" in r.message]
        assert warnings, "an unresolved ${VAR} must be reported"
        # Any of them — JARVIS_TIMEZONE resolves on a configured machine and
        # not in CI, so asserting on warnings[0] would make this test pass or
        # fail on environment rather than on behaviour.
        joined = " ".join(warnings)
        assert "NOT_SET_ANYWHERE_AT_ALL" in joined
        assert "mcp-test" in joined

    async def test_an_unresolved_var_does_not_prevent_startup(
            self, monkeypatch, config_file, captured):
        """Degraded, never dead. Refusing to start would convert a broken
        reminder into a silent voice loop — and mcp_git/mcp_repo already set
        the precedent of ignoring, not raising."""
        monkeypatch.delenv("NOT_SET_ANYWHERE_AT_ALL", raising=False)
        registry = SkillRegistry(config_file)
        await registry.start()
        assert captured, "startup must complete"


class TestReminderTimezoneFallback:
    """E2's other half, in the child. The parent's warning makes the
    misconfiguration findable; this keeps the tool alive while someone
    reads it."""

    def test_tz_treats_a_literal_placeholder_as_unset(self, monkeypatch):
        from mcp_servers.mcp_reminders import logic
        monkeypatch.setenv("JARVIS_TIMEZONE", "${JARVIS_TIMEZONE}")
        assert str(logic._tz()) == "UTC"  # not a ZoneInfoNotFoundError

    def test_tz_uses_a_real_value(self, monkeypatch):
        from mcp_servers.mcp_reminders import logic
        monkeypatch.setenv("JARVIS_TIMEZONE", "America/New_York")
        assert str(logic._tz()) == "America/New_York"

    def test_tz_survives_a_nonsense_zone(self, monkeypatch):
        from mcp_servers.mcp_reminders import logic
        monkeypatch.setenv("JARVIS_TIMEZONE", "Mars/Olympus_Mons")
        assert str(logic._tz()) == "UTC"
