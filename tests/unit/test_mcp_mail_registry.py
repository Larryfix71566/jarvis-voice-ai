"""mcp-mail's registry side (plan §R.12 rows S1-7 and S1-8): the host source
contract that classifies a `mail_headlines` result, and K2 env scoping for
the four vault names. Spawn-free, modeled on test_registry_source_policy.py.
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest
import yaml

from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn, is_sensitive
from jarvis.privacy_policy import DataPolicy, make_tool_execution_scope, validate_tool_result
from jarvis.runlog.context import run_logger_scope
from jarvis.runlog.store import RunLogger
from jarvis.skills import registry as registry_module
from jarvis.skills.registry import (
    REPO_ROOT, SkillRegistry, _ServerHandle, _ToolSourceContract, build_child_env,
    env_scoping_enabled,
)
from mcp_servers.mcp_mail import logic

CANARY = "SYNTHETIC_MAIL_SUBJECT_CANARY"
MAIL_NAMES = ("MAIL_ATT_USER", "MAIL_ATT_SECURE_MAIL_KEY",
              "MAIL_GMAIL_USER", "MAIL_GMAIL_APP_PASSWORD")


@pytest.fixture(autouse=True)
def initialized_turn():
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        yield
    finally:
        current_sensitive_turn.reset(token)


def response(body):
    return SimpleNamespace(isError=False, structuredContent=body, content=[SimpleNamespace(text="")])


class Session:
    def __init__(self, value):
        self.value, self.calls = value, []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return self.value


def registry_for(session, *, pinned=True, module="mcp_servers.mcp_mail.server"):
    registry = SkillRegistry("unused.yaml")
    entry = {"name": "mcp-mail", "command": "python", "args": ["-m", module], "env": {}}
    schema = SimpleNamespace(name="mail_headlines", description="t",
                             inputSchema={"type": "object", "properties": {}})
    registry._tools["mail_headlines"] = ("mcp-mail", schema)
    registry._sessions["mcp-mail"] = session
    registry._handles["mcp-mail"] = _ServerHandle("mcp-mail", entry, state="up", session=session)
    if pinned:
        registry._source_contracts["mcp-mail"] = _ToolSourceContract("mcp-mail", module, session, None)
    return registry


def execution(arguments, privacy="approved_external"):
    return make_tool_execution_scope("brief-parent", "subagent:brief-parent:0", "mail-call",
                                     "mail_headlines", arguments, DataPolicy(privacy, "input"))


def memory_logger():
    logger = RunLogger("brief-parent", "developer", "Developer", "synthetic task",
                       enabled=True, sensitive=False)
    logger._execute = lambda *_args: None
    original = logger._safe
    logger._safe = lambda operation, callback: (
        None if operation == "skill_trace_redaction" else original(operation, callback)
    )
    return logger


def mail_result():
    return {"ok": True, "window_hours": 24, "accounts": [], "notice": logic.UNTRUSTED_NOTICE,
            "messages": [{"id": "ab" * 16, "account": "att", "subject": CANARY,
                          "sender": "x@example.test"}]}


# ---------------------------------------------------------------------------
# S1-7  Policy envelope
# ---------------------------------------------------------------------------


def test_mcp_mail_is_a_pinned_confidential_source():
    assert registry_module._PINNED_SOURCE_MODULES["mcp-mail"] == "mcp_servers.mcp_mail.server"
    assert registry_module._CONFIDENTIAL_SOURCE_OPERATIONS["mcp-mail"] == frozenset({"mail_headlines"})
    assert "mail_headlines" not in registry_module._PUBLIC_SOURCE_OPERATIONS.get("mcp-mail", ())
    assert registry_module._MAIL_ACCOUNT_KEYS == tuple(a.key for a in logic.ACCOUNTS)


@pytest.mark.parametrize("arguments,scope", [
    ({}, "mail:att/gmail"),
    ({"account": "all"}, "mail:att/gmail"),
    ({"account": "att"}, "mail:att"),
    ({"account": "gmail"}, "mail:gmail"),
    ({"account": "yahoo"}, "mail:unknown"),
])
async def test_envelope_carries_the_d4_level_and_the_mail_source(arguments, scope):
    session = Session(response(mail_result()))
    registry = registry_for(session)
    execution_scope = execution(arguments)
    logger = memory_logger()
    with run_logger_scope(logger):
        envelope = await registry.call_classified("mail_headlines", arguments,
                                                  execution_scope=execution_scope)
    policy, content = validate_tool_result(execution_scope, envelope)
    assert policy.level == "confidential"                      # D4 (a)
    assert policy.source.endswith("verified-host-confidential-source")   # strictest() joins input+source
    assert envelope.source_scope == scope
    assert json.loads(content)["messages"][0]["subject"] == CANARY   # retained, not reduced
    assert is_sensitive()                                      # the turn is armed
    assert CANARY not in repr(logger._buffer)                  # and the run log holds no content
    assert session.calls == [("mail_headlines", arguments)]


async def test_without_the_pinned_contract_the_result_is_merely_unclassified():
    session = Session(response(mail_result()))
    registry = registry_for(session, pinned=False)
    execution_scope = execution({"account": "att"})
    with run_logger_scope(memory_logger()):
        envelope = await registry.call_classified("mail_headlines", {"account": "att"},
                                                  execution_scope=execution_scope)
    policy, _ = validate_tool_result(execution_scope, envelope)
    assert policy.level == "confidential"
    assert envelope.source_scope != "mail:att"


async def test_a_wrong_module_never_earns_the_mail_source():
    session = Session(response(mail_result()))
    registry = registry_for(session, module="mcp_servers.mcp_notes.server")
    execution_scope = execution({"account": "att"})
    with run_logger_scope(memory_logger()):
        envelope = await registry.call_classified("mail_headlines", {"account": "att"},
                                                  execution_scope=execution_scope)
    assert envelope.source_scope != "mail:att"


@pytest.mark.parametrize("privacy", ["confidential", "local_only"])
async def test_the_input_floor_is_kept(privacy):
    session = Session(response(mail_result()))
    registry = registry_for(session)
    execution_scope = execution({"account": "att"}, privacy)
    with run_logger_scope(memory_logger()):
        envelope = await registry.call_classified("mail_headlines", {"account": "att"},
                                                  execution_scope=execution_scope)
    policy, _ = validate_tool_result(execution_scope, envelope)
    assert policy.level == privacy


async def test_content_that_claims_a_lower_policy_stays_confidential():
    body = mail_result() | {"policy": {"level": "approved_external"}, "data_policy": "public"}
    session = Session(response(body))
    registry = registry_for(session)
    execution_scope = execution({"account": "gmail"})
    with run_logger_scope(memory_logger()):
        envelope = await registry.call_classified("mail_headlines", {"account": "gmail"},
                                                  execution_scope=execution_scope)
    policy, _ = validate_tool_result(execution_scope, envelope)
    assert policy.level == "confidential"
    assert envelope.source_scope == "mail:gmail"


async def test_plain_call_without_a_scope_is_not_how_the_brief_reads_mail():
    """registry.call (no execution_scope) returns raw content with no envelope;
    R.10.2 requires call_classified. This pins what the unscoped path does so
    a P3 reviewer can see the difference, not to endorse it."""
    session = Session(response(mail_result()))
    registry = registry_for(session)
    with run_logger_scope(memory_logger()):
        raw = await registry.call("mail_headlines", {"account": "att"})
    assert isinstance(raw, str) and CANARY in raw


# ---------------------------------------------------------------------------
# S1-8  Child environment, names only (item 26)
# ---------------------------------------------------------------------------


def _server_entries() -> list[dict]:
    data = yaml.safe_load((REPO_ROOT / "config" / "mcp_servers.yaml").read_text())
    return data if isinstance(data, list) else (data.get("servers") or data.get("mcp_servers") or [])


def test_mail_names_reach_mcp_mail_and_no_other_server(monkeypatch, caplog):
    monkeypatch.delenv(registry_module.ENV_SCOPING_ENABLED_ENV, raising=False)
    assert env_scoping_enabled() is True
    sentinels = {name: f"SENTINEL-{name}" for name in MAIL_NAMES}
    sentinels["JARVIS_MAIL_ENABLED"] = "SENTINEL-SWITCH"
    for name, value in sentinels.items():
        monkeypatch.setenv(name, value)
    entries = _server_entries()
    assert {e["name"] for e in entries} >= {"mcp-mail", "mcp-web", "mcp-notes", "mcp-status"}
    for entry in entries:
        child = build_child_env(entry)
        present = {name for name in sentinels if name in child}
        if entry["name"] == "mcp-mail":
            assert present == set(sentinels), entry["name"]
            for name, value in sentinels.items():
                assert child[name] == value
        else:
            assert present == set(), f"{entry['name']} received {present}"
    assert "SENTINEL-" not in caplog.text


def test_missing_mail_names_are_silent_and_optional(monkeypatch, caplog):
    for name in MAIL_NAMES + ("JARVIS_MAIL_ENABLED",):
        monkeypatch.delenv(name, raising=False)
    entry = next(e for e in _server_entries() if e["name"] == "mcp-mail")
    child = build_child_env(entry)
    assert not any(name in child for name in MAIL_NAMES)
    assert "mcp_server_env_missing" not in caplog.text        # optional, never required
    # and the server itself reports not_configured for that env, without a socket
    out = logic.mail_headlines(24, "all", env=child, endpoints={})
    assert {a["status"] for a in out["accounts"]} == {"not_configured"}


def test_manifest_declares_exactly_the_five_names_as_optional():
    manifest = yaml.safe_load((REPO_ROOT / "mcp_servers" / "mcp_mail" / "skill.yaml").read_text())
    assert manifest["requires_env"] == []
    assert sorted(manifest["optional_env"]) == sorted(MAIL_NAMES + ("JARVIS_MAIL_ENABLED",))
    assert manifest["tools"] == ["mail_headlines"]
    assert manifest["class"] == "standard"
    entry = next(e for e in _server_entries() if e["name"] == "mcp-mail")
    assert entry.get("env", {}) == {}
    assert entry["args"] == ["-m", "mcp_servers.mcp_mail.server"]


def _preflight(extra_env: dict, tmp_path, dotenv_text: str = "") -> "subprocess.CompletedProcess":
    import subprocess
    import sys

    env_file = tmp_path / "startup.env"
    env_file.write_text(dotenv_text)
    env = dict(os.environ)
    env.pop(registry_module.ENV_SCOPING_ENABLED_ENV, None)
    env.update({name: f"SENTINEL-{name}" for name in MAIL_NAMES})
    env["JARVIS_VAULT_ENABLED"] = "false"
    env.update(extra_env)
    return subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "check_mail_env.py"),
                           "--env-file", str(env_file)],
                          env=env, capture_output=True, text=True, timeout=60, cwd=str(REPO_ROOT))


def test_preflight_matrix_shows_mail_names_reach_only_mcp_mail(monkeypatch, tmp_path):
    """M1-1 (Codex review of #204, item 5): one row per name, one column per
    configured server, plus the effective scoping flag; never a value."""
    proc = _preflight({}, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "SENTINEL-" not in proc.stdout + proc.stderr
    out = proc.stdout
    assert "JARVIS_ENV_SCOPING_ENABLED (effective): on" in out
    servers = [e["name"] for e in _server_entries()]
    header = next(line for line in out.splitlines() if line.startswith("name"))
    for server in servers:
        assert server in header
    columns = header.split()[2:]                       # after "name" and "set"
    assert columns == servers
    for name in MAIL_NAMES:
        row = next(line for line in out.splitlines() if line.startswith(name + " "))
        cells = row.split()[2:]
        assert len(cells) == len(servers)
        assert {s for s, cell in zip(servers, cells) if cell == "yes"} == {"mcp-mail"}, row
    assert "M1-1: PASS" in out
    assert "would be read" in out


def test_preflight_reports_disabled_scoping_as_a_failure(tmp_path):
    proc = _preflight({registry_module.ENV_SCOPING_ENABLED_ENV: "false"}, tmp_path)
    assert proc.returncode == 0
    assert "SENTINEL-" not in proc.stdout + proc.stderr
    assert "JARVIS_ENV_SCOPING_ENABLED (effective): OFF" in proc.stdout
    assert "M1-1: FAIL" in proc.stdout
    # with scoping off every child inherits the names: the matrix says so
    row = next(line for line in proc.stdout.splitlines() if line.startswith("MAIL_ATT_USER "))
    assert set(row.split()[2:]) == {"yes"}


def _preflight_main(monkeypatch, tmp_path, argv, *, dotenv_text="", env=None, config_text=None):
    """Run the preflight in-process against a temporary repo root, so its
    .env handling is tested without touching the real one. `dotenv_text=None`
    means no .env at all. The process environment is restored afterwards,
    because the preflight applies the loaded .env to os.environ."""
    import importlib.util
    import shutil

    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    if config_text is None:
        shutil.copy(REPO_ROOT / "config" / "mcp_servers.yaml", root / "config" / "mcp_servers.yaml")
    else:
        (root / "config" / "mcp_servers.yaml").write_text(config_text)
    if dotenv_text is not None:
        (root / ".env").write_text(dotenv_text)
    spec = importlib.util.spec_from_file_location("check_mail_env_under_test",
                                                  REPO_ROOT / "scripts" / "check_mail_env.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setenv("JARVIS_VAULT_ENABLED", "false")
    monkeypatch.delenv(registry_module.ENV_SCOPING_ENABLED_ENV, raising=False)
    for name in MAIL_NAMES + ("JARVIS_MAIL_ENABLED",):
        monkeypatch.delenv(name, raising=False)
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    saved = dict(os.environ)
    try:
        module.main(argv)
    finally:
        os.environ.clear()
        os.environ.update(saved)


def test_preflight_with_no_mail_name_set_is_not_a_pass(monkeypatch, tmp_path, capsys):
    """Larry's merged-build run (10-13) printed PASS with nothing set: a check
    with nothing to observe must say NOT TESTED."""
    _preflight_main(monkeypatch, tmp_path, [])
    out = capsys.readouterr().out
    assert "M1-1: NOT TESTED" in out and "M1-1: PASS" not in out


def test_preflight_sentinel_mode_passes_and_prints_no_value(monkeypatch, tmp_path, capsys):
    _preflight_main(monkeypatch, tmp_path, ["--sentinel"])
    out = capsys.readouterr()
    assert "M1-1: PASS" in out.out
    assert "preflight-sentinel" not in out.out + out.err
    for name in MAIL_NAMES:
        row = next(line for line in out.out.splitlines() if line.startswith(name + " "))
        assert row.split()[1] == "yes" and row.split()[-1] == "yes"     # set, and mcp-mail is last
        assert row.split()[2:-1] == ["no"] * (len(row.split()) - 3)


def test_preflight_applies_dotenv_like_the_run_scripts(monkeypatch, tmp_path, capsys):
    """The run scripts `set -a; . ./.env`: a scoping switch in .env is the one
    the bot gets, so the preflight must see it too, even over the shell."""
    _preflight_main(monkeypatch, tmp_path, ["--sentinel"],
                    dotenv_text="# comment\nJARVIS_ENV_SCOPING_ENABLED=false\n",
                    env={registry_module.ENV_SCOPING_ENABLED_ENV: "true"})
    out = capsys.readouterr().out
    assert "environment: .env loaded by the startup shell" in out
    assert "JARVIS_ENV_SCOPING_ENABLED (effective): OFF" in out
    assert "M1-1: FAIL - env scoping is off" in out


def _startup_shell_value(env_file, name: str) -> str:
    """What scripts/run_bot.sh's own loading gives the bot for `name`."""
    import subprocess

    proc = subprocess.run(["bash", "-c", f'set -e; set -a; . "$1"; set +a; printf %s "${{{name}-}}"',
                           "startup", str(env_file)], capture_output=True, text=True,
                          timeout=30, env={k: v for k, v in os.environ.items() if k != name})
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.mark.parametrize("line", [
    "JARVIS_ENV_SCOPING_ENABLED=false # intentionally disabled",    # Codex's reproduction
    "export JARVIS_ENV_SCOPING_ENABLED='false'",
    'JARVIS_ENV_SCOPING_ENABLED="false"   # quoted, then a comment',
    "OFF_VALUE=false\nJARVIS_ENV_SCOPING_ENABLED=$OFF_VALUE",
])
def test_preflight_reads_dotenv_exactly_as_the_startup_shell(monkeypatch, tmp_path, capsys, line):
    """Codex review of #205, item 1: the effective flag must be the startup
    shell's, comments, quoting, export and expansion included."""
    env_file = tmp_path / "check.env"
    env_file.write_text(line + "\n")
    assert _startup_shell_value(env_file, registry_module.ENV_SCOPING_ENABLED_ENV) == "false"
    _preflight_main(monkeypatch, tmp_path, ["--sentinel"], dotenv_text=line + "\n")
    out = capsys.readouterr().out
    assert "JARVIS_ENV_SCOPING_ENABLED (effective): OFF" in out
    assert "M1-1: FAIL - env scoping is off" in out
    assert "M1-1: PASS" not in out


@pytest.mark.parametrize("dotenv_text,reason", [
    (None, ".env not found"),
    ("JARVIS_ENV_SCOPING_ENABLED=on value-with-space-is-a-command\n", "the startup shell fails on this .env"),
    ("JARVIS_ENV_SCOPING_ENABLED='unterminated\n", "the startup shell fails on this .env"),
])
def test_preflight_is_not_tested_when_the_startup_env_cannot_be_established(
        monkeypatch, tmp_path, capsys, dotenv_text, reason):
    _preflight_main(monkeypatch, tmp_path, ["--sentinel"], dotenv_text=dotenv_text)
    out = capsys.readouterr().out
    assert "M1-1: NOT TESTED" in out and reason in out
    assert "JARVIS_ENV_SCOPING_ENABLED (effective): unknown" in out
    assert "M1-1: PASS" not in out


def test_preflight_fails_when_mcp_mail_is_not_configured(monkeypatch, tmp_path, capsys):
    """Codex review of #205, item 2: no mail server, no PASS."""
    import yaml

    data = yaml.safe_load((REPO_ROOT / "config" / "mcp_servers.yaml").read_text())
    servers = data if isinstance(data, list) else data["servers"]
    kept = [s for s in servers if s["name"] != "mcp-mail"]
    config = yaml.safe_dump(kept if isinstance(data, list) else {**data, "servers": kept})
    _preflight_main(monkeypatch, tmp_path, ["--sentinel"], config_text=config)
    out = capsys.readouterr().out
    assert "M1-1: FAIL - mcp-mail is not in config/mcp_servers.yaml" in out
    assert "M1-1: PASS" not in out
