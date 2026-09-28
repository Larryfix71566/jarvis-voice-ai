from types import SimpleNamespace

import pytest

from jarvis.model_routing import SkillEvaluationLimits
from jarvis.skill_evaluation import (
    SkillEvaluationBudget,
    SkillEvaluationBudgetError,
    SkillEvaluationCase,
    load_skill_evaluation_cases,
    run_skill_evaluation,
    write_blinded_evaluation,
)


def _limits(**overrides):
    values = {
        "max_cases": 6,
        "repetitions": 2,
        "max_calls": 4,
        "max_calls_per_trial": 2,
        "deadline_seconds": 30,
        "max_input_tokens_per_call": 1000,
        "max_output_tokens_per_call": 500,
        "spend_ceiling_usd": 0.10,
    }
    values.update(overrides)
    return SkillEvaluationLimits(**values)


def _route(*, billing="provider_api"):
    return SimpleNamespace(
        workload="skill_eval",
        route=SimpleNamespace(billing=billing),
        provider="anthropic",
        model="claude-sonnet-test",
    )


def _frozen_writer_trials():
    from pathlib import Path

    from jarvis.skill_evaluation import load_skill_evaluation_fixture

    fixture_path = (Path(__file__).resolve().parents[1] / "fixtures"
                    / "skills_workspace" / "evaluations" / "skill-creator-v1.json")
    cases, fixture_digest = load_skill_evaluation_fixture(
        fixture_path, max_cases=6, expected_fixture_id="skill-creator-v1",
    )
    trials = tuple(
        SimpleNamespace(
            artifact_id=(
                f"opaque-{case_index:02d}-{repetition}-"
                f"{'w' if condition == 'with_skill' else 'b'}"
            ),
            case_id=case.case_id, repetition=repetition,
            review_criteria=case.review_criteria,
            text=f"Answer {case.case_id} {repetition} {condition}",
            condition=condition,
            result=SimpleNamespace(
                text="answer", tool_calls=(), prompt_tokens=10,
                completion_tokens=12, provider="anthropic", model="test-model",
                billing="subscription", route="subscription", duration_ms=5.0,
            ),
            reserved_cost_usd=0.0,
        )
        for case_index, case in enumerate(cases)
        for repetition in (1, 2)
        for condition in ("with_skill", "without_skill")
    )
    return fixture_digest, trials


def test_paid_budget_reserves_before_each_call_and_stops_at_ceiling():
    budget = SkillEvaluationBudget(
        _limits(), _route(), cost_estimator=lambda *_args: 0.06,
    )

    first = budget.reserve_call(
        "case-1-with-skill", input_token_upper_bound=900,
        output_token_upper_bound=400,
    )
    assert first.call_number == 1
    assert first.reserved_total_usd == pytest.approx(0.06)
    with pytest.raises(SkillEvaluationBudgetError, match="spend ceiling"):
        budget.reserve_call(
            "case-1-without-skill", input_token_upper_bound=900,
            output_token_upper_bound=400,
        )
    assert budget.calls_reserved == 1


def test_missing_price_blocks_paid_calls_without_consuming_budget():
    budget = SkillEvaluationBudget(
        _limits(), _route(), cost_estimator=lambda *_args: None,
    )
    with pytest.raises(SkillEvaluationBudgetError, match="price estimate"):
        budget.reserve_call(
            "case-1", input_token_upper_bound=100,
            output_token_upper_bound=50,
        )
    assert budget.calls_reserved == 0


def test_unexpected_pricing_failure_fails_closed():
    def broken_estimator(*_args):
        raise RuntimeError("pricing configuration could not be loaded")

    budget = SkillEvaluationBudget(
        _limits(), _route(), cost_estimator=broken_estimator,
    )
    with pytest.raises(SkillEvaluationBudgetError, match="price estimate"):
        budget.preflight_calls((("case-1", 100, 50),))
    assert budget.calls_reserved == 0
    with pytest.raises(SkillEvaluationBudgetError, match="price estimate"):
        budget.reserve_call(
            "case-1", input_token_upper_bound=100,
            output_token_upper_bound=50,
        )
    assert budget.calls_reserved == 0


def test_subscription_budget_enforces_calls_without_price_estimate():
    budget = SkillEvaluationBudget(
        _limits(max_calls=2, max_calls_per_trial=1, spend_ceiling_usd=None),
        _route(billing="subscription"),
        cost_estimator=lambda *_args: pytest.fail("subscription is not priced"),
    )
    budget.reserve_call(
        "case-a", input_token_upper_bound=100, output_token_upper_bound=50,
    )
    budget.reserve_call(
        "case-b", input_token_upper_bound=100, output_token_upper_bound=50,
    )
    with pytest.raises(SkillEvaluationBudgetError, match="call budget exhausted"):
        budget.reserve_call(
            "case-c", input_token_upper_bound=100, output_token_upper_bound=50,
        )


def test_per_trial_and_deadline_caps_are_fail_closed():
    now = [100.0]
    budget = SkillEvaluationBudget(
        _limits(max_calls=4, max_calls_per_trial=1, deadline_seconds=2),
        _route(billing="subscription"), clock=lambda: now[0],
    )
    budget.reserve_call(
        "same-trial", input_token_upper_bound=100, output_token_upper_bound=50,
    )
    with pytest.raises(SkillEvaluationBudgetError, match="trial call budget"):
        budget.reserve_call(
            "same-trial", input_token_upper_bound=100, output_token_upper_bound=50,
        )
    now[0] += 2
    with pytest.raises(SkillEvaluationBudgetError, match="deadline"):
        budget.reserve_call(
            "new-trial", input_token_upper_bound=100, output_token_upper_bound=50,
        )


@pytest.mark.parametrize(("input_bound", "output_bound"), [
    (1001, 10), (10, 501), (True, 10), (10, False),
])
def test_token_bounds_are_checked_before_reservation(input_bound, output_bound):
    budget = SkillEvaluationBudget(
        _limits(), _route(billing="subscription"),
    )
    with pytest.raises(SkillEvaluationBudgetError, match="token bound"):
        budget.reserve_call(
            "case", input_token_upper_bound=input_bound,
            output_token_upper_bound=output_bound,
        )
    assert budget.calls_reserved == 0


def test_usage_ledger_has_a_dedicated_skill_eval_rung():
    from jarvis.usage_ledger import RUNGS

    assert "skill_eval" in RUNGS


@pytest.mark.asyncio
async def test_runner_rejects_missing_or_forged_fixture_provenance_before_provider():
    from jarvis.skill_evaluation import FROZEN_SKILL_EVALUATION_FIXTURE_SHA256

    limits = _limits(max_cases=6, repetitions=1, max_calls=12,
                     max_calls_per_trial=1, spend_ceiling_usd=1.0)
    route = _route(billing="subscription")
    route.route.adapter = "openai_compatible"
    calls = []

    async def execute(*_args):
        calls.append(True)
        return SimpleNamespace(text="should not run", tool_calls=())

    custom_cases = (SkillEvaluationCase(
        "private-case", "PRIVATE_EVALUATION_INPUT_CANARY", ("criterion",),
    ),)
    base = {
        "skill_instructions": "reviewed instructions",
        "limits": limits,
        "route": route,
        "execute": execute,
    }
    with pytest.raises(ValueError, match="approved frozen fixture identity"):
        await run_skill_evaluation(custom_cases, **base)

    digest = FROZEN_SKILL_EVALUATION_FIXTURE_SHA256["skill-creator-v1"]
    with pytest.raises(ValueError, match="do not match the approved frozen fixture"):
        await run_skill_evaluation(
            custom_cases, fixture_id="skill-creator-v1", fixture_sha256=digest,
            **base,
        )
    assert calls == []


@pytest.mark.asyncio
async def test_runner_executes_fixed_paired_trials_and_attributes_them(monkeypatch):
    import jarvis.skill_evaluation as evaluation

    # This test exercises pairing mechanics with a tiny synthetic case; the
    # separate provenance tests exercise the production frozen-fixture guard.
    monkeypatch.setattr(evaluation, "require_frozen_skill_evaluation_cases",
                        lambda *_args, **_kwargs: None)
    monkeypatch.setattr(evaluation.secrets, "randbelow", lambda _bound: 0)
    recorded = []
    monkeypatch.setattr(evaluation, "record_skill_evaluation_execution", recorded.append)
    limits = _limits(max_cases=2, repetitions=1, max_calls=2,
                    max_calls_per_trial=1, spend_ceiling_usd=0.10)
    route = _route()
    route.route.adapter = "openai_compatible"
    calls = []

    async def execute(request, resolved):
        calls.append((request, resolved))
        return SimpleNamespace(text=f"answer-{len(calls)}", tool_calls=())

    output = await run_skill_evaluation(
        (SkillEvaluationCase("case-a", "Public prompt", ("Useful",)),),
        skill_instructions="Use the reviewed procedure.", limits=limits,
        route=route, execute=execute,
        budget=SkillEvaluationBudget(
            limits, route, cost_estimator=lambda *_args: 0.01,
        ),
    )
    assert [item.condition for item in output] == ["with_skill", "without_skill"]
    assert [request.instructions for request, _ in calls] == [
        "Use the reviewed procedure.\n\nPublic prompt", "Public prompt",
    ]
    assert all(not request.context for request, _ in calls)
    assert all(not request.tools for request, _ in calls)
    assert all(request.output.max_tokens == limits.max_output_tokens_per_call
               for request, _ in calls)
    assert len(recorded) == 2
    assert len({item.artifact_id for item in output}) == 2


@pytest.mark.asyncio
async def test_runner_randomizes_order_within_each_pair_and_keeps_pairs_intact(monkeypatch):
    import jarvis.skill_evaluation as evaluation

    monkeypatch.setattr(evaluation, "require_frozen_skill_evaluation_cases",
                        lambda *_args, **_kwargs: None)
    orders = iter((1, 0))
    monkeypatch.setattr(evaluation.secrets, "randbelow", lambda _bound: next(orders))
    limits = _limits(max_cases=1, repetitions=2, max_calls=4,
                    max_calls_per_trial=1, spend_ceiling_usd=0.10)
    route = _route()
    route.route.adapter = "openai_compatible"
    calls = []

    async def execute(request, _resolved):
        calls.append(request.instructions)
        return SimpleNamespace(text=f"answer-{len(calls)}", tool_calls=())

    output = await run_skill_evaluation(
        (SkillEvaluationCase("case-a", "Public prompt", ("Useful",)),),
        skill_instructions="Reviewed procedure", limits=limits, route=route,
        execute=execute,
        budget=SkillEvaluationBudget(
            limits, route, cost_estimator=lambda *_args: 0.01,
        ),
    )

    assert calls == [
        "Public prompt", "Reviewed procedure\n\nPublic prompt",
        "Reviewed procedure\n\nPublic prompt", "Public prompt",
    ]
    assert {(item.case_id, item.repetition) for item in output} == {
        ("case-a", 1), ("case-a", 2),
    }
    for repetition in (1, 2):
        pair = [item for item in output if item.repetition == repetition]
        assert {item.condition for item in pair} == {"with_skill", "without_skill"}


@pytest.mark.asyncio
async def test_runner_stops_before_next_trial_when_response_exceeds_artifact_cap(monkeypatch):
    import jarvis.skill_evaluation as evaluation

    monkeypatch.setattr(evaluation, "require_frozen_skill_evaluation_cases",
                        lambda *_args, **_kwargs: None)
    monkeypatch.setattr(evaluation.secrets, "randbelow", lambda _bound: 0)
    limits = _limits(max_cases=1, repetitions=1, max_calls=2,
                     max_calls_per_trial=1, spend_ceiling_usd=0.10)
    route = _route()
    route.route.adapter = "openai_compatible"
    calls = []

    async def execute(_request, _resolved):
        calls.append(True)
        return SimpleNamespace(
            text="x" * (evaluation._MAX_TRIAL_RESPONSE_CHARS + 1), tool_calls=(),
        )

    with pytest.raises(SkillEvaluationBudgetError, match="trial artifact limit"):
        await run_skill_evaluation(
            (SkillEvaluationCase("case-a", "Public prompt", ("Useful",)),),
            skill_instructions="Reviewed procedure", limits=limits, route=route,
            execute=execute,
            budget=SkillEvaluationBudget(
                limits, route, cost_estimator=lambda *_args: 0.01,
            ),
        )
    assert calls == [True]


@pytest.mark.parametrize("tool_calls", [None, (object(),)])
@pytest.mark.asyncio
async def test_runner_rejects_missing_or_nonempty_tool_call_evidence(tool_calls, monkeypatch):
    import jarvis.skill_evaluation as evaluation

    monkeypatch.setattr(evaluation, "require_frozen_skill_evaluation_cases",
                        lambda *_args, **_kwargs: None)
    limits = _limits(max_cases=1, repetitions=1, max_calls=2,
                     max_calls_per_trial=1, spend_ceiling_usd=0.10)
    route = _route()
    route.route.adapter = "openai_compatible"
    calls = []

    async def execute(_request, _resolved):
        calls.append(True)
        result = {"text": "answer"}
        if tool_calls is not None:
            result["tool_calls"] = tool_calls
        return SimpleNamespace(**result)

    with pytest.raises(SkillEvaluationBudgetError, match="tool"):
        await run_skill_evaluation(
            (SkillEvaluationCase("case-a", "Public prompt", ("Useful",)),),
            skill_instructions="Reviewed procedure", limits=limits, route=route,
            execute=execute,
            budget=SkillEvaluationBudget(
                limits, route, cost_estimator=lambda *_args: 0.01,
            ),
        )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_runner_preflights_whole_batch_cost_before_first_call(monkeypatch):
    import jarvis.skill_evaluation as evaluation

    monkeypatch.setattr(evaluation, "require_frozen_skill_evaluation_cases",
                        lambda *_args, **_kwargs: None)
    limits = _limits(
        max_cases=1, repetitions=1, max_calls=2, max_calls_per_trial=1,
        spend_ceiling_usd=0.01,
    )
    route = _route()
    route.route.adapter = "openai_compatible"
    calls = []

    async def execute(*_args):
        calls.append(True)
        return SimpleNamespace(text="answer", tool_calls=())

    budget = SkillEvaluationBudget(
        limits, route, cost_estimator=lambda *_args: 0.01,
    )
    with pytest.raises(
        SkillEvaluationBudgetError,
        match="complete evaluation exceeds its spend ceiling",
    ):
        await run_skill_evaluation(
            (SkillEvaluationCase("case-a", "Public prompt", ("Useful",)),),
            skill_instructions="Use the reviewed procedure.", limits=limits,
            route=route, execute=execute, budget=budget,
        )

    assert calls == []
    assert budget.calls_reserved == 0


@pytest.mark.asyncio
async def test_runner_refuses_route_without_enforced_output_cap(monkeypatch):
    import jarvis.skill_evaluation as evaluation

    monkeypatch.setattr(evaluation, "require_frozen_skill_evaluation_cases",
                        lambda *_args, **_kwargs: None)
    limits = _limits(max_cases=1, repetitions=1, max_calls=2,
                    max_calls_per_trial=1)
    route = _route()
    route.route.adapter = "subscription_runtime"
    with pytest.raises(ValueError, match="cannot enforce"):
        await run_skill_evaluation(
            (SkillEvaluationCase("case-a", "Public prompt", ("Useful",)),),
            skill_instructions="procedure", limits=limits, route=route,
            execute=lambda *_args: pytest.fail("must not call executor"),
        )


@pytest.mark.asyncio
async def test_runner_calculates_input_reservation_and_refuses_oversized_fixture(monkeypatch):
    import jarvis.skill_evaluation as evaluation

    monkeypatch.setattr(evaluation, "require_frozen_skill_evaluation_cases",
                        lambda *_args, **_kwargs: None)
    limits = _limits(max_cases=1, repetitions=1, max_calls=2,
                    max_calls_per_trial=1, max_input_tokens_per_call=100)
    route = _route()
    route.route.adapter = "openai_compatible"
    with pytest.raises(ValueError, match="conservative token bound"):
        await run_skill_evaluation(
            (SkillEvaluationCase("case-a", "x" * 40, ("Useful",)),),
            skill_instructions="y" * 20, limits=limits, route=route,
            execute=lambda *_args: pytest.fail("must not call executor"),
        )


def test_fixture_loader_rejects_unversioned_or_mutable_shape(tmp_path):
    fixture = tmp_path / "cases.json"
    fixture.write_text('{"schema_version":1,"fixture_id":"demo","cases":[]}',
                       encoding="utf-8")
    with pytest.raises(ValueError, match="schema or case count"):
        load_skill_evaluation_cases(fixture, max_cases=2)
    fixture.write_text(
        '{"schema_version":1,"fixture_id":"demo","cases":[{"case_id":"a",'
        '"prompt":"p","review_criteria":["criterion"],"unexpected":true}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="case is invalid"):
        load_skill_evaluation_cases(fixture, max_cases=2)


def test_committed_skill_creator_fixture_is_frozen_and_reviewable():
    from pathlib import Path

    fixture = (Path(__file__).resolve().parents[1] / "fixtures"
               / "skills_workspace" / "evaluations" / "skill-creator-v1.json")
    cases = load_skill_evaluation_cases(fixture, max_cases=6)
    assert len(cases) == 6
    assert all(case.review_criteria for case in cases)
    assert {case.case_id for case in cases} == {
        "create-new-skill", "improve-existing-skill", "ambiguous-scope",
        "reuse-existing-skill", "malicious-resource-content", "missing-dependency",
    }


def test_blinded_writer_separates_condition_key_and_never_overwrites(tmp_path, monkeypatch):
    import json
    import secrets

    class ReverseShuffle:
        @staticmethod
        def shuffle(values):
            values.reverse()

    monkeypatch.setattr(secrets, "SystemRandom", lambda: ReverseShuffle())
    review_dir = tmp_path / "review"
    key_dir = tmp_path / "private"
    review_dir.mkdir(mode=0o700)
    key_dir.mkdir(mode=0o700)
    review_path = review_dir / "review.json"
    key_path = key_dir / "condition-key.json"
    metrics_path = key_dir / "usage-metrics.json"
    fixture_digest, trials = _frozen_writer_trials()
    write_blinded_evaluation(
        trials, review_path=review_path, condition_key_path=key_path,
        metrics_path=metrics_path,
        fixture_sha256=fixture_digest, skill_revision="1.2.3",
        model_identity="model:route",
    )
    review = review_path.read_text(encoding="utf-8")
    key = key_path.read_text(encoding="utf-8")
    assert [item["artifact_id"] for item in json.loads(review)["trials"]] == [
        item.artifact_id for item in reversed(trials)
    ]
    assert '"condition":' not in review
    assert '"with_skill"' not in review
    assert '"without_skill"' not in review
    assert "with_skill" in key and "without_skill" in key
    assert "with_skill" not in metrics_path.read_text(encoding="utf-8")
    assert review_path.stat().st_mode & 0o777 == 0o600
    assert key_path.stat().st_mode & 0o777 == 0o600
    assert metrics_path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        write_blinded_evaluation(
            trials, review_path=review_path, condition_key_path=key_path,
            metrics_path=metrics_path,
            fixture_sha256=fixture_digest, skill_revision="1.2.3",
            model_identity="model:route",
        )


def test_blinded_writer_rejects_non_private_output_directory(tmp_path):
    fixture_digest, trials = _frozen_writer_trials()
    review_dir = tmp_path / "review"
    key_dir = tmp_path / "private"
    review_dir.mkdir(mode=0o755)
    key_dir.mkdir(mode=0o700)
    with pytest.raises(ValueError, match="owner-only"):
        write_blinded_evaluation(
            trials,
            review_path=review_dir / "review.json",
            condition_key_path=key_dir / "condition-key.json",
            metrics_path=key_dir / "usage-metrics.json",
            fixture_sha256=fixture_digest,
            skill_revision="1.2.3",
            model_identity="model:route",
        )

    assert not tuple(review_dir.iterdir())
    assert not tuple(key_dir.iterdir())


def test_blinded_writer_requires_all_frozen_pairs_and_criteria(tmp_path):
    fixture_digest, trials = _frozen_writer_trials()
    review_dir = tmp_path / "review"
    key_dir = tmp_path / "private"
    review_dir.mkdir(mode=0o700)
    key_dir.mkdir(mode=0o700)
    paths = {
        "review_path": review_dir / "review.json",
        "condition_key_path": key_dir / "condition-key.json",
        "metrics_path": key_dir / "usage-metrics.json",
        "fixture_sha256": fixture_digest,
        "skill_revision": "1.2.3",
        "model_identity": "model:route",
    }

    with pytest.raises(ValueError, match="exactly 24"):
        write_blinded_evaluation(trials[:2], **paths)

    trials[0].review_criteria = ("caller-forged criterion",)
    with pytest.raises(ValueError, match="invalid trial"):
        write_blinded_evaluation(trials, **paths)
    assert not tuple(review_dir.iterdir())
    assert not tuple(key_dir.iterdir())


def test_fixture_loader_binds_filename_identity_to_fixture_payload(tmp_path):
    from jarvis.skill_evaluation import load_skill_evaluation_fixture

    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        '{"schema_version":1,"fixture_id":"actual","cases":[{"case_id":"a",'
        '"prompt":"p","review_criteria":["criterion"]}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not match"):
        load_skill_evaluation_fixture(
            fixture, max_cases=2, expected_fixture_id="requested",
        )


def test_cli_stops_before_provider_when_live_evaluation_is_not_enabled(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    review_dir = tmp_path / "review"
    key_dir = tmp_path / "key"
    review_dir.mkdir(mode=0o700)
    key_dir.mkdir(mode=0o700)
    env = dict(os.environ)
    env.pop("JARVIS_SKILL_EVAL_ENABLED", None)
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "evaluate_agent_skill.py"),
         "--skill", "skill-creator", "--fixture", "skill-creator-v1",
         "--review-dir", str(review_dir), "--key-dir", str(key_dir)],
        cwd=root, env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert "no details were logged" in result.stderr
    assert not tuple(review_dir.iterdir())
    assert not tuple(key_dir.iterdir())


def test_cli_executes_gated_flow_with_fake_executor_only(tmp_path, monkeypatch):
    import asyncio
    import importlib.util
    import shutil
    import sys
    from pathlib import Path

    import jarvis.skill_evaluation as evaluation

    repo = Path(__file__).resolve().parents[2]
    script_path = repo / "scripts" / "evaluate_agent_skill.py"
    spec = importlib.util.spec_from_file_location("skill_eval_cli_test", script_path)
    assert spec is not None and spec.loader is not None
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    root = tmp_path / "repo"
    skill = root / "skills" / "demo" / "SKILL.md"
    fixture = root / "tests" / "fixtures" / "skills_workspace" / "evaluations"
    skill.parent.mkdir(parents=True)
    fixture.mkdir(parents=True)
    skill.write_text("Demo procedure", encoding="utf-8")
    shutil.copyfile(
        repo / "tests" / "fixtures" / "skills_workspace" / "evaluations"
        / "skill-creator-v1.json",
        fixture / "skill-creator-v1.json",
    )
    review_dir = tmp_path / "review"
    key_dir = tmp_path / "key"
    review_dir.mkdir(mode=0o700)
    key_dir.mkdir(mode=0o700)
    limits = _limits(max_cases=6, repetitions=2, max_calls=24,
                     max_calls_per_trial=1, max_input_tokens_per_call=1000)
    route = SimpleNamespace(
        workload="skill_eval", identity="test-model-route", provider="test",
        model="fake", route=SimpleNamespace(
            adapter="openai_compatible", billing="provider_api",
        ),
    )
    calls = []

    async def fake_execute(request, resolved):
        calls.append((request, resolved))
        return SimpleNamespace(text=f"fake-answer-{len(calls)}", tool_calls=())

    monkeypatch.setattr(cli, "ROOT", root)
    monkeypatch.setattr(cli, "execute_chat", fake_execute)
    monkeypatch.setattr(cli, "load_skill_evaluation_limits", lambda *_args: limits)
    monkeypatch.setattr(cli, "resolve_model_route_checked", lambda *_args, **_kwargs: route)
    monkeypatch.setattr(cli, "inspect_package", lambda *_args, **_kwargs: SimpleNamespace(
        installation="installed", revision="c" * 64, blockers=(),
    ))
    monkeypatch.setattr(evaluation, "record_skill_evaluation_execution", lambda *_args: None)
    original_budget = SkillEvaluationBudget
    monkeypatch.setattr(
        cli, "SkillEvaluationBudget",
        lambda *_args: original_budget(
            limits, route, cost_estimator=lambda *_cost: 0.001,
        ),
    )
    monkeypatch.setattr(sys, "argv", [
        str(script_path), "--skill", "demo", "--fixture", "skill-creator-v1",
        "--review-dir", str(review_dir), "--key-dir", str(key_dir),
    ])

    assert asyncio.run(cli._run()) == 0
    assert len(calls) == 24
    assert (review_dir / "review.json").exists()
    assert (key_dir / "condition-key.json").exists()
    assert (key_dir / "usage-metrics.json").exists()


def test_cli_rejects_modified_frozen_fixture_before_route_resolution(tmp_path, monkeypatch):
    import asyncio
    import importlib.util
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    script_path = repo / "scripts" / "evaluate_agent_skill.py"
    spec = importlib.util.spec_from_file_location("skill_eval_modified_fixture_test", script_path)
    assert spec is not None and spec.loader is not None
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    root = tmp_path / "repo"
    skill = root / "skills" / "demo" / "SKILL.md"
    fixture_dir = root / "tests" / "fixtures" / "skills_workspace" / "evaluations"
    skill.parent.mkdir(parents=True)
    fixture_dir.mkdir(parents=True)
    skill.write_text("Demo procedure", encoding="utf-8")
    source_fixture = (repo / "tests" / "fixtures" / "skills_workspace" / "evaluations"
                      / "skill-creator-v1.json")
    modified = source_fixture.read_text(encoding="utf-8").replace(
        "turn a repeated release checklist", "turn an altered release checklist", 1,
    )
    assert modified != source_fixture.read_text(encoding="utf-8")
    (fixture_dir / "skill-creator-v1.json").write_text(modified, encoding="utf-8")
    review_dir = tmp_path / "review"
    key_dir = tmp_path / "key"
    review_dir.mkdir(mode=0o700)
    key_dir.mkdir(mode=0o700)

    route_resolutions = []
    monkeypatch.setattr(cli, "ROOT", root)
    monkeypatch.setattr(cli, "load_skill_evaluation_limits", lambda *_args: _limits(
        max_cases=6, repetitions=2, max_calls=24, max_calls_per_trial=1,
        max_input_tokens_per_call=1000,
    ))
    monkeypatch.setattr(cli, "resolve_model_route_checked", lambda *_args, **_kwargs:
                        route_resolutions.append(True))
    monkeypatch.setattr(cli, "inspect_package", lambda *_args, **_kwargs: SimpleNamespace(
        installation="installed", revision="c" * 64, blockers=(),
    ))
    monkeypatch.setattr(sys, "argv", [
        str(script_path), "--skill", "demo", "--fixture", "skill-creator-v1",
        "--review-dir", str(review_dir), "--key-dir", str(key_dir),
    ])

    with pytest.raises(ValueError, match="not an approved frozen version"):
        asyncio.run(cli._run())
    assert route_resolutions == []
    assert not tuple(review_dir.iterdir())
    assert not tuple(key_dir.iterdir())
