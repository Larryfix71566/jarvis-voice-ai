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


# ---- spec P5 A3: per-endpoint catalogues rendered into data/status/generated/

from jarvis.agents import upgrade_agent as ua  # noqa: E402

OR_URL = "https://openrouter.ai/api/v1"
AN_URL = "https://api.anthropic.com/v1/"
MS_URL = "https://api.moonshot.ai/v1"

LAYERS = {
    "shape": "split",
    "endpoints": {
        "anthropic": {"provider": "anthropic", "base_url": AN_URL, "api_key_env": "ANTHROPIC_API_KEY"},
        "codex-subscription": {"provider": "openai", "kind": "subscription",
                               "route": "codex_subscription"},
        "moonshot": {"provider": "moonshot", "base_url": MS_URL, "api_key_env": "MOONSHOT_API_KEY"},
        "openrouter": {"provider": "openrouter", "base_url": OR_URL,
                       "api_key_env": "OPENROUTER_API_KEY"},
    },
    "profiles": [
        {"name": "claude-opus", "endpoint": "anthropic", "identity": "anthropic/claude-opus-5",
         "model": "claude-opus-5"},
        {"name": "codex-subscription", "endpoint": "codex-subscription",
         "identity": "openai/gpt-6-astra", "model": "gpt-6-astra"},
        {"name": "kimi-k3", "endpoint": "moonshot", "identity": "moonshotai/kimi-k3",
         "model": "kimi-k3"},
        {"name": "or-grok-4.6", "endpoint": "openrouter", "identity": "x-ai/grok-4.6",
         "model": "x-ai/grok-4.6"},
    ],
}

REFS = [
    ProviderRef("anthropic", "llm", "anthropic_models", AN_URL, "ANTHROPIC_API_KEY",
                ("registry:claude-opus",), ("claude-opus",)),
    ProviderRef("codex-subscription", "llm", "subscription_probe", "subscription://codex", None,
                ("registry:codex-subscription",), ("codex-subscription",)),
    ProviderRef("moonshot", "llm", "openai_models", MS_URL, "MOONSHOT_API_KEY",
                ("registry:kimi-k3",), ("kimi-k3",)),
    ProviderRef("openrouter", "llm", "openai_models", OR_URL, "OPENROUTER_API_KEY",
                ("registry:or-grok-4.6",), ("or-grok-4.6",)),
]

OR_FACTS = {"x-ai/grok-4.6": {"pricing": {"prompt": "0.000003", "completion": "0.000015"},
                              "context_length": 256000},
            "openai/gpt-5.1": {"pricing": {"prompt": "0.00000125", "completion": "0.00001"}},
            "openrouter/auto": {"pricing": {"prompt": "-1", "completion": "-1"}}}


def _results(*, moonshot_ok=True):
    anth = _res("anthropic", ["claude-opus-5", "claude-haiku-4-5"])
    orr = CatalogResult(**{**_res("openrouter", ["x-ai/grok-4.6", "openai/gpt-5.1",
                                                 "openrouter/auto"]).__dict__, "facts": OR_FACTS})
    ms = _res("moonshot", ["kimi-k3", "kimi-k4"]) if moonshot_ok else \
        _res("moonshot", [], ok=False, category="rejected")
    codex = _res("codex-subscription", [], ok=False, category="unsupported")
    return [anth, codex, ms, orr]


def _load(out_dir):
    """Read the rendered files back with the loader's own catalogue reader."""
    return ua.load_upstream_catalogs(config_dir=out_dir.parent)


def _tree_digest(root):
    import hashlib

    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def test_catalogues_render_per_endpoint_in_the_4a_schema(tmp_path):
    out_dir = tmp_path / "generated"
    report = D.render_endpoint_catalogs(LAYERS, REFS, _results(), out_dir=out_dir)
    assert sorted(p.name for p in out_dir.iterdir()) == [
        "model_catalog.anthropic.json", "model_catalog.moonshot.json",
        "model_catalog.openrouter.json"]
    assert report["codex-subscription"] == {"skipped": "no model list (unsupported)"}
    assert report["openrouter"] == {"file": "model_catalog.openrouter.json", "models": 3}
    catalogs = _load(out_dir)
    for eid, cat in catalogs.items():
        assert cat["provider"] == LAYERS["endpoints"][eid]["provider"]
        assert "GENERATED" in cat["_generated"] and cat["schema"] == 1
        for entry in cat["models"]:
            assert tuple(entry) == ua.CATALOG_ENTRY_KEYS, entry
            assert "/" in entry["identity"]
            assert entry["fetched_at"] == "2026-09-23T10:30:00+00:00"
            assert entry["source"] == f"{eid}:/v1/models"
    by_model = {e["model"]: e for e in catalogs["openrouter"]["models"]}
    assert by_model["x-ai/grok-4.6"] == {
        "identity": "x-ai/grok-4.6", "model": "x-ai/grok-4.6", "context_window": 256000,
        "input_price_per_mtok": 3.0, "output_price_per_mtok": 15.0, "input_modalities": None,
        "deprecation": None, "fetched_at": "2026-09-23T10:30:00+00:00",
        "source": "openrouter:/v1/models"}
    assert (by_model["openai/gpt-5.1"]["input_price_per_mtok"],
            by_model["openai/gpt-5.1"]["output_price_per_mtok"],
            by_model["openai/gpt-5.1"]["context_window"]) == (1.25, 10.0, None)
    # A variable-price router publishes -1: not a price.
    assert by_model["openrouter/auto"]["input_price_per_mtok"] is None
    # No published prices -> null, never invented.
    anth = {e["model"]: e for e in catalogs["anthropic"]["models"]}
    assert anth["claude-opus-5"]["identity"] == "anthropic/claude-opus-5"  # the profile's
    assert anth["claude-haiku-4-5"]["identity"] == "anthropic/claude-haiku-4-5"
    assert anth["claude-opus-5"]["input_price_per_mtok"] is None
    # Identity vendor follows the endpoint's profiles, not the provider id.
    ms = {e["model"]: e["identity"] for e in catalogs["moonshot"]["models"]}
    assert ms == {"kimi-k3": "moonshotai/kimi-k3", "kimi-k4": "moonshotai/kimi-k4"}


def test_an_endpoint_without_a_list_keeps_its_previous_file(tmp_path):
    out_dir = tmp_path / "generated"
    D.render_endpoint_catalogs(LAYERS, REFS, _results(), out_dir=out_dir)
    before = (out_dir / "model_catalog.moonshot.json").read_text()
    report = D.render_endpoint_catalogs(LAYERS, REFS, _results(moonshot_ok=False), out_dir=out_dir)
    assert report["moonshot"] == {"skipped": "no model list (rejected)"}
    assert (out_dir / "model_catalog.moonshot.json").read_text() == before


def test_a_list_from_another_base_url_is_not_rendered_for_an_endpoint(tmp_path):
    layers = {**LAYERS, "endpoints": {**LAYERS["endpoints"], "openrouter": {
        **LAYERS["endpoints"]["openrouter"], "base_url": "https://eu.openrouter.ai/api/v1"}}}
    report = D.render_endpoint_catalogs(layers, REFS, _results(), out_dir=tmp_path / "g")
    assert report["openrouter"] == {"skipped": "the catalog was fetched from a different base URL"}
    assert not (tmp_path / "g" / "model_catalog.openrouter.json").exists()


def test_catalogue_render_is_atomic(tmp_path, monkeypatch):
    out_dir = tmp_path / "generated"
    swaps = []
    real_replace = os.replace

    def spy(src, dst):
        text = open(src, encoding="utf-8").read()
        assert json.loads(text)["endpoint"] in LAYERS["endpoints"]  # complete before the swap
        swaps.append(os.path.basename(dst))
        return real_replace(src, dst)

    monkeypatch.setattr(D.os, "replace", spy)
    D.render_endpoint_catalogs(LAYERS, REFS, _results(), out_dir=out_dir)
    assert sorted(swaps) == sorted(p.name for p in out_dir.iterdir())  # no temp left behind
    # A failure mid-write leaves yesterday's file whole and no temp file.
    before = (out_dir / "model_catalog.anthropic.json").read_text()
    monkeypatch.setattr(D.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        D.render_endpoint_catalogs(LAYERS, REFS, _results(), out_dir=out_dir)
    assert (out_dir / "model_catalog.anthropic.json").read_text() == before
    assert not [p for p in out_dir.iterdir() if p.name.startswith(".")]


def test_catalogues_never_go_under_the_tracked_config_dir():
    config = D.REPO_ROOT / "config"
    before = _tree_digest(config)
    for target in (config / "generated", config, config / "generated" / "x"):
        with pytest.raises(ValueError, match="never writes under config"):
            D.render_endpoint_catalogs(LAYERS, REFS, _results(), out_dir=target)
    assert _tree_digest(config) == before


def test_default_location_is_ignored_runtime_data():
    assert D.STATUS_DIR / D.GENERATED_DIRNAME == D.REPO_ROOT / "data" / "status" / "generated"
    ignored = (D.REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/status/" in [line.strip() for line in ignored]


def test_run_renders_catalogues_and_touches_no_tracked_file(tmp_path):
    config = D.REPO_ROOT / "config"
    before = _tree_digest(config)
    snap = D.run(status_dir=tmp_path, now=NOW, notice=lambda *a: 1, deps=_deps(
        layers=lambda: LAYERS, discover=lambda reg: REFS, fetch_all=lambda refs: _results()))
    assert snap["generated_catalogs"]["openrouter"]["models"] == 3
    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert written == [f"daily-{NOW.astimezone().date().isoformat()}.json",
                       "generated/model_catalog.anthropic.json",
                       "generated/model_catalog.moonshot.json",
                       "generated/model_catalog.openrouter.json"]
    assert _tree_digest(config) == before  # never model_endpoints/model_profiles/generated
    daily = json.loads((tmp_path / written[0]).read_text())
    assert daily["generated_catalogs"] == snap["generated_catalogs"]
    assert all("facts" not in c for c in daily["catalogs"])  # the snapshot stays lean
    # A failing render is recorded, never raised, and the rest still runs.
    snap2 = D.run(status_dir=tmp_path, now=NOW, notice=lambda *a: 1,
                  deps=_deps(layers=lambda: (_ for _ in ()).throw(RuntimeError("bad layers"))))
    assert [e["step"] for e in snap2["errors"]] == ["generated_catalogs"]
    assert set(snap2["subscriptions"]) == {"claude", "codex"}


def test_real_endpoints_map_to_their_discovered_providers(tmp_path, monkeypatch):
    """Against the real split registry: every endpoint with a base URL gets
    its catalogue from the provider discovery found for it; the credential-
    less codex-subscription endpoint has no list and is skipped."""
    from jarvis.status.providers import discover_providers

    monkeypatch.delenv(ua.REGISTRY_PATH_ENV, raising=False)
    layers = ua.load_registry_layers()
    refs = discover_providers(registry=ua.load_model_registry(), access={}, env={})
    results = [_res(r.id, [f"{r.id}-model"]) if r.adapter in ("anthropic_models", "openai_models")
               else _res(r.id, [], ok=False, category="unsupported") for r in refs]
    report = D.render_endpoint_catalogs(layers, refs, results, out_dir=tmp_path / "generated")
    assert set(report) == set(layers["endpoints"])
    for eid, endpoint in layers["endpoints"].items():
        if endpoint.get("base_url"):
            assert report[eid] == {"file": f"model_catalog.{eid}.json", "models": 1}, eid
        else:
            assert "skipped" in report[eid], eid
    assert set(_load(tmp_path / "generated")) == {e for e, v in layers["endpoints"].items()
                                                   if v.get("base_url")}


def _voice_snap(anthropic_ids, voice_ids, *, base_urls=None, missing=()):
    snap = {
        "catalogs": [{"provider": "anthropic", "ok": True,
                      "models": [{"id": i} for i in anthropic_ids]},
                     {"provider": "voice", "ok": True,
                      "models": [{"id": i} for i in voice_ids]}],
        "comparison": {p: {"configured_available": ["claude-haiku-5"],
                           "configured_missing": list(missing)}
                       for p in ("anthropic", "voice")},
        "subscriptions": {}, "key_health": {}, "coverage_gaps": [],
    }
    if base_urls is not None:
        snap["base_urls"] = base_urls
    return snap


def test_voice_endpoint_on_the_same_api_is_not_reported_twice():
    """Review finding 7: OPENAI_BASE_URL points the voice endpoint at the
    Anthropic API, so both results offered the same new model and the daily
    notice named it twice. The voice duplicate is skipped."""
    same = {"anthropic": "https://api.anthropic.com/v1",
            "voice": "https://api.anthropic.com/v1/"}
    prev = _voice_snap(["claude-haiku-5"], ["claude-haiku-5"], base_urls=same)
    cur = _voice_snap(["claude-haiku-5", "claude-opus-6"],
                      ["claude-haiku-5", "claude-opus-6"], base_urls=same,
                      missing=("claude-haiku-5",))
    d = D.diff(prev, cur)
    assert d["new_offered"] == {"anthropic": ["claude-opus-6"]}
    assert d["newly_missing"] == {"anthropic": ["claude-haiku-5"]}
    assert D.daily_notice_text(d).count("claude-opus-6") == 1

    # Older snapshots carry no base URLs: an identical list is the same source.
    d = D.diff(_voice_snap(["claude-haiku-5"], ["claude-haiku-5"]),
               _voice_snap(["claude-haiku-5", "claude-opus-6"],
                           ["claude-haiku-5", "claude-opus-6"]))
    assert d["new_offered"] == {"anthropic": ["claude-opus-6"]}


def test_voice_endpoint_on_its_own_api_is_still_reported():
    urls = {"anthropic": "https://api.anthropic.com/v1",
            "voice": "https://api.openai.com/v1"}
    d = D.diff(_voice_snap(["claude-haiku-5"], ["gpt-6"], base_urls=urls),
               _voice_snap(["claude-haiku-5"], ["gpt-6", "gpt-7"], base_urls=urls))
    assert d["new_offered"] == {"voice": ["gpt-7"]}


def test_snapshot_records_each_providers_base_url(tmp_path):
    snap = D.collect(_deps(), now=NOW)
    assert snap["base_urls"] == {"openrouter": "https://openrouter.ai/api/v1"}
