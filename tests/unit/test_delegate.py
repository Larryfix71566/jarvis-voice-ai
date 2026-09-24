"""Unit tests for jarvis/agents/delegate.py (plan Phase 3 Tests; Phase 4
concurrency tests below)."""

import asyncio
import time

import pytest
import yaml

from jarvis.agents.delegate import (
    RETRY_GUARD_OVERLAP,
    RETRY_GUARD_WINDOW_S,
    build_delegate_tool,
)
from jarvis.prompts import render_agent_catalog

from tests.unit.test_orchestrator import FakeSubAgent


class SlowFakeSubAgent:
    """Like FakeSubAgent but sleeps for `delay` seconds, so tests can
    observe whether concurrent delegations actually overlap in time."""

    def __init__(self, name, delay=0.05, result="done"):
        self.name = name
        self.display_name = name.title()
        self.description = f"{name} things."
        self.mcp_servers = []
        self.delay = delay
        self.result = result
        self.model = "fake-model"
        self.model_is_fallback = False
        self.model_unusable = False
        self.model_unusable_detail = ""
        self.tasks = []
        self.started_at: float | None = None
        self.finished_at: float | None = None

    async def run(self, task, on_event=None, **kwargs):
        self.started_at = time.perf_counter()
        self.tasks.append(task)
        await asyncio.sleep(self.delay)
        if self.result.startswith("FAILED"):
            self.finished_at = time.perf_counter()
            return self.result
        self.finished_at = time.perf_counter()
        return self.result

AGENTS = {n: FakeSubAgent(n)
          for n in ("scheduler", "librarian", "analyst", "systems", "developer")}


class TestSchema:
    def test_schema_matches_locked_spec(self):
        schema, _ = build_delegate_tool(AGENTS)
        fn = schema["function"]
        assert schema["type"] == "function"
        assert fn["name"] == "delegate_task"
        assert "self-contained" in fn["description"]
        props = fn["parameters"]["properties"]
        assert props["agent_name"]["enum"] == [
            "scheduler", "librarian", "analyst", "systems", "developer"]
        assert fn["parameters"]["required"] == ["agent_name", "task"]

    def test_schema_has_optional_model_profile(self):
        """F6 (MORTIMER_GATE_V2_AND_MODEL_REQUEST_PLAN.md) — a named
        per-run model request is an OPTIONAL parameter, never required:
        omitting it (the overwhelming majority of delegations) must not
        become a validation error."""
        schema, _ = build_delegate_tool(AGENTS)
        fn = schema["function"]
        props = fn["parameters"]["properties"]
        assert "model_profile" in props
        assert props["model_profile"]["type"] == "string"
        assert "model_profile" not in fn["parameters"]["required"]


class TestModelProfileOverride:
    """F6/F7/F8/F9 — delegate.py's side of the named-model request."""

    async def test_overridden_reply_names_resolved_model(self):
        agents = {"developer": FakeSubAgent(
            "developer", result="done", override_model="claude-fable-5")}
        _, handler = build_delegate_tool(agents)
        result = await handler({
            "agent_name": "developer", "task": "research radar",
            "model_profile": "fable",
        })
        assert result == "done\n[ran on claude-fable-5]"
        # The override was passed through to SubAgent.run() itself.
        assert agents["developer"].run_kwargs[-1]["model_profile_override"] == "fable"

    async def test_no_model_profile_no_suffix(self):
        agents = {"developer": FakeSubAgent("developer", result="done")}
        _, handler = build_delegate_tool(agents)
        result = await handler({"agent_name": "developer", "task": "research radar"})
        assert result == "done"
        assert agents["developer"].run_kwargs[-1]["model_profile_override"] is None

    async def test_unresolvable_override_refuses_before_any_run_row(self):
        """F7: an unresolvable named request refuses immediately — no
        delegate_start event, no run row, agent.run() never called."""
        agents = {"developer": FakeSubAgent(
            "developer", override_refused=(
                "model profile 'fable' could not be resolved "
                "(ANTHROPIC_API_KEY is unset)"
            ),
        )}
        events = []
        _, handler = build_delegate_tool(agents, on_event=events.append)
        result = await handler({
            "agent_name": "developer", "task": "research radar",
            "model_profile": "fable",
        })
        assert result.startswith("REFUSED:")
        assert "fable" in result
        assert events == []  # no delegate_start fired
        assert agents["developer"].tasks == []  # run() never called

    async def test_delegate_start_shows_override_model_never_as_fallback(self):
        """F8: an explicit override is never reported as a 'fallback' —
        it was requested, not defaulted into."""
        agents = {"developer": FakeSubAgent(
            "developer", model="or-codex-max", model_is_fallback=False,
            override_model="claude-fable-5",
        )}
        events = []
        _, handler = build_delegate_tool(agents, on_event=events.append)
        await handler({
            "agent_name": "developer", "task": "research radar",
            "model_profile": "fable",
        })
        assert events[0]["type"] == "delegate_start"
        assert events[0]["model"] == "claude-fable-5"
        assert events[0]["model_fallback"] is False


class TestHandler:
    async def test_routes_to_named_agent_and_returns_result(self):
        agents = {**AGENTS}
        _, handler = build_delegate_tool(agents)
        result = await handler({"agent_name": "scheduler", "task": "set alarm"})
        assert result == "done"
        assert agents["scheduler"].tasks == ["set alarm"]

    async def test_unknown_agent_returns_plain_error(self):
        _, handler = build_delegate_tool(AGENTS)
        result = await handler({"agent_name": "chef", "task": "cook"})
        assert result == ("Unknown agent 'chef'. Available: "
                          "scheduler, librarian, analyst, systems, developer.")

    async def test_events_forwarded(self):
        events = []
        _, handler = build_delegate_tool(AGENTS, on_event=events.append)
        await handler({"agent_name": "analyst", "task": "weather"})
        types = [e["type"] for e in events]
        assert types[0] == "delegate_start"
        assert types[-1] == "delegate_done"
        assert events[0]["agent"] == "analyst"

    async def test_protected_workload_task_is_redacted_only_on_status_event(self):
        """Confidential prompts may reach the specialist, never the UI/stdout
        activity event that announces the delegation."""
        events = []
        agents = {"librarian": FakeSubAgent("librarian")}
        _, handler = build_delegate_tool(agents, on_event=events.append)
        private_task = "read the private customer record: SSN 123-45-6789"
        await handler({"agent_name": "librarian", "task": private_task})

        assert agents["librarian"].tasks == [private_task]
        assert events[0]["task"] == "<protected task>"

    async def test_protected_failure_detail_is_redacted_on_status_event(self):
        agents = {"librarian": FakeSubAgent(
            "librarian", result="FAILED: private document contents leaked here")}
        events = []
        _, handler = build_delegate_tool(agents, on_event=events.append)
        result = await handler({"agent_name": "librarian", "task": "inspect private file"})

        assert result.startswith("FAILED:")
        assert events[-1]["detail"] == "<protected task>"

    async def test_delegate_start_carries_the_resolved_model(self):
        """Larry 2026-08-19 — the Agents tab card header shows which LLM
        is doing the work. It can only show what delegate_start carries."""
        events = []
        _, handler = build_delegate_tool(AGENTS, on_event=events.append)
        await handler({"agent_name": "analyst", "task": "weather"})
        assert events[0]["model"] == "fake-model"
        assert events[0]["model_fallback"] is False

    async def test_a_model_profile_fallback_is_carried_not_hidden(self):
        """A profile that failed to resolve must reach the UI as a
        fallback. Reporting the configured name, or reporting nothing,
        would make a misconfiguration look like a deliberate assignment —
        the same reason RunLogger records the resolved model."""
        agents = {"analyst": FakeSubAgent(
            "analyst", model="voice-model", model_is_fallback=True)}
        events = []
        _, handler = build_delegate_tool(agents, on_event=events.append)
        await handler({"agent_name": "analyst", "task": "weather"})
        assert events[0]["model"] == "voice-model"
        assert events[0]["model_fallback"] is True

    async def test_delegate_done_marks_success(self):
        events = []
        _, handler = build_delegate_tool(AGENTS, on_event=events.append)
        await handler({"agent_name": "analyst", "task": "weather"})
        done = events[-1]
        assert done["ok"] is True
        assert done["detail"] == ""

    async def test_delegate_done_marks_failure_with_detail(self):
        agents = {"analyst": FakeSubAgent("analyst", result="FAILED: web_search down")}
        events = []
        _, handler = build_delegate_tool(agents, on_event=events.append)
        result = await handler({"agent_name": "analyst", "task": "news"})
        assert result.startswith("FAILED:")
        done = events[-1]
        assert done["type"] == "delegate_done"
        assert done["ok"] is False
        assert done["detail"] == "FAILED: web_search down"


class TestParallelDelegation:
    """Plan Phase 4: two independent delegations run concurrently, a
    failure in one does not affect the other, and max_parallel is a real
    cap — not just documentation."""

    async def test_two_independent_delegations_overlap_in_time(self):
        """If calls ran serially, total wall time would be >= 2x delay.
        Run concurrently (via asyncio.gather, as pipecat's own parallel
        tool-call dispatch does), total wall time should stay close to a
        single delay."""
        agents = {
            "scheduler": SlowFakeSubAgent("scheduler", delay=0.08),
            "analyst": SlowFakeSubAgent("analyst", delay=0.08),
        }
        _, handler = build_delegate_tool(agents, max_parallel=3)

        start = time.perf_counter()
        results = await asyncio.gather(
            handler({"agent_name": "scheduler", "task": "remind me"}),
            handler({"agent_name": "analyst", "task": "weather"}),
        )
        elapsed = time.perf_counter() - start

        assert results == ["done", "done"]
        # Serial would take ~0.16s; concurrent should be well under that.
        assert elapsed < 0.15, f"expected overlap, took {elapsed:.3f}s"

        # Both agents were actually in flight at the same time.
        sched, analyst = agents["scheduler"], agents["analyst"]
        assert sched.started_at < analyst.finished_at
        assert analyst.started_at < sched.finished_at

    async def test_one_failure_does_not_affect_sibling(self):
        """SubAgent.run() never raises (failures come back as 'FAILED:
        ...' strings), and each delegation is independent — a failing
        sibling must not cancel or corrupt the other's result."""
        agents = {
            "scheduler": SlowFakeSubAgent("scheduler", delay=0.02, result="done"),
            "analyst": SlowFakeSubAgent(
                "analyst", delay=0.02, result="FAILED: web_search down"
            ),
        }
        events = []
        _, handler = build_delegate_tool(
            agents, on_event=events.append, max_parallel=3
        )

        sched_result, analyst_result = await asyncio.gather(
            handler({"agent_name": "scheduler", "task": "remind me"}),
            handler({"agent_name": "analyst", "task": "news"}),
        )

        assert sched_result == "done"
        assert analyst_result == "FAILED: web_search down"

        done_events = {e["agent"]: e for e in events if e["type"] == "delegate_done"}
        assert done_events["scheduler"]["ok"] is True
        assert done_events["analyst"]["ok"] is False

    async def test_max_parallel_caps_concurrent_execution(self):
        """With max_parallel=1, three delegations must run strictly
        serially even though they're all launched at once — proves the
        semaphore, not just pipecat's own dispatch, is what's bounding it."""
        agents = {
            "scheduler": SlowFakeSubAgent("scheduler", delay=0.05),
            "librarian": SlowFakeSubAgent("librarian", delay=0.05),
            "analyst": SlowFakeSubAgent("analyst", delay=0.05),
        }
        _, handler = build_delegate_tool(agents, max_parallel=1)

        start = time.perf_counter()
        await asyncio.gather(
            handler({"agent_name": "scheduler", "task": "a"}),
            handler({"agent_name": "librarian", "task": "b"}),
            handler({"agent_name": "analyst", "task": "c"}),
        )
        elapsed = time.perf_counter() - start

        # Capped to 1 at a time: ~3x a single delay, not ~1x.
        assert elapsed >= 0.14, f"expected serial execution, took {elapsed:.3f}s"

    async def test_max_parallel_allows_bounded_concurrency(self):
        """With max_parallel=2, two of three delegations should overlap
        (faster than fully serial) while still being capped (slower than
        fully unbounded)."""
        agents = {
            "scheduler": SlowFakeSubAgent("scheduler", delay=0.05),
            "librarian": SlowFakeSubAgent("librarian", delay=0.05),
            "analyst": SlowFakeSubAgent("analyst", delay=0.05),
        }
        _, handler = build_delegate_tool(agents, max_parallel=2)

        start = time.perf_counter()
        await asyncio.gather(
            handler({"agent_name": "scheduler", "task": "a"}),
            handler({"agent_name": "librarian", "task": "b"}),
            handler({"agent_name": "analyst", "task": "c"}),
        )
        elapsed = time.perf_counter() - start

        # Two batches of ~0.05s (2 concurrent, then 1) — well under fully
        # serial (~0.15s), well over fully unbounded (~0.05s).
        assert 0.08 <= elapsed < 0.14, f"expected 2-wide batching, took {elapsed:.3f}s"

    async def test_default_max_parallel_matches_config_default(self):
        """DEFAULT_MAX_PARALLEL_DELEGATIONS must match
        Settings.jarvis_max_parallel_delegations's default so the two
        stay in sync without every caller having to pass it explicitly."""
        from jarvis.agents.delegate import DEFAULT_MAX_PARALLEL_DELEGATIONS
        from jarvis.config import Settings

        default_settings = Settings(
            openai_api_key="x", deepgram_api_key="x", elevenlabs_api_key="x"
        )
        assert (
            DEFAULT_MAX_PARALLEL_DELEGATIONS
            == default_settings.jarvis_max_parallel_delegations
        )


class TestAgentsYaml:
    def test_repo_agents_yaml_matches_locked_schema(self):
        from pathlib import Path

        path = (Path(__file__).resolve().parents[2]
                / "config" / "agents.yaml")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        entries = data["sub_agents"]
        # 2026-09-06: app_builder split out of developer, appended so the
        # existing five keep their order (config/agents.yaml is read in file
        # order and the star layout's angular order follows it).
        assert [e["name"] for e in entries] == [
            "scheduler", "librarian", "analyst", "systems", "developer",
            "app_builder"]
        for e in entries:
            assert e["display_name"] and e["description"]
            assert e["mcp_servers"], e["name"]
        # Larry 2026-08-21: every agent carries mcp-screen now.
        assert entries[0]["mcp_servers"] == [
            "mcp-time", "mcp-reminders", "mcp-screen"]

    def test_catalog_rendering_format(self):
        catalog = render_agent_catalog([
            {"name": "scheduler", "display_name": "Scheduler",
             "description": "Time stuff."}])
        assert catalog == "- scheduler (Scheduler): Time stuff."


# MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md A2 — the mechanical
# retry guard: a same-shaped retry within the window after a failure is
# refused without running; a genuinely different task, or one arriving
# after the window, or a retry after a SUCCESS, all pass through.
class TestRetryGuard:
    async def test_reworded_retry_refused_after_failure(self):
        agents = {"developer": FakeSubAgent("developer", result="FAILED: boom")}
        _, handler = build_delegate_tool(agents)
        first = await handler({
            "agent_name": "developer",
            "task": "find the upper left updates display component and add a close button",
        })
        assert first == "FAILED: boom"
        second = await handler({
            "agent_name": "developer",
            "task": "locate the upper left status panel and add a dismiss button to it",
        })
        assert second.startswith("REFUSED:")
        assert "developer" in second
        # The agent must not have actually been invoked a second time.
        assert agents["developer"].tasks == [
            "find the upper left updates display component and add a close button",
        ]

    async def test_unrelated_task_not_refused(self):
        """Low-overlap wording passes the guard — the agent actually runs
        (and returns its scripted result, whatever that is) rather than
        being refused mechanically."""
        agents = {"developer": FakeSubAgent("developer", result="FAILED: boom")}
        _, handler = build_delegate_tool(agents)
        await handler({"agent_name": "developer", "task": "find the upper left status panel"})
        result = await handler({"agent_name": "developer", "task": "show me the last five commits"})
        assert result == "FAILED: boom"  # ran again — not "REFUSED: ..."
        assert len(agents["developer"].tasks) == 2

    async def test_guard_clears_after_success(self):
        """A low-overlap task that SUCCEEDS clears the guard, so a later
        retry of the ORIGINAL failed wording is no longer refused."""
        calls = {"n": 0}

        class FlakySubAgent(FakeSubAgent):
            async def run(self, task, on_event=None, **kwargs):
                calls["n"] += 1
                self.tasks.append(task)
                return self.result

        agents = {"developer": FlakySubAgent("developer", result="FAILED: boom")}
        _, handler = build_delegate_tool(agents)
        first = await handler({"agent_name": "developer", "task": "add a dismiss button"})
        assert first == "FAILED: boom"
        agents["developer"].result = "done"
        second = await handler({"agent_name": "developer", "task": "show me the last five commits"})
        assert second == "done"  # unrelated wording, not refused, and it succeeded
        # The guard was cleared by that success — a retry of the ORIGINAL
        # failed wording now runs instead of being refused.
        third = await handler({"agent_name": "developer", "task": "add a dismiss button"})
        assert third == "done"
        assert calls["n"] == 3

    async def test_window_expiry_allows_retry(self, monkeypatch):
        import jarvis.agents.delegate as delegate_module
        agents = {"developer": FakeSubAgent("developer", result="FAILED: boom")}
        _, handler = build_delegate_tool(agents)
        clock = {"t": 1000.0}
        monkeypatch.setattr(delegate_module.time, "monotonic", lambda: clock["t"])
        await handler({"agent_name": "developer", "task": "add a dismiss button"})
        clock["t"] += RETRY_GUARD_WINDOW_S + 1
        result = await handler({"agent_name": "developer", "task": "add a dismiss button"})
        # Same wording, but the window expired — not refused (agent ran,
        # returning its scripted FAILED result rather than REFUSED).
        assert result == "FAILED: boom"

    async def test_different_agent_not_guarded_by_another_agents_failure(self):
        agents = {
            "developer": FakeSubAgent("developer", result="FAILED: boom"),
            "analyst": FakeSubAgent("analyst", result="done"),
        }
        _, handler = build_delegate_tool(agents)
        await handler({"agent_name": "developer", "task": "add a dismiss button"})
        result = await handler({"agent_name": "analyst", "task": "add a dismiss button"})
        assert result == "done"


class TestRetryGuardInputSubstitution:
    """T1.1 (2026-09-22): a single-word correction is new input, not a
    reworded retry. The Alfreda/Alpharetta tasks are the exact ones the
    guard refused live at 21:53 (delegate_retry_guard_refused overlap=0.75)."""

    FAILED = "Get current weather for Alfreda, Georgia."

    async def _fail_then(self, second_task, monkeypatch=None):
        agents = {"analyst": FakeSubAgent("analyst", result="FAILED: no such place")}
        _, handler = build_delegate_tool(agents)
        assert await handler({"agent_name": "analyst", "task": self.FAILED}) == "FAILED: no such place"
        return agents, await handler({"agent_name": "analyst", "task": second_task})

    async def test_corrected_place_name_is_not_a_retry(self):
        agents, second = await self._fail_then("Get current weather for Alpharetta, Georgia.")
        assert not second.startswith("REFUSED:")
        assert len(agents["analyst"].tasks) == 2

    async def test_longer_corrected_request_is_not_a_retry(self):
        agents, second = await self._fail_then(
            "Retrieve current weather conditions for Alpharetta in Fulton County, "
            "Georgia, including temperature, conditions, humidity")
        assert not second.startswith("REFUSED:")
        assert len(agents["analyst"].tasks) == 2

    async def test_superset_rewording_is_still_refused(self):
        agents, second = await self._fail_then("Get current weather for Alfreda, Georgia, try harder")
        assert second.startswith("REFUSED:")
        assert len(agents["analyst"].tasks) == 1

    def test_multi_word_rewording_is_not_a_substitution(self):
        from jarvis.agents.delegate import _is_input_substitution
        from jarvis.procedures import _tokens
        failed = _tokens("find the upper left updates display component and add a close button")
        new = _tokens("locate the upper left status panel and add a dismiss button to it")
        assert _is_input_substitution(failed, new) is False

    async def test_substitution_exemption_kill_switch(self, monkeypatch):
        monkeypatch.setenv("JARVIS_RETRY_GUARD_SUBSTITUTION_ENABLED", "false")
        agents, second = await self._fail_then("Get current weather for Alpharetta, Georgia.")
        assert second.startswith("REFUSED:")

    async def test_refusal_forbids_telling_user_to_wait(self):
        _, second = await self._fail_then("Get current weather for Alfreda, Georgia, try harder")
        assert "Never tell the user to wait" in second


class TestMissingTool:
    """T1.2 (2026-09-22): MISSING-TOOL is a capability gap, not a failed
    approach and not a question for the user."""

    GAP = "FAILED: MISSING-TOOL: read live provider model catalogs"

    async def test_missing_tool_does_not_arm_the_guard(self):
        agents = {"developer": FakeSubAgent("developer", result=self.GAP)}
        _, handler = build_delegate_tool(agents)
        await handler({"agent_name": "developer", "task": "list the models openrouter offers today"})
        second = await handler({"agent_name": "developer", "task": "list the models openrouter offers now please"})
        assert not second.startswith("REFUSED:")
        assert len(agents["developer"].tasks) == 2

    async def test_missing_tool_note_appended(self):
        agents = {"developer": FakeSubAgent("developer", result=self.GAP)}
        _, handler = build_delegate_tool(agents)
        result = await handler({"agent_name": "developer", "task": "list openrouter models"})
        assert result.startswith(self.GAP)
        assert "no tool for this" in result
        assert "Do not show or speak commands" in result

    async def test_missing_tool_is_not_awaiting_user(self, caplog):
        """A continuation claim after MISSING-TOOL is unearned: nothing was
        asked of the user, so it must not be honoured as a handoff."""
        import logging
        agents = {"developer": FakeSubAgent(
            "developer", result="NEEDS-INPUT: MISSING-TOOL: read the vault")}
        _, handler = build_delegate_tool(agents)
        await handler({"agent_name": "developer", "task": "read the vault key list"})
        with caplog.at_level(logging.INFO, logger="jarvis.agents.delegate"):
            await handler({"agent_name": "developer", "task": "read the vault key list",
                           "continuation": True})
        assert "delegate_continuation_unearned" in caplog.text
        assert "delegate_continuation agent=" not in caplog.text


class TestRetryGuardSharedIdentifierExemption:
    """2026-08-25 — a live incident (staging_id 469bff19ef49) showed the
    guard refusing the LEGITIMATE confirm-half of a two-phase flow: a
    preview call failed for an expected, benign reason, and the very next
    call — confirming and starting that same staged edit — necessarily
    shares most of its wording (same files, same goal, same staging_id)
    and scored well above RETRY_GUARD_OVERLAP. A shared long identifier
    (staging_id, commit hash) is the signal that distinguishes "same
    in-flight thing being confirmed" from an actual reworded retry."""

    async def test_shared_staging_id_exempts_high_overlap_from_refusal(self):
        agents = {"developer": FakeSubAgent(
            "developer", result="FAILED: nothing to preview yet",
        )}
        _, handler = build_delegate_tool(agents)
        first = await handler({
            "agent_name": "developer",
            "task": "preview self-edit staging_id 469bff19ef49 for the "
                    "drawer glass fix",
        })
        assert first == "FAILED: nothing to preview yet"
        agents["developer"].result = "started"
        second = await handler({
            "agent_name": "developer",
            "task": "confirm and start self-edit staging_id 469bff19ef49 "
                    "for the drawer glass fix",
        })
        # High wording overlap, but the shared 12-char staging_id exempts
        # it — the agent actually ran rather than being refused.
        assert second == "started"
        assert len(agents["developer"].tasks) == 2

    @pytest.mark.parametrize("word", [
        "implement", "component", "refactor", "configuration", "investigate",
    ])
    async def test_shared_long_english_word_does_not_exempt(self, word):
        """The first cut of this exemption keyed on LENGTH ALONE, which
        broke the guard rather than narrowing it: ordinary developer
        wording shares 8+ char English words constantly, so a reworded
        retry containing any of these sailed straight through. The digit
        requirement is what makes the carve-out narrow — no English word
        has one, an identifier essentially always does."""
        agents = {"developer": FakeSubAgent("developer", result="FAILED: boom")}
        _, handler = build_delegate_tool(agents)
        await handler({
            "agent_name": "developer",
            "task": f"{word} the drawer translucency change per the plan",
        })
        second = await handler({
            "agent_name": "developer",
            "task": f"{word} the drawer transparency update per the plan",
        })
        assert second.startswith("REFUSED:")
        assert len(agents["developer"].tasks) == 1

    async def test_short_or_digitless_token_does_not_exempt(self):
        """A 7-char short git hash is below the length floor, and a
        digit-free token is not identifier-shaped — both fall back to the
        pre-existing refusal, which is the safe direction."""
        from jarvis.agents.delegate import _shares_long_identifier
        assert not _shares_long_identifier({"88d58bc"}, {"88d58bc"})   # 7 chars
        assert not _shares_long_identifier({"abcdefgh"}, {"abcdefgh"})  # no digit
        assert _shares_long_identifier({"469bff19ef49"}, {"469bff19ef49"})
        assert _shares_long_identifier({"a2af4494"}, {"a2af4494"})

    async def test_high_overlap_without_shared_id_still_refused(self):
        """The exemption must not swallow the original guard: ordinary
        reworded retries with no shared long identifier are still
        refused."""
        agents = {"developer": FakeSubAgent("developer", result="FAILED: boom")}
        _, handler = build_delegate_tool(agents)
        await handler({
            "agent_name": "developer",
            "task": "find the upper left updates display component and add a close button",
        })
        second = await handler({
            "agent_name": "developer",
            "task": "locate the upper left status panel and add a dismiss button to it",
        })
        assert second.startswith("REFUSED:")

    async def test_refused_message_disclaims_expiry_and_validity(self):
        """2026-08-25 — the Supervisor once fabricated 'the staging ID is
        expired or invalid' from a REFUSED message that said no such
        thing. The message must explicitly disclaim that class of cause
        so a paraphrase can't reintroduce it."""
        agents = {"developer": FakeSubAgent("developer", result="FAILED: boom")}
        _, handler = build_delegate_tool(agents)
        await handler({
            "agent_name": "developer",
            "task": "find the upper left updates display component and add a close button",
        })
        second = await handler({
            "agent_name": "developer",
            "task": "locate the upper left status panel and add a dismiss button to it",
        })
        assert second.startswith("REFUSED:")
        assert "safety guard" in second
        assert "NOTHING about any ID" in second
        assert "expired" in second and "invalid" in second


# --- MORTIMER_HANDOFF_LOOP_PLAN.md H1 -------------------------------------


class ScriptedAgent:
    """Returns a queued reply per call, so a test can drive a multi-run
    handoff conversation."""

    def __init__(self, name, replies):
        self.name = name
        self.display_name = name.title()
        self.description = f"{name} things."
        self.mcp_servers = []
        self.replies = list(replies)
        self.tasks = []

    async def run(self, task, on_event=None, **kwargs):
        self.tasks.append(task)
        return self.replies.pop(0) if self.replies else "done"


EXHAUSTED = (
    "FAILED: ran out of tool-call rounds (15 of 15) before finishing. "
    "Nothing was blocked — the work was incomplete, not refused."
)


def _tool(agent):
    schema, handler = build_delegate_tool({agent.name: agent})
    return schema, handler


class TestExhaustedDoesNotArmTheGuard:
    """H1.1 — an exhausted budget is an unfinished job, not a failed
    approach. Arming the guard on it refuses the one thing that should
    happen next: continuing where it stopped."""

    async def test_exhausted_run_allows_an_immediate_follow_up(self):
        agent = ScriptedAgent("developer", [EXHAUSTED, "found it"])
        _, handler = _tool(agent)
        first = await handler({"agent_name": "developer",
                               "task": "investigate the weather chip staleness"})
        assert first.startswith("FAILED: ran out of tool-call rounds")
        second = await handler({"agent_name": "developer",
                                "task": "investigate the weather chip staleness"})
        assert second == "found it"          # not REFUSED
        assert len(agent.tasks) == 2

    async def test_a_real_failure_still_arms_the_guard(self):
        """The original defect must stay fixed: a reworded retry after a
        genuine failure is still refused."""
        agent = ScriptedAgent("developer", ["FAILED: the API key is invalid", "x"])
        _, handler = _tool(agent)
        await handler({"agent_name": "developer", "task": "read the weather config file"})
        again = await handler({"agent_name": "developer",
                               "task": "read the weather config file please"})
        assert again.startswith("REFUSED:")


class TestContinuationMustBeEarned:
    """H1.2 — the reset is earned by a RECORDED handoff, not claimed by a
    flag. Unlimited reset plus a self-declared marker would be infinite
    guard-free retries, which is what the guard exists to prevent."""

    async def test_claiming_continuation_without_a_handoff_is_refused(self):
        agent = ScriptedAgent("developer", ["FAILED: the API key is invalid", "x"])
        _, handler = _tool(agent)
        await handler({"agent_name": "developer", "task": "read the weather config file"})
        again = await handler({"agent_name": "developer",
                               "task": "read the weather config file",
                               "continuation": True})
        assert again.startswith("REFUSED:")

    async def test_continuation_after_a_real_handoff_is_allowed(self):
        agent = ScriptedAgent("developer", [
            "FAILED: NEEDS-INPUT: run `curl localhost:7861/api/ambient` and tell me the source field",
            "the source field proves it",
        ])
        _, handler = _tool(agent)
        first = await handler({"agent_name": "developer",
                               "task": "find why the weather chip is wrong"})
        assert "NEEDS-INPUT:" in first
        second = await handler({"agent_name": "developer",
                                "task": "find why the weather chip is wrong; source is weather.gov",
                                "continuation": True})
        assert second == "the source field proves it"

    async def test_the_refusal_message_teaches_the_way_forward(self):
        agent = ScriptedAgent("developer", ["FAILED: nope", "x"])
        _, handler = _tool(agent)
        await handler({"agent_name": "developer", "task": "check the weather config"})
        msg = await handler({"agent_name": "developer", "task": "check the weather config"})
        assert "continuation" in msg
        assert "not a retry" in msg


class TestHandoffDepth:
    """H1.4 — visible, never capped. A cap is quitting on a timer, which
    is the behaviour this plan exists to remove."""

    async def test_notice_appears_only_after_repeated_handoffs(self):
        from jarvis.agents.delegate import HANDOFF_DEPTH_NOTICE

        asks = [f"NEEDS-INPUT: run command {i}" for i in range(HANDOFF_DEPTH_NOTICE + 2)]
        agent = ScriptedAgent("developer", asks)
        _, handler = _tool(agent)

        first = await handler({"agent_name": "developer", "task": "investigate the thing"})
        assert "handoff" not in first.lower() or "This is handoff" not in first

        last = first
        for _ in range(HANDOFF_DEPTH_NOTICE):
            last = await handler({"agent_name": "developer",
                                  "task": "investigate the thing, here is the output",
                                  "continuation": True})
        assert "This is handoff" in last
        assert "what you still do not know" in last

    async def test_there_is_no_cap(self):
        """Ten handoffs must all be allowed — the notice is guidance."""
        agent = ScriptedAgent("developer", [f"NEEDS-INPUT: step {i}" for i in range(12)])
        _, handler = _tool(agent)
        await handler({"agent_name": "developer", "task": "long investigation"})
        for _ in range(10):
            out = await handler({"agent_name": "developer",
                                 "task": "long investigation, more output",
                                 "continuation": True})
            assert not out.startswith("REFUSED:")

    async def test_a_resolved_run_resets_the_depth(self):
        agent = ScriptedAgent("developer", [
            "NEEDS-INPUT: run this", "all done — no further input needed",
            "NEEDS-INPUT: a new investigation",
        ])
        _, handler = _tool(agent)
        await handler({"agent_name": "developer", "task": "first investigation"})
        await handler({"agent_name": "developer", "task": "first investigation, output",
                       "continuation": True})
        third = await handler({"agent_name": "developer", "task": "second investigation"})
        assert "This is handoff" not in third


class TestFindingsCarryForward:
    """H2.2 — a reset that hands back 15 rounds is only progress if those
    rounds start where the last one stopped."""

    async def test_findings_are_prepended_to_the_task(self, monkeypatch):
        """Patch the real reader: _read_findings goes through mcp_repo so
        path confinement and the secret deny-list apply to an
        agent-supplied path too."""
        from mcp_servers.mcp_repo import logic as repo_logic

        monkeypatch.setattr(
            repo_logic, "repo_read_file",
            lambda path, **kw: {"content": "The temperature comes from periods[0]."})

        agent = ScriptedAgent("developer", ["NEEDS-INPUT: run it", "done"])
        _, handler = _tool(agent)
        await handler({"agent_name": "developer", "task": "investigate"})
        await handler({"agent_name": "developer", "task": "here is the output",
                       "continuation": True,
                       "findings_path": "docs/findings/x.md"})
        assert "periods[0]" in agent.tasks[1]
        assert "continue from here rather than starting over" in agent.tasks[1]

    async def test_an_unreadable_findings_path_refuses_rather_than_silently_continuing(self):
        agent = ScriptedAgent("developer", ["NEEDS-INPUT: run it", "done"])
        _, handler = _tool(agent)
        await handler({"agent_name": "developer", "task": "investigate"})
        out = await handler({"agent_name": "developer", "task": "here is the output",
                             "continuation": True,
                             "findings_path": "does/not/exist.md"})
        assert out.startswith("REFUSED:")
        assert "without them" in out
        assert len(agent.tasks) == 1        # the run never happened


class TestBargeInSurvival:
    """Larry 2026-08-21: "me continuing to talk should not kill existing
    work." Observed live: pipecat cancels the delegate_task function call
    on user interruption, which killed 5 of 9 developer runs mid-flight —
    one AFTER its repo write had executed — leaving zombie 'running' rows
    and no spoken result. The handler now shields a detached task: the
    voice turn's cancellation lands, the work finishes anyway, and the
    result is delivered through the late_delivery hook."""

    async def test_cancelling_the_handler_does_not_cancel_the_work(self):
        agent = SlowFakeSubAgent("developer", delay=0.05, result="done late")
        delivered: list[str] = []

        async def deliver(text):
            delivered.append(text)

        _, handler = build_delegate_tool(
            {"developer": agent}, late_delivery={"fn": deliver})
        turn = asyncio.create_task(
            handler({"agent_name": "developer", "task": "do the thing"}))
        await asyncio.sleep(0.01)  # let the run start
        turn.cancel()
        with pytest.raises(asyncio.CancelledError):
            await turn
        # The work survives the turn's death and finishes...
        await asyncio.sleep(0.1)
        assert agent.finished_at is not None
        # ...and the result reaches the conversation via the hook.
        assert len(delivered) == 1
        assert "done late" in delivered[0]
        assert "Background update" in delivered[0]
        # MORTIMER_SESSION_MISSES_PLAN.md S6 (belt-and-suspenders to the
        # LateResultNeutralizer): the note asks for ONE relay, explicitly.
        assert "Relay this to the user once" in delivered[0]
        assert "do not repeat it in later turns" in delivered[0]

    async def test_normal_completion_never_uses_late_delivery(self):
        agent = SlowFakeSubAgent("developer", delay=0.01, result="done now")
        delivered: list[str] = []

        async def deliver(text):
            delivered.append(text)

        _, handler = build_delegate_tool(
            {"developer": agent}, late_delivery={"fn": deliver})
        result = await handler(
            {"agent_name": "developer", "task": "do the thing"})
        assert result == "done now"
        await asyncio.sleep(0.05)
        assert delivered == []

    async def test_bookkeeping_still_runs_on_the_orphaned_path(self):
        """delegate_done must fire from the detached task so the Agents
        card resolves instead of showing 'running' forever — the zombie
        symptom this exists to kill."""
        agent = SlowFakeSubAgent("developer", delay=0.05, result="done late")
        events: list[dict] = []
        _, handler = build_delegate_tool(
            {"developer": agent}, on_event=events.append,
            late_delivery={"fn": lambda t: asyncio.sleep(0)})
        turn = asyncio.create_task(
            handler({"agent_name": "developer", "task": "do the thing"}))
        await asyncio.sleep(0.01)
        turn.cancel()
        with pytest.raises(asyncio.CancelledError):
            await turn
        await asyncio.sleep(0.1)
        types = [e["type"] for e in events]
        assert "delegate_start" in types
        assert "delegate_done" in types

    async def test_no_hook_installed_is_logged_not_raised(self):
        """A missing late_delivery hook must not take down anything —
        the run still completes and finalizes."""
        agent = SlowFakeSubAgent("developer", delay=0.05, result="done late")
        _, handler = build_delegate_tool({"developer": agent})
        turn = asyncio.create_task(
            handler({"agent_name": "developer", "task": "do the thing"}))
        await asyncio.sleep(0.01)
        turn.cancel()
        with pytest.raises(asyncio.CancelledError):
            await turn
        await asyncio.sleep(0.1)
        assert agent.finished_at is not None


class TestNoticeOutbox:
    """Status spec T3.2 (L12): a late result nobody can hear now — no hook,
    or a hook whose session has ended (inject_late_result returns False) —
    goes to the notice outbox instead of being lost (fact 3.5)."""

    @pytest.fixture
    def outbox(self, monkeypatch):
        calls: list[tuple[str, str]] = []

        def record(source, text):
            calls.append((source, text))
            return len(calls)

        monkeypatch.setattr("jarvis.agents.delegate._to_outbox", record)
        return calls

    @staticmethod
    async def _orphan(handler, task="do the thing"):
        turn = asyncio.create_task(handler({"agent_name": "developer", "task": task}))
        await asyncio.sleep(0.01)
        turn.cancel()
        with pytest.raises(asyncio.CancelledError):
            await turn
        await asyncio.sleep(0.1)

    async def test_undeliverable_late_result_goes_to_outbox(self, outbox, caplog):
        agent = SlowFakeSubAgent("developer", delay=0.05, result="audit: 3 findings")
        _, handler = build_delegate_tool({"developer": agent})     # no hook
        with caplog.at_level("INFO", logger="jarvis.agents.delegate"):
            await self._orphan(handler)
        assert len(outbox) == 1
        source, text = outbox[0]
        assert source == "Developer"
        assert "Background update" in text and "audit: 3 findings" in text
        assert "delegate_late_result_undeliverable" in caplog.text, "the log line stays"

    async def test_dead_session_hook_returning_false_goes_to_outbox(self, outbox):
        agent = SlowFakeSubAgent("developer", delay=0.05, result="audit: 3 findings")
        offered: list[str] = []

        async def dead_hook(text):
            offered.append(text)
            return False                        # runtime.alive is False

        _, handler = build_delegate_tool(
            {"developer": agent}, late_delivery={"fn": dead_hook})
        await self._orphan(handler)
        assert len(offered) == 1
        assert outbox == [("Developer", offered[0])]

    @pytest.mark.parametrize("returned", [True, None])
    async def test_a_delivered_result_is_not_outboxed(self, outbox, returned):
        agent = SlowFakeSubAgent("developer", delay=0.05, result="done late")

        async def live_hook(text):
            return returned

        _, handler = build_delegate_tool(
            {"developer": agent}, late_delivery={"fn": live_hook})
        await self._orphan(handler)
        assert outbox == []

    async def test_a_hook_that_raises_goes_to_outbox(self, outbox):
        agent = SlowFakeSubAgent("developer", delay=0.05, result="done late")

        async def broken_hook(text):
            raise RuntimeError("pipeline gone")

        _, handler = build_delegate_tool(
            {"developer": agent}, late_delivery={"fn": broken_hook})
        await self._orphan(handler)
        assert len(outbox) == 1 and "done late" in outbox[0][1]

    async def test_sensitive_late_result_is_redacted_in_outbox(self, outbox):
        from jarvis.agents.delegate import SENSITIVE_LATE_NOTICE
        from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn

        agent = SlowFakeSubAgent("developer", delay=0.05,
                                 result="balance is 12,345.67 in account 9876")

        async def dead_hook(text):
            return False

        _, handler = build_delegate_tool(
            {"developer": agent}, late_delivery={"fn": dead_hook})
        holder = SensitiveTurn()
        holder.arm("financial")
        token = current_sensitive_turn.set(holder)
        try:
            await self._orphan(handler)
        finally:
            current_sensitive_turn.reset(token)
        assert outbox == [("Developer", SENSITIVE_LATE_NOTICE)]
        assert SENSITIVE_LATE_NOTICE == (
            "A background task you asked for finished; ask me for its result.")

    async def test_outboxed_result_reaches_the_notices_table(self, fresh_db, monkeypatch):
        """End to end through jarvis.notices, with the real table."""
        from functools import partial

        from jarvis import notices

        monkeypatch.setattr("jarvis.agents.delegate._to_outbox",
                            partial(notices.add_notice, "late_result"))
        agent = SlowFakeSubAgent("developer", delay=0.05, result="audit: 3 findings")
        _, handler = build_delegate_tool({"developer": agent})
        await self._orphan(handler)
        (item,) = notices.take_pending()
        assert item["kind"] == "late_result" and item["source"] == "Developer"
        assert "audit: 3 findings" in item["text"]


class TestKeyHealthNoteSuccess:
    """Status spec T3.3 — a run that did not fail recovers its agent's own
    credential verdict (keyhealth.note_success), except under a per-run
    model_profile override, which rode on a different credential."""

    @pytest.fixture
    def noted(self, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr("jarvis.keyhealth.note_success", calls.append)
        return calls

    @staticmethod
    def _agent(result="done"):
        agent = FakeSubAgent("developer", result=result)
        agent.api_key_env = "ANTHROPIC_API_KEY"
        return agent

    async def test_success_notes_the_agents_key(self, noted):
        _, handler = build_delegate_tool({"developer": self._agent()})
        await handler({"agent_name": "developer", "task": "read the file"})
        assert noted == ["ANTHROPIC_API_KEY"]

    async def test_failure_notes_nothing(self, noted):
        _, handler = build_delegate_tool({"developer": self._agent("FAILED: 401")})
        await handler({"agent_name": "developer", "task": "read the file"})
        assert noted == []

    async def test_override_notes_nothing(self, noted):
        _, handler = build_delegate_tool({"developer": self._agent()})
        await handler({"agent_name": "developer", "task": "read the file",
                       "model_profile": "fable"})
        assert noted == []

    async def test_a_fake_without_the_property_is_fine(self, noted):
        _, handler = build_delegate_tool({"developer": FakeSubAgent("developer")})
        assert await handler({"agent_name": "developer", "task": "x"}) == "done"
        assert noted == []

    async def test_the_real_verdict_recovers(self, monkeypatch):
        from jarvis import keyhealth

        keyhealth.reset_for_tests()
        monkeypatch.delenv(keyhealth.KILL_SWITCH_ENV, raising=False)
        with keyhealth._lock:
            keyhealth._verdicts["ANTHROPIC_API_KEY"] = "rejected"
        try:
            _, handler = build_delegate_tool({"developer": self._agent()})
            await handler({"agent_name": "developer", "task": "read the file"})
            assert keyhealth.verdict("ANTHROPIC_API_KEY") == "ok"
            assert keyhealth.detail("ANTHROPIC_API_KEY") == "recovered: a call succeeded"
        finally:
            keyhealth.reset_for_tests()


def test_subagent_exposes_api_key_env_read_only():
    from jarvis.agents.base import SubAgent

    prop = SubAgent.__dict__["api_key_env"]
    assert isinstance(prop, property) and prop.fset is None
