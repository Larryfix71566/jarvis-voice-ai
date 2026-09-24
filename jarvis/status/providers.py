"""Provider discovery and catalog coverage (spec T2.1, locked decision L3).

Every provider, route and credential Mortimer is configured with is
DERIVED from configuration — `config/upgrade_models.yaml` (through the one
registry loader), the route keys of `config/model_access.yaml`, the voice
`OPENAI_BASE_URL` setting and the fixed service credentials below — never
from a hand-maintained provider list. A provider that no catalog adapter
covers is reported as a coverage gap, and
`tests/unit/test_status_providers.py::test_real_config_has_no_coverage_gaps`
fails on the real config when one appears.

Pure: no network I/O, deterministic output sorted by id. Key NAMES only,
never key values (R7).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

from jarvis.usage_ledger import provider_from_base_url


@dataclass(frozen=True)
class ProviderRef:
    id: str              # stable: "anthropic", "openrouter", "moonshot", "openai", "saygm",
                         # "claude-subscription", "codex-subscription", "local", "voice",
                         # "deepgram", "elevenlabs", "tavily", "github", "github-selfedit"
    kind: str            # "llm" | "service"
    adapter: str         # one of ADAPTERS keys below, or "UNMAPPED"
    base_url: str | None
    credential_env: str | None
    sources: tuple[str, ...]   # e.g. ("registry:claude-opus", "route:saygm", "settings:OPENAI_BASE_URL")
    profiles: tuple[str, ...]  # registry profile names served by this provider


UNMAPPED = "UNMAPPED"

# Every value is implemented by the catalog phase (T4.1) or is one of the
# non-fetching kinds.
ADAPTERS = {
    "anthropic_models":  "GET {base}/models with x-api-key + anthropic-version",
    "openai_models":     "GET {base}/models with Bearer (OpenAI-compatible)",
    "saygm_catalog":     "jarvis.saygm.fetch_catalog",
    "subscription_probe": "no list API; availability only via jarvis.status.subscriptions",
    "not_configured":    "route exists but has no runtime (local)",
    "service_health":    "not an LLM catalog; reachability only",
}

# provider_from_base_url() result -> catalog adapter. Anything else is a gap.
_BASE_URL_ADAPTERS = {
    "anthropic": "anthropic_models",
    "openrouter": "openai_models",
    "moonshot": "openai_models",
    "openai": "openai_models",
}

# Keys of model_access.yaml `routes` -> (ref id, adapter).
_ROUTE_ADAPTERS = {
    "subscription": ("claude-subscription", "subscription_probe"),
    "codex_subscription": ("codex-subscription", "subscription_probe"),
    "saygm": ("saygm", "saygm_catalog"),
    "local": ("local", "not_configured"),
}

# Not model providers, so this is the only hand-listed part.
SERVICE_CREDENTIALS = {
    "deepgram": "DEEPGRAM_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "github": "GITHUB_TOKEN",
    "github-selfedit": "JARVIS_GITHUB_TOKEN",
}

DEFAULT_VOICE_BASE_URL = "https://api.openai.com/v1"


def _classify_base_url(base_url: str) -> tuple[str, str]:
    """(ref id, adapter) for an endpoint, via the one provider classifier
    (I6). Unknown hosts get their own id so two never merge."""
    provider = provider_from_base_url(base_url)
    adapter = _BASE_URL_ADAPTERS.get(provider)
    if adapter is not None:
        return provider, adapter
    host = urlparse(base_url).hostname or base_url
    return f"unknown:{host}", UNMAPPED


class _Acc:
    """Mutable accumulator for one ref while discovering."""

    def __init__(self, id: str, kind: str, adapter: str) -> None:
        self.id = id
        self.kind = kind
        self.adapter = adapter
        self.base_url: str | None = None
        self.credential_env: str | None = None
        self.sources: set[str] = set()
        self.profiles: set[str] = set()

    def fill(self, *, base_url: str | None = None,
             credential_env: str | None = None) -> None:
        if self.base_url is None and base_url:
            self.base_url = base_url
        if self.credential_env is None and credential_env:
            self.credential_env = credential_env

    def freeze(self) -> ProviderRef:
        return ProviderRef(
            id=self.id, kind=self.kind, adapter=self.adapter,
            base_url=self.base_url, credential_env=self.credential_env,
            sources=tuple(sorted(self.sources)),
            profiles=tuple(sorted(self.profiles)),
        )


def discover_providers(*, registry: dict | None = None, access: dict | None = None,
                       env: Mapping[str, str] = os.environ) -> list[ProviderRef]:
    """Every configured provider, route and credential, sorted by id. No
    network I/O."""
    if registry is None:
        from jarvis.agents.upgrade_agent import load_model_registry

        registry = load_model_registry()
    if access is None:
        from jarvis.model_routing import ModelRouteError, load_access_config

        try:
            access = load_access_config()
        except ModelRouteError:
            # A checkout without config/model_access.yaml (fact 3.1) has no
            # routes; that is reported by absence, not by crashing.
            access = {}

    refs: dict[str, _Acc] = {}

    def ref(id: str, kind: str, adapter: str) -> _Acc:
        if id not in refs:
            refs[id] = _Acc(id, kind, adapter)
        return refs[id]

    profiles = registry.get("profiles") or {}
    items: list[tuple[str, dict[str, Any]]]
    if isinstance(profiles, dict):
        items = [(str(k), v) for k, v in profiles.items() if isinstance(v, dict)]
    else:
        items = [(str(p.get("name")), p) for p in profiles if isinstance(p, dict)]
    for name, prof in sorted(items):
        base_url = str(prof.get("base_url") or "")
        if base_url:
            rid, adapter = _classify_base_url(base_url)
            acc = ref(rid, "llm", adapter)
            acc.fill(base_url=base_url, credential_env=prof.get("api_key_env"))
        elif prof.get("provider") == "openai" and name == "codex-subscription":
            rid, adapter = _ROUTE_ADAPTERS["codex_subscription"]
            acc = ref(rid, "llm", adapter)
            acc.fill(base_url="subscription://codex")
        else:
            acc = ref(f"profile:{name}", "llm", UNMAPPED)
        acc.sources.add(f"registry:{name}")
        acc.profiles.add(name)

    # Only the KEYS of access["routes"]: direct_api is synthesized in code,
    # and workload routes are not providers.
    routes = (access or {}).get("routes") or {}
    if isinstance(routes, dict):
        for key in sorted(str(k) for k in routes):
            route = routes.get(key) if isinstance(routes.get(key), dict) else {}
            mapped = _ROUTE_ADAPTERS.get(key)
            if mapped is None:
                acc = ref(f"route:{key}", "llm", UNMAPPED)
            else:
                acc = ref(mapped[0], "llm", mapped[1])
            if key == "saygm":
                acc.fill(base_url=route.get("base_url"),
                         credential_env=route.get("credential_env"))
            elif key == "subscription":
                acc.fill(base_url="subscription://claude")
            elif key == "codex_subscription":
                acc.fill(base_url="subscription://codex")
            acc.sources.add(f"route:{key}")

    # Voice supervisor: whatever OPENAI_BASE_URL points at (in this
    # deployment, Anthropic — which is why the key's NAME is not a label).
    voice_url = (env.get("OPENAI_BASE_URL") or "").strip() or DEFAULT_VOICE_BASE_URL
    _, voice_adapter = _classify_base_url(voice_url)
    voice = ref("voice", "llm", voice_adapter)
    voice.fill(base_url=voice_url, credential_env="OPENAI_API_KEY")
    voice.sources.add("settings:OPENAI_BASE_URL")

    for sid, key_env in SERVICE_CREDENTIALS.items():
        svc = ref(sid, "service", "service_health")
        svc.fill(credential_env=key_env)
        svc.sources.add(f"service:{key_env}")

    return [refs[k].freeze() for k in sorted(refs)]


def coverage_gaps(refs: list[ProviderRef]) -> list[str]:
    """Sorted ids no catalog adapter covers (the L3 tripwire)."""
    return sorted(r.id for r in refs if r.adapter == UNMAPPED)
