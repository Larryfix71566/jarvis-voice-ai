"""Unit tests for the Upgrade Agent contract (plan section 3.5).

The LLM is faked with a scripted client; what is under test is the agent's
side of the contract: closed toolset, loop bounds, the single-repair rule,
and that off-allowlist goals cannot produce edits.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import jarvis.council.council as council_mod
from jarvis.agents.upgrade_agent import TOOL_SPECS, UpgradeAgent
from jarvis.council.types import Proposal, RoundResult
from jarvis.selfedit.service import SelfEditService

ALLOWLIST = {"allow": ["web/src/**"], "deny": ["jarvis/**"]}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


@pytest.fixture()
def service(tmp_path: Path) -> SelfEditService:
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", str(origin))
    work = tmp_path / "work"
    _git(tmp_path, "clone", str(origin), str(work))
    _git(work, "config", "user.email", "t@e.com")
    _git(work, "config", "user.name", "T")
    _git(work, "checkout", "-b", "main")
    (work / "web/src").mkdir(parents=True)
    (work / "web/src/App.tsx").write_text("export default 1;\n")
    (work / "config").mkdir()
    (work / "config/self_edit_allowlist.json").write_text(json.dumps(ALLOWLIST))
    cfg = {
        "model": "fake-model", "temperature": 0.2,
        "max_iterations": 6, "max_session_minutes": 30,
    }
    (work / "config/upgrade_agent.yaml").write_text(yaml.safe_dump(cfg))
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "-u", "origin", "main")
    return SelfEditService(repo_root=work, github_token=None)


def _tool_call(name: str, args: dict, call_id: str = "c1") -> SimpleNamespace:
    return SimpleNamespace(
        id=call_id, type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def _response(message: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class ScriptedClient:
    """Plays back a list of messages, one per completion call."""

    def __init__(self, messages: list[SimpleNamespace]):
        self._messages = list(messages)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.calls = 0
        self.received: list[dict] = []  # kwargs passed to each create() call

    def _create(self, **kwargs) -> SimpleNamespace:
        self.calls += 1
        self.received.append(kwargs)
        assert self._messages, "scripted client ran out of messages"
        return _response(self._messages.pop(0))


def _msg(content=None, tool_calls=None) -> SimpleNamespace:
    return SimpleNamespace(content=content, tool_calls=tool_calls or [])


def _agent(service: SelfEditService, client: ScriptedClient) -> UpgradeAgent:
    return UpgradeAgent(
        service,
        config_path=service.repo_root / "config/upgrade_agent.yaml",
        client_factory=lambda: client,
    )


def test_toolset_is_closed() -> None:
    names = {t["function"]["name"] for t in TOOL_SPECS}
    assert names == {
        "file_read", "edit_propose", "session_validate", "session_submit",
        "session_decline",
    }


def test_unknown_tool_refused(service: SelfEditService) -> None:
    agent = _agent(service, ScriptedClient([_msg(content="done")]))
    result = agent._dispatch("shell", {"cmd": "rm -rf /"})
    assert not result["ok"]


def test_off_allowlist_goal_cannot_edit(service: SelfEditService) -> None:
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("edit_propose", {
            "path": "jarvis/wakeword.py", "new_content": "x=1\n",
            "rationale": "rewrite",
        })]),
        _msg(content="That path requires human development; I declined."),
    ])
    agent = _agent(service, client)
    result = agent.run("rewrite the wake word detector")
    assert result["ok"]  # agent finished by declining
    assert "declined" in result["summary"].lower() or "human" in result["summary"].lower()
    assert not (service.repo_root / "jarvis/wakeword.py").exists()


def test_iteration_bound_stops_runaway(service: SelfEditService) -> None:
    # The fake model keeps proposing the same edit forever.
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("edit_propose", {
            "path": "web/src/App.tsx", "new_content": f"export default {i};\n",
            "rationale": "loop",
        }, call_id=f"c{i}")])
        for i in range(50)
    ])
    agent = _agent(service, client)
    result = agent.run("endless tinkering")
    assert not result["ok"]
    assert "iteration limit" in result["summary"]
    assert client.calls == agent.cfg["max_iterations"]


def test_session_decline_dispatch(service: SelfEditService) -> None:
    agent = _agent(service, ScriptedClient([_msg(content="done")]))
    result = agent._dispatch(
        "session_decline", {"reason": "off-allowlist: touches jarvis/wakeword"},
    )
    assert result == {
        "ok": False, "declined": True,
        "reason": "off-allowlist: touches jarvis/wakeword",
    }


def test_session_decline_tool_ends_session_immediately(service: SelfEditService) -> None:
    """D3/D2 E2 — a decline is a recorded fact (declined=True), never
    inferred from prose."""
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("session_decline", {
            "reason": "requires changes to jarvis/wakeword, which is off "
                      "the self-edit allowlist",
        })]),
    ])
    agent = _agent(service, client)
    result = agent.run("rewrite the wake word detector")
    assert result["ok"] is False
    assert result["declined"] is True
    assert "wakeword" in result["summary"]
    assert not (service.repo_root / "jarvis/wakeword.py").exists()


def test_double_validation_failure_ends_session(service: SelfEditService) -> None:
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("session_validate", {}, "v1")]),
        _msg(tool_calls=[_tool_call("session_validate", {}, "v2")]),
    ])
    # Dirty a forbidden file so validation can never pass.
    agent = _agent(service, client)
    service.start_session("doomed")
    (service.repo_root / "jarvis").mkdir(exist_ok=True)
    (service.repo_root / "jarvis/x.py").write_text("bad\n")
    result = agent.run("validate me")
    assert not result["ok"]
    assert "validation failed twice" in result["summary"]


# ------------------------------------------------------- D2.1 escalation
# MORTIMER_LLM_COUNCIL_PLAN.md §6's required escalation test table. The
# real jarvis.council.council.convene() is monkeypatched (fake council, no
# network) — what's under test is upgrade_agent.py's side of the D2 hook.


def _dirty_forbidden_file(service: SelfEditService) -> None:
    service.start_session("doomed")
    (service.repo_root / "jarvis").mkdir(exist_ok=True)
    (service.repo_root / "jarvis/x.py").write_text("bad\n")


def _fake_convene_factory(
    tiers_seen: list[int], winner_content: str = "do the right thing",
    contexts_seen: list[dict] | None = None,
):
    async def _fake_convene(*, workflow, placement, trigger, goal, tier, context, run_id=None):
        tiers_seen.append(tier)
        if contexts_seen is not None:
            contexts_seen.append(context)
        winner = Proposal(
            label="Proposal A", profile="kimi-k2",
            content=f"{winner_content} (tier {tier})",
        )
        return RoundResult(
            round_id=f"round-tier{tier}", winner=winner, winner_mean=8.0,
            select_reason="highest mean score (8.0)", proposals=[winner],
            scores=[], abstentions=0, tier=tier,
        )
    return _fake_convene


async def _fake_convene_unavailable(**_kwargs):
    return None


def test_escalation_injects_council_brief_and_retries(
    service: SelfEditService, monkeypatch,
) -> None:
    tiers_seen: list[int] = []
    monkeypatch.setattr(council_mod, "convene", _fake_convene_factory(tiers_seen))
    recorded: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        council_mod, "record_retry_validated",
        lambda round_id, validated: recorded.append((round_id, validated)),
    )
    service.start_session("doomed")
    (service.repo_root / "jarvis").mkdir(exist_ok=True)
    (service.repo_root / "jarvis/x.py").write_text("bad\n")

    # First two validate calls fail (the second escalates); the third —
    # the council-guided retry — succeeds, once the forbidden file is
    # "fixed." Real SelfEditService.validate() re-checks actual git
    # state, so a stateful fake stands in for it here rather than trying
    # to make the fixture repo pass a real allowlist/build check.
    calls = {"n": 0}
    real_validate = service.validate

    def _fake_validate():
        calls["n"] += 1
        if calls["n"] <= 2:
            return real_validate()
        return {"ok": True, "checks": [{"name": "allowlist", "ok": True, "output": "ok"}]}

    monkeypatch.setattr(service, "validate", _fake_validate)

    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("session_validate", {}, "v1")]),  # fails, repairs=1
        _msg(tool_calls=[_tool_call("session_validate", {}, "v2")]),  # fails, repairs=2>1 -> escalate tier1
        _msg(tool_calls=[_tool_call("session_validate", {}, "v3")]),  # the retry: succeeds
        _msg(content="submitted after council-guided retry"),
    ])
    agent = _agent(service, client)
    result = agent.run("validate me")

    assert result["ok"] is True  # session ended normally after the retry
    assert tiers_seen == [1]     # exactly one escalation, at tier 1
    assert agent._escalations_used == 1

    # The council's winning content was injected as a system message
    # ahead of the retry's (3rd) completion call.
    third_call_messages = client.received[2]["messages"]
    assert any(
        m.get("role") == "system" and "do the right thing" in (m.get("content") or "")
        for m in third_call_messages
    )
    # D8.1 — the retry's own validate result (v3, ok=True) was written back.
    assert recorded == [("round-tier1", True)]


def test_escalation_council_unavailable_falls_through_unchanged(
    service: SelfEditService, monkeypatch,
) -> None:
    monkeypatch.setattr(council_mod, "convene", _fake_convene_unavailable)
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("session_validate", {}, "v1")]),
        _msg(tool_calls=[_tool_call("session_validate", {}, "v2")]),
    ])
    agent = _agent(service, client)
    _dirty_forbidden_file(service)
    result = agent.run("validate me")
    assert not result["ok"]
    assert "validation failed twice" in result["summary"]
    assert agent._escalations_used == 1  # the attempt still counted


def test_escalation_uses_tier1_then_tier2_never_repeats(
    service: SelfEditService, monkeypatch,
) -> None:
    tiers_seen: list[int] = []
    monkeypatch.setattr(council_mod, "convene", _fake_convene_factory(tiers_seen))
    monkeypatch.setattr(
        council_mod, "record_retry_validated", lambda *a, **k: None,
    )
    # The forbidden file stays dirty throughout, so every validate call
    # fails and each escalation gets its own fresh one-repair budget
    # (D2.1: `repairs_used = 0` on retry) before the next one triggers:
    # v1 fail(repairs=1) -> v2 fail(repairs=2>1, escalate tier1, reset)
    # -> v3 fail(repairs=1) -> v4 fail(repairs=2>1, escalate tier2, reset)
    # -> v5 fail(repairs=1) -> v6 fail(repairs=2>1, no 3rd escalation:
    # COUNCIL_MAX_ESCALATIONS=2 already used) -> session ends.
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("session_validate", {}, f"v{i}")])
        for i in range(1, 7)
    ])
    agent = _agent(service, client)
    _dirty_forbidden_file(service)
    result = agent.run("validate me")
    assert not result["ok"]
    assert tiers_seen == [1, 2]
    assert agent._escalations_used == 2
    assert "validation failed twice" in result["summary"]


def test_v1_second_escalation_carries_first_winner_forward(
    service: SelfEditService, monkeypatch,
) -> None:
    """MORTIMER_LLM_COUNCIL_V2_PLAN.md V1 — the tier-2 convene call
    receives context["carry_forward"] with the tier-1 winner's
    (profile, content)."""
    tiers_seen: list[int] = []
    contexts_seen: list[dict] = []
    monkeypatch.setattr(
        council_mod, "convene",
        _fake_convene_factory(tiers_seen, contexts_seen=contexts_seen),
    )
    monkeypatch.setattr(
        council_mod, "record_retry_validated", lambda *a, **k: None,
    )
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("session_validate", {}, f"v{i}")])
        for i in range(1, 7)
    ])
    agent = _agent(service, client)
    _dirty_forbidden_file(service)
    agent.run("validate me")

    assert tiers_seen == [1, 2]
    assert "carry_forward" not in contexts_seen[0]  # tier 1: nothing to carry yet
    assert contexts_seen[1]["carry_forward"] == {
        "profile": "kimi-k2", "content": "do the right thing (tier 1)",
    }


def test_v10_escalation_grants_extra_iterations_not_starved(
    service: SelfEditService, monkeypatch,
) -> None:
    """MORTIMER_LLM_COUNCIL_V2_PLAN.md V10 — a council-guided retry that
    would otherwise die on a near-exhausted iteration cap gets extra
    budget instead. max_iterations is set to 2, so without V10 the
    escalation at iteration 2 would be the last iteration ever run;
    with V10 the budget grows by COUNCIL_RETRY_EXTRA_ITERATIONS (4),
    letting the retry (iteration 3) and the final submit (iteration 4)
    actually execute."""
    tiers_seen: list[int] = []
    monkeypatch.setattr(council_mod, "convene", _fake_convene_factory(tiers_seen))
    monkeypatch.setattr(
        council_mod, "record_retry_validated", lambda *a, **k: None,
    )
    calls = {"n": 0}
    real_validate = service.validate

    def _fake_validate():
        calls["n"] += 1
        if calls["n"] <= 2:
            return real_validate()
        return {"ok": True, "checks": [{"name": "allowlist", "ok": True, "output": "ok"}]}

    monkeypatch.setattr(service, "validate", _fake_validate)
    service.start_session("doomed")
    (service.repo_root / "jarvis").mkdir(exist_ok=True)
    (service.repo_root / "jarvis/x.py").write_text("bad\n")

    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("session_validate", {}, "v1")]),  # iter1: fails, repairs=1
        _msg(tool_calls=[_tool_call("session_validate", {}, "v2")]),  # iter2: fails, repairs=2>1 -> escalate tier1
        _msg(tool_calls=[_tool_call("session_validate", {}, "v3")]),  # iter3 (needs V10 budget): retry succeeds
        _msg(content="submitted after council-guided retry"),          # iter4 (needs V10 budget)
    ])
    agent = _agent(service, client)
    agent.cfg["max_iterations"] = 2  # deliberately too small without V10's grant

    result = agent.run("validate me")

    assert tiers_seen == [1]
    assert result["ok"] is True  # would be False (iteration limit) without V10
    assert client.calls == 4


def test_v10_no_escalation_iteration_cap_unchanged(service: SelfEditService) -> None:
    """Regression guard from the plan's own test table: without an
    escalation, the budget never grows, and the existing byte-for-byte
    iteration-bound behavior is unchanged."""
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("edit_propose", {
            "path": "web/src/App.tsx", "new_content": f"export default {i};\n",
            "rationale": "loop",
        }, call_id=f"c{i}")])
        for i in range(50)
    ])
    agent = _agent(service, client)
    result = agent.run("endless tinkering")
    assert not result["ok"]
    assert "iteration limit" in result["summary"]
    assert client.calls == agent.cfg["max_iterations"]


# ----------------------------------------------------- V14 scope council

def _fake_scope_convene_factory(calls_seen: list[dict], winner_content: str = "narrow the goal"):
    async def _fake_convene(*, workflow, placement, trigger, goal, tier, context, run_id=None):
        calls_seen.append({
            "workflow": workflow, "placement": placement, "trigger": trigger,
            "goal": goal, "tier": tier, "context": context,
        })
        winner = Proposal(label="Proposal A", profile="kimi-k2", content=winner_content)
        return RoundResult(
            round_id="scope-round-1", winner=winner, winner_mean=8.0,
            select_reason="highest mean score (8.0)", proposals=[winner],
            scores=[], abstentions=0, tier=tier,
        )
    return _fake_convene


def test_v14_decline_convenes_one_scope_council_and_appends_brief(
    service: SelfEditService, monkeypatch,
) -> None:
    calls_seen: list[dict] = []
    monkeypatch.setattr(
        council_mod, "convene", _fake_scope_convene_factory(calls_seen),
    )
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("session_decline", {
            "reason": "requires changes to jarvis/wakeword, off allowlist",
        })]),
    ])
    agent = _agent(service, client)
    result = agent.run("rewrite the wake word detector")

    assert result["ok"] is False
    assert result["declined"] is True
    assert "wakeword" in result["summary"]  # original decline reason still present
    assert "narrow the goal" in result["summary"]  # V14 brief appended
    assert len(calls_seen) == 1
    call = calls_seen[0]
    assert call["workflow"] == "selfedit"
    assert call["placement"] == "scope"
    assert call["trigger"] == "E2"
    assert call["tier"] == 1
    assert call["context"]["reason"] == "requires changes to jarvis/wakeword, off allowlist"
    assert "allow" in call["context"]["allowlist"]  # the fixture's allowlist JSON
    assert agent._escalations_used == 0  # V14: does NOT touch the escalation ladder


def test_v14_scope_council_returns_none_leaves_summary_unchanged(
    service: SelfEditService, monkeypatch,
) -> None:
    async def _fake_convene(**_kwargs):
        return None

    monkeypatch.setattr(council_mod, "convene", _fake_convene)
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("session_decline", {
            "reason": "off-allowlist: touches jarvis/wakeword",
        })]),
    ])
    agent = _agent(service, client)
    result = agent.run("rewrite the wake word detector")
    assert result["declined"] is True
    assert result["summary"] == "off-allowlist: touches jarvis/wakeword"


def test_v14_scope_council_used_flag_set_after_first_decline(
    service: SelfEditService, monkeypatch,
) -> None:
    """session_decline ends the session immediately, so one run() can
    only ever produce one decline — this confirms the guard flag that
    prevents a second scope council (in a session that somehow declined
    twice) is actually set after the first, at-most-once by construction."""
    calls_seen: list[dict] = []
    monkeypatch.setattr(
        council_mod, "convene", _fake_scope_convene_factory(calls_seen),
    )
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("session_decline", {"reason": "first decline"})]),
    ])
    agent = _agent(service, client)
    agent.run("goal one")
    assert len(calls_seen) == 1
    assert agent._scope_council_used is True

    # Directly exercise the guard the run() loop checks: once the flag
    # is set, `_maybe_scope_council` is simply never called again in the
    # same run() (see the `if not self._scope_council_used:` gate) — here
    # we confirm calling it explicitly still works (it has no internal
    # gate of its own; the gate lives in run(), by design) but that the
    # flag itself does not reset except at the top of run().
    agent._maybe_scope_council(goal="g2", reason="r2", allowlist="a2")
    assert len(calls_seen) == 2  # the helper itself is ungated; run() is the gate
    assert agent._scope_council_used is True  # unchanged — no re-arming mid-session


def test_v14_kill_switch_off_no_scope_council(
    service: SelfEditService, monkeypatch,
) -> None:
    monkeypatch.setenv("JARVIS_COUNCIL_ENABLED", "false")
    called = {"n": 0}

    async def _spy(*a, **k):
        called["n"] += 1
        return "unused"

    monkeypatch.setattr(council_mod, "_call_profile", _spy)
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("session_decline", {
            "reason": "off-allowlist: touches jarvis/wakeword",
        })]),
    ])
    agent = _agent(service, client)
    result = agent.run("rewrite the wake word detector")
    assert result["declined"] is True
    assert called["n"] == 0
    assert result["summary"] == "off-allowlist: touches jarvis/wakeword"


def test_kill_switch_disables_escalation_entirely(
    service: SelfEditService, monkeypatch,
) -> None:
    monkeypatch.setenv("JARVIS_COUNCIL_ENABLED", "false")
    called = {"n": 0}

    async def _spy(**_kwargs):
        called["n"] += 1
        return None

    # convene() itself checks the kill switch (D11); patching the real
    # function (not a fake) verifies the switch is honored end to end.
    monkeypatch.setattr(council_mod, "_call_profile", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("must not fan out when the kill switch is off")
    ))
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("session_validate", {}, "v1")]),
        _msg(tool_calls=[_tool_call("session_validate", {}, "v2")]),
    ])
    agent = _agent(service, client)
    _dirty_forbidden_file(service)
    result = agent.run("validate me")
    assert not result["ok"]
    assert "validation failed twice" in result["summary"]
