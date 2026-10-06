from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis import subscription as S


def valid_receipt(monkeypatch, tmp_path, model="gpt-6-astra"):
    identity = {"path": "/fixture/codex", "sha256": "b" * 64, "version": "codex-cli 0.160.0"}
    monkeypatch.setattr(S, "codex_runtime_identity", lambda: identity)
    catalog = {"models": [{"slug": model, "tool_mode": "code_mode_only"}]}
    receipt = {
        "schema_version": 1, "runtime": "codex", "model": model,
        "executable": identity, "proof_kind": "installed_cli_loopback_mock",
        "catalog": catalog, "catalog_sha256": S._json_digest(catalog),
        "invocation_sha256": S._json_digest(S._codex_argv(model, command=identity["path"])),
        "advertised_tools": [], "terminal_success_without_error_items": True,
        "negative_unadvertised_tool_rejected": True,
        "api_credentials_absent": True, "real_provider_calls": 0,
    }
    path = tmp_path / "capability.json"
    path.write_text(json.dumps(receipt))
    monkeypatch.setenv(S.CODEX_CAPABILITY_RECEIPT_ENV, str(path))
    return path, receipt


def test_bare_flag_never_launches_provider_without_receipt(monkeypatch):
    monkeypatch.setenv(S._CODEX_NO_TOOL_VERIFICATION_ENV, "1")
    monkeypatch.delenv(S.CODEX_CAPABILITY_RECEIPT_ENV, raising=False)
    monkeypatch.setattr(S.subprocess, "Popen", lambda *_a, **_k: pytest.fail("provider launched"))
    with pytest.raises(S.SubscriptionCapabilityError, match="receipt is required"):
        S._run_codex("gpt-6-astra", [], 1)


@pytest.mark.parametrize("field,value", [
    ("model", "different-model"), ("schema_version", 2),
    ("advertised_tools", [{"name": "shell"}]),
    ("terminal_success_without_error_items", False),
    ("terminal_success_without_error_items", "true"),
    ("negative_unadvertised_tool_rejected", "true"),
    ("negative_unadvertised_tool_rejected", 1),
    ("schema_version", True), ("real_provider_calls", False),
    ("api_credentials_absent", False), ("real_provider_calls", 1),
    ("invocation_sha256", "wrong"), ("catalog_sha256", "wrong"),
    ("executable", {"path": "/other/codex", "sha256": "b" * 64, "version": "codex-cli 0.160.0"}),
])
def test_receipt_rejects_model_binary_config_and_proof_drift(monkeypatch, tmp_path, field, value):
    path, receipt = valid_receipt(monkeypatch, tmp_path)
    receipt[field] = value
    path.write_text(json.dumps(receipt))
    with pytest.raises(S.SubscriptionCapabilityError):
        S.validate_codex_capability_receipt("gpt-6-astra")


def test_catalog_content_is_verified_and_copied_into_owned_directory(monkeypatch, tmp_path):
    _path, receipt = valid_receipt(monkeypatch, tmp_path)
    argv, catalog = S.validate_codex_capability_receipt("gpt-6-astra")
    workdir = tmp_path / "private-request"
    workdir.mkdir()
    materialized = S._materialize_catalog(argv, str(workdir), catalog)
    catalog_arg = next(arg for arg in materialized if arg.startswith("model_catalog_json="))
    pinned = Path(json.loads(catalog_arg.split("=", 1)[1]))
    assert pinned.parent == workdir
    assert json.loads(pinned.read_text()) == receipt["catalog"]
    assert pinned.stat().st_mode & 0o777 == 0o600
    receipt["catalog"]["models"][0]["slug"] = "tampered"
    assert json.loads(pinned.read_text())["models"][0]["slug"] == "gpt-6-astra"


def test_unknown_installed_version_fails_before_provider(monkeypatch, tmp_path):
    executable = tmp_path / "codex"
    executable.write_text("fixture binary")
    monkeypatch.setattr(S.shutil, "which", lambda _: str(executable))
    monkeypatch.setattr(S.subprocess, "run", lambda *_a, **_k: type("R", (), {"stdout": "codex-cli 0.161.0", "returncode": 0})())
    with pytest.raises(S.SubscriptionCapabilityError, match="no verified capability contract"):
        S.codex_runtime_identity()


def test_text_parser_rejects_tool_execution_even_after_successful_terminal():
    stream = ('{"type":"item.completed","item":{"type":"command_execution","command":"touch /tmp/canary"}}\n'
              '{"type":"item.completed","item":{"type":"agent_message","text":"answer"}}\n'
              '{"type":"turn.completed"}')
    with pytest.raises(S.SubscriptionRuntimeError, match="non-text item"):
        S._codex_text(stream)


def test_constrained_argv_keeps_host_but_has_no_extension_or_planning_tools():
    argv = S._codex_argv("gpt-6-astra")
    assert ["--enable", "code_mode_host"] in [argv[i:i+2] for i in range(len(argv)-1)]
    assert "code_mode_host" not in S.CODEX_DISABLED_FEATURES
    assert 'tools.update_plan.enabled=false' in argv
    assert 'tools.experimental_request_user_input.enabled=false' in argv
    assert 'mcp_servers={}' in argv
    assert 'project_doc_max_bytes=0' in argv


@pytest.mark.parametrize("requirements", [{"max_tokens": 10}, {"stream": True},
                                         {"temperature": 0.2}, {"response_format": {"type": "json_object"}}])
async def test_text_clients_fail_before_launch_when_requirement_cannot_be_enforced(monkeypatch, requirements):
    monkeypatch.setattr(S, "_run_claude_async", lambda *_a: pytest.fail("provider launched"))
    with pytest.raises(S.SubscriptionCapabilityError):
        await S.SubscriptionTextClient("model").chat.completions.create(
            messages=[{"role": "user", "content": "public fixture"}], **requirements)


@pytest.mark.parametrize("message", [{"role": "tool", "content": "result"},
                                    {"role": "user", "content": [{"type": "image_url"}]},
                                    {"role": "assistant", "content": "", "tool_calls": [{"id": "x"}]}])
def test_text_prompt_never_stringifies_images_or_tool_history(message):
    with pytest.raises(S.SubscriptionCapabilityError):
        S._prompt([message])


@pytest.mark.parametrize("change", [{"call_id": "other"}, {"type": "message"},
                                   {"output": "unsupported call: another_function"},
                                   {"output": "exec_command completed"}, {"output": "unsupported"}])
def test_installed_host_refusal_requires_exact_call_and_diagnostic(change):
    from scripts.verify_subscription_capability import installed_host_refusal
    item = {"type": "function_call_output", "call_id": "call_unadvertised_fixture",
            "output": "unsupported call: exec_command"}
    assert installed_host_refusal({"input": [item]}) is True
    assert installed_host_refusal({"input": [item, item]}) is False
    item.update(change)
    assert installed_host_refusal({"input": [item]}) is False
