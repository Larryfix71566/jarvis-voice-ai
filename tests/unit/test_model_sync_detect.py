"""Unit tests for jarvis.model_sync.detect (WS-41). Hand-built inputs, no I/O."""
from datetime import date

import pytest

from jarvis.model_sync import detect as d

TODAY = date(2026, 11, 23)


def pin(model, file, context="", raw=None):
    return {"model": model, "raw": raw or model, "file": file, "line": 1, "context": context}


def launch(model, source="anthropic_release_notes"):
    return {"model": model, "vendor": "x", "date": "2026-11-01", "source": source}


def run(public=None, subs=None, pins=None, installed=None, today=TODAY):
    return d.detect(public or {}, subs or {}, pins or {}, today=today, installed=installed)


def kinds(findings, kind):
    return [f for f in findings if f["kind"] == kind]


# ---------------------------------------------------------------- level_for
def test_level_for_boundaries():
    assert d.level_for(None) == "notice"
    assert d.level_for(-1) == "retired"
    assert d.level_for(0) == "urgent"
    assert d.level_for(7) == "urgent"
    assert d.level_for(8) == "task"
    assert d.level_for(30) == "task"
    assert d.level_for(31) == "notice"


def test_level_rank_order_and_unknown():
    assert [d.level_rank(x) for x in d.LEVELS] == [0, 1, 2, 3]
    assert d.level_rank(None) == -1
    assert d.level_rank("bogus") == -1


# ---------------------------------------------------------------- new_model
def test_new_model_picks_newest_and_merges_files():
    pins = {"models": [
        pin("claude-fable-5", "config/b.yaml", "big"),
        pin("claude-fable-5", "config/a.yaml", "fast"),
        pin("claude-fable-5", "config/a.yaml", "fast"),  # duplicate
    ]}
    public = {"launches": [launch("claude-fable-5-1"), launch("claude-fable-5-2")]}
    found = kinds(run(public, {}, pins), "new_model")
    assert len(found) == 1
    f = found[0]
    assert f["model"] == "claude-fable-5-2"
    assert f["replaces"] == "claude-fable-5"
    assert f["key"] == "new_model:claude-fable-5->claude-fable-5-2"
    assert f["files"] == ["config/a.yaml", "config/b.yaml"]
    assert f["roles"] == ["big", "fast"] or sorted(f["roles"]) == ["big", "fast"]
    assert f["reason"] == "newer release"
    assert f["vendor"] == "anthropic"
    assert f["voice"] is False
    assert f["on_subscription"] is False
    assert f["sources"] == ["anthropic_release_notes"]


def test_lineages_do_not_cross():
    pins = {"models": [pin("claude-sonnet-4-5", "config/a.yaml")]}
    public = {"launches": [launch("claude-opus-5-5")]}
    assert kinds(run(public, {}, pins), "new_model") == []


def test_dated_snapshot_of_same_version_not_newer():
    pins = {"models": [pin("claude-sonnet-4-5", "config/a.yaml")]}
    public = {"launches": [launch("claude-sonnet-4-5-20250929")]}
    assert kinds(run(public, {}, pins), "new_model") == []


def test_older_model_not_a_candidate():
    pins = {"models": [pin("claude-sonnet-5-5", "config/a.yaml")]}
    public = {"launches": [launch("claude-sonnet-4-5")]}
    assert kinds(run(public, {}, pins), "new_model") == []


def test_active_deprecation_rows_are_evidence_but_deprecated_and_retired_are_not():
    pins = {"models": [pin("claude-sonnet-4-5", "config/a.yaml")]}
    for state, expect in (("active", True), ("deprecated", False), ("retired", False)):
        public = {"deprecations": [{"model": "claude-sonnet-5-5", "state": state,
                                    "source": "dep"}]}
        got = kinds(run(public, {}, pins), "new_model")
        assert bool(got) is expect, state
        if expect:
            assert got[0]["model"] == "claude-sonnet-5-5"
            assert got[0]["sources"] == ["dep"]


def test_router_prefixed_pins_ignored_but_anthropic_prefix_kept():
    pins = {"models": [
        pin("gpt-5.1", "config/r.yaml", raw="openai/gpt-5.1"),
        pin("claude-fable-5", "config/a.yaml", raw="anthropic/claude-fable-5"),
    ]}
    public = {"launches": [launch("gpt-5.2"), launch("claude-fable-5-1")]}
    found = kinds(run(public, {}, pins), "new_model")
    assert [f["replaces"] for f in found] == ["claude-fable-5"]


def test_unparseable_pin_and_non_dict_entries_ignored():
    pins = {"models": ["junk", None, {"model": "not-a-model", "file": "x"}]}
    assert run({"launches": [launch("claude-fable-5-1")]}, {}, pins) == []


def test_voice_via_context():
    pins = {"models": [pin("claude-haiku-4-5", "config/m.yaml", "voice_supervisor")]}
    f = kinds(run({"launches": [launch("claude-haiku-4-6")]}, {}, pins), "new_model")[0]
    assert f["voice"] is True


def test_voice_via_pins_voice_key():
    pins = {"models": [], "voice": {"model": "gpt-4.1-mini", "source": "config/model_access.yaml:workloads.voice_supervisor"}}
    public = {"launches": [launch("gpt-4.2-mini")]}
    f = kinds(run(public, {}, pins), "new_model")[0]
    assert f["replaces"] == "gpt-4.1-mini"
    assert f["voice"] is True
    assert "voice" in f["roles"]


def test_voice_false_for_nonvoice_pin():
    pins = {"models": [pin("claude-fable-5", "config/a.yaml", "big")]}
    f = kinds(run({"launches": [launch("claude-fable-5-1")]}, {}, pins), "new_model")[0]
    assert f["voice"] is False


def test_claude_alias_probe_is_subscription_evidence():
    pins = {"models": [pin("claude-opus-5", "config/a.yaml")]}
    subs = {"claude": {"aliases": {"opus": {"ok": True, "model": "claude-opus-5-5"}}}}
    f = kinds(run({}, subs, pins), "new_model")[0]
    assert f["model"] == "claude-opus-5-5"
    assert f["on_subscription"] is True
    assert f["sources"] == ["claude_alias:opus"]


def test_failed_alias_probe_ignored():
    pins = {"models": [pin("claude-opus-5", "config/a.yaml")]}
    subs = {"claude": {"aliases": {"opus": {"ok": False, "model": "claude-opus-5-5"}}}}
    assert run({}, subs, pins) == []


def test_public_and_subscription_sources_merge():
    pins = {"models": [pin("claude-opus-5", "config/a.yaml")]}
    public = {"launches": [launch("claude-opus-5-5")]}
    subs = {"claude": {"aliases": {"opus": {"ok": True, "model": "claude-opus-5-5"}}}}
    f = kinds(run(public, subs, pins), "new_model")[0]
    assert f["sources"] == ["anthropic_release_notes", "claude_alias:opus"]
    assert f["on_subscription"] is True


# ---------------------------------------------------------- Codex default rule
def codex(default, models, ok=True):
    return {"codex": {"ok": ok, "default": default, "models": models}}


def cm(mid, hidden=False):
    return {"id": mid, "display_name": mid, "is_default": False, "hidden": hidden}


def test_codex_default_candidate():
    pins = {"models": [pin("gpt-6-astra", "config/a.yaml", "big")]}
    subs = codex("gpt-6.2-sol", [cm("gpt-6-astra"), cm("gpt-6.2-sol")])
    f = kinds(run({}, subs, pins), "new_model")
    assert len(f) == 1
    assert f[0]["model"] == "gpt-6.2-sol"
    assert f[0]["replaces"] == "gpt-6-astra"
    assert f[0]["reason"] == "new Codex default"
    assert f[0]["key"] == "new_model:gpt-6-astra->gpt-6.2-sol"
    assert f[0]["on_subscription"] is True
    assert f[0]["sources"] == ["codex_model_list"]


def test_codex_default_skipped_when_same_lineage_newer_exists():
    pins = {"models": [pin("gpt-6-astra", "config/a.yaml")]}
    subs = codex("gpt-6.2-sol", [cm("gpt-6-astra"), cm("gpt-6.1-astra"), cm("gpt-6.2-sol")])
    f = kinds(run({}, subs, pins), "new_model")
    assert len(f) == 1
    assert f[0]["model"] == "gpt-6.1-astra"
    assert f[0]["reason"] == "newer release"


def test_codex_default_ignored_for_openai_pin_not_offered_by_codex():
    pins = {"models": [pin("gpt-4.1-mini", "config/a.yaml")]}
    subs = codex("gpt-6.2-sol", [cm("gpt-6-astra"), cm("gpt-6.2-sol")])
    assert kinds(run({}, subs, pins), "new_model") == []


def test_codex_default_not_used_when_already_pinned():
    pins = {"models": [pin("gpt-6.2-sol", "config/a.yaml"), pin("gpt-6-astra", "config/b.yaml")]}
    subs = codex("gpt-6.2-sol", [cm("gpt-6-astra"), cm("gpt-6.2-sol")])
    assert kinds(run({}, subs, pins), "new_model") == []


def test_codex_not_ok_gives_no_candidate():
    pins = {"models": [pin("gpt-6-astra", "config/a.yaml")]}
    subs = codex("gpt-6.2-sol", [cm("gpt-6-astra"), cm("gpt-6.2-sol")], ok=False)
    assert kinds(run({}, subs, pins), "new_model") == []


def test_hidden_codex_models_ignored():
    pins = {"models": [pin("gpt-6-astra", "config/a.yaml")]}
    subs = codex("gpt-6-astra", [cm("gpt-6-astra"), cm("gpt-6.1-astra", hidden=True)])
    assert kinds(run({}, subs, pins), "new_model") == []


# ------------------------------------------------------------- deprecations
def dep_public(state="deprecated", retirement="2026-11-30", replacement="claude-sonnet-5-5"):
    return {"deprecations": [{"model": "claude-sonnet-4-5-20250929", "state": state,
                              "retirement": retirement, "replacement": replacement,
                              "source": "anthropic_deprecations"}]}


DEP_PINS = {"models": [pin("claude-sonnet-4-5", "config/a.yaml", "fast")]}


@pytest.mark.parametrize("today,days,level", [
    (date(2026, 11, 23), 7, "urgent"),
    (date(2026, 10, 15), 46, "notice"),
    (date(2026, 11, 5), 25, "task"),
    (date(2026, 12, 1), -1, "retired"),
])
def test_deprecation_levels(today, days, level):
    f = kinds(run(dep_public(), {}, DEP_PINS, today=today), "deprecation")
    assert len(f) == 1
    assert f[0]["days_left"] == days
    assert f[0]["level"] == level
    assert f[0]["model"] == "claude-sonnet-4-5"
    assert f[0]["vendor_model"] == "claude-sonnet-4-5-20250929"
    assert f[0]["key"] == "deprecation:claude-sonnet-4-5"
    assert f[0]["replacement"] == "claude-sonnet-5-5"
    assert f[0]["files"] == ["config/a.yaml"]


def test_retired_state_row_is_retired_level_even_with_future_date():
    f = kinds(run(dep_public(state="retired"), {}, DEP_PINS), "deprecation")[0]
    assert f["level"] == "retired"


def test_deprecation_without_date_is_notice():
    f = kinds(run(dep_public(retirement=None), {}, DEP_PINS), "deprecation")[0]
    assert f["days_left"] is None
    assert f["level"] == "notice"


def test_deprecation_bad_date_is_notice():
    f = kinds(run(dep_public(retirement="soon"), {}, DEP_PINS), "deprecation")[0]
    assert f["days_left"] is None and f["level"] == "notice"


def test_active_row_is_not_a_deprecation():
    assert kinds(run(dep_public(state="active"), {}, DEP_PINS), "deprecation") == []


def test_deprecation_for_unpinned_model_ignored():
    pins = {"models": [pin("claude-haiku-4-5", "config/a.yaml")]}
    assert kinds(run(dep_public(), {}, pins), "deprecation") == []


def test_deprecation_replacement_falls_back_to_newest_in_lineage():
    public = dep_public(replacement=None)
    public["launches"] = [launch("claude-sonnet-5-5")]
    f = kinds(run(public, {}, DEP_PINS), "deprecation")[0]
    assert f["replacement"] == "claude-sonnet-5-5"


def test_findings_ordered_deprecations_then_new_then_cli():
    pins = {"models": [pin("claude-sonnet-4-5", "config/a.yaml"),
                       pin("claude-fable-5", "config/b.yaml")],
            "cli": {"claude": []}}
    public = dep_public()
    public["launches"] = [launch("claude-fable-5-1")]
    out = run(public, {}, pins, installed={"claude": "2.1.330 (Claude Code)"})
    assert [f["kind"] for f in out] == ["deprecation", "new_model", "cli"]


def test_deprecations_sorted_by_level_then_days():
    pins = {"models": [pin("claude-sonnet-4-5", "a"), pin("claude-haiku-4-5", "b")]}
    public = {"deprecations": [
        {"model": "claude-sonnet-4-5", "state": "deprecated", "retirement": "2027-01-20"},
        {"model": "claude-haiku-4-5", "state": "deprecated", "retirement": "2026-11-25"},
    ]}
    out = kinds(run(public, {}, pins), "deprecation")
    assert [f["model"] for f in out] == ["claude-haiku-4-5", "claude-sonnet-4-5"]


# ---------------------------------------------------------------- candidates
def test_candidates_adds_deprecation_replacement_with_reason():
    fs = run(dep_public(), {}, DEP_PINS)
    cands = d.candidates(fs)
    assert len(cands) == 1
    c = cands[0]
    assert c["kind"] == "new_model"
    assert c["model"] == "claude-sonnet-5-5"
    assert c["replaces"] == "claude-sonnet-4-5"
    assert c["key"] == "new_model:claude-sonnet-4-5->claude-sonnet-5-5"
    assert "retires on 2026-11-30" in c["reason"]
    assert c["files"] == ["config/a.yaml"]
    assert c["on_subscription"] is False


def test_candidates_reason_retired():
    fs = run(dep_public(), {}, DEP_PINS, today=date(2026, 12, 5))
    assert "retired on 2026-11-30" in d.candidates(fs)[0]["reason"]


def test_candidates_does_not_duplicate_when_new_model_covers_pin():
    public = dep_public()
    public["launches"] = [launch("claude-sonnet-5-6")]
    fs = run(public, {}, DEP_PINS)
    cands = d.candidates(fs)
    assert [c["model"] for c in cands] == ["claude-sonnet-5-6"]


def test_candidates_skips_deprecation_without_replacement():
    fs = run(dep_public(replacement=None), {}, DEP_PINS)
    assert d.candidates(fs) == []


# ----------------------------------------------------------------------- cli
def cli_pins(claude=(), codex_=()):
    return {"models": [], "cli": {"claude": list(claude), "codex": list(codex_)}}


def test_cli_unverified_and_not_behind():
    out = kinds(run({"cli_latest": {"claude": "2.1.330"}}, {},
                    cli_pins(claude=["2.1.291 (Claude Code)"]),
                    installed={"claude": "2.1.330 (Claude Code)"}), "cli")
    assert len(out) == 1
    f = out[0]
    assert f["installed_verified"] is False
    assert f["behind"] is False
    assert f["cli"] == "claude"
    assert f["verified"] == ["2.1.291 (Claude Code)"]
    assert f["key"] == "cli:claude:2.1.330 (Claude Code):2.1.330"


def test_cli_verified_and_current_no_finding():
    out = run({"cli_latest": {"claude": "2.1.330"}}, {},
              cli_pins(claude=["2.1.330 (Claude Code)"]),
              installed={"claude": "2.1.330 (Claude Code)"})
    assert kinds(out, "cli") == []


def test_codex_verified_but_behind():
    out = kinds(run({"cli_latest": {"codex": "0.171.0"}}, {},
                    cli_pins(codex_=["codex-cli 0.160.0"]),
                    installed={"codex": "codex-cli 0.160.0"}), "cli")
    assert len(out) == 1
    assert out[0]["installed_verified"] is True
    assert out[0]["behind"] is True
    assert out[0]["cli"] == "codex"


def test_cli_installed_defaults_to_subs_claude_version():
    subs = {"claude": {"version": "2.1.330 (Claude Code)"}}
    out = kinds(run({"cli_latest": {"claude": "2.1.330"}}, subs, cli_pins()), "cli")
    assert [f["cli"] for f in out] == ["claude"]


def test_cli_not_installed_skipped():
    assert kinds(run({"cli_latest": {"claude": "2.1.330"}}, {}, cli_pins()), "cli") == []


def test_cli_unparseable_installed_is_unverified_not_behind():
    out = kinds(run({"cli_latest": {"claude": "2.1.330"}}, {}, cli_pins(claude=["x"]),
                    installed={"claude": "weird"}), "cli")
    assert out[0]["installed_verified"] is False and out[0]["behind"] is False


def test_version_tuple_parsing_and_prerelease_order():
    assert d._version_tuple("2.1.330 (Claude Code)") == (2, 1, 330, 1)
    assert d._version_tuple("codex-cli 0.171.0") == (0, 171, 0, 1)
    assert d._version_tuple("garbage") is None
    assert d._version_tuple(None) is None
    alpha = d._version_tuple("0.163.0-alpha.1")
    rel = d._version_tuple("0.163.0")
    assert alpha < rel
    assert sorted([rel, alpha]) == [alpha, rel]
    assert d._version_tuple("0.163.1-alpha") > rel


def test_prerelease_installed_not_behind_same_release():
    # alpha of the same x.y.z is compared on the first three fields only
    out = kinds(run({"cli_latest": {"codex": "0.163.0"}}, {},
                    cli_pins(codex_=["0.163.0-alpha"]),
                    installed={"codex": "0.163.0-alpha"}), "cli")
    assert out == []


# ------------------------------------------------------------------ robustness
def test_non_dict_inputs_do_not_raise():
    assert d.detect(None, None, None, today=TODAY) == []  # type: ignore[arg-type]
    assert d.detect([], "x", 3, today=TODAY) == []  # type: ignore[arg-type]
