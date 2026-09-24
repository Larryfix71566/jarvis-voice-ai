"""T4.1 — provider catalogs (fake `http` only; no network in unit tests)."""

from __future__ import annotations

import io
import json
import threading
import urllib.error
from dataclasses import asdict

import pytest

from jarvis.status import catalog as C
from jarvis.status.providers import ADAPTERS, ProviderRef, discover_providers

KEY = "sk-FIXTURE-SECRET-VALUE-0123456789abcdef"


def _ref(id, adapter, base_url=None, credential_env=None, profiles=(), kind="llm"):
    return ProviderRef(id=id, kind=kind, adapter=adapter, base_url=base_url,
                       credential_env=credential_env, sources=(), profiles=tuple(profiles))


ANTHROPIC = _ref("anthropic", "anthropic_models", "https://api.anthropic.com/v1/",
                 "ANTHROPIC_API_KEY", ("claude-opus",))
OPENROUTER = _ref("openrouter", "openai_models", "https://openrouter.ai/api/v1",
                  "OPENROUTER_API_KEY", ("or-a",))
MOONSHOT = _ref("moonshot", "openai_models", "https://api.moonshot.ai/v1", "MOONSHOT_API_KEY")
ENV = {"ANTHROPIC_API_KEY": KEY, "OPENROUTER_API_KEY": KEY, "MOONSHOT_API_KEY": KEY,
       "OPENAI_API_KEY": KEY, "SAYGM_API_KEY": KEY}

# Trimmed real OpenRouter item shape (GET /api/v1/models, captured 2026-09-23):
# top-level data, total_count, links; items carry id, name, created (epoch s).
OPENROUTER_PAGE = {
    "data": [
        {"id": "x-ai/grok-5", "name": "xAI: Grok 5", "created": 1790000000,
         "pricing": {"prompt": "0.000003", "completion": "0.000015"}, "context_length": 256000},
        {"id": "openai/gpt-5.1", "name": "OpenAI: GPT-5.1", "created": 1763000000,
         "pricing": {"prompt": "0.00000125", "completion": "0.00001"}, "context_length": 400000},
    ],
    "total_count": 2,
    "links": {"next": None},
}


class FakeHTTP:
    """Maps URL -> (status, body) or an exception; records every call."""

    def __init__(self, routes=None, default=(200, {"data": []})):
        self.routes = routes or {}
        self.default = default
        self.calls: list[tuple[str, dict]] = []
        self.lock = threading.Lock()

    def __call__(self, url, headers, timeout):
        with self.lock:
            self.calls.append((url, dict(headers)))
        answer = self.routes.get(url, self.default)
        if callable(answer):
            answer = answer(url)
        if isinstance(answer, BaseException):
            raise answer
        status, body = answer
        if not isinstance(body, (bytes, str)):
            body = json.dumps(body).encode()
        return status, body


@pytest.fixture(autouse=True)
def _clean_cache():
    C.clear_cache_for_tests()
    yield
    C.clear_cache_for_tests()


def test_anthropic_uses_x_api_key_not_bearer():
    http = FakeHTTP(default=(200, {"data": [{"id": "claude-opus-5", "display_name": "Claude Opus 5",
                                             "created_at": "2026-08-01T00:00:00Z"}],
                                   "has_more": False}))
    res = C.fetch_catalog(ANTHROPIC, http=http, env=ENV)
    assert res.ok and res.error_category is None
    assert len(http.calls) == 1
    url, headers = http.calls[0]
    assert url == "https://api.anthropic.com/v1/models?limit=1000"
    assert headers["x-api-key"] == KEY
    assert headers["anthropic-version"] == "2023-06-01"
    assert "Authorization" not in headers
    assert not any("bearer" in str(v).lower() for v in headers.values())
    assert res.models == ({"id": "claude-opus-5", "display_name": "Claude Opus 5",
                           "created": "2026-08-01T00:00:00Z"},)
    assert res.source == "anthropic:/v1/models"


def test_anthropic_pagination():
    base = "https://api.anthropic.com/v1/models?limit=1000"
    http = FakeHTTP({
        base: (200, {"data": [{"id": "a"}], "has_more": True, "last_id": "a"}),
        base + "&after_id=a": (200, {"data": [{"id": "b"}], "has_more": True, "last_id": "b"}),
        base + "&after_id=b": (200, {"data": [{"id": "c"}], "has_more": False, "last_id": "c"}),
    })
    res = C.fetch_catalog(ANTHROPIC, http=http, env=ENV)
    assert [m["id"] for m in res.models] == ["a", "b", "c"]
    assert len(http.calls) == 3


def test_anthropic_pagination_is_capped_at_ten_pages():
    http = FakeHTTP(default=(200, {"data": [{"id": "x"}], "has_more": True, "last_id": "x"}))
    res = C.fetch_catalog(ANTHROPIC, http=http, env=ENV)
    assert res.ok
    assert len(http.calls) == C.MAX_PAGES == 10


def test_openai_compatible_parse():
    http = FakeHTTP({"https://openrouter.ai/api/v1/models": (200, OPENROUTER_PAGE)})
    res = C.fetch_catalog(OPENROUTER, http=http, env=ENV)
    assert res.ok
    url, headers = http.calls[0]
    assert headers["Authorization"] == f"Bearer {KEY}"
    assert "x-api-key" not in headers
    assert res.models[0] == {"id": "x-ai/grok-5", "display_name": "xAI: Grok 5",
                             "created": "2026-09-21T14:13:20+00:00"}
    assert res.models[1]["id"] == "openai/gpt-5.1"
    assert res.source == "openrouter:/api/v1/models"
    # A plain OpenAI-shaped item has no name: display_name is None.
    http2 = FakeHTTP(default=(200, {"object": "list", "data": [{"id": "kimi-k3", "object": "model",
                                                               "created": 1760000000}]}))
    res2 = C.fetch_catalog(MOONSHOT, http=http2, env=ENV)
    assert res2.models == ({"id": "kimi-k3", "display_name": None,
                            "created": "2025-10-09T08:53:20+00:00"},)


def test_openrouter_follows_links_next_on_same_host_only():
    first = "https://openrouter.ai/api/v1/models"
    page2 = "https://openrouter.ai/api/v1/models?offset=2"
    http = FakeHTTP({
        first: (200, {**OPENROUTER_PAGE, "links": {"next": "/api/v1/models?offset=2"}}),
        page2: (200, {"data": [{"id": "z/last", "name": "Z", "created": 1700000000}],
                      "links": {"next": "https://evil.example/steal"}}),
    })
    res = C.fetch_catalog(OPENROUTER, http=http, env=ENV)
    assert [m["id"] for m in res.models] == ["x-ai/grok-5", "openai/gpt-5.1", "z/last"]
    assert [c[0] for c in http.calls] == [first, page2]  # never the other host


def test_openai_pagination_is_capped_at_ten_pages():
    http = FakeHTTP(default=(200, {"data": [{"id": "m"}],
                                   "links": {"next": "https://openrouter.ai/api/v1/models?p=n"}}))
    C.fetch_catalog(OPENROUTER, http=http, env=ENV)
    assert len(http.calls) == 10


def _probe_verdict(code):
    """What scripts/check_env.py:model_key_probe says for an HTTP status."""
    from unittest import mock

    from jarvis.keyhealth import _load_probe

    probe = _load_probe()

    def raise_http(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(b""))

    with mock.patch("urllib.request.urlopen", raise_http):
        return probe("https://api.example.com/v1", KEY, "m")[0]


@pytest.mark.parametrize("code,expected", [(401, "rejected"), (402, "unfunded"),
                                           (403, "rejected"), (500, "unreachable")])
def test_status_mapping_matches_key_probe(code, expected):
    res = C.fetch_catalog(OPENROUTER, http=FakeHTTP(default=(code, b"")), env=ENV)
    assert not res.ok
    assert res.error_category == expected
    assert res.models == ()
    if code != 500:
        # Auth statuses: the one key probe gives the same verdict (R8).
        assert _probe_verdict(code) == expected


def test_timeout_and_non_json_are_unreachable():
    res = C.fetch_catalog(OPENROUTER, http=FakeHTTP(default=TimeoutError("timed out")), env=ENV)
    assert res.error_category == "unreachable"
    assert "TimeoutError" in res.error
    res2 = C.fetch_catalog(MOONSHOT, http=FakeHTTP(default=(200, b"<html>")), env=ENV)
    assert res2.error_category == "unreachable"


def test_no_credential_makes_no_request():
    http = FakeHTTP()
    for ref in (ANTHROPIC, OPENROUTER, MOONSHOT):
        res = C.fetch_catalog(ref, http=http, env={})
        assert res.error_category == "no_credential"
        assert res.error == f"{ref.credential_env} is not set"
    assert http.calls == []


def test_non_fetching_adapters_are_explicit():
    sub = C.fetch_catalog(_ref("codex-subscription", "subscription_probe"), http=FakeHTTP(), env=ENV)
    assert (sub.ok, sub.error_category, sub.error) == (
        False, "unsupported", "no model list API; use the subscription probe")
    local = C.fetch_catalog(_ref("local", "not_configured"), env=ENV)
    assert local.error_category == "not_configured"
    gap = C.fetch_catalog(_ref("unknown:api.newco.ai", "UNMAPPED", "https://api.newco.ai/v1"), env=ENV)
    assert gap.error_category == "unsupported"
    assert "coverage gap" in gap.error


def test_saygm_uses_the_one_saygm_reader(monkeypatch):
    from jarvis import saygm

    seen = {}

    def fake_fetch(*, api_key=None, base_url=saygm.DEFAULT_BASE_URL, timeout=10.0):
        seen.update(api_key=api_key, base_url=base_url)
        return [saygm.SayGMModel("llama-TEE", "confidential", None, None, {}),
                saygm.SayGMModel("mixtral", "open", None, None, {})]

    monkeypatch.setattr(saygm, "fetch_catalog", fake_fetch)
    ref = _ref("saygm", "saygm_catalog", "https://api.saygm.com/v1", "SAYGM_API_KEY")
    res = C.fetch_catalog(ref, env=ENV)
    assert res.ok
    assert seen == {"api_key": KEY, "base_url": "https://api.saygm.com/v1"}
    assert res.models[0] == {"id": "llama-TEE", "display_name": None, "created": None,
                             "tier": "confidential"}


def test_saygm_http_error_maps_like_the_probe(monkeypatch):
    from jarvis import saygm

    def fake_fetch(**kw):
        try:
            raise urllib.error.HTTPError("u", 402, "Payment Required", {}, None)
        except urllib.error.HTTPError as exc:
            raise saygm.SayGMError(f"SAYGM model catalog request failed: {exc}") from exc

    monkeypatch.setattr(saygm, "fetch_catalog", fake_fetch)
    ref = _ref("saygm", "saygm_catalog", "https://api.saygm.com/v1", "SAYGM_API_KEY")
    assert C.fetch_catalog(ref, env=ENV).error_category == "unfunded"


def test_one_provider_failure_does_not_stop_others():
    def boom(url):
        raise ConnectionError("refused")

    http = FakeHTTP({
        "https://api.anthropic.com/v1/models?limit=1000": (200, {"data": [{"id": "claude-opus-5"}]}),
        "https://openrouter.ai/api/v1/models": boom,
        "https://api.moonshot.ai/v1/models": (401, b""),
    })
    out = C.fetch_all([ANTHROPIC, OPENROUTER, MOONSHOT], http=http, env=ENV)
    assert [r.provider for r in out] == ["anthropic", "openrouter", "moonshot"]
    assert [r.ok for r in out] == [True, False, False]
    assert [r.error_category for r in out] == [None, "unreachable", "rejected"]


def test_fetch_all_total_timeout_reports_timed_out():
    release = threading.Event()

    def slow(url):
        release.wait(5)
        return (200, {"data": []})

    http = FakeHTTP({"https://openrouter.ai/api/v1/models": slow},
                    default=(200, {"data": [{"id": "ok"}]}))
    try:
        out = C.fetch_all([ANTHROPIC, OPENROUTER], http=http, env=ENV, total_timeout=0.3)
    finally:
        release.set()
    assert out[0].ok
    assert (out[1].ok, out[1].error_category, out[1].error) == (False, "unreachable", "timed out")


REGISTRY = {
    "default": "claude-opus",
    "profiles": {
        "claude-opus": {"provider": "anthropic", "model": "claude-opus-5",
                        "base_url": "https://api.anthropic.com/v1/", "api_key_env": "ANTHROPIC_API_KEY"},
        "claude-fable": {"provider": "anthropic", "model": "claude-fable-5-1",
                         "base_url": "https://api.anthropic.com/v1/", "api_key_env": "ANTHROPIC_API_KEY"},
        "or-grok": {"provider": "openrouter", "model": "x-ai/grok-5",
                    "base_url": "https://openrouter.ai/api/v1", "api_key_env": "OPENROUTER_API_KEY"},
    },
}


def _ok(provider, models):
    return C.CatalogResult(provider=provider, ok=True, fetched_at="2026-09-23T10:30:00+00:00",
                           source=f"{provider}:/v1/models", models=tuple(models),
                           error_category=None, error=None)


def test_compare_to_registry():
    results = [
        _ok("anthropic", [{"id": "claude-opus-5", "display_name": None, "created": "2026-08-01"},
                          {"id": "claude-haiku-4-5", "display_name": None, "created": "2025-10-01"},
                          {"id": "claude-new-6", "display_name": None, "created": "2026-09-20"}]),
        _ok("openrouter", [{"id": "x-ai/grok-5", "display_name": "G", "created": None},
                           {"id": "b/old", "display_name": None, "created": None},
                           {"id": "a/old", "display_name": None, "created": None},
                           {"id": "z/new", "display_name": None, "created": "2026-09-01"}]),
        _ok("voice", [{"id": "claude-haiku-4-5", "display_name": None, "created": None}]),
        C.CatalogResult("moonshot", False, "t", "moonshot:/v1/models", (), "rejected", "HTTP 401"),
    ]
    out = C.compare_to_registry(results, REGISTRY, env={"OPENAI_MODEL": "claude-haiku-4-5"})
    assert out["anthropic"] == {
        "configured_available": ["claude-opus"],
        "configured_missing": ["claude-fable"],
        "offered_not_configured_count": 2,
        "offered_not_configured_sample": ["claude-new-6", "claude-haiku-4-5"],
    }
    assert out["openrouter"]["configured_available"] == ["or-grok"]
    assert out["openrouter"]["offered_not_configured_sample"] == ["z/new", "a/old", "b/old"]
    assert out["voice"] == {"configured_available": ["voice:claude-haiku-4-5"],
                            "configured_missing": [], "offered_not_configured_count": 0,
                            "offered_not_configured_sample": []}
    assert "moonshot" not in out


def test_compare_sample_is_capped():
    models = [{"id": f"m{i:03d}", "display_name": None, "created": None} for i in range(60)]
    out = C.compare_to_registry([_ok("openrouter", models)], REGISTRY, env={})
    assert out["openrouter"]["offered_not_configured_count"] == 60
    assert len(out["openrouter"]["offered_not_configured_sample"]) == 25


def test_cache_and_force():
    http = FakeHTTP(default=(200, {"data": [{"id": "m"}]}))
    first = C.fetch_catalog(MOONSHOT, http=http, env=ENV)
    again = C.fetch_catalog(MOONSHOT, http=http, env=ENV)
    assert again is first and len(http.calls) == 1
    C.fetch_catalog(MOONSHOT, http=http, env=ENV, force=True)
    assert len(http.calls) == 2
    # A failure is not cached: the next request tries again.
    bad = FakeHTTP(default=(500, b""))
    C.fetch_catalog(OPENROUTER, http=bad, env=ENV)
    C.fetch_catalog(OPENROUTER, http=bad, env=ENV)
    assert len(bad.calls) == 2


def test_cache_expires(monkeypatch):
    http = FakeHTTP(default=(200, {"data": [{"id": "m"}]}))
    clock = [1000.0]
    monkeypatch.setattr(C.time, "monotonic", lambda: clock[0])
    C.fetch_catalog(MOONSHOT, http=http, env=ENV)
    clock[0] += C.CACHE_TTL_S + 1
    C.fetch_catalog(MOONSHOT, http=http, env=ENV)
    assert len(http.calls) == 2


def test_error_text_never_contains_key():
    def echo_key(url):
        raise OSError(f"proxy said: Authorization: Bearer {KEY} x-api-key={KEY} {KEY}")

    for ref in (ANTHROPIC, OPENROUTER):
        res = C.fetch_catalog(ref, http=FakeHTTP(default=echo_key), env=ENV)
        blob = json.dumps(asdict(res))
        assert KEY not in blob
        assert "FIXTURE-SECRET" not in blob
        assert len(res.error) <= 200
    for code in (401, 402, 403, 500):
        res = C.fetch_catalog(MOONSHOT, http=FakeHTTP(default=(code, KEY.encode())), env=ENV)
        assert KEY not in json.dumps(asdict(res))


def _real_refs():
    return discover_providers()


def test_every_configured_provider_gets_an_adapter_or_an_explicit_result(monkeypatch):
    """Larry, 2026-09-23: catalogs cover EVERY configured provider, derived
    from configuration — no silent skips. Each ref discover_providers()
    returns for the real config either reaches its fetcher or answers an
    explicit unsupported/not_configured result."""
    from jarvis import saygm

    refs = _real_refs()
    env = {r.credential_env: KEY for r in refs if r.credential_env}
    saygm_calls = []
    monkeypatch.setattr(saygm, "fetch_catalog",
                        lambda **kw: saygm_calls.append(kw) or [])
    fetching = {"anthropic_models", "openai_models", "saygm_catalog"}
    assert set(ADAPTERS) >= fetching
    ids = {r.id for r in refs}
    # The providers Larry named are all discovered from configuration.
    assert {"anthropic", "openrouter", "moonshot", "saygm", "voice",
            "codex-subscription", "claude-subscription"} <= ids
    for ref in refs:
        http = FakeHTTP(default=(200, {"data": [{"id": "m"}]}))
        res = C.fetch_catalog(ref, http=http, env=env, force=True)
        assert res.provider == ref.id
        if ref.adapter in ("anthropic_models", "openai_models"):
            assert res.ok, ref
            assert http.calls and http.calls[0][0].startswith(ref.base_url.rstrip("/")), ref
        elif ref.adapter == "saygm_catalog":
            assert res.ok, ref
        else:
            assert ref.adapter in ADAPTERS, f"{ref.id} has no adapter (coverage gap)"
            assert not res.ok
            assert res.error_category in ("unsupported", "not_configured"), ref
            assert http.calls == []
    assert saygm_calls, "the configured SAYGM route was not fetched"
    # fetch_all over the catalog refs returns exactly one result per model provider.
    llm = C.catalog_refs(refs)
    assert {r.id for r in llm} == {r.id for r in refs if r.kind == "llm"}
    out = C.fetch_all(llm, http=FakeHTTP(default=(200, {"data": []})), env=env, force=True)
    assert [r.provider for r in out] == [r.id for r in llm]


def test_catalog_status_payload_and_unknown_provider():
    http = FakeHTTP(default=(200, {"data": [{"id": "claude-opus-5"}]}))
    access = {"routes": {"local": {}}}
    out = C.catalog_status("all", registry=REGISTRY, access=access, env=ENV, http=http)
    assert out["ok"] and out["source"] == "catalog"
    assert [r["provider"] for r in out["results"]] == ["anthropic", "local", "openrouter", "voice"]
    assert out["comparison"]["anthropic"]["configured_available"] == ["claude-opus"]
    one = C.catalog_status("openrouter", registry=REGISTRY, access=access, env=ENV, http=http)
    assert [r["provider"] for r in one["results"]] == ["openrouter"]
    assert C.catalog_status("nope", registry=REGISTRY, access=access, env=ENV, http=http) == {
        "ok": False, "error": "unknown provider 'nope'"}
    assert KEY not in json.dumps(out)
