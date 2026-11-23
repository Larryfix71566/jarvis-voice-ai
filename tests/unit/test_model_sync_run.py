"""Unit tests for jarvis.model_sync.run (WS-41). All deps injected; no CLI, no network."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from jarvis.model_sync import run as r

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("MORTIMER_MODEL_SYNC", "MORTIMER_MODEL_SYNC_CERTIFY",
                 "MORTIMER_MODEL_SYNC_PROPOSE"):
        monkeypatch.delenv(name, raising=False)


class Notices:
    def __init__(self, result=1, raises=False):
        self.calls = []
        self.result = result
        self.raises = raises

    def __call__(self, kind, key, text):
        self.calls.append((kind, key, text))
        if self.raises:
            raise RuntimeError("notice boom")
        return self.result

    @property
    def texts(self):
        return [c[2] for c in self.calls]


class Harness:
    """Recording deps. Mutate the attributes between runs."""

    def __init__(self, pins=None, launches=None, deprecations=None, claude_version="2.1.330 (Claude Code)",
                 cert_passed=True, cli_verified=None):
        self.public = {"sources": {"x": {"ok": True}}, "launches": launches or [],
                       "deprecations": deprecations or [], "cli_latest": {}}
        self.subs = {"claude": {"version": claude_version, "aliases": {}},
                     "codex": {"ok": False}, "kimi": {"ok": False, "category": "unsupported"}}
        self.pins = {"models": pins or [], "voice": None,
                     "cli": cli_verified or {"claude": [claude_version], "codex": []}}
        self.codex_version = None
        self.cert_passed = cert_passed
        self.certify_calls = []
        self.propose_calls = []
        self.propose_result = {"status": "pr_opened", "url": "https://example.invalid/pr/1"}
        self.public_raises = False

    def _public(self):
        if self.public_raises:
            raise ValueError("public boom")
        return self.public

    def _certify(self, cand, status_dir):
        self.certify_calls.append((cand, status_dir))
        return {"model": cand["model"], "passed": self.cert_passed,
                "certified_at": NOW.isoformat(timespec="seconds"),
                "steps": [{"name": "exact_probe", "ok": self.cert_passed,
                           "detail": "ok" if self.cert_passed else "no_such_model"}],
                "manual": []}

    def _propose(self, old, new, files, evidence, status_dir):
        self.propose_calls.append((old, new, files, evidence, status_dir))
        return dict(self.propose_result)

    @property
    def deps(self):
        return {"public": self._public, "subs": lambda: self.subs, "pins": lambda: self.pins,
                "codex_version": lambda: self.codex_version,
                "certify": self._certify, "propose": self._propose}


def pin(model, file, context="big"):
    return {"model": model, "raw": model, "file": file, "line": 1, "context": context}


def launch(model):
    return {"model": model, "vendor": "anthropic", "date": "2026-11-20", "source": "release_notes"}


def one_candidate(**kw):
    return Harness(pins=[pin("claude-fable-5", "config/a.yaml"),
                         pin("claude-fable-5", ".env:JARVIS_VOICE_MODEL", "voice")],
                   launches=[launch("claude-fable-5-1")], **kw)


def go(h, tmp_path, notice, **kw):
    kw.setdefault("now", NOW)
    return r.run_daily(tmp_path, deps=h.deps, notice=notice, **kw)


def read(tmp_path, name):
    return json.loads((tmp_path / name).read_text())


# ------------------------------------------------------------------ first run
def test_first_run_certifies_proposes_reports_and_notifies(tmp_path):
    h, n = one_candidate(), Notices()
    rep = go(h, tmp_path, n)
    assert rep["ok"] is True and rep["automatic_switch"] is False
    assert len(h.certify_calls) == 1
    cand = h.certify_calls[0][0]
    assert cand["model"] == "claude-fable-5-1" and cand["replaces"] == "claude-fable-5"
    assert h.certify_calls[0][1] == tmp_path
    assert len(h.propose_calls) == 1
    old, new, files, evidence, sd = h.propose_calls[0]
    assert (old, new) == ("claude-fable-5", "claude-fable-5-1")
    assert files == ["config/a.yaml"]
    assert evidence["reason"] == "newer release"
    assert evidence["certification"]["passed"] is True
    assert sd == tmp_path
    assert (tmp_path / "model-sync.json").is_file()
    assert (tmp_path / "model-sync-state.json").is_file()
    assert len(n.calls) == 1
    assert n.calls[0][:2] == ("daily_status", "model-sync")
    assert n.texts[0].startswith("Model check:")
    assert "claude-fable-5-1" in n.texts[0]
    assert "pull request is waiting" in n.texts[0]
    saved = read(tmp_path, "model-sync.json")
    assert saved["ok"] is True and saved["notice"] == n.texts[0]
    assert saved["candidates"][0]["proposal"]["status"] == "pr_opened"
    state = read(tmp_path, "model-sync-state.json")
    assert "notified_at" in state["candidates"]["new_model:claude-fable-5->claude-fable-5-1"]


def test_second_run_same_inputs_is_quiet_and_does_not_recertify(tmp_path):
    h, n = one_candidate(), Notices()
    go(h, tmp_path, n)
    rep = go(h, tmp_path, n, now=NOW + timedelta(days=1))
    assert len(h.certify_calls) == 1
    assert len(h.propose_calls) == 1
    assert len(n.calls) == 1
    assert rep["notice"] is None
    assert rep["candidates"][0]["changed"] is False


# ------------------------------------------------------------ failed certification
def test_failed_cert_not_retried_next_day(tmp_path):
    h, n = one_candidate(cert_passed=False), Notices()
    go(h, tmp_path, n)
    assert h.propose_calls == []
    assert "failed the exact probe check (no_such_model)" in n.texts[0]
    go(h, tmp_path, n, now=NOW + timedelta(days=1))
    assert len(h.certify_calls) == 1
    assert len(n.calls) == 1


def test_failed_cert_retried_when_cli_version_changes(tmp_path):
    h, n = one_candidate(cert_passed=False), Notices()
    go(h, tmp_path, n)
    h.subs["claude"]["version"] = "2.1.400 (Claude Code)"
    go(h, tmp_path, n, now=NOW + timedelta(days=1))
    assert len(h.certify_calls) == 2


def test_failed_cert_retried_after_seven_days(tmp_path):
    h, n = one_candidate(cert_passed=False), Notices()
    go(h, tmp_path, n)
    go(h, tmp_path, n, now=NOW + timedelta(days=6))
    assert len(h.certify_calls) == 1
    go(h, tmp_path, n, now=NOW + timedelta(days=7))
    assert len(h.certify_calls) == 2


def test_certify_exception_recorded_as_failed_and_error(tmp_path):
    h, n = one_candidate(), Notices()
    deps = h.deps
    deps["certify"] = lambda c, s: (_ for _ in ()).throw(RuntimeError("cert boom"))
    rep = r.run_daily(tmp_path, deps=deps, notice=n, now=NOW)
    assert rep["ok"] is True
    assert any(e["step"] == "certify:claude-fable-5-1" and "cert boom" in e["error"]
               for e in rep["errors"])
    assert rep["candidates"][0]["certification"]["passed"] is False
    assert h.propose_calls == []


def test_propose_exception_recorded(tmp_path):
    h, n = one_candidate(), Notices()
    deps = h.deps
    deps["propose"] = lambda *a: (_ for _ in ()).throw(RuntimeError("pr boom"))
    rep = r.run_daily(tmp_path, deps=deps, notice=n, now=NOW)
    assert rep["candidates"][0]["proposal"]["status"] == "error"
    assert any(e["step"].startswith("propose:") for e in rep["errors"])
    assert "opening the pull request failed" in n.texts[0]


def test_passed_cert_with_failed_proposal_retries_propose_only(tmp_path):
    h, n = one_candidate(), Notices()
    h.propose_result = {"status": "error"}
    go(h, tmp_path, n)
    h.propose_result = {"status": "pr_opened"}
    go(h, tmp_path, n, now=NOW + timedelta(days=1))
    assert len(h.certify_calls) == 1
    assert len(h.propose_calls) == 2


# -------------------------------------------------------------- manual proposals
def test_env_only_candidate_is_manual_without_propose(tmp_path):
    h = Harness(pins=[pin("claude-fable-5", ".env:JARVIS_VOICE_MODEL", "voice")],
                launches=[launch("claude-fable-5-1")])
    n = Notices()
    rep = go(h, tmp_path, n)
    assert len(h.certify_calls) == 1
    assert h.propose_calls == []
    prop = rep["candidates"][0]["proposal"]
    assert prop["status"] == "manual"
    assert "by hand" in prop["instruction"]
    assert "switch it by hand" in n.texts[0]
    # manual counts as done: no recertify next day
    go(h, tmp_path, n, now=NOW + timedelta(days=1))
    assert len(h.certify_calls) == 1


# -------------------------------------------------------------------- switches
def test_certify_false_reports_only(tmp_path):
    h, n = one_candidate(), Notices()
    rep = go(h, tmp_path, n, certify=False)
    assert h.certify_calls == [] and h.propose_calls == []
    assert len(rep["findings"]) == 1
    assert rep["candidates"][0]["certification"] is None
    assert "not tested yet" in n.texts[0]


def test_env_certify_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("MORTIMER_MODEL_SYNC_CERTIFY", "0")
    h = one_candidate()
    go(h, tmp_path, Notices())
    assert h.certify_calls == [] and h.propose_calls == []


def test_env_propose_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("MORTIMER_MODEL_SYNC_PROPOSE", "0")
    h, n = one_candidate(), Notices()
    rep = go(h, tmp_path, n)
    assert len(h.certify_calls) == 1 and h.propose_calls == []
    assert rep["candidates"][0]["proposal"] is None
    assert "tested" in n.texts[0]


def test_explicit_args_override_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MORTIMER_MODEL_SYNC_CERTIFY", "0")
    h = one_candidate()
    go(h, tmp_path, Notices(), certify=True)
    assert len(h.certify_calls) == 1


def test_master_switch_skips(tmp_path, monkeypatch):
    monkeypatch.setenv("MORTIMER_MODEL_SYNC", "0")
    h, n = one_candidate(), Notices()
    rep = go(h, tmp_path, n)
    assert rep == {"ok": False, "skipped": "MORTIMER_MODEL_SYNC=0"}
    assert h.certify_calls == [] and n.calls == []
    assert not (tmp_path / "model-sync.json").exists()


def test_max_certify_per_run(tmp_path):
    assert r.MAX_CERTIFY_PER_RUN == 3
    names = ["fable", "opus", "sonnet", "haiku"]
    h = Harness(pins=[pin(f"claude-{x}-5", f"config/{x}.yaml") for x in names],
                launches=[launch(f"claude-{x}-6") for x in names])
    rep = go(h, tmp_path, Notices())
    assert len(rep["candidates"]) == 4
    assert len(h.certify_calls) == 3
    # the fourth is picked up on the next run (CLI unchanged, never certified)
    go(h, tmp_path, Notices(), now=NOW + timedelta(days=1))
    assert len(h.certify_calls) == 4


# ----------------------------------------------------------------------- notices
def test_many_candidates_use_compact_sentence_and_cap_length(tmp_path):
    names = ["fable", "opus", "sonnet", "haiku", "mythos"]
    h = Harness(pins=[pin(f"claude-{x}-5", f"config/{x}.yaml") for x in names],
                launches=[launch(f"claude-{x}-6") for x in names])
    n = Notices()
    go(h, tmp_path, n)
    text = n.texts[0]
    assert "5 newer models could replace ones Mortimer uses" in text
    assert "3 pull requests waiting for you" in text
    assert len(text) <= r.MAX_NOTICE_CHARS


def test_notice_truncated_to_max_chars():
    outcomes = [{"model": "claude-x-" + "a" * 100, "replaces": "claude-y-" + "b" * 100,
                 "proposal": None, "certification": None}] * 3
    text = r.notice_text(outcomes, [], [])
    assert len(text) == r.MAX_NOTICE_CHARS and text.endswith("…")


def test_notice_text_empty_when_nothing():
    assert r.notice_text([], [], []) == ""


def test_notice_text_cli_phrases():
    unv = {"cli": "codex", "installed": "0.1.0", "latest": "0.2.0",
           "installed_verified": False, "behind": True}
    beh = {"cli": "claude", "installed": "1.0.0", "latest": "1.1.0",
           "installed_verified": True, "behind": True}
    text = r.notice_text([], [], [unv, beh])
    assert "Codex CLI on this Mac (0.1.0) isn't a version Mortimer has verified" in text
    assert "Claude CLI 1.1.0 is out" in text


def test_notice_text_retired_and_undated_deprecation():
    deps = [{"model": "m1", "level": "retired", "days_left": -3},
            {"model": "m2", "level": "notice", "days_left": None, "replacement": "m3"}]
    text = r.notice_text([], deps, [])
    assert "m1 has been retired and Mortimer still uses it." in text
    assert "m2 retires at a date not yet announced; the replacement is m3." in text


# ----------------------------------------------------------- deprecation speaking
def dep_harness(retirement="2026-12-31"):
    return Harness(pins=[pin("claude-sonnet-4-5", "config/a.yaml")],
                   deprecations=[{"model": "claude-sonnet-4-5-20250929", "state": "deprecated",
                                  "retirement": retirement, "replacement": None,
                                  "source": "deps"}])


def retires_count(n):
    return sum("retires" in t for t in n.texts)


def test_deprecation_spoken_first_time_then_not_at_same_level(tmp_path):
    h, n = dep_harness(), Notices()
    go(h, tmp_path, n, now=datetime(2026, 10, 15, 12, tzinfo=timezone.utc))
    assert retires_count(n) == 1
    assert "claude-sonnet-4-5 retires in 77 days" in n.texts[0]
    go(h, tmp_path, n, now=datetime(2026, 10, 16, 12, tzinfo=timezone.utc))
    assert retires_count(n) == 1


def test_deprecation_spoken_on_each_escalation_and_daily_while_urgent(tmp_path):
    h, n = dep_harness(), Notices()
    seq = [(datetime(2026, 10, 15, 12, tzinfo=timezone.utc), 1),   # notice, first sight
           (datetime(2026, 10, 16, 12, tzinfo=timezone.utc), 1),   # same level, quiet
           (datetime(2026, 12, 5, 12, tzinfo=timezone.utc), 2),    # task
           (datetime(2026, 12, 6, 12, tzinfo=timezone.utc), 2),    # task again, quiet
           (datetime(2026, 12, 25, 12, tzinfo=timezone.utc), 3),   # urgent
           (datetime(2026, 12, 26, 12, tzinfo=timezone.utc), 4),   # urgent again, spoken
           (datetime(2026, 12, 27, 12, tzinfo=timezone.utc), 5)]   # and again
    for when, expected in seq:
        go(h, tmp_path, n, now=when)
        assert retires_count(n) == expected, when
    go(h, tmp_path, n, now=datetime(2027, 1, 2, 12, tzinfo=timezone.utc))
    assert any("has been retired" in t for t in n.texts)


def test_failed_notice_delivery_repeats_deprecation_next_run(tmp_path):
    h = dep_harness()
    bad = Notices(result=-1)
    go(h, tmp_path, bad, now=datetime(2026, 10, 15, 12, tzinfo=timezone.utc))
    assert retires_count(bad) == 1
    good = Notices()
    go(h, tmp_path, good, now=datetime(2026, 10, 16, 12, tzinfo=timezone.utc))
    assert retires_count(good) == 1
    go(h, tmp_path, good, now=datetime(2026, 10, 17, 12, tzinfo=timezone.utc))
    assert retires_count(good) == 1


def test_raising_notice_recorded_and_deprecation_repeats(tmp_path):
    h = dep_harness()
    boom = Notices(raises=True)
    rep = go(h, tmp_path, boom, now=datetime(2026, 10, 15, 12, tzinfo=timezone.utc))
    assert rep["ok"] is True
    assert any(e["step"] == "notice" and "notice boom" in e["error"] for e in rep["errors"])
    good = Notices()
    go(h, tmp_path, good, now=datetime(2026, 10, 16, 12, tzinfo=timezone.utc))
    assert retires_count(good) == 1


def test_failed_notice_delivery_repeats_candidate_next_run(tmp_path):
    h = one_candidate()
    go(h, tmp_path, Notices(result=-1))
    good = Notices()
    go(h, tmp_path, good, now=NOW + timedelta(days=1))
    assert len(good.calls) == 1
    assert "claude-fable-5-1" in good.texts[0]
    assert len(h.certify_calls) == 1  # still certified only once


def test_cli_notice_spoken_once_per_distinct_finding(tmp_path):
    h, n = Harness(), Notices()
    h.public["cli_latest"] = {"claude": "2.1.330"}
    h.pins["cli"] = {"claude": ["2.1.291 (Claude Code)"], "codex": []}
    go(h, tmp_path, n)
    assert len(n.calls) == 1 and "isn't a version Mortimer has verified" in n.texts[0]
    go(h, tmp_path, n, now=NOW + timedelta(days=1))
    assert len(n.calls) == 1


# --------------------------------------------------------------- error handling
def test_dep_failure_recorded_and_report_still_written(tmp_path):
    h = one_candidate()
    h.public_raises = True
    rep = go(h, tmp_path, Notices())
    assert rep["ok"] is True
    assert rep["errors"][0]["step"] == "public"
    assert "public boom" in rep["errors"][0]["error"]
    saved = read(tmp_path, "model-sync.json")
    assert saved["errors"] == rep["errors"]
    assert saved["findings"] == []


def test_codex_version_failure_recorded(tmp_path):
    h = Harness()
    deps = h.deps
    deps["codex_version"] = lambda: (_ for _ in ()).throw(OSError("no codex"))
    rep = r.run_daily(tmp_path, deps=deps, notice=Notices(), now=NOW)
    assert rep["ok"] is True
    assert rep["errors"][0]["step"] == "codex_version"
    assert rep["installed_cli"]["codex"] is None


def test_unwritable_status_dir_never_raises(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    rep = r.run_daily(blocker / "sub", deps=Harness().deps, notice=Notices(), now=NOW)
    assert rep["ok"] is False
    assert rep["errors"][-1]["step"] == "run"


def test_report_has_no_api_key_text(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-appear")
    go(one_candidate(), tmp_path, Notices())
    for name in ("model-sync.json", "model-sync-state.json"):
        text = (tmp_path / name).read_text()
        assert "API_KEY" not in text
        assert "sk-should-not-appear" not in text


# ----------------------------------------------------------------- read_report
def test_read_report_missing(tmp_path):
    out = r.read_report(tmp_path)
    assert out["ok"] is False and "error" in out


def test_read_report_after_run(tmp_path):
    go(one_candidate(), tmp_path, Notices())
    out = r.read_report(tmp_path)
    assert out["ok"] is True
    assert out["report"]["generated_at"] == NOW.isoformat(timespec="seconds")
    assert out["report"]["candidates"][0]["model"] == "claude-fable-5-1"


def test_read_report_corrupt_file(tmp_path):
    (tmp_path / "model-sync.json").write_text("{not json")
    assert r.read_report(tmp_path)["ok"] is False


def test_state_corrupt_is_tolerated(tmp_path):
    (tmp_path / "model-sync-state.json").write_text("[1,2")
    h = one_candidate()
    rep = go(h, tmp_path, Notices())
    assert rep["ok"] is True and len(h.certify_calls) == 1
