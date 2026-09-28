"""T2.5 — summaries.summarize: pure, golden, source line first, <= 1500."""

from __future__ import annotations

import time

import pytest

from jarvis.status.summaries import MAX_CHARS, summarize

KEY = "sk-ant-api03-FIXTURE-SECRET-0123456789"

MODELS = {
    "ok": True, "generated_at": "2026-09-22T10:30:00+00:00", "source": "registry",
    "default": "claude-fable-5",
    "profiles": [
        {"name": "claude-fable-5", "tier": "frontier", "key_env": "ANTHROPIC_API_KEY",
         "key_present": True, "key_health": "ok"},
        {"name": "claude-opus", "tier": "frontier", "key_env": "ANTHROPIC_API_KEY",
         "key_present": True, "key_health": "ok"},
        {"name": "codex-subscription", "tier": "frontier", "key_env": None,
         "key_present": False, "key_health": "n/a (subscription)"},
        {"name": "or-deepseek", "tier": "economy", "key_env": "OPENROUTER_API_KEY",
         "key_present": True, "key_health": "unfunded"},
        {"name": "kimi-k2", "tier": "economy", "key_env": "MOONSHOT_API_KEY",
         "key_present": False, "key_health": "unknown"},
    ],
    "providers": [
        {"id": "anthropic", "profiles": ["claude-fable-5", "claude-opus"]},
        {"id": "codex-subscription", "profiles": ["codex-subscription"]},
        {"id": "deepgram", "profiles": []},
        {"id": "moonshot", "profiles": ["kimi-k2"]},
        {"id": "openrouter", "profiles": ["or-deepseek"]},
    ],
    "coverage_gaps": ["unknown:api.newco.ai"],
}

SERVICES = {
    "ok": True, "generated_at": "2026-09-22T10:30:00+00:00",
    "services": [
        {"name": "bot", "state": "up", "launchd": "loaded (pid 12)"},
        {"name": "vault", "state": "down", "launchd": "not loaded"},
        {"name": "extractor", "state": "no port", "launchd": "loaded (idle)"},
        {"name": "admin", "state": "up", "launchd": "unknown"},
    ],
    "source": {"head": "0123456789abcdef0123456789abcdef01234567", "dirty_files": 118},
}

BUILD = {
    "ok": True, "app_path": "macos/MortimerHost/.build/MortimerHost.app", "exists": True,
    "modified_at": "2026-09-22T09:15:42-04:00",
    "MortimerSourceRevision": "abcdef0123456789abcdef0123456789abcdef01",
    "MortimerSourceDirty": "false", "MortimerBuildConfiguration": "release",
    "repo_head": "0123456789abcdef0123456789abcdef01234567", "matches_repo_head": False,
}

LOCATION = {"ok": True, "lat": 34.07, "lon": -84.29, "label": "Alpharetta",
            "source": "device", "age_s": 300}

OVERVIEW = {
    "ok": True,
    "agents": [{"name": "scheduler", "model_profile": "claude-sonnet-5"},
               {"name": "developer", "model_profile": "claude-opus"}],
    "mcp_servers": ["mcp-time", "mcp-git", "mcp-screen"],
    "flags": {"JARVIS_UI_CONTROL_ENABLED": "on", "JARVIS_SPEAKER_GATE_ENABLED": "off",
              "JARVIS_MODEL_ROUTING_ENABLED": "off"},
}


CATALOG = {
    "ok": True, "generated_at": "2026-09-23T10:31:00+00:00", "source": "catalog",
    "results": [
        {"provider": "anthropic", "ok": True, "fetched_at": "2026-09-23T06:30:00+00:00",
         "source": "anthropic:/v1/models", "error_category": None, "error": None,
         "models": [{"id": "claude-opus-5"}, {"id": "claude-new-6"}, {"id": "claude-haiku-4-5"}]},
        {"provider": "openrouter", "ok": True, "fetched_at": "2026-09-23T10:30:00+00:00",
         "source": "openrouter:/api/v1/models", "error_category": None, "error": None,
         "models": [{"id": f"m{i}"} for i in range(459)]},
        {"provider": "moonshot", "ok": False, "fetched_at": "2026-09-23T10:30:00+00:00",
         "source": "moonshot:/v1/models", "models": [], "error_category": "rejected",
         "error": "HTTP 401: the key was refused"},
        {"provider": "codex-subscription", "ok": False, "fetched_at": "2026-09-23T10:30:00+00:00",
         "source": "codex-subscription:subscription_probe", "models": [],
         "error_category": "unsupported",
         "error": "no model list API; use the subscription probe"},
    ],
    "comparison": {
        "anthropic": {"configured_available": ["claude-opus"],
                      "configured_missing": ["claude-fable"],
                      "offered_not_configured_count": 2,
                      "offered_not_configured_sample": ["claude-new-6", "claude-haiku-4-5"]},
        "openrouter": {"configured_available": ["or-grok"], "configured_missing": [],
                       "offered_not_configured_count": 458,
                       "offered_not_configured_sample": ["x-ai/grok-5", "a/b", "c/d", "e/f",
                                                         "g/h", "i/j", "k/l"]},
    },
}

SUBSCRIPTION = {
    "ok": True, "source": "probe:claude@2026-09-23T10:30:00+00:00",
    "probe": {"which": "claude", "model": "claude-fable-5-1", "ok": False,
              "response_present": False, "category": "model_unavailable", "installed": True,
              "command": "claude", "probed_at": "2026-09-23T10:30:00+00:00", "cached": False},
}


@pytest.fixture(autouse=True)
def _utc(monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


GOLDEN = {
    "models": (MODELS, (
        "Source: registry (configured, not proof of availability).\n"
        "Default: claude-fable-5.\n"
        "anthropic: claude-fable-5 (frontier, ok), claude-opus (frontier, ok).\n"
        "codex-subscription: codex-subscription (frontier, n/a (subscription)).\n"
        "moonshot: kimi-k2 (economy, key missing).\n"
        "openrouter: or-deepseek (economy, unfunded).\n"
        "Coverage gaps: unknown:api.newco.ai."
    )),
    "services": (SERVICES, (
        "Source: live checks at 10:30 (reachability now, launchd state).\n"
        "bot: up, launchd loaded (pid 12).\n"
        "vault: down, launchd not loaded.\n"
        "extractor: no port, launchd loaded (idle).\n"
        "admin: up.\n"
        "Code: commit 0123456, 118 uncommitted file(s)."
    )),
    "build": (BUILD, (
        "Source: the app bundle on disk (macos/MortimerHost/.build/MortimerHost.app).\n"
        "Built 2026-09-22 09:15 from commit abcdef0 (release build).\n"
        "It does not match the current checkout (0123456)."
    )),
    "location": (LOCATION, (
        "Source: the Mac's own location, reported 5 minute(s) ago.\n"
        "Location: Alpharetta."
    )),
    "overview": (OVERVIEW, (
        "Source: configuration (config/agents.yaml, config/mcp_servers.yaml, switches).\n"
        "2 agents: scheduler (claude-sonnet-5), developer (claude-opus).\n"
        "3 MCP servers.\n"
        "Switches off: JARVIS_SPEAKER_GATE_ENABLED, JARVIS_MODEL_ROUTING_ENABLED."
    )),
    "catalog": (CATALOG, (
        "Source: live provider catalogs — what each account offers now, not the registry "
        "(time fetched shown per provider).\n"
        "anthropic (catalog:anthropic@06:30): 3 models offered. Configured but NOT offered: "
        "claude-fable. 2 offered but not configured, newest first: claude-new-6, "
        "claude-haiku-4-5.\n"
        "openrouter (catalog:openrouter@10:30): 459 models offered. Every configured model is "
        "offered. 458 offered but not configured, newest first: x-ai/grok-5, a/b, c/d, e/f, g/h.\n"
        "moonshot: rejected (HTTP 401: the key was refused).\n"
        "codex-subscription: unsupported (no model list API; use the subscription probe)."
    )),
    "subscription": (SUBSCRIPTION, (
        "Source: a live probe of the Claude subscription at 10:30 (probe:claude).\n"
        "Model tried: claude-fable-5-1 (exactly as named).\n"
        "Result: failed — that model is not available on this subscription (model_unavailable).\n"
        "This check used a small amount of your Claude subscription."
    )),
}


@pytest.mark.parametrize("topic", list(GOLDEN))
def test_golden(topic):
    payload, expected = GOLDEN[topic]
    assert summarize(topic, payload) == expected


@pytest.mark.parametrize("topic", list(GOLDEN))
def test_source_line_first(topic):
    payload, _ = GOLDEN[topic]
    assert summarize(topic, payload).startswith("Source: ")


@pytest.mark.parametrize("topic", list(GOLDEN))
def test_deterministic(topic):
    payload, _ = GOLDEN[topic]
    assert summarize(topic, payload) == summarize(topic, payload)


def test_length_is_capped():
    big = dict(MODELS)
    big["profiles"] = [{"name": f"profile-{i:03d}-with-a-long-name", "tier": "frontier",
                        "key_env": "K", "key_present": True, "key_health": "ok"}
                       for i in range(200)]
    big["providers"] = [{"id": "openrouter",
                         "profiles": [p["name"] for p in big["profiles"]]}]
    out = summarize("models", big)
    assert len(out) <= MAX_CHARS == 1500
    assert out.startswith("Source: registry")
    for topic, (payload, _) in GOLDEN.items():
        assert len(summarize(topic, payload)) <= MAX_CHARS


def test_services_clean_checkout_omits_dirty_count():
    clean = dict(SERVICES, source={"head": "f" * 40, "dirty_files": 0})
    assert summarize("services", clean).endswith("Code: commit fffffff.")


def test_build_variants():
    assert summarize("build", {"ok": True, "exists": False}) == (
        "Source: the app bundle on disk (MortimerHost.app).\n"
        "The Mac app has not been built: no bundle found.")
    same = dict(BUILD, matches_repo_head=True, repo_head=BUILD["MortimerSourceRevision"],
                MortimerSourceDirty="true")
    out = summarize("build", same)
    assert "with uncommitted changes" in out
    assert out.endswith("It matches the current checkout (abcdef0).")


def test_location_variants():
    assert summarize("location", {"ok": True, "lat": 34.07, "lon": -84.29, "label": "",
                                  "source": "ip"}) == (
        "Source: IP geolocation (approximate).\nLocation: coordinates 34.07, -84.29.")


def test_failure_payloads():
    assert summarize("models", {"ok": False, "error": "status tools are disabled"}) == (
        "system_status failed: status tools are disabled.")
    assert summarize("nope", {"ok": True}) == "system_status failed: unknown topic 'nope'."
    assert summarize("models", None) == "system_status failed: the admin sidecar returned no status."


def test_no_key_material_is_invented():
    for topic, (payload, _) in GOLDEN.items():
        assert KEY not in summarize(topic, payload)


def test_subscription_variants():
    ok = dict(SUBSCRIPTION, probe=dict(SUBSCRIPTION["probe"], ok=True, category=None,
                                        response_present=True, which="codex",
                                        model="gpt-6-astra", cached=True))
    assert summarize("subscription", ok) == (
        "Source: a live probe of the Codex subscription at 10:30 (probe:codex); reused, since "
        "one probe per model is allowed every 10 minutes.\n"
        "Model tried: gpt-6-astra (exactly as named).\n"
        "Result: it answered — the model is available on this subscription.\n"
        "This check used a small amount of your Codex subscription.")
    missing = dict(SUBSCRIPTION, probe=dict(SUBSCRIPTION["probe"], category="not_installed",
                                             installed=False))
    out = summarize("subscription", missing)
    assert "command is not installed" in out and out.endswith("No subscription quota was used.")
    odd = dict(SUBSCRIPTION, probe=dict(SUBSCRIPTION["probe"], category=None,
                                         response_present=True))
    assert "not with the expected check text" in summarize("subscription", odd)


def test_catalog_summary_is_capped_with_many_providers():
    many = dict(CATALOG, results=[dict(CATALOG["results"][1], provider=f"p{i}-" + "x" * 40)
                                  for i in range(40)])
    out = summarize("catalog", many)
    assert len(out) <= MAX_CHARS and out.startswith("Source: live provider catalogs")
