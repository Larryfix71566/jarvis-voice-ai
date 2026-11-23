"""WS-40: recorded tool menus, the receipt folder and the receipt script.

Larry 2026-11-23: voice and every tool-using agent run only on the Claude
subscription. The native tool route refuses a request until a capability
receipt matches its model, CLI and exact tool menu, and voice and the agents
each have their own menu. These tests pin that the bot records the menu it
sends, that a folder holding one receipt per menu is accepted by the route's
own validator for each of them (and refused once a menu changes), and the
script's dry and live rows. No CLI runs and no network is used.
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
from jarvis.model_execution import ModelToolReference
from jarvis.model_routing import resolve_model_route
from jarvis import subscription_tools
from scripts import verify_claude_tool_receipts as probe

IDENTITY = {"path": "/usr/local/bin/claude", "version": "2.1.291 (Claude Code)", "sha256": "ab" * 32}
DELEGATE = {"type": "function", "function": {"name": "delegate_task",
    "description": "Hand a task to a specialist.", "parameters": {"type": "object",
        "properties": {"agent_name": {"type": "string", "enum": ["scheduler", "librarian"]},
                       "task": {"type": "string"}}, "required": ["agent_name", "task"]}}}
AGENT_TOOLS = (
    ModelToolReference("read_file", {"type": "object", "properties": {"path": {"type": "string"}},
                                     "required": ["path"]}, "Read a file."),
    ModelToolReference("list_tasks", {"type": "object", "properties": {}}, "List open tasks."),
)


def _context(**flags):
    tools = [FunctionSchema(name=item["function"]["name"], description=item["function"]["description"],
                            properties=item["function"]["parameters"]["properties"],
                            required=item["function"]["parameters"]["required"])
             for item in supervisor_tool_schemas(DELEGATE, **flags)]
    return LLMContext(messages=[{"role": "system", "content": "voice"}],
                      tools=ToolsSchema(standard_tools=tools))


def _service():
    return voice.SubscriptionVoiceLLMService(resolved=resolve_model_route("voice_supervisor"))


@pytest.fixture
def menus(tmp_path, monkeypatch):
    folder = tmp_path / "tool-menus"
    monkeypatch.setenv(subscription_tools.TOOL_MENU_DIR_ENV, str(folder))
    return folder


def _voice_menu(**flags):
    return probe.load_menu(_service().record_tool_menu(_context(**flags)))


def _agent_menu(tools=AGENT_TOOLS, model="claude-opus-5", workload="developer"):
    return probe.load_menu(subscription_tools.record_tool_menu(workload, model, tools))


def _round(**values):
    base = {"native_tool_call_observed": True, "unknown_tool_rejected": True,
            "system_constraints_observed": True, "terminal_success_without_error_items": True,
            "unadvertised_host_tool_rejected": False, "cleanup_verified": True,
            "native_tool_names": [], "native_calls": [], "native_host_ingress_count": 0}
    return {**base, **values}


def _loopback(menu, count, tmp_path, name):
    names = probe.wire_tool_names(menu.refs)
    seen = {"names": names, "schemas_match": True, "model": menu.model,
            "canary_absent": True, "constraint_present": True, "synthetic_auth_only": True}
    return {"observations": [dict(seen) for _ in range(count)], "closed": True,
            "expected_names": names,
            "expected_message_counts": (1, 2) if name == "negative" else (2,),
            "canary": tmp_path / f"{name}-canary-{menu.path.stem}"}


def _receipt(tmp_path, menu, **negative_values):
    negative = _round(native_tool_call_observed=False, system_constraints_observed=False,
                      terminal_success_without_error_items=False, unadvertised_host_tool_rejected=True,
                      native_tool_names=["Bash"], native_calls=[{"name": "Bash"}], **negative_values)
    return probe.build_receipt(IDENTITY, menu, _round(), _round(), negative,
                               _loopback(menu, 2, tmp_path, "isolation"),
                               _loopback(menu, 1, tmp_path, "negative"))


def _store(tmp_path, *menus_):
    store = tmp_path / "receipts"
    for menu in menus_:
        probe.publish(store / menu.path.name, _receipt(tmp_path, menu))
    return store


@pytest.fixture
def pinned_cli(monkeypatch):
    monkeypatch.setattr(subscription_tools, "claude_tool_runtime_identity", lambda: dict(IDENTITY))


def test_recorded_voice_menu_is_exactly_what_a_voice_turn_sends(menus):
    context = _context(status=True, weather=True)
    service = _service()
    params = service.get_llm_adapter().get_llm_invocation_params(context, convert_developer_to_user=False)
    sent = voice.voice_tool_references(params["tools"])
    path = service.record_tool_menu(context)
    assert path.parent == menus and path.name.startswith("voice_supervisor-")
    record = json.loads(path.read_text())
    assert record["model"] == "claude-sonnet-5-5" and record["workload"] == "voice_supervisor"
    assert record["tools"] == [{"name": tool.name, "description": tool.description,
                                "parameters": dict(tool.parameters)} for tool in sent]
    assert [tool["name"] for tool in record["tools"]][:4] == [
        "delegate_task", "set_voice", "remember", "cost_summary"]


def test_menu_file_is_owner_only_rewritten_only_on_change_and_keyed_by_menu(menus):
    record = subscription_tools.tool_menu_record("developer", "claude-opus-5", AGENT_TOOLS)
    path = subscription_tools.tool_menu_path(menus, record)
    assert subscription_tools.write_tool_menu(path, record) is True
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert subscription_tools.write_tool_menu(path, record) is False
    assert set(record) == {"record_kind", "schema_version", "workload", "model", "tools"}
    wider = subscription_tools.tool_menu_record("developer", "claude-opus-5", AGENT_TOOLS[:1])
    other_model = subscription_tools.tool_menu_record("developer", "claude-sonnet-5", AGENT_TOOLS)
    assert len({path, subscription_tools.tool_menu_path(menus, wider),
                subscription_tools.tool_menu_path(menus, other_model)}) == 3


def test_menu_record_holds_no_conversation_text(menus):
    context = _context()
    context.add_message({"role": "user", "content": "PRIVATE-TURN-TEXT"})
    assert "PRIVATE-TURN-TEXT" not in _service().record_tool_menu(context).read_text()


def test_recording_never_raises(monkeypatch, menus):
    def broken(*_args):
        raise OSError("disk full")
    monkeypatch.setattr(subscription_tools, "write_tool_menu", broken)
    assert subscription_tools.record_tool_menu("developer", "claude-opus-5", AGENT_TOOLS) is None


def test_pipeline_records_the_voice_menu_and_never_blocks(menus):
    from jarvis.bot import pipeline
    pipeline._record_voice_tool_menu(_service(), _context())
    assert [probe.load_menu(path).workload for path in menus.glob("*.json")] == ["voice_supervisor"]

    class Broken:
        def record_tool_menu(self, context):
            raise RuntimeError("no adapter")
    pipeline._record_voice_tool_menu(Broken(), _context())  # logged, not raised
    pipeline._record_voice_tool_menu(object(), _context())  # not a subscription service


async def test_native_request_records_its_menu_before_the_receipt_check(monkeypatch, menus):
    from tests.unit.test_subscription_tools import request, route
    monkeypatch.setenv(subscription_tools.TOOLS_ENABLED_ENV, "1")
    monkeypatch.delenv(subscription_tools.TOOL_CAPABILITY_RECEIPT_ENV, raising=False)
    with pytest.raises(subscription_tools.SubscriptionCapabilityError, match="receipt is required"):
        await subscription_tools.ClaudeSubscriptionToolClient("claude-sonnet-5").execute_request(
            request(), route(), {"messages": []})
    menu = probe.load_menu(next(menus.glob("developer-*.json")))
    assert (menu.workload, menu.model, [ref.name for ref in menu.refs]) == (
        "developer", "claude-sonnet-5", ["fixture"])


def test_load_menu_round_trips_and_refuses_bad_files(tmp_path, menus):
    menu = _voice_menu(status=True)
    assert menu.model == "claude-sonnet-5-5" and menu.probe == "cost_summary"
    record = json.loads(menu.path.read_text())
    for broken, reason in [
        ({**record, "record_kind": "other"}, "tool_menu_invalid"),
        ({**record, "model": "gpt-5"}, "tool_menu_invalid"),
        ({**record, "tools": record["tools"] + record["tools"][:1]}, "tool_menu_invalid"),
    ]:
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps(broken))
        with pytest.raises(probe.CapabilityUnavailable, match=reason):
            probe.load_menu(bad)
    with pytest.raises(probe.CapabilityUnavailable, match="tool_menu_missing"):
        probe.load_menu(tmp_path / "absent.json")


def test_probe_tool_prefers_cost_summary_and_needs_an_argument_free_tool():
    assert probe.probe_tool(AGENT_TOOLS) == "list_tasks"
    with pytest.raises(probe.CapabilityUnavailable, match="no_argument_free_probe_tool"):
        probe.probe_tool(AGENT_TOOLS[:1])
    # cost_summary is unconditional on the voice menu, whatever the switches.
    for flags in ({}, {"status": True, "screen": True, "clipboard": True, "weather": True}):
        names = [item["function"]["name"] for item in supervisor_tool_schemas(None, **flags)]
        assert probe.PREFERRED_PROBE_TOOL in names


def test_one_folder_serves_voice_and_agents(tmp_path, menus, pinned_cli):
    voice_menu, agent_menu = _voice_menu(status=True, weather=True), _agent_menu()
    store = _store(tmp_path, voice_menu, agent_menu)
    assert sorted(path.name for path in store.iterdir()) == sorted(
        [voice_menu.path.name, agent_menu.path.name])
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in store.iterdir())
    assert probe.accepted(store, voice_menu) and probe.accepted(store, agent_menu)
    # A single receipt file still works as before.
    assert probe.accepted(store / voice_menu.path.name, voice_menu)
    assert not probe.accepted(store / voice_menu.path.name, agent_menu)


def test_folder_refuses_a_changed_menu_model_or_cli(tmp_path, monkeypatch, menus, pinned_cli):
    voice_menu, agent_menu = _voice_menu(), _agent_menu()
    store = _store(tmp_path, voice_menu, agent_menu)
    assert not probe.accepted(store, _voice_menu(weather=True))
    assert not probe.accepted(store, _agent_menu(AGENT_TOOLS[1:]))
    assert not probe.accepted(store, _agent_menu(model="claude-sonnet-5"))
    monkeypatch.setattr(subscription_tools, "claude_tool_runtime_identity",
                        lambda: {**IDENTITY, "sha256": "cd" * 32})
    assert not probe.accepted(store, voice_menu)


def test_folder_ignores_hidden_symlinked_and_broken_files(tmp_path, menus, pinned_cli):
    menu = _agent_menu()
    store = _store(tmp_path, menu)
    (store / "junk.json").write_text("{not json")
    (store / ".tool-receipt-partial.json").write_text("{}")
    real = store / menu.path.name
    hidden = tmp_path / "elsewhere"
    hidden.mkdir()
    real.rename(hidden / real.name)
    (store / real.name).symlink_to(hidden / real.name)
    assert not probe.accepted(store, menu)  # only a symlink matches: refused
    (store / real.name).unlink()
    (hidden / real.name).rename(real)
    assert probe.accepted(store, menu)


def test_oversized_folder_is_refused(tmp_path, monkeypatch, menus, pinned_cli):
    menu = _agent_menu()
    store = _store(tmp_path, menu)
    monkeypatch.setattr(subscription_tools, "MAX_RECEIPTS_IN_STORE", 0)
    assert not probe.accepted(store, menu)


def test_failed_proofs_are_named(tmp_path, menus):
    menu = _agent_menu()
    receipt = _receipt(tmp_path, menu, native_host_ingress_count=1)
    assert probe.failed_checks(receipt) == ["unadvertised_host_tool_rejected"]
    assert receipt["workload"] == "developer" and receipt["probe_tool"] == "list_tasks"
    (tmp_path / f"negative-canary-{menu.path.stem}").write_text("side effect")
    assert "unadvertised_host_tool_side_effect_absent" in probe.failed_checks(_receipt(tmp_path, menu))


def test_loopback_failures_name_the_broken_observation(tmp_path, menus):
    menu = _voice_menu()
    fixture = _loopback(menu, 2, tmp_path, "isolation")
    assert probe.loopback_failures(fixture, menu.model) == []
    fixture["observations"][0]["names"] = fixture["observations"][0]["names"] + ["DeferredToolPlaceholder"]
    fixture["observations"][1]["canary_absent"] = False
    assert probe.loopback_failures(fixture, menu.model) == [
        "request1:tool_names", "request2:customization_canary_present"]


def _main_rows(capsys, argv):
    code = probe.main(argv)
    out = capsys.readouterr()
    return code, (json.loads(out.out) if out.out.strip() else None), out.err


def test_dry_run_lists_every_menu_without_inference(tmp_path, monkeypatch, capsys, menus, pinned_cli):
    _voice_menu(), _agent_menu()
    monkeypatch.setattr(probe, "acquire", lambda *args: pytest.fail("dry run must not run proofs"))
    code, summary, _ = _main_rows(capsys, ["--menus", str(menus)])
    assert code == 0 and summary["mode"] == "dry" and summary["claude_cli"] == IDENTITY["version"]
    assert {row["workload"]: row["status"] for row in summary["menus"]} == {
        "voice_supervisor": "needs_receipt", "developer": "needs_receipt"}
    code, summary, _ = _main_rows(capsys, ["--menus", str(menus), "--workload", "developer"])
    assert [row["workload"] for row in summary["menus"]] == ["developer"]


def test_live_writes_only_missing_receipts(tmp_path, monkeypatch, capsys, menus, pinned_cli):
    voice_menu, agent_menu = _voice_menu(), _agent_menu()
    store = _store(tmp_path, voice_menu)
    proved = []

    async def fake_acquire(menu, timeout):
        proved.append(menu.workload)
        return _receipt(tmp_path, menu)
    monkeypatch.setattr(probe, "acquire", fake_acquire)
    code, summary, _ = _main_rows(capsys, ["--menus", str(menus), "--live", "--output", str(store)])
    assert code == 0 and proved == ["developer"]
    assert {row["workload"]: row["status"] for row in summary["menus"]} == {
        "voice_supervisor": "has_receipt", "developer": "receipt_written"}
    assert probe.accepted(store, agent_menu)


def test_live_failure_is_reported_and_nothing_is_written(tmp_path, monkeypatch, capsys, menus, pinned_cli):
    menu = _agent_menu()

    async def failing(menu_, timeout):
        return _receipt(tmp_path, menu_, native_host_ingress_count=1)
    monkeypatch.setattr(probe, "acquire", failing)
    store = tmp_path / "receipts"
    code, summary, _ = _main_rows(capsys, ["--menus", str(menus), "--live", "--output", str(store)])
    assert code == 2 and summary["menus"][0]["status"] == "refused"
    assert summary["menus"][0]["failed"] == ["unadvertised_host_tool_rejected"]
    assert list(store.iterdir()) == [] and not probe.accepted(store, menu)


def test_live_requires_a_folder_and_stale_menus_are_flagged(tmp_path, monkeypatch, capsys, menus, pinned_cli):
    _agent_menu(model="claude-sonnet-4-5")
    code, _, err = _main_rows(capsys, ["--menus", str(menus), "--live"])
    assert code == 2 and "output_folder_required" in err
    afile = tmp_path / "afile"
    afile.write_text("x")
    code, _, err = _main_rows(capsys, ["--menus", str(menus), "--output", str(afile)])
    assert code == 2 and "output_must_be_a_folder" in err
    code, summary, _ = _main_rows(capsys, ["--menus", str(menus)])
    assert summary["menus"][0]["status"] == "stale"
    assert summary["menus"][0]["reason"] == "route now uses claude-opus-5"
    code, _, err = _main_rows(capsys, ["--menus", str(tmp_path / "none")])
    assert code == 2 and "tool_menus_missing" in err


def test_unpinned_cli_gets_a_readable_refusal(monkeypatch):
    def unpinned():
        raise subscription_tools.SubscriptionCapabilityError(
            "Claude native tool version has no verified contract")
    monkeypatch.setattr(subscription_tools, "claude_tool_runtime_identity", unpinned)
    with pytest.raises(probe.CapabilityUnavailable, match=r"needs 2\.1\.290 or 2\.1\.291"):
        probe.runtime_identity()


def test_script_reads_the_folder_the_bot_writes(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(subscription_tools.TOOL_MENU_DIR_ENV)
    path = subscription_tools.record_tool_menu("developer", "claude-opus-5", AGENT_TOOLS)
    assert path == Path("logs/tool-menus") / path.name
    monkeypatch.setattr(subscription_tools, "claude_tool_runtime_identity", lambda: dict(IDENTITY))
    code, summary, _ = _main_rows(capsys, [])
    assert code == 0 and [row["menu"] for row in summary["menus"]] == [path.name]
