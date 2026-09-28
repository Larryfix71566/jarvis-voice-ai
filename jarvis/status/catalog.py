"""Provider model catalogs: fetch, cache, compare (spec T4.1, L3/L4).

`fetch_catalog(ref)` answers "what does this provider offer right now" for
one `ProviderRef` from `discover_providers()` — so the set of providers is
whatever configuration names (L3), never a list kept here. Every adapter in
`jarvis.status.providers.ADAPTERS` has a branch below; a ref no adapter can
list (subscriptions, services, UNMAPPED) gets an explicit ok=False result
with `error_category` "unsupported" or "not_configured", never a silent skip.

Sources are named on every result (I5): `source` is "<provider>:<path>" and
`fetched_at` is when the list was read. Status codes map exactly like
`scripts/check_env.py:model_key_probe` for auth (401/403 rejected, 402
unfunded); anything else that is not a usable list is "unreachable".

R7: a key value is only ever placed in the request header. Every error
text is built here, run through `jarvis.status.logs.redact`, scrubbed of
the key value, and capped at 200 characters.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urljoin, urlparse

from jarvis.status.logs import redact
from jarvis.status.providers import ProviderRef, discover_providers

ANTHROPIC_VERSION = "2023-06-01"
MAX_PAGES = 10
CACHE_TTL_S = 3600.0
MAX_ERROR_CHARS = 200
SAMPLE_SIZE = 25
USER_AGENT = "mortimer-status"


@dataclass(frozen=True)
class CatalogResult:
    provider: str
    ok: bool
    fetched_at: str
    source: str                 # e.g. "anthropic:/v1/models"
    models: tuple[dict, ...]    # each {"id": str, "display_name": str|None, "created": str|None}
    error_category: str | None  # rejected|unfunded|unreachable|unsupported|not_configured|no_credential
    error: str | None           # sanitized, <= 200 chars, never contains a key or header
    # Upstream facts some providers publish per model, keyed by model id:
    # {"pricing": {"prompt": str, "completion": str}, "context_length": int},
    # each part only when the provider returned it (OpenRouter's /models
    # carries both; pricing is USD per token, as strings). Read only by the
    # daily job's per-endpoint catalogue render (spec P5 A3); as_payload()
    # leaves it out, so the status answers do not grow by a row per model.
    facts: dict = field(default_factory=dict, compare=False, repr=False)


class _HTTPStatus(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status


def _default_http(url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
    """GET `url`. Returns (status, body); an HTTP error status is returned,
    not raised. Transport failures raise. Test seam."""
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - configured HTTPS endpoint
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), b""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sanitize(text: str, secret: str | None) -> str:
    out = str(text)
    if secret:
        out = out.replace(secret, "<redacted>")
    out = redact(out)
    return out[:MAX_ERROR_CHARS]


def _category_for_status(status: int) -> str:
    """The same auth mapping as model_key_probe (R8): 401/403 refused, 402
    valid but unfunded. For a list, any other non-2xx means no list."""
    if status in (401, 403):
        return "rejected"
    if status == 402:
        return "unfunded"
    return "unreachable"


_STATUS_TEXT = {
    "rejected": "the key was refused",
    "unfunded": "the key is valid but the account has no credit",
}


def _epoch_iso(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return None


def _get_json(http, url: str, headers: dict[str, str], timeout: float) -> dict:
    status, body = http(url, headers, timeout)
    if not 200 <= int(status) < 300:
        raise _HTTPStatus(int(status))
    payload = json.loads(body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else body)
    if not isinstance(payload, dict):
        raise ValueError("response is not a JSON object")
    return payload


def _items(payload: dict) -> list[dict]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("response has no data list")
    return [item for item in data if isinstance(item, dict) and item.get("id")]


def _anthropic(base: str, key: str, http, timeout: float) -> list[dict]:
    headers = {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION,
               "User-Agent": USER_AGENT}
    url = f"{base.rstrip('/')}/models?limit=1000"
    models: list[dict] = []
    for _ in range(MAX_PAGES):
        payload = _get_json(http, url, headers, timeout)
        for item in _items(payload):
            models.append({"id": str(item["id"]),
                           "display_name": item.get("display_name"),
                           "created": item.get("created_at")})
        if not payload.get("has_more") or not payload.get("last_id"):
            break
        url = f"{base.rstrip('/')}/models?limit=1000&after_id={payload['last_id']}"
    return models


_PRICE_KEYS = ("prompt", "completion")


def _upstream_facts(item: dict) -> dict:
    """The published price and context size of one /models item, if any."""
    out: dict[str, Any] = {}
    pricing = item.get("pricing")
    if isinstance(pricing, dict):
        kept = {k: pricing[k] for k in _PRICE_KEYS
                if isinstance(pricing.get(k), (str, int, float))
                and not isinstance(pricing.get(k), bool)}
        if kept:
            out["pricing"] = kept
    ctx = item.get("context_length")
    if isinstance(ctx, int) and not isinstance(ctx, bool) and ctx > 0:
        out["context_length"] = ctx
    return out


def _openai(base: str, key: str, http, timeout: float,
            facts: dict | None = None) -> list[dict]:
    headers = {"Authorization": f"Bearer {key}", "User-Agent": USER_AGENT}
    first = f"{base.rstrip('/')}/models"
    host = urlparse(first).hostname
    url: str | None = first
    models: list[dict] = []
    pages = 0
    while url and pages < MAX_PAGES:
        pages += 1
        payload = _get_json(http, url, headers, timeout)
        for item in _items(payload):
            models.append({"id": str(item["id"]),
                           "display_name": item.get("name"),
                           "created": _epoch_iso(item.get("created"))})
            found = _upstream_facts(item)
            if found and facts is not None:
                facts[str(item["id"])] = found
        # OpenRouter (verified 2026-09-23): top-level `links.next` is a
        # pagination link, null when everything fits in one page. Followed
        # only on the SAME host, so the Bearer key never goes elsewhere.
        links = payload.get("links")
        nxt = links.get("next") if isinstance(links, dict) else None
        if not nxt or not isinstance(nxt, str):
            break
        candidate = urljoin(url, nxt)
        if urlparse(candidate).hostname != host:
            break
        url = candidate
    return models


def _result(ref: ProviderRef, *, ok: bool, source: str, models: Iterable[dict] = (),
            category: str | None = None, error: str | None = None,
            facts: dict | None = None) -> CatalogResult:
    return CatalogResult(provider=ref.id, ok=ok, fetched_at=_now_iso(), source=source,
                         models=tuple(models), error_category=category, error=error,
                         facts=dict(facts or {}))


def _source(ref: ProviderRef, path: str) -> str:
    return f"{ref.id}:{path}"


def _fetch_uncached(ref: ProviderRef, *, timeout: float, http, env: Mapping[str, str]) -> CatalogResult:
    adapter = ref.adapter
    if adapter == "subscription_probe":
        return _result(ref, ok=False, source=_source(ref, adapter), category="unsupported",
                       error="no model list API; use the subscription probe")
    if adapter == "not_configured":
        return _result(ref, ok=False, source=_source(ref, adapter), category="not_configured",
                       error="route exists but has no runtime")
    if adapter == "service_health":
        return _result(ref, ok=False, source=_source(ref, adapter), category="unsupported",
                       error="not an LLM catalog; reachability only (services topic)")
    if adapter not in ("anthropic_models", "openai_models", "saygm_catalog"):
        return _result(ref, ok=False, source=_source(ref, adapter), category="unsupported",
                       error="no catalog adapter for this provider (coverage gap)")

    key = str(env.get(ref.credential_env) or "").strip() if ref.credential_env else ""
    base = ref.base_url or ""
    path = urlparse(base.rstrip("/") + "/models").path
    source = _source(ref, path)
    if not key:
        return _result(ref, ok=False, source=source, category="no_credential",
                       error=f"{ref.credential_env or 'no credential'} is not set")
    facts: dict[str, dict] = {}
    try:
        if adapter == "anthropic_models":
            models = _anthropic(base, key, http, timeout)
        elif adapter == "openai_models":
            models = _openai(base, key, http, timeout, facts)
        else:
            models = _saygm(ref, key, timeout)
    except _HTTPStatus as exc:
        category = _category_for_status(exc.status)
        why = _STATUS_TEXT.get(category)
        text = f"HTTP {exc.status}" + (f": {why}" if why else "")
        return _result(ref, ok=False, source=source, category=category,
                       error=_sanitize(text, key))
    except (ValueError, UnicodeDecodeError) as exc:
        return _result(ref, ok=False, source=source, category="unreachable",
                       error=_sanitize(f"not a usable model list: {exc}", key))
    except Exception as exc:  # noqa: BLE001 — network error is a result, not a crash
        return _result(ref, ok=False, source=source, category="unreachable",
                       error=_sanitize(f"{type(exc).__name__}: {exc}", key))
    return _result(ref, ok=True, source=source, models=models, facts=facts)


def _saygm(ref: ProviderRef, key: str, timeout: float) -> list[dict]:
    """The one SAYGM catalog reader (R8): jarvis.saygm.fetch_catalog."""
    from jarvis import saygm

    kwargs: dict[str, Any] = {"api_key": key, "timeout": timeout}
    if ref.base_url:
        kwargs["base_url"] = ref.base_url
    try:
        catalog = saygm.fetch_catalog(**kwargs)
    except saygm.SayGMError as exc:
        cause = exc.__cause__
        if isinstance(cause, urllib.error.HTTPError):
            raise _HTTPStatus(int(cause.code)) from None
        raise RuntimeError(str(exc)) from None
    return [{"id": item.model, "display_name": None, "created": None, "tier": item.tier}
            for item in catalog]


# ---- cache (module dict keyed by provider id; only usable lists are kept,
# so a failure is retried on the next request instead of repeated for an hour)

_cache: dict[str, tuple[float, CatalogResult]] = {}
_cache_lock = threading.Lock()


def clear_cache_for_tests() -> None:
    with _cache_lock:
        _cache.clear()


def fetch_catalog(ref: ProviderRef, *, force: bool = False, timeout: float = 10.0,
                  http: Callable[..., tuple[int, bytes]] | None = None,
                  env: Mapping[str, str] = os.environ) -> CatalogResult:
    """One provider's model list. Never raises. `http` defaults to
    `_default_http`, resolved at call time (the test seam)."""
    http = http or _default_http
    now = time.monotonic()
    if not force:
        with _cache_lock:
            hit = _cache.get(ref.id)
        if hit is not None and now - hit[0] < CACHE_TTL_S:
            return hit[1]
    try:
        result = _fetch_uncached(ref, timeout=timeout, http=http, env=env)
    except Exception as exc:  # noqa: BLE001 — defensive: one provider never breaks the rest
        result = _result(ref, ok=False, source=_source(ref, ref.adapter),
                         category="unreachable", error=_sanitize(type(exc).__name__, None))
    if result.ok:
        with _cache_lock:
            _cache[ref.id] = (now, result)
    return result


def catalog_refs(refs: Iterable[ProviderRef]) -> list[ProviderRef]:
    """The refs a catalog request covers: every model provider (kind llm),
    including the ones that cannot list (they answer unsupported or
    not_configured explicitly). Services are the services topic."""
    return [r for r in refs if r.kind == "llm"]


def fetch_all(refs: Iterable[ProviderRef], *, force: bool = False,
              per_provider_timeout: float = 8.0, total_timeout: float = 20.0,
              http: Callable[..., tuple[int, bytes]] | None = None,
              env: Mapping[str, str] = os.environ) -> list[CatalogResult]:
    """Every ref in parallel, one result per ref in input order. A provider
    still running at `total_timeout` is "unreachable" / "timed out"; one
    failure never stops the others."""
    refs = list(refs)
    if not refs:
        return []
    pool = ThreadPoolExecutor(max_workers=min(8, len(refs)),
                              thread_name_prefix="status-catalog")
    try:
        futures = [pool.submit(fetch_catalog, ref, force=force,
                               timeout=per_provider_timeout, http=http, env=env)
                   for ref in refs]
        wait(futures, timeout=total_timeout)
        out: list[CatalogResult] = []
        for ref, fut in zip(refs, futures):
            if fut.done() and not fut.cancelled() and fut.exception() is None:
                out.append(fut.result())
            else:
                out.append(_result(ref, ok=False, source=_source(ref, ref.adapter),
                                   category="unreachable", error="timed out"))
        return out
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _profiles(registry: dict) -> dict[str, dict]:
    raw = registry.get("profiles") or {}
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items() if isinstance(v, dict)}
    return {str(p.get("name")): p for p in raw if isinstance(p, dict)}


def _sample(models: list[dict]) -> list[str]:
    # Newest first (stable sort, so equal timestamps stay in id order).
    dated = sorted((m for m in models if m.get("created")), key=lambda m: str(m["id"]))
    dated.sort(key=lambda m: str(m["created"]), reverse=True)
    undated = sorted((m for m in models if not m.get("created")), key=lambda m: str(m["id"]))
    return [str(m["id"]) for m in (dated + undated)[:SAMPLE_SIZE]]


def compare_to_registry(results: Iterable[CatalogResult], registry: dict, *,
                        env: Mapping[str, str] = os.environ) -> dict[str, dict]:
    """Per provider with a usable list: which configured profiles the
    catalog offers, which it does not, and what it offers that nothing is
    configured for. Providers whose fetch failed are absent (their result
    carries the error)."""
    refs = {r.id: r for r in discover_providers(registry=registry, access={}, env=env)}
    profiles = _profiles(registry)
    out: dict[str, dict] = {}
    for res in results:
        if not res.ok:
            continue
        if res.provider == "voice":
            model = str(env.get("OPENAI_MODEL") or "").strip()
            configured = [(f"voice:{model}", model)] if model else []
        else:
            ref = refs.get(res.provider)
            names = ref.profiles if ref is not None else ()
            configured = [(n, str(profiles.get(n, {}).get("model") or "")) for n in names]
        offered = {str(m["id"]) for m in res.models}
        configured_ids = {mid for _, mid in configured}
        extra = [m for m in res.models if str(m["id"]) not in configured_ids]
        out[res.provider] = {
            "configured_available": sorted(n for n, mid in configured if mid in offered),
            "configured_missing": sorted(n for n, mid in configured if mid not in offered),
            "offered_not_configured_count": len({str(m["id"]) for m in extra}),
            "offered_not_configured_sample": _sample(extra),
        }
    return out


def catalog_status(provider: str = "all", *, force: bool = False, registry: dict | None = None,
                   access: dict | None = None, env: Mapping[str, str] = os.environ,
                   http: Callable[..., tuple[int, bytes]] | None = None) -> dict[str, Any]:
    """The /api/status/catalog payload: results for every configured model
    provider (or one), plus the registry comparison."""
    if registry is None:
        from jarvis.agents.upgrade_agent import load_model_registry

        registry = load_model_registry()
    refs = catalog_refs(discover_providers(registry=registry, access=access, env=env))
    wanted = (provider or "all").strip()
    if wanted != "all":
        refs = [r for r in refs if r.id == wanted]
        if not refs:
            return {"ok": False, "error": f"unknown provider {wanted!r}"}
    results = fetch_all(refs, force=force, http=http, env=env)
    return {
        "ok": True,
        "generated_at": _now_iso(),
        "source": "catalog",
        "results": [as_payload(r) for r in results],
        "comparison": compare_to_registry(results, registry, env=env),
    }


def as_payload(result: CatalogResult) -> dict[str, Any]:
    """A result as the status payloads and the daily snapshot carry it:
    every field but the per-model upstream `facts`."""
    out = asdict(result)
    out.pop("facts", None)
    return out
