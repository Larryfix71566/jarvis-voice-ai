"""T4.5 — the daily status job (fake collectors; no network, no CLI)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest

from jarvis.status import daily as D
from jarvis.status.catalog import CatalogResult
from jarvis.status.providers import ProviderRef

KEY = "sk-FIXTURE-SECRET-VALUE-0123456789abcdef"
NOW = datetime(2026, 9, 23, 10, 30, tzinfo=timezone.utc)


def _res(provider, ids, ok=True, category=None):
    return CatalogResult(provider=provider, ok=ok, fetched_at="2026-09-23T10:30:00+00:00",
                         source=f"{provider}:/v1/models",
                         models=tuple({"id": i, "display_name": None, "created": None} for i in ids),
                         error_category=category, error=None if ok else "HTTP 401")


def _snap(*, openrouter=("x-ai/grok-4.6", "a/b"), missing=(), codex_ok=True, codex_cat=None,
          keys=None, gaps=()):
    return {
        "generated_at": "2026-09-22T10:30:00+00:00",
        "catalogs": [{"provider": "openrouter", "ok": True,
                      "models": [{"id": i} for i in openrouter]},
                     {"provider": "saygm", "ok": True, "models": [{"id": "z"}]}],
        "comparison": {"openrouter": {"configured_available": ["or-grok-4.6"],
                                      "configured_missing": list(missing),
                                      "offered_not_configured_count": 1,
                                      "offered_not_configured_sample": ["a/b"]},
                       "saygm": {"configured_available": [], "configured_missing": [],
                                 "offered_not_configured_count": 1,
                                 "offered_not_configured_sample": ["z"]}},
        "subscriptions": {"claude": {"ok": True, "model": "claude-sonnet-5", "category": None},
                          "codex": {"ok": codex_ok, "model": "gpt-6-astra", "category": codex_cat}},
        "key_health": keys if keys is not None else {"ANTHROPIC_API_KEY": "ok",
                                                     "OPENROUTER_API_KEY": "ok"},
        "coverage_gaps": list(gaps),
    }


def test_daily_notice_text_golden():
    prev = _snap()
    cur = _snap(openrouter=("x-ai/grok-4.6", "a/b", "x-ai/grok-5", "google/gemini-4",
                            "meta/llama-5", "qwen/qwen-4"),
                missing=("or-gpt-5.1",), codex_ok=False, codex_cat="authentication",
                keys={"ANTHROPIC_API_KEY": "ok", "OPENROUTER_API_KEY": "unfunded"})
    cur["catalogs"][1]["models"].append({"id": "new-saygm-model"})  # no configured profile
    d = D.diff(prev, cur)
    assert d["new_offered"] == {"openrouter": ["x-ai/grok-5", "google/gemini-4",
                                               "meta/llama-5", "qwen/qwen-4"]}
    assert d["newly_missing"] == {"openrouter": ["or-gpt-5.1"]}
    assert D.daily_notice_text(d) == (
        "Daily check: OpenRouter added 4 models (x-ai/grok-5, google/gemini-4, meta/llama-5, …). "
        "OpenRouter no longer offers or-gpt-5.1. "
        "Codex subscription probe failed: authentication. "
        "OPENROUTER_API_KEY is now unfunded (was ok).")


def test_recovery_and_gaps_text():
    prev = _snap(codex_ok=False, codex_cat="timeout")
    cur = _snap(gaps=("unknown:api.newco.ai",))
    assert D.daily_notice_text(D.diff(prev, cur)) == (
        "Daily check: Codex subscription probe works again. "
        "No catalog adapter for: unknown:api.newco.ai.")


def test_no_change_no_notice(tmp_path):
    assert D.daily_notice_text(D.diff(_snap(), _snap())) == ""
    assert not D.has_changes(D.diff(_snap(), _snap()))
    # A provider whose fetch failed yesterday does not make today's list "new".
    prev = _snap()
    prev["catalogs"][0]["ok"] = False
    assert D.diff(prev, _snap())["new_offered"] == {}
    # First run ever: nothing to compare, and no gaps -> no notice.
    assert D.daily_notice_text(D.diff(None, _snap())) == ""


def test_notice_is_capped():
    cur = _snap(openrouter=tuple(f"vendor-{i}/model-with-a-long-name-{i}" for i in range(80)),
                missing=tuple(f"or-profile-{i}-with-long-name" for i in range(40)))
    text = D.daily_notice_text(D.diff(_snap(), cur))
    assert len(text) <= D.MAX_NOTICE_CHARS == 600


def _deps(**over):
    ref_or = ProviderRef("openrouter", "llm", "openai_models", "https://openrouter.ai/api/v1",
                         "OPENROUTER_API_KEY", ("registry:or-grok",), ("or-grok",))
    registry = {"profiles": {"or-grok": {"model": "x-ai/grok-5", "base_url": "https://openrouter.ai/api/v1",
                                          "api_key_env": "OPENROUTER_API_KEY"}}}
    deps = {
        "registry": lambda: registry,
        "discover": lambda reg: [ref_or],
        "fetch_all": lambda refs: [_res("openrouter", ["x-ai/grok-5", "a/b"])],
        "compare": lambda results, reg: {"openrouter": {
            "configured_available": ["or-grok"], "configured_missing": [],
            "offered_not_configured_count": 1, "offered_not_configured_sample": ["a/b"]}},
        "probe": lambda which: {"which": which, "ok": True, "model": "m", "category": None},
        "keyprobe": lambda reg: {"OPENROUTER_API_KEY": "ok"},
        "access_status": lambda reg: {"coverage_gaps": []},
        "head": lambda: "abc1234",
    }
    deps.update(over)
    return deps


def test_run_writes_snapshot_and_notices_only_on_change(tmp_path):
    notices = []
    snap = D.run(status_dir=tmp_path, deps=_deps(), now=NOW,
                 notice=lambda *a: notices.append(a) or 1)
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == [f"daily-{NOW.astimezone().date().isoformat()}.json"]
    written = json.loads((tmp_path / files[0]).read_text())
    assert set(written) >= {"generated_at", "source_head", "coverage_gaps", "catalogs",
                            "comparison", "subscriptions", "key_health", "errors"}
    assert written["source_head"] == "abc1234"
    assert written["catalogs"][0]["provider"] == "openrouter"
    assert set(written["subscriptions"]) == {"claude", "codex"}
    assert snap["notice"] is None and notices == []
    # Next day: OpenRouter adds a model -> exactly one notice.
    later = datetime(2026, 9, 24, 10, 30, tzinfo=timezone.utc)
    D.run(status_dir=tmp_path, deps=_deps(fetch_all=lambda refs: [
        _res("openrouter", ["x-ai/grok-5", "a/b", "x-ai/grok-6"])]), now=later,
        notice=lambda *a: notices.append(a) or 1)
    assert notices == [("daily_status", "daily",
                        "Daily check: OpenRouter added 1 model (x-ai/grok-6).")]
    # Same day again, nothing new versus yesterday's file -> still that one notice.
    D.run(status_dir=tmp_path, deps=_deps(fetch_all=lambda refs: [
        _res("openrouter", ["x-ai/grok-5", "a/b"])]), now=later,
        notice=lambda *a: notices.append(a) or 1)
    assert len(notices) == 1


def test_retention_keeps_30(tmp_path):
    for i in range(35):
        (tmp_path / f"daily-2026-08-{i + 1:02d}.json").write_text("{}")
    (tmp_path / "unrelated.txt").write_text("keep")
    D.run(status_dir=tmp_path, deps=_deps(), now=NOW, notice=lambda *a: 1)
    daily = sorted(p.name for p in tmp_path.iterdir() if p.name.startswith("daily-"))
    assert len(daily) == 30
    assert daily[-1] == f"daily-{NOW.astimezone().date().isoformat()}.json"
    assert daily[0] == "daily-2026-08-07.json"
    assert (tmp_path / "unrelated.txt").exists()


def test_atomic_write(tmp_path, monkeypatch):
    target = tmp_path / "daily-2026-09-23.json"
    target.write_text('{"old": true}')
    replaced = []
    real_replace = os.replace

    def spy(src, dst):
        replaced.append((os.path.dirname(src), os.path.basename(dst)))
        assert json.loads(open(src).read()) == {"new": True}  # complete before the swap
        return real_replace(src, dst)

    monkeypatch.setattr(D.os, "replace", spy)
    D.write_atomic(target, {"new": True})
    assert replaced == [(str(tmp_path), target.name)]
    assert json.loads(target.read_text()) == {"new": True}
    # A failure mid-write leaves the old file and no temp file behind.
    monkeypatch.setattr(D.json, "dump", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        D.write_atomic(target, {"newer": True})
    assert json.loads(target.read_text()) == {"new": True}
    assert [p.name for p in tmp_path.iterdir()] == [target.name]


def test_failing_provider_is_recorded_without_an_exception(tmp_path):
    def boom(*a):
        raise RuntimeError(f"network down, key {KEY}")

    snap = D.run(status_dir=tmp_path, now=NOW, notice=lambda *a: 1, deps=_deps(
        fetch_all=lambda refs: [_res("openrouter", ["x"]),
                                _res("moonshot", [], ok=False, category="rejected")],
        probe=boom, keyprobe=boom, head=boom))
    assert snap["catalogs"][1]["error_category"] == "rejected"
    steps = [e["step"] for e in snap["errors"]]
    assert steps == ["source_head", "subscription:claude", "subscription:codex", "key_health"]
    blob = (tmp_path / f"daily-{NOW.astimezone().date().isoformat()}.json").read_text()
    assert KEY not in blob and "FIXTURE-SECRET" not in blob
    # Even a failing catalog step does not stop the rest.
    snap2 = D.run(status_dir=tmp_path, now=NOW, notice=lambda *a: 1,
                  deps=_deps(fetch_all=boom, discover=boom))
    assert [e["step"] for e in snap2["errors"]] == ["discover_providers", "catalogs"]
    assert set(snap2["subscriptions"]) == {"claude", "codex"}


def test_main_always_exits_zero(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "daily.db"))  # main migrates
    monkeypatch.setattr(D, "run", lambda **k: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr("jarvis.vault.inject_env", lambda: (_ for _ in ()).throw(RuntimeError("v")))
    assert D.main() == 0


def test_default_collectors_cover_every_configured_provider(monkeypatch):
    """The daily job's catalog step is fetch_all over catalog_refs of
    discover_providers() — every configured model provider, never a list."""
    from jarvis.status import catalog
    from jarvis.status.providers import discover_providers

    seen = []
    monkeypatch.setattr(catalog, "fetch_all",
                        lambda refs, force=False, **kw: seen.append((list(refs), force)) or [])
    deps = D._default_deps()
    deps["fetch_all"](discover_providers())
    refs, force = seen[0]
    assert force is True
    assert [r.id for r in refs] == [r.id for r in discover_providers() if r.kind == "llm"]
    assert {"anthropic", "openrouter", "moonshot", "saygm", "voice",
            "claude-subscription", "codex-subscription"} <= {r.id for r in refs}
