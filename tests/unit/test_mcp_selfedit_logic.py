"""Unit tests for mcp_selfedit logic (thin client of the admin sidecar)."""

from __future__ import annotations

import pytest

from mcp_servers.mcp_selfedit import logic


@pytest.fixture(autouse=True)
def _clear_profile_env(monkeypatch):
    """Selection order must not leak from the developer's own shell env."""
    monkeypatch.delenv("JARVIS_UPGRADE_PROFILE", raising=False)


class FakeClient:
    """Duck-typed AdminClient stand-in: routes keyed on (method, path)."""

    def __init__(self, routes=None, fail=False):
        self.routes = routes or {}
        self.fail = fail
        self.posts = []
        self.gets = []

    def get(self, path, params=None):
        if self.fail:
            raise ConnectionError("refused")
        self.gets.append((path, params))
        return self.routes[("GET", path)]

    def post(self, path, json=None):
        if self.fail:
            raise ConnectionError("refused")
        self.posts.append((path, json))
        return self.routes[("POST", path)]


MODELS = {
    "ok": True,
    "models": [
        {"name": "kimi-k2", "label": "Kimi K2.7 Code", "provider": "moonshot",
         "model": "kimi-k2.7-code", "key_env": "MOONSHOT_API_KEY",
         "key_present": True, "default": True},
        {"name": "kimi-k3", "label": "Kimi K3", "provider": "moonshot",
         "model": "kimi-k3", "key_env": "MOONSHOT_API_KEY",
         "key_present": False, "default": False},
        {"name": "claude-opus", "label": "Claude Opus 5", "provider": "anthropic",
         "model": "claude-opus-5", "key_env": "ANTHROPIC_API_KEY",
         "key_present": True, "default": False},
    ],
}

SESSION_ACTIVE = {
    "ok": True,
    "job": {"state": "done", "goal": "add a clock", "profile": "kimi-k2 (kimi-k2.7-code)",
            "summary": "3 planning iterations, 1 file edit(s) proposed"},
    "status": {
        "active": True,
        "branch": "jarvis/self-edit/20260811-add-clock",
        "proposals": [{"path": "web/src/components/ClockPanel.tsx",
                       "rationale": "add a clock panel", "diff": "+..."}],
        "validated_ok": True,
    },
}


def _client(overrides: dict | None = None) -> FakeClient:
    routes = {
        ("GET", "/api/selfedit/models"): MODELS,
        ("GET", "/api/selfedit/run"): {"ok": True, "job": {"state": "idle"}, "status": {}},
        # G2: confirm=false now stages, rather than staying entirely local.
        ("POST", "/api/selfedit/stage"): {"ok": True, "staging_id": "stg-fake",
                                           "expires_in_s": 600.0},
        ("POST", "/api/selfedit/run"): {"ok": True, "started": True,
                                         "profile": "kimi-k2 (kimi-k2.7-code)"},
        ("POST", "/api/selfedit/validate"): {"ok": True, "checks": [{"name": "allowlist", "ok": True, "output": ""}]},
        ("POST", "/api/selfedit/submit"): {"ok": True, "pr_url": "https://github.com/x/y/pull/9"},
        ("POST", "/api/selfedit/revert"): {"ok": True},
    }
    routes.update(overrides or {})
    return FakeClient(routes)


# ── selfedit_start ─────────────────────────────────────────────────────────

def test_start_preview_starts_nothing():
    c = _client()
    r = logic.selfedit_start(c, "add a clock panel")
    assert r["ok"] and r["needs_confirmation"]
    assert r["profile"] == "kimi-k2"  # registry default
    assert "add a clock panel" in r["summary"]
    assert r["staging_id"] == "stg-fake"
    # G2: preview STAGES (so confirm=true can replay it byte-identical) but
    # never starts a run — the invariant is "doesn't start", not "no POST".
    assert c.posts == [
        ("/api/selfedit/stage",
         {"goal": "add a clock panel", "profile": "kimi-k2", "plan_path": None,
          "run_id": None, "target_paths": None}),
    ]


def test_start_preview_posts_target_paths_for_the_tier_check():
    """2026-09-07: preflight classifies what the edit CHANGES, not what the
    goal mentions. Blank entries are dropped; an all-blank list is None."""
    c = _client()
    logic.selfedit_start(c, "add a line about jarvis/model_catalog.py to docs/REPO_MAP.md",
                         target_paths=["docs/REPO_MAP.md", " ", ""])
    assert c.posts[0][1]["target_paths"] == ["docs/REPO_MAP.md"]
    c = _client()
    logic.selfedit_start(c, "tidy the docs", target_paths=["", " "])
    assert c.posts[0][1]["target_paths"] is None


def test_start_honors_spoken_profile():
    c = _client()
    r = logic.selfedit_start(c, "add a clock", profile="claude-opus", confirm=True)
    assert r["ok"] and r["started"]
    assert c.posts == [("/api/selfedit/run", {"goal": "add a clock", "profile": "claude-opus",
                                               "run_id": None})]
    assert "several minutes" in r["summary"]


def test_selfedit_start_forwards_run_id():
    """MORTIMER_GRAPH_LAYER_PLAN.md GL9 (contract G2, step 11d) — run_id is
    filled in by the system (SkillRegistry.call()'s injection), never
    spoken by the model; this pins that it reaches the stage POST."""
    c = _client()
    logic.selfedit_start(c, "add a clock panel", run_id="r9")
    assert c.posts == [
        ("/api/selfedit/stage",
         {"goal": "add a clock panel", "profile": "kimi-k2", "plan_path": None,
          "run_id": "r9", "target_paths": None}),
    ]


def test_start_unknown_profile_names_available():
    r = logic.selfedit_start(_client(), "x", profile="gpt-99")
    assert r["ok"] is False
    assert "gpt-99" in r["error"] and "kimi-k2" in r["error"]


def test_start_missing_key_names_env_var():
    r = logic.selfedit_start(_client(), "x", profile="kimi-k3")
    assert r["ok"] is False
    assert "MOONSHOT_API_KEY" in r["error"]


def test_start_confirm_with_no_id_and_no_goal_posts_to_run():
    """A bare 'yes' — no staging_id survived the relay and no goal was
    restated — is still handed to the sidecar, which resolves the single
    live staging or names the real state. It must never be answered
    client-side with 'I need a goal'."""
    client = FakeClient({
        ("POST", "/api/selfedit/run"): {"ok": True, "started": True,
                                         "profile": "kimi-k2 (kimi-k2.7-code)"},
    })
    res = logic.selfedit_start(client, confirm=True)
    assert res["ok"] and res["started"]
    assert client.posts == [("/api/selfedit/run", {"staging_id": "", "author": True})]


def test_start_confirm_with_a_mangled_id_is_passed_through_unchanged():
    client = FakeClient({
        ("POST", "/api/selfedit/run"): {"ok": True, "started": True, "profile": "p"},
    })
    logic.selfedit_start(client, confirm=True, staging_id="stg-0d049db0947d")
    assert client.posts == [("/api/selfedit/run",
                             {"staging_id": "stg-0d049db0947d", "author": True})]


def test_start_confirm_posts_goal_and_profile():
    c = _client()
    r = logic.selfedit_start(c, "dark theme", confirm=True)
    assert r["started"]
    assert c.posts == [("/api/selfedit/run", {"goal": "dark theme", "profile": "kimi-k2",
                                               "run_id": None})]


def test_start_env_profile_beats_registry_default(monkeypatch):
    monkeypatch.setenv("JARVIS_UPGRADE_PROFILE", "claude-opus")
    c = _client()
    r = logic.selfedit_start(c, "add a clock")
    assert r["ok"] and r["profile"] == "claude-opus"  # env beats registry default


def test_start_explicit_profile_beats_env(monkeypatch):
    monkeypatch.setenv("JARVIS_UPGRADE_PROFILE", "claude-opus")
    c = _client()
    logic.selfedit_start(c, "add a clock", profile="kimi-k2", confirm=True)
    assert c.posts == [("/api/selfedit/run", {"goal": "add a clock", "profile": "kimi-k2",
                                               "run_id": None})]


def test_start_env_profile_missing_key_names_env_profile(monkeypatch):
    monkeypatch.setenv("JARVIS_UPGRADE_PROFILE", "kimi-k3")
    r = logic.selfedit_start(_client(), "x")
    assert r["ok"] is False and "MOONSHOT_API_KEY" in r["error"] and "kimi-k3" in r["error"]


def test_start_plan_path_in_preview_summary():
    c = _client()
    r = logic.selfedit_start(
        c, "implement geolocation phase 1",
        plan_path="docs/plans/GEOLOCATION_DEVELOPMENT_PLAN.md",
    )
    assert r["ok"] and r["needs_confirmation"]
    assert "docs/plans/GEOLOCATION_DEVELOPMENT_PLAN.md" in r["summary"]
    assert r["staging_id"] == "stg-fake"
    assert c.posts == [
        ("/api/selfedit/stage", {
            "goal": "implement geolocation phase 1",
            "profile": "kimi-k2",
            "plan_path": "docs/plans/GEOLOCATION_DEVELOPMENT_PLAN.md",
            "run_id": None,
            "target_paths": None,
        }),
    ]


def test_start_confirm_posts_plan_path():
    c = _client()
    r = logic.selfedit_start(
        c, "implement geolocation phase 1", confirm=True,
        plan_path="docs/plans/GEOLOCATION_DEVELOPMENT_PLAN.md",
    )
    assert r["started"]
    assert c.posts == [("/api/selfedit/run", {
        "goal": "implement geolocation phase 1",
        "profile": "kimi-k2",
        "plan_path": "docs/plans/GEOLOCATION_DEVELOPMENT_PLAN.md",
        "run_id": None,
    })]


def test_start_empty_plan_path_omitted_from_post():
    c = _client()
    logic.selfedit_start(c, "dark theme", confirm=True, plan_path="  ")
    assert c.posts == [("/api/selfedit/run", {"goal": "dark theme", "profile": "kimi-k2",
                                               "run_id": None})]


# ── selfedit_start: G2 staged confirm flow ──────────────────────────────────

def test_start_confirm_with_staging_id_replays_without_restating_goal():
    """G2: confirm=true + staging_id skips model selection AND goal/profile
    entirely — the sidecar replays the staged record. No models lookup, no
    goal required on this call."""
    c = _client(overrides={
        ("POST", "/api/selfedit/run"): {"ok": True, "started": True, "profile": "kimi-k3"},
    })
    r = logic.selfedit_start(c, confirm=True, staging_id="stg-abc")
    assert r["ok"] and r["started"]
    assert r["profile"] == "kimi-k3"
    assert c.posts == [("/api/selfedit/run",
                       {"staging_id": "stg-abc", "author": True})]


def test_start_confirm_staging_id_takes_priority_over_goal():
    """Even if goal/profile are (redundantly) also passed, a present
    staging_id short-circuits straight to the replay — it never re-derives
    from the restated goal."""
    c = _client()
    r = logic.selfedit_start(
        c, goal="some other goal entirely", confirm=True, staging_id="stg-abc",
    )
    assert r["ok"] and r["started"]
    assert c.posts == [("/api/selfedit/run",
                       {"staging_id": "stg-abc", "author": True})]


def test_start_confirm_stale_staging_id_surfaces_sidecar_error():
    """G2: the sidecar's own 'no staged edit' error (TTL or already-used)
    must pass straight through — it names the real state, never a
    fabricated 'session expired' narrative."""
    c = _client(overrides={
        ("POST", "/api/selfedit/run"): {
            "ok": False,
            "error": "no staged edit with id 'stg-old' — it may have expired "
                     "(staging lasts 10 minutes) or was already used. Call "
                     "selfedit_start again (confirm=false) to preview a new one.",
        },
    })
    r = logic.selfedit_start(c, confirm=True, staging_id="stg-old")
    assert r["ok"] is False
    assert "no staged edit" in r["error"]
    assert "session expired" not in r["error"]


# ── selfedit_status ────────────────────────────────────────────────────────

def test_status_while_running():
    c = _client({("GET", "/api/selfedit/run"): {
        "ok": True,
        "job": {"state": "running", "goal": "add a clock", "profile": "kimi-k2 (kimi-k2.7-code)"},
        "status": {}}})
    r = logic.selfedit_status(c)
    assert "Still planning" in r["summary"] and "add a clock" in r["summary"]


def test_status_composes_session_and_proposals():
    c = _client({("GET", "/api/selfedit/run"): SESSION_ACTIVE})
    r = logic.selfedit_status(c)
    assert "ClockPanel.tsx" in r["summary"]
    assert "Validation has passed" in r["summary"]
    assert r["active"] is True


def test_status_speaks_the_pull_request_the_run_opened():
    done = {
        "ok": True,
        "job": {"state": "done", "goal": "add a clock", "profile": "p",
                "summary": "planned it", "submitted": True,
                "pr_url": "https://github.com/x/y/pull/12"},
        "status": {"active": False, "proposals": [], "validated_ok": False},
        "stagings": [],
    }
    r = logic.selfedit_status(_client({("GET", "/api/selfedit/run"): done}))
    assert "planned it" in r["summary"]
    assert "https://github.com/x/y/pull/12" in r["summary"]
    assert "merging is yours" in r["summary"]


def test_status_when_idle():
    r = logic.selfedit_status(_client())
    assert "No upgrade run" in r["summary"]


def test_status_reports_live_staging_when_asked():
    """2026-08-25 — a developer run once fabricated 'staging expired'
    from this exact tool, which had no way to know that. Passing
    staging_id must answer from the real `stagings` list the sidecar
    now returns."""
    c = _client({("GET", "/api/selfedit/run"): {
        "ok": True, "job": {"state": "idle"}, "status": {},
        "stagings": [{"staging_id": "469bff19ef49", "age_s": 5.0,
                      "expires_in_s": 595.0}],
    }})
    r = logic.selfedit_status(c, staging_id="469bff19ef49")
    assert r["staging_found"] is True
    assert "still live" in r["summary"]
    assert "469bff19ef49" in r["summary"]


def test_status_reports_missing_staging_honestly():
    c = _client({("GET", "/api/selfedit/run"): {
        "ok": True, "job": {"state": "idle"}, "status": {}, "stagings": [],
    }})
    r = logic.selfedit_status(c, staging_id="does-not-exist")
    assert r["staging_found"] is False
    assert "not currently live" in r["summary"]
    # Must not fabricate a specific cause — "may have" hedges honestly.
    assert "may have" in r["summary"]


def test_status_without_staging_id_omits_staging_language():
    r = logic.selfedit_status(_client())
    assert r["staging_found"] is None
    assert "staging" not in r["summary"].lower()


def test_status_answers_staging_question_even_while_running():
    """The running-state branch returns early. The first cut computed the
    staging answer only on the idle path, so asking during a run got a
    cheerful 'still planning…' with no staging_found key and no mention of
    the question — a silent non-answer, exactly the shape that invites the
    model to invent one. If it was asked, it gets an answer."""
    c = _client({("GET", "/api/selfedit/run"): {
        "ok": True,
        "job": {"state": "running", "goal": "add a clock", "profile": "kimi-k2"},
        "status": {},
        "stagings": [{"staging_id": "469bff19ef49", "age_s": 5.0,
                      "expires_in_s": 595.0}],
    }})
    r = logic.selfedit_status(c, staging_id="469bff19ef49")
    assert r["staging_found"] is True
    assert "Still planning" in r["summary"]
    assert "still live" in r["summary"]

    missing = logic.selfedit_status(c, staging_id="nope")
    assert missing["staging_found"] is False
    assert "not currently live" in missing["summary"]


# ── selfedit_read / selfedit_write / selfedit_finish (SE2/SE4) ─────────────

def test_read_passes_the_path_as_a_query_param():
    c = _client({("GET", "/api/selfedit/file"): {"ok": True, "content": "x = 1\n"}})
    r = logic.selfedit_read(c, "jarvis/bot/display.py")
    assert r["ok"] and r["content"] == "x = 1\n"
    assert c.gets == [("/api/selfedit/file", {"path": "jarvis/bot/display.py"})]


def test_read_and_write_refuse_an_empty_path():
    c = _client()
    assert logic.selfedit_read(c, "  ")["ok"] is False
    assert logic.selfedit_write(c, "", "x", "why")["ok"] is False
    assert c.posts == []


def test_write_requires_a_rationale():
    """It goes in the pull request; an unexplained edit is not reviewable."""
    c = _client()
    r = logic.selfedit_write(c, "docs/x.md", "hi\n", "  ")
    assert r["ok"] is False and "rationale" in r["error"]
    assert c.posts == []


def test_write_posts_the_whole_file_and_reports_the_diff():
    c = _client({("POST", "/api/selfedit/write"): {
        "ok": True, "path": "docs/x.md", "diff": "+hi"}})
    r = logic.selfedit_write(c, "docs/x.md", "hi\n", "note it", "looks blue")
    assert r["ok"] and r["diff"] == "+hi"
    assert "selfedit_finish" in r["summary"]
    assert c.posts == [("/api/selfedit/write", {
        "path": "docs/x.md", "content": "hi\n", "rationale": "note it",
        "visual_intent": "looks blue"})]


def test_write_relays_an_allowlist_refusal_unchanged():
    """SE2 changes who writes, never what may be written."""
    c = _client({("POST", "/api/selfedit/write"): {
        "ok": False, "error": "jarvis/vault.py is not on the allowlist"}})
    r = logic.selfedit_write(c, "jarvis/vault.py", "x\n", "why")
    assert r["ok"] is False and "allowlist" in r["error"]


def test_finish_starts_the_job_and_says_it_runs_in_the_background():
    c = _client({("POST", "/api/selfedit/finish"): {
        "ok": True, "started": True, "state": "validating"}})
    r = logic.selfedit_finish(c)
    assert r["ok"] and r["started"]
    assert "Validating now" in r["summary"]
    assert c.posts == [("/api/selfedit/finish", {})]


def test_finish_relays_a_refusal():
    c = _client({("POST", "/api/selfedit/finish"): {
        "ok": False, "error": "nothing has been written yet"}})
    assert logic.selfedit_finish(c)["error"] == "nothing has been written yet"


def test_status_speaks_the_finish_job_states():
    def status_with(finish):
        return _client({("GET", "/api/selfedit/run"): {
            "ok": True, "job": {"state": "idle"},
            "status": {"active": True, "proposals": []}, "finish": finish}})

    validating = logic.selfedit_status(status_with({"state": "validating"}))
    assert "Validating" in validating["summary"]

    done = logic.selfedit_status(status_with({
        "state": "done", "pr_url": "https://x/pull/3",
        "notice": "SWIFT CHANGE: rebuild the app"}))
    assert "SWIFT CHANGE" in done["summary"]
    assert "https://x/pull/3" in done["summary"]

    failed = logic.selfedit_status(status_with({
        "state": "failed",
        "checks": [{"name": "pytest", "ok": False, "output": "1 failed"}]}))
    assert "pytest" in failed["summary"] and "1 failed" in failed["summary"]
    assert "want me to fix it" in failed["summary"]

    errored = logic.selfedit_status(status_with({
        "state": "error", "notice": "push rejected"}))
    assert "push rejected" in errored["summary"]


def test_status_says_nothing_about_a_finish_that_never_ran():
    c = _client({("GET", "/api/selfedit/run"): {
        "ok": True, "job": {"state": "idle"},
        "status": {"active": False}, "finish": {"state": "idle"}}})
    summary = logic.selfedit_status(c)["summary"]
    assert "No upgrade run or edit session is active" in summary
    assert "Validating" not in summary


# ── selfedit_revert ────────────────────────────────────────────────────────

def test_revert_two_phase():
    c = _client({("GET", "/api/selfedit/run"): SESSION_ACTIVE})
    preview = logic.selfedit_revert(c, confirm=False)
    assert preview["needs_confirmation"] and "1 proposed edit" in preview["summary"]
    done = logic.selfedit_revert(c, confirm=True)
    assert done["ok"] and "back to normal" in done["summary"]


def test_revert_refused_while_running():
    c = _client({("GET", "/api/selfedit/run"): {
        "ok": True, "job": {"state": "running", "goal": "x"}, "status": {"active": True}}})
    r = logic.selfedit_revert(c, confirm=True)
    assert r["ok"] is False and "still working" in r["error"]


# ── offline degradation ────────────────────────────────────────────────────

@pytest.mark.parametrize("call", [
    lambda c: logic.selfedit_start(c, "goal", confirm=True),
    lambda c: logic.selfedit_status(c),
    lambda c: logic.selfedit_read(c, "docs/x.md"),
    lambda c: logic.selfedit_write(c, "docs/x.md", "hi\n", "why"),
    lambda c: logic.selfedit_finish(c),
    lambda c: logic.selfedit_revert(c, confirm=True),
    lambda c: logic.plan_start(c, "goal", confirm=True),
    lambda c: logic.plan_status(c),
    lambda c: logic.plan_choose(c, "Proposal A"),
    lambda c: logic.plan_adopt(c, confirm=True),
])
def test_offline_degrades_to_spoken_error(call):
    r = call(FakeClient(fail=True))
    assert r["ok"] is False
    assert "mortimer.sh" in r["error"]


# ── plan_start / plan_status / plan_choose / plan_adopt (P7) ───────────────


def test_plan_start_requires_goal():
    r = logic.plan_start(_client(), "  ", confirm=False)
    assert r["ok"] is False
    assert "goal" in r["error"]


def test_plan_start_rejects_bad_mode():
    r = logic.plan_start(_client(), "write a spec", mode="parallel", confirm=False)
    assert r["ok"] is False
    assert "mode" in r["error"]


def test_plan_start_previews_without_confirm():
    r = logic.plan_start(_client(), "write a spec", mode="single", confirm=False)
    assert r["ok"] is True
    assert r["needs_confirmation"] is True
    assert "write a spec" in r["summary"]


def test_plan_start_council_confirm_posts_and_summarizes(monkeypatch):
    c = _client({("POST", "/api/plan/start"): {"ok": True, "started": True}})
    r = logic.plan_start(c, "write a spec", mode="council", confirm=True)
    assert r["ok"] is True
    assert r["started"] is True
    assert c.posts[0] == ("/api/plan/start", {
        "goal": "write a spec", "mode": "council", "profile": None,
        "review_path": "", "run_id": None,
    })


def test_plan_start_forwards_run_id():
    """GL9 (contract G2, step 11d) — run_id reaches the /api/plan/start POST."""
    c = _client({("POST", "/api/plan/start"): {"ok": True, "started": True}})
    logic.plan_start(c, "write a spec", mode="single", confirm=True, run_id="r9")
    assert c.posts[0] == ("/api/plan/start", {
        "goal": "write a spec", "mode": "single", "profile": None,
        "review_path": "", "run_id": "r9",
    })


def test_plan_status_idle():
    c = _client({("GET", "/api/plan/job"): {"ok": True, "job": {"state": "idle"}}})
    r = logic.plan_status(c)
    assert r["ok"] is True
    assert "No planning job" in r["summary"]


def test_plan_status_running():
    c = _client({("GET", "/api/plan/job"): {
        "ok": True,
        "job": {"state": "running", "mode": "single", "goal": "write a spec"},
    }})
    r = logic.plan_status(c)
    assert "Still drafting" in r["summary"]
    assert "write a spec" in r["summary"]


def test_plan_status_awaiting_choice_lists_candidates():
    c = _client({("GET", "/api/plan/job"): {
        "ok": True,
        "job": {
            "state": "awaiting_choice",
            "candidates": [
                {"label": "Proposal A", "profile": "kimi-k2", "advisory_mean": 8.1},
                {"label": "Proposal B", "profile": "claude-opus", "advisory_mean": None},
            ],
        },
    }})
    r = logic.plan_status(c)
    assert "Proposal A by kimi-k2 (advisory score 8.1)" in r["summary"]
    assert "Proposal B by claude-opus" in r["summary"]
    assert "which one" in r["summary"].lower()


def test_plan_status_done():
    c = _client({("GET", "/api/plan/job"): {
        "ok": True, "job": {"state": "done", "author": "kimi-k2"},
    }})
    r = logic.plan_status(c)
    assert "kimi-k2" in r["summary"]
    assert "draft" in r["summary"].lower()


def test_plan_choose_requires_label():
    r = logic.plan_choose(_client(), "")
    assert r["ok"] is False


def test_plan_choose_posts_label():
    c = _client({("POST", "/api/plan/choose"): {"ok": True}})
    r = logic.plan_choose(c, "Proposal B")
    assert r["ok"] is True
    assert c.posts[0] == ("/api/plan/choose", {"label": "Proposal B"})
    assert "Proposal B" in r["summary"]


def test_plan_adopt_requires_finished_plan():
    c = _client({("GET", "/api/plan/job"): {"ok": True, "job": {"state": "running"}}})
    r = logic.plan_adopt(c, confirm=True)
    assert r["ok"] is False
    assert "no finished plan" in r["error"]


def test_plan_adopt_previews_without_confirm():
    c = _client({("GET", "/api/plan/job"): {"ok": True, "job": {"state": "done"}}})
    r = logic.plan_adopt(c, confirm=False)
    assert r["ok"] is True
    assert r["needs_confirmation"] is True


def test_plan_adopt_confirm_posts_and_reports_pending():
    c = _client({
        ("GET", "/api/plan/job"): {"ok": True, "job": {"state": "done"}},
        ("POST", "/api/plan/adopt"): {
            "ok": True, "pending": True, "action_id": 5,
            "path": "docs/plans/write-a-spec.md",
        },
    })
    r = logic.plan_adopt(c, path="docs/plans/write-a-spec.md", confirm=True)
    assert r["ok"] is True
    assert r["pending"] is True
    assert r["action_id"] == 5
    assert "nothing has been" in r["summary"].lower()
    assert c.posts[0] == ("/api/plan/adopt", {"path": "docs/plans/write-a-spec.md"})


# ── review mode (MORTIMER_PLAN_REVIEW_AND_DOCS_PLAN.md R5) ────────────────


def test_plan_start_review_path_passed_through_on_confirm():
    c = _client({("POST", "/api/plan/start"): {"ok": True, "started": True}})
    r = logic.plan_start(
        c, "review the geolocation plan", mode="single", confirm=True,
        review_path="docs/plans/GEOLOCATION_DEVELOPMENT_PLAN.md",
    )
    assert r["ok"] is True
    assert c.posts[0] == ("/api/plan/start", {
        "goal": "review the geolocation plan", "mode": "single", "profile": None,
        "review_path": "docs/plans/GEOLOCATION_DEVELOPMENT_PLAN.md", "run_id": None,
    })
    assert "started the review" in r["summary"].lower()


def test_plan_start_review_path_empty_is_authoring_mode_unchanged():
    r = logic.plan_start(_client(), "write a spec", mode="single", confirm=False)
    assert r["review_path"] is None
    assert "review" not in r["summary"].lower()


def test_plan_start_review_preview_names_the_document():
    r = logic.plan_start(
        _client(), "review the plan", mode="single", profile="kimi-k2",
        confirm=False, review_path="docs/plans/x.md",
    )
    assert r["ok"] is True
    assert r["needs_confirmation"] is True
    assert "review" in r["summary"].lower()
    assert "docs/plans/x.md" in r["summary"]


def test_plan_status_says_review_when_job_has_review_path():
    c = _client({("GET", "/api/plan/job"): {
        "ok": True,
        "job": {"state": "done", "author": "kimi-k2", "review_path": "docs/plans/x.md"},
    }})
    r = logic.plan_status(c)
    assert "review is ready" in r["summary"].lower()
    assert "plan is ready" not in r["summary"].lower()


def test_plan_status_says_plan_when_job_has_no_review_path():
    c = _client({("GET", "/api/plan/job"): {
        "ok": True, "job": {"state": "done", "author": "kimi-k2"},
    }})
    r = logic.plan_status(c)
    assert "plan is ready" in r["summary"].lower()


def test_plan_adopt_preview_names_reviews_default_when_review_path_set():
    c = _client({("GET", "/api/plan/job"): {
        "ok": True, "job": {"state": "done", "review_path": "docs/plans/x.md"},
    }})
    r = logic.plan_adopt(c, confirm=False)
    assert r["ok"] is True
    assert "docs/reviews/" in r["summary"]
    assert "docs/plans/" not in r["summary"]


def test_plan_adopt_confirm_reports_review_wording():
    c = _client({
        ("GET", "/api/plan/job"): {
            "ok": True, "job": {"state": "done", "review_path": "docs/plans/x.md"},
        },
        ("POST", "/api/plan/adopt"): {
            "ok": True, "pending": True, "action_id": 7,
            "path": "docs/reviews/x.md",
        },
    })
    r = logic.plan_adopt(c, confirm=True)
    assert r["ok"] is True
    assert "drafted the review" in r["summary"].lower()


def test_workspace_preparation_is_reported_without_inventing_a_planner():
    client = FakeClient({('POST', '/api/selfedit/run'): {'ok': True, 'started': True, 'opening': True}})
    result = logic.selfedit_start(client, confirm=True, staging_id='stage-1')
    assert result['opening'] and 'prepared' in result['summary']
    assert 'planner_model' not in result
    client = FakeClient({('GET', '/api/selfedit/run'): {'ok': True,
        'opening': {'state': 'starting'}, 'status': {}, 'stagings': []}})
    result = logic.selfedit_status(client)
    assert 'not ready for edits' in result['summary']
