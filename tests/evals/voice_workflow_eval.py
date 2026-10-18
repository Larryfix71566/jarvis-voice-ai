"""Voice-workflow eval — MORTIMER_VOICE_WORKFLOWS_PLAN.md §7 T3b.

Replays requests that produced a refusal or a hand-off in the logged
corpus (tests/evals/voice_workflow_cases.yaml, turn ids in `from`) through
the real Orchestrator in the parity profile, and grades the FINAL reply
with the same detector the live reply guard uses.

Usage (repo root; the guard ships in log mode, so set correct to grade it):
    RUN_LIVE=1 JARVIS_REPLY_GUARD_MODE=correct python -m tests.evals.voice_workflow_eval
Baseline (the pre-plan behaviour, same code):
    RUN_LIVE=1 JARVIS_VOICE_WORKFLOWS_ENABLED=false JARVIS_REPLY_GUARD_MODE=off \
        python -m tests.evals.voice_workflow_eval

Exit 0 iff passed/total >= PASS_THRESHOLD. Real LLM calls, real
specialists, self-edit sidecar sandboxed exactly as routing_eval does.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tests.evals.routing_eval import (  # noqa: E402
    _apply_candidate_overrides,
    _one_line,
    isolate_selfedit_service,
    resolve_profile,
)

CASES_PATH = Path(__file__).resolve().parent / "voice_workflow_cases.yaml"
PASS_THRESHOLD = 0.90


def grade(case: dict, reply: str, delegated: list[str], tools_called: list[str],
          actions_called: list[str] | None = None) -> tuple[bool, str]:
    """Deterministic: (passed, reason)."""
    from jarvis.voice_workflows import ALLOWED_RE, reply_violations

    actions = actions_called or []
    required_action = case.get("require_action")
    if required_action and required_action not in actions:
        return False, f"did not call console_action {required_action}"
    required_order = case.get("action_order") or []
    cursor = 0
    for action in actions:
        if cursor < len(required_order) and action == required_order[cursor]:
            cursor += 1
    if cursor != len(required_order):
        return False, f"missing ordered console actions {required_order}"
    required_delegate = case.get("require_delegate")
    if required_delegate and required_delegate not in delegated:
        return False, f"did not delegate to {required_delegate}"
    if case.get("capability_question"):
        return (bool((reply or "").strip()), "capability question: any non-empty reply")
    if case.get("explicit_ask") or case.get("approve_proposal"):
        # D-L5 (Larry, 2026-09-25): he asked for the command, so it belongs
        # on screen (show_commands), never spoken, and nothing is refused.
        # W8: the same for the apply command once he approves a proposal.
        what = "explicit ask" if case.get("explicit_ask") else "approved proposal"
        refusals = [v for v in reply_violations(reply) if v[1] == "refusal"]
        if refusals:
            return False, f"spoken refusal: {refusals[0][0]!r}"
        if "show_commands" not in tools_called:
            return False, f"{what}: show_commands was not called"
        return True, f"{what}: shown"
    violations = reply_violations(reply)
    if violations:
        sentence, kind = violations[0]
        return False, f"spoken {kind}: {sentence!r}"
    if "show_commands" in tools_called:
        return False, "called show_commands"
    # W8 / self-rebuild (Phase 3): what the reply must and must not say.
    if case.get("must_say") and case["must_say"].lower() not in (reply or "").lower():
        return False, f"did not say {case['must_say']!r}"
    if case.get("must_not_say") and re.search(case["must_not_say"], reply or "", re.I):
        return False, f"said {case['must_not_say']!r}"
    # Phase 2 D4 (D-L6): location questions must be answered by the tool,
    # never from memory, so a reply without the call fails outright.
    required = case.get("require_tool")
    if required and required not in tools_called:
        return False, f"did not call {required}"
    or_tool = case.get("or_tool")
    if or_tool and or_tool in tools_called:
        return True, f"called {or_tool}"
    expect = case.get("expect_any") or []
    if expect and not (set(expect) & set(delegated)) and not ALLOWED_RE.search(reply or ""):
        return False, f"expected one of {expect}, delegated {sorted(set(delegated))}"
    return True, "ok"


def _hooked(message: dict, settings) -> dict:
    """A replayed specialist result gets the guidance production's result
    hook (voice_workflows.wrap_delegate_handler) would have appended."""
    from jarvis.voice_workflows import match_voice_workflow, render_guidance, result_kinds

    message = dict(message)
    if message.get("role") != "tool" or not getattr(settings, "jarvis_voice_workflows_enabled", False):
        return message
    kinds = result_kinds(message.get("content"))
    wf = match_voice_workflow(result_kinds=kinds) if kinds else None
    if wf is not None:
        message["content"] += "\n\n" + render_guidance(wf)
    return message


async def run_eval() -> tuple[int, int]:
    os.environ["JARVIS_DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="jarvis-veval-")) / "eval.db")
    os.environ.setdefault("JARVIS_CAPABILITY_GAP_LOG",
                          str(Path(tempfile.mkdtemp(prefix="jarvis-veval-gaps-")) / "gaps.jsonl"))
    isolate_selfedit_service()
    _apply_candidate_overrides()

    from jarvis.agents.supervisor import Orchestrator
    from jarvis.bot.tool_schemas import supervisor_tool_schemas
    from jarvis.bot.voice_switch import catalog_summary, load_voice_catalog
    from jarvis.config import load_settings
    from jarvis.db import run_migrations
    from jarvis.logging_config import setup_logging
    from jarvis.skills.registry import REPO_ROOT as REG_ROOT
    from jarvis.skills.registry import SkillRegistry

    settings = load_settings()
    profile_name, flags, show_tools = resolve_profile(os.environ.get("EVAL_PROFILE"))

    async def _stub(_arguments: dict) -> str:
        return "ok"

    from jarvis.status import status_enabled

    status_on = status_enabled()
    # W12: the timing tools ship behind their own switches, read the way
    # pipeline.py reads them, so the eval scores the menu production shows.
    from jarvis.bot.follow_up import follow_ups_enabled, progress_updates_enabled

    timing = {"progress": progress_updates_enabled() and show_tools,
              "follow_up": follow_ups_enabled() and show_tools}
    extra_tools = [
        (schema, _stub)
        for schema in supervisor_tool_schemas(
            None, ui_control=flags["ui_control"], screen=flags["screen"],
            clipboard=flags["clipboard"], status=status_on, **timing,
            weather=True,  # WS-15: local_weather ships unconditionally (W8)
        )
    ] if show_tools else []
    voice_catalog = catalog_summary(load_voice_catalog()) if flags["voice"] else None
    print(f"eval model: {settings.openai_model}  ({settings.openai_base_url})")
    print(f"eval profile: {profile_name}  voice_workflows="
          f"{settings.jarvis_voice_workflows_enabled}  reply_guard={settings.jarvis_reply_guard_mode}")
    setup_logging("WARNING")
    run_migrations()
    registry = SkillRegistry(REG_ROOT / "config" / "mcp_servers.yaml")
    await registry.start()

    cases = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    passed = 0
    try:
        for i, case in enumerate(cases, 1):
            delegated: list[str] = []
            tools_called: list[str] = []
            actions_called: list[str] = []

            async def console_probe(arguments: dict) -> str:
                # Synthetic UI fixture; never contacts or controls the live app.
                # Record only the closed action name, not private arguments.
                from jarvis.bot.console_protocol import ALLOWED_ACTIONS
                action = arguments.get("action")
                if isinstance(action, str) and action in ALLOWED_ACTIONS:
                    actions_called.append(action)
                if action == "inventory":
                    return json.dumps({"revision": 1, "results": [
                        {"id": "00000000-0000-4000-8000-000000000001", "number": 1,
                         "kind": "Weather", "subject": "Atlanta", "title": "Weather · Atlanta"},
                        {"id": "00000000-0000-4000-8000-000000000002", "number": 2,
                         "kind": "Weather", "subject": "Folly Beach", "title": "Weather · Folly Beach"},
                    ]})
                return "Console action applied in the synthetic evaluation fixture."

            case_tools = list(extra_tools)
            if case.get("require_action") and show_tools:
                from jarvis.bot.console_actions import CONSOLE_ACTION_SCHEMA
                case_tools.append((CONSOLE_ACTION_SCHEMA, console_probe))

            def on_event(event: dict) -> None:
                if event.get("type") == "delegate_start":
                    delegated.append(event["agent"])
                elif event.get("type") == "supervisor_tool":
                    tools_called.append(event["tool"])

            orch = Orchestrator(settings, registry, str(uuid.uuid4()), on_event=on_event,
                                extra_tools=case_tools, voice_catalog=voice_catalog,
                                status=status_on and show_tools, weather=show_tools,
                                **timing, **flags)
            orch._history.extend(_hooked(m, settings) for m in case.get("prior") or [])
            try:
                reply = await orch.chat(case["input"])
            except Exception as exc:  # noqa: BLE001 — a crash is a failed case
                print(f"[{i:2d}/{len(cases)}] ERROR {case['input']!r}: {exc}")
                continue
            ok, reason = grade(case, reply, delegated, tools_called, actions_called)
            passed += ok
            print(f"[{i:2d}/{len(cases)}] {'ok  ' if ok else 'FAIL'} from={case.get('from', '-')} "
                  f"{case['input']!r} -> {reason}")
            if not ok:
                print(f"{'':>9}delegated: {', '.join(delegated) or '(none)'}; "
                      f"tools: {', '.join(tools_called) or '(none)'}; actions: {actions_called}")
                print(f"{'':>9}said: {_one_line(reply)}")
    finally:
        await registry.stop()
    print(f"\nVoice workflows: {passed}/{len(cases)} = {passed / len(cases):.0%} "
          f"(threshold {PASS_THRESHOLD:.0%})")
    return passed, len(cases)


async def run_ws17_routing_probe(settings, *, client_factory=None) -> tuple[int, int]:
    """Only model routing is live. No MCP servers, specialists or native actions.

    Caller must select an isolated database before constructing Settings. This
    does not establish end-to-end reuse/selection or live UI acceptance.
    """
    from jarvis.agents.supervisor import Orchestrator
    from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
    from jarvis.bot.console_protocol import ALLOWED_ACTIONS
    from jarvis.bot.tool_schemas import supervisor_tool_schemas
    from jarvis.bot.voice_switch import catalog_summary, load_voice_catalog

    roster = yaml.safe_load((REPO_ROOT / "config/agents.yaml").read_text())["sub_agents"]
    agents = {a["name"]: SimpleNamespace(name=a["name"], display_name=a["display_name"],
                                       description=a["description"]) for a in roster}
    cases = [c for c in yaml.safe_load(CASES_PATH.read_text()) if c.get("id", "").startswith("ws17-")]
    passed = 0
    for case in cases:
        called, delegated, actions = [], [], []
        if client_factory is None:
            from jarvis.llm_client import make_async_client
            live_client = make_async_client(api_key=settings.openai_api_key,
                                            base_url=settings.openai_base_url,
                                            timeout=30, max_retries=0)
            request_count = [0]
            async def bounded_completion(**kwargs):
                if request_count[0] >= 6:
                    raise RuntimeError("routing probe request limit reached")
                request_count[0] += 1
                kwargs["max_tokens"] = 1024
                return await live_client.chat.completions.create(**kwargs)
            factory = lambda _: SimpleNamespace(base_url=settings.openai_base_url,
                chat=SimpleNamespace(completions=SimpleNamespace(create=bounded_completion)))
        else:
            factory = client_factory
        async def no_side_effect(_arguments):
            return "Synthetic evaluation fixture: no live action was performed."
        schemas = supervisor_tool_schemas(None, ui_control=True, screen=True, clipboard=True,
                                         command_console=True, weather=True)
        orch = Orchestrator(settings, None, str(uuid.uuid4()), sub_agents=agents,
                            client_factory=factory,
                            extra_tools=[(s, no_side_effect) for s in schemas],
                            voice_catalog=catalog_summary(load_voice_catalog()),
                            voice=True, ui_control=True, screen=True, clipboard=True, weather=True)
        async def dispatch(name, arguments):
            # Replace the execution seam, not the model's tool menu or prompt.
            # No fallback to real handlers is possible, even for an unexpected call.
            called.append(name)
            if name == "delegate_task":
                if arguments.get("agent_name") in agents:
                    delegated.append(arguments["agent_name"])
                return "Synthetic weather fixture: Folly Beach is sunny and 75 degrees; the card is available."
            if name == "console_action":
                action = arguments.get("action")
                if isinstance(action, str) and action in ALLOWED_ACTIONS:
                    actions.append(action)
                if action == "inventory":
                    return json.dumps({"revision": 1, "results": [
                        {"id": "00000000-0000-4000-8000-000000000001", "number": 1, "kind": "Weather", "subject": "Atlanta", "title": "Weather · Atlanta"},
                        {"id": "00000000-0000-4000-8000-000000000002", "number": 2, "kind": "Weather", "subject": "Folly Beach", "title": "Weather · Folly Beach"},
                    ]})
            return await no_side_effect(arguments)
        orch._execute_tool = dispatch
        orch._history.extend(_hooked(m, settings) for m in case.get("prior") or [])
        token = current_sensitive_turn.set(SensitiveTurn())
        try:
            reply = await asyncio.wait_for(orch.chat(case["input"]), timeout=90)
            ok, reason = grade(case, reply, delegated, called, actions)
        except Exception as exc:
            ok, reason = False, f"probe failed ({type(exc).__name__})"
        finally:
            current_sensitive_turn.reset(token)
            if client_factory is None:
                closer = getattr(live_client, "close", None)
                if closer is None:
                    closer = getattr(getattr(live_client, "_anthropic", None), "close", None)
                if closer is not None:
                    await closer()
        passed += ok
        print(f"{case['id']}: {'PASS' if ok else 'FAIL'}; {reason}; tools={called}; actions={actions}; delegated={delegated}")
    return passed, len(cases)


def main() -> int:
    if os.environ.get("RUN_LIVE") != "1":
        print("voice_workflow_eval makes real LLM calls; re-run with RUN_LIVE=1")
        return 2
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws17-routing-only", action="store_true",
                        help="Only two synthetic WS-17 cases; model calls live, all tools stubbed")
    args = parser.parse_args()
    if args.ws17_routing_only:
        root = Path(tempfile.mkdtemp(prefix="mortimer-ws17-routing-"))
        os.environ["JARVIS_DB_PATH"] = str(root / "eval.db")
        os.environ["JARVIS_COSTS_DB"] = str(root / "costs.db")
        os.environ["JARVIS_CAPABILITY_GAP_LOG"] = str(root / "gaps.jsonl")
        from jarvis.config import load_settings
        from jarvis.db import run_migrations
        settings = load_settings()
        run_migrations()
        passed, total = asyncio.run(run_ws17_routing_probe(settings))
    else:
        passed, total = asyncio.run(run_eval())
    return 0 if passed / total >= PASS_THRESHOLD else 1


if __name__ == "__main__":
    raise SystemExit(main())
