"""WS-40: the voice tool menu record and the receipt the subscription route needs.

Larry 2026-11-23: voice runs only on the Claude subscription, and the native
tool route refuses a voice turn until a capability receipt matches the exact
voice menu. These tests pin that the bot records the same menu it sends, and
that a receipt built from it is accepted by the route's own validator (and
refused once the menu changes). No CLI runs and no network is used.
"""
from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.processors.aggregators.llm_context import LLMContext

from jarvis.bot import subscription_llm as voice
from jarvis.bot.tool_schemas import supervisor_tool_schemas
from jarvis.model_routing import resolve_model_route
from jarvis import subscription_tools
from scripts import verify_claude_voice_capability as probe

IDENTITY = {"path": "/usr/local/bin/claude", "version": "2.1.291 (Claude Code)", "sha256": "ab" * 32}
DELEGATE = {"type": "function", "function": {"name": "delegate_task",
    "description": "Hand a task to a specialist.", "parameters": {"type": "object",
        "properties": {"agent_name": {"type": "string", "enum": ["scheduler", "librarian"]},
                       "task": {"type": "string"}}, "required": ["agent_name", "task"]}}}


def _context(**flags):
    tools = [FunctionSchema(name=item["function"]["name"], description=item["function"]["description"],
                            properties=item["function"]["parameters"]["properties"],
                            required=item["function"]["parameters"]["required"])
             for item in supervisor_tool_schemas(DELEGATE, **flags)]
    return LLMContext(messages=[{"role": "system", "content": "voice"}],
                      tools=ToolsSchema(standard_tools=tools))


def _service():
    return voice.SubscriptionVoiceLLMService(resolved=resolve_model_route("voice_supervisor"))


def _menu(tmp_path, **flags):
    path = tmp_path / "voice-tool-menu.json"
    assert voice.write_voice_tool_menu(path, _service().tool_menu_record(_context(**flags)))
    return path


def _round(**values):
    base = {"native_tool_call_observed": True, "unknown_tool_rejected": True,
            "system_constraints_observed": True, "terminal_success_without_error_items": True,
            "unadvertised_host_tool_rejected": False, "cleanup_verified": True,
            "native_tool_names": [], "native_calls": [], "native_host_ingress_count": 0}
    return {**base, **values}


def _loopback(refs, model, count, tmp_path, name):
    seen = {"names": probe.wire_tool_names(refs), "schemas_match": True, "model": model,
            "canary_absent": True, "constraint_present": True, "synthetic_auth_only": True}
    return {"observations": [dict(seen) for _ in range(count)], "closed": True,
            "expected_names": probe.wire_tool_names(refs),
            "expected_message_counts": (1, 2) if name == "negative" else (2,),
            "canary": tmp_path / f"{name}-canary"}


def _receipt(tmp_path, model, refs, **negative_values):
    negative = _round(native_tool_call_observed=False, system_constraints_observed=False,
                      terminal_success_without_error_items=False, unadvertised_host_tool_rejected=True,
                      native_tool_names=["Bash"], native_calls=[{"name": "Bash"}], **negative_values)
    return probe.build_receipt(IDENTITY, model, refs, _round(), _round(), negative,
                               _loopback(refs, model, 2, tmp_path, "isolation"),
                               _loopback(refs, model, 1, tmp_path, "negative"))


@pytest.fixture
def pinned_cli(monkeypatch):
    monkeypatch.setattr(subscription_tools, "claude_tool_runtime_identity", lambda: dict(IDENTITY))


def test_recorded_menu_is_exactly_what_a_voice_turn_sends():
    context = _context(status=True, weather=True)
    service = _service()
    params = service.get_llm_adapter().get_llm_invocation_params(context, convert_developer_to_user=False)
    sent = voice.voice_tool_references(params["tools"])
    record = service.tool_menu_record(context)
    assert record["model"] == "claude-sonnet-5-5"
    assert record["workload"] == "voice_supervisor"
    assert [tool["name"] for tool in record["tools"]] == [tool.name for tool in sent]
    assert record["tools"] == [{"name": tool.name, "description": tool.description,
                                "parameters": dict(tool.parameters)} for tool in sent]
    assert [tool["name"] for tool in record["tools"]][:4] == [
        "delegate_task", "set_voice", "remember", "cost_summary"]


def test_menu_file_is_owner_only_and_rewritten_only_on_change(tmp_path):
    record = _service().tool_menu_record(_context())
    path = tmp_path / "logs" / "voice-tool-menu.json"
    assert voice.write_voice_tool_menu(path, record) is True
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert voice.write_voice_tool_menu(path, record) is False
    assert json.loads(path.read_text())["tools"] == record["tools"]
    assert set(record) == {"record_kind", "schema_version", "workload", "model", "tools"}


def test_menu_record_holds_no_conversation_text():
    context = _context()
    context.add_message({"role": "user", "content": "PRIVATE-TURN-TEXT"})
    assert "PRIVATE-TURN-TEXT" not in json.dumps(_service().tool_menu_record(context))


def test_pipeline_records_menu_and_never_blocks(tmp_path, monkeypatch):
    from jarvis.bot import pipeline
    path = tmp_path / "menu.json"
    monkeypatch.setenv(voice.VOICE_TOOL_MENU_ENV, str(path))
    pipeline._record_voice_tool_menu(_service(), _context())
    assert probe.load_menu(path)[0] == "claude-sonnet-5-5"

    class Broken:
        def tool_menu_record(self, context):
            raise RuntimeError("no adapter")
    pipeline._record_voice_tool_menu(Broken(), _context())  # logged, not raised
    pipeline._record_voice_tool_menu(object(), _context())  # not a subscription service


def test_load_menu_round_trips_and_refuses_bad_files(tmp_path):
    path = _menu(tmp_path, status=True)
    model, refs = probe.load_menu(path)
    assert model == "claude-sonnet-5-5" and "cost_summary" in [ref.name for ref in refs]
    record = json.loads(path.read_text())
    for broken, reason in [
        ({**record, "workload": "developer"}, "voice_tool_menu_invalid"),
        ({**record, "tools": record["tools"] + record["tools"][:1]}, "voice_tool_menu_invalid"),
        ({**record, "tools": [t for t in record["tools"] if t["name"] != "cost_summary"]},
         "voice_probe_tool_missing"),
    ]:
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps(broken))
        with pytest.raises(probe.CapabilityUnavailable, match=reason):
            probe.load_menu(bad)
    with pytest.raises(probe.CapabilityUnavailable, match="voice_tool_menu_missing"):
        probe.load_menu(tmp_path / "absent.json")


def test_receipt_is_accepted_by_the_route_validator(tmp_path, pinned_cli):
    model, refs = probe.load_menu(_menu(tmp_path, status=True, weather=True))
    receipt = _receipt(tmp_path, model, refs)
    assert probe.failed_checks(receipt) == []
    path = probe.publish(tmp_path / "receipts" / "voice.json", receipt)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    probe.validate_published(path, model, refs)


def test_receipt_is_refused_once_the_voice_menu_changes(tmp_path, monkeypatch, pinned_cli):
    model, refs = probe.load_menu(_menu(tmp_path))
    path = probe.publish(tmp_path / "voice.json", _receipt(tmp_path, model, refs))
    _, wider = probe.load_menu(_menu(tmp_path, weather=True))
    with pytest.raises(subscription_tools.SubscriptionCapabilityError):
        probe.validate_published(path, model, wider)
    with pytest.raises(subscription_tools.SubscriptionCapabilityError):
        probe.validate_published(path, "claude-sonnet-4-5", refs)


def test_failed_proofs_are_named_and_block_publication(tmp_path):
    model, refs = probe.load_menu(_menu(tmp_path))
    receipt = _receipt(tmp_path, model, refs, native_host_ingress_count=1)
    assert probe.failed_checks(receipt) == ["unadvertised_host_tool_rejected"]
    (tmp_path / "negative-canary").write_text("side effect")
    receipt = _receipt(tmp_path, model, refs)
    assert "unadvertised_host_tool_side_effect_absent" in probe.failed_checks(receipt)


def test_loopback_failures_name_the_broken_observation(tmp_path):
    model, refs = probe.load_menu(_menu(tmp_path))
    fixture = _loopback(refs, model, 2, tmp_path, "isolation")
    assert probe.loopback_failures(fixture, model) == []
    fixture["observations"][0]["names"] = fixture["observations"][0]["names"] + ["DeferredToolPlaceholder"]
    fixture["observations"][1]["canary_absent"] = False
    assert probe.loopback_failures(fixture, model) == [
        "request1:tool_names", "request2:customization_canary_present"]


def test_dry_run_checks_menu_route_and_cli_without_inference(tmp_path, monkeypatch, capsys):
    path = _menu(tmp_path)
    monkeypatch.setattr(probe, "runtime_identity", lambda: dict(IDENTITY))
    monkeypatch.setattr(probe, "acquire", lambda *args: pytest.fail("dry run must not run proofs"))
    assert probe.main(["--menu", str(path)]) == 0
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary["mode"] == "dry" and summary["model"] == "claude-sonnet-5-5"
    assert summary["claude_cli"] == IDENTITY["version"]


def test_live_requires_output_and_stale_menu_model_is_refused(tmp_path, monkeypatch, capsys):
    path = _menu(tmp_path)
    monkeypatch.setattr(probe, "runtime_identity", lambda: dict(IDENTITY))
    assert probe.main(["--menu", str(path), "--live"]) == 2
    assert "output_path_required" in capsys.readouterr().err
    monkeypatch.setattr(probe, "route_model", lambda: "claude-opus-5-5")
    assert probe.main(["--menu", str(path)]) == 2
    assert "differs_from_voice_route" in capsys.readouterr().err


def test_unpinned_cli_gets_a_readable_refusal(monkeypatch):
    def unpinned():
        raise subscription_tools.SubscriptionCapabilityError(
            "Claude native tool version has no verified contract")
    monkeypatch.setattr(subscription_tools, "claude_tool_runtime_identity", unpinned)
    with pytest.raises(probe.CapabilityUnavailable, match=r"needs 2\.1\.290 or 2\.1\.291"):
        probe.runtime_identity()


def test_probe_tool_is_always_on_the_menu():
    # cost_summary is unconditional, so the probe works whatever the switches.
    for flags in ({}, {"status": True, "screen": True, "clipboard": True, "weather": True}):
        names = [item["function"]["name"] for item in supervisor_tool_schemas(None, **flags)]
        assert probe.PROBE_TOOL in names


def test_default_paths_agree():
    assert Path(probe.DEFAULT_MENU) == Path(voice.DEFAULT_VOICE_TOOL_MENU_PATH)
