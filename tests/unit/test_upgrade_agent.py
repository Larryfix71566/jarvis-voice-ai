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
from jarvis.db import get_conn, run_migrations
from jarvis.selfedit.service import SelfEditService

ALLOWLIST = {"allow": ["web/src/**"], "deny": ["jarvis/**"]}


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Council escalation paths write rounds via get_conn()'s default
    path — without this, every pytest run pollutes the LIVE
    data/jarvis.db (8 junk rounds observed on 2026-08-17)."""
    db_path = tmp_path / "upgrade_agent_test.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()


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


class TestPlannerFailover:
    """Larry 2026-08-22: "spin on a dead model is not a great look."

    Before this, UpgradeAgent's client carried NO timeout, so the openai
    SDK default (600s read) applied, and max_session_minutes could not
    help — it is checked between iterations, while a hung call blocks
    inside the HTTP read.
    """

    def _registry(self, tmp_path, monkeypatch):
        """Two key-present profiles so failover has somewhere to go."""
        reg = {
            "default": "alpha",
            "profiles": [
                {"name": "alpha", "label": "Alpha", "provider": "openai",
                 "model": "alpha-model", "base_url": "https://alpha.example/v1",
                 "api_key_env": "ALPHA_KEY", "temperature": None, "tier": "mid"},
                {"name": "beta", "label": "Beta", "provider": "openai",
                 "model": "beta-model", "base_url": "https://beta.example/v1",
                 "api_key_env": "BETA_KEY", "temperature": None, "tier": "mid"},
            ],
        }
        path = tmp_path / "registry.yaml"
        path.write_text(yaml.safe_dump(reg))
        monkeypatch.setenv("ALPHA_KEY", "x")
        monkeypatch.setenv("BETA_KEY", "y")
        monkeypatch.delenv("JARVIS_UPGRADE_PROFILE", raising=False)
        return path

    def test_client_call_timeout_is_bounded(
        self, service: SelfEditService, monkeypatch
    ) -> None:
        """The whole point: a bounded call, and no SDK retry silently
        tripling it."""
        from jarvis.agents.upgrade_agent import PLANNER_CALL_TIMEOUT_S

        monkeypatch.setenv("ALPHA_KEY", "x")
        captured = {}

        class FakeOpenAI:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        agent = UpgradeAgent(
            service, config_path=service.repo_root / "config/upgrade_agent.yaml",
            client_factory=lambda: object(),
        )
        import openai
        original = openai.OpenAI
        openai.OpenAI = FakeOpenAI
        try:
            agent._build_client("ALPHA_KEY", "https://alpha.example/v1")
        finally:
            openai.OpenAI = original
        assert captured["timeout"] == PLANNER_CALL_TIMEOUT_S
        assert captured["max_retries"] == 0

    def test_only_unreachable_class_triggers_failover(self, service) -> None:
        """A 4xx must NOT fail over — it would repeat identically on every
        profile AND mask a real config bug (the 2026-08-22 claude-opus
        `temperature` 400 is the worked example)."""
        import httpx
        from openai import APIStatusError, APITimeoutError

        req = httpx.Request("POST", "https://x.example/v1/chat/completions")
        bad_request = APIStatusError(
            "temperature is deprecated",
            response=httpx.Response(400, request=req), body=None,
        )
        server_error = APIStatusError(
            "upstream boom",
            response=httpx.Response(503, request=req), body=None,
        )
        assert UpgradeAgent._is_unreachable(bad_request) is False
        assert UpgradeAgent._is_unreachable(server_error) is True
        assert UpgradeAgent._is_unreachable(APITimeoutError(request=req)) is True
        assert UpgradeAgent._is_unreachable(ValueError("nope")) is False

    def test_timeout_fails_over_and_announces(
        self, service: SelfEditService, tmp_path, monkeypatch
    ) -> None:
        """The headline behaviour Larry chose: kill, switch, and SAY SO."""
        import httpx
        from openai import APITimeoutError

        registry_path = self._registry(tmp_path, monkeypatch)
        req = httpx.Request("POST", "https://alpha.example/v1/chat/completions")

        class FailingThenWorkingClient:
            def __init__(self):
                self.calls = 0
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=self._create))

            def _create(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise APITimeoutError(request=req)
                return _response(_msg(content="done on the second model"))

        client = FailingThenWorkingClient()
        agent = UpgradeAgent(
            service,
            config_path=service.repo_root / "config/upgrade_agent.yaml",
            registry_path=registry_path,
            client_factory=lambda: client,
        )
        # Failover rebuilds the client; keep the same fake so the retry is
        # observable rather than reaching the network.
        monkeypatch.setattr(agent, "_build_client", lambda *a, **k: client)

        assert agent.profile_name == "alpha"
        result = agent.run("do a small thing")

        assert result["ok"] is True
        assert agent.profile_name == "beta"          # switched
        assert "alpha" not in (agent.model or "")     # really on beta now
        assert result["failovers"], "failover must be reported, never silent"
        assert "alpha" in result["failovers"][0]
        assert "beta" in result["failovers"][0]
        # Mechanical disclosure in the spoken summary (never prompt-reliant).
        assert "continued on beta" in result["summary"]

    def test_failed_profile_is_never_retried_in_the_same_session(
        self, service: SelfEditService, tmp_path, monkeypatch
    ) -> None:
        registry_path = self._registry(tmp_path, monkeypatch)
        agent = UpgradeAgent(
            service,
            config_path=service.repo_root / "config/upgrade_agent.yaml",
            registry_path=registry_path,
            client_factory=lambda: ScriptedClient([_msg(content="x")]),
        )
        agent._failed_profiles.add("alpha")
        nxt = agent._next_failover_profile()
        assert nxt is not None and nxt["name"] == "beta"
        agent._failed_profiles.add("beta")
        assert agent._next_failover_profile() is None  # nothing left

    def test_profile_without_key_is_not_a_failover_candidate(
        self, service: SelfEditService, tmp_path, monkeypatch
    ) -> None:
        registry_path = self._registry(tmp_path, monkeypatch)
        monkeypatch.delenv("BETA_KEY", raising=False)
        agent = UpgradeAgent(
            service,
            config_path=service.repo_root / "config/upgrade_agent.yaml",
            registry_path=registry_path,
            client_factory=lambda: ScriptedClient([_msg(content="x")]),
        )
        assert agent._next_failover_profile() is None

    def test_no_failover_notes_means_clean_summary(
        self, service: SelfEditService
    ) -> None:
        """A run with no failover must be byte-identical to before this
        feature — no stray bracket appended."""
        client = ScriptedClient([_msg(content="all good")])
        agent = _agent(service, client)
        result = agent.run("do a small thing")
        assert result["summary"] == "all good"
        assert result["failovers"] == []


class TestRepoMapInjection:
    """G5 (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md): the
    self-edit loop's own prompt now carries docs/REPO_MAP.md via the SAME
    shared helper SubAgent uses (jarvis/repo_map.py) — one implementation,
    not two."""

    def test_upgrade_agent_prompt_carries_repo_map(
        self, service: SelfEditService, tmp_path, monkeypatch
    ) -> None:
        import jarvis.repo_map as repo_map_module

        repo_root = tmp_path / "fake_repo"
        (repo_root / "docs").mkdir(parents=True)
        (repo_root / "docs" / "REPO_MAP.md").write_text(
            "## Test map\n- delegate_task lives in jarvis/agents/delegate.py\n"
        )
        monkeypatch.setattr(repo_map_module, "__file__", str(repo_root / "jarvis" / "repo_map.py"))

        agent = _agent(service, ScriptedClient([_msg(content="done")]))
        assert "Test map" in agent._system_prompt
        assert "delegate_task lives in jarvis/agents/delegate.py" in agent._system_prompt

    def test_missing_repo_map_skipped_silently(
        self, service: SelfEditService, tmp_path, monkeypatch
    ) -> None:
        import jarvis.repo_map as repo_map_module

        monkeypatch.setattr(
            repo_map_module, "__file__", str(tmp_path / "no_docs_here" / "jarvis" / "repo_map.py")
        )
        agent = _agent(service, ScriptedClient([_msg(content="done")]))
        assert "Repository map" not in agent._system_prompt


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


def test_halfway_checkpoint_injected_at_half_budget_zero_edits(service: SelfEditService) -> None:
    """G6 (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md): a
    session that only reads, never proposing an edit, gets a forcing
    nudge injected once it's halfway through its iteration budget."""
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call(
            "file_read", {"path": "web/src/App.tsx"}, call_id=f"c{i}",
        )])
        for i in range(6)
    ])
    agent = _agent(service, client)
    result = agent.run("read everything forever")
    assert not result["ok"]
    transcript = client.received[-1]["messages"]  # append-only: final call sees everything
    assert any(
        m.get("role") == "system"
        and "halfway through this session's iteration budget" in (m.get("content") or "")
        for m in transcript
    )


def test_halfway_checkpoint_not_injected_once_an_edit_exists(service: SelfEditService) -> None:
    """The nudge is specifically for ZERO proposals — a session that
    already proposed something legitimately keeps reading/refining."""
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call("edit_propose", {
            "path": "web/src/App.tsx", "new_content": "export default 2;\n",
            "rationale": "first edit",
        }, call_id="c0")]),
    ] + [
        _msg(tool_calls=[_tool_call(
            "file_read", {"path": "web/src/App.tsx"}, call_id=f"c{i}",
        )])
        for i in range(1, 6)
    ])
    agent = _agent(service, client)
    agent.run("propose then keep reading")
    transcript = client.received[-1]["messages"]
    assert not any(
        m.get("role") == "system"
        and "halfway through this session's iteration budget" in (m.get("content") or "")
        for m in transcript
    )


def test_exhaustion_with_zero_proposals_names_never_converged(service: SelfEditService) -> None:
    """G6: exhausting the budget having never proposed a single edit is a
    DIFFERENT failure from exhausting it mid-edit — the summary must say
    so, not the generic 'iteration limit' message."""
    client = ScriptedClient([
        _msg(tool_calls=[_tool_call(
            "file_read", {"path": "web/src/App.tsx"}, call_id=f"c{i}",
        )])
        for i in range(6)
    ])
    agent = _agent(service, client)
    result = agent.run("read everything forever")
    assert not result["ok"]
    assert "never converged on a first edit" in result["summary"]
    assert "iteration limit" not in result["summary"]


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


# ------------------------------------------------ P7: pre-written plan input

def test_plan_kwarg_injects_system_message_before_first_completion_call(
    service: SelfEditService,
) -> None:
    """MORTIMER_PLANNING_PATHWAY_PLAN.md P7 — a plan adopted via the
    planning pathway (or passed to POST /api/selfedit/run) is injected as
    a system message, before the edit loop's first completion call."""
    client = ScriptedClient([_msg(content="done")])
    agent = _agent(service, client)
    result = agent.run("do the thing", plan="# The Plan\n\nStep one, step two.")
    assert result["ok"]
    first_call_messages = client.received[0]["messages"]
    plan_messages = [
        m for m in first_call_messages
        if m["role"] == "system" and "Step one, step two" in m["content"]
    ]
    assert len(plan_messages) == 1
    assert "pre-written implementation plan" in plan_messages[0]["content"]


def test_no_plan_kwarg_omits_plan_system_message(service: SelfEditService) -> None:
    client = ScriptedClient([_msg(content="done")])
    agent = _agent(service, client)
    agent.run("do the thing")
    first_call_messages = client.received[0]["messages"]
    assert not any(
        "pre-written implementation plan" in (m.get("content") or "")
        for m in first_call_messages
    )
