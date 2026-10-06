"""SAYGM catalog and endpoint helpers.

No network call happens at import time. The catalog is authoritative for
whether a route is confidential; a model name or ``-TEE`` suffix alone is not.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DEFAULT_BASE_URL = "https://api.saygm.com/v1"
API_KEY_ENV = "SAYGM_API_KEY"


class SayGMError(RuntimeError):
    pass


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # urllib otherwise forwards request headers, including Authorization,
        # to the redirect destination. The approved origin is the whole gate.
        return None


def urlopen(request: Request, *, timeout: float):
    """Mockable catalog transport whose credential-bearing request cannot redirect."""
    return build_opener(_NoRedirectHandler()).open(request, timeout=timeout)


@dataclass(frozen=True)
class SayGMModel:
    model: str
    tier: str
    gateway_provider: str | None
    owned_by: str | None
    raw: dict

    @property
    def confidential(self) -> bool:
        return self.tier == "confidential" and self.model.endswith("-TEE")

    @property
    def api_shapes(self) -> tuple[str, ...]:
        """Catalog-declared interfaces; missing metadata proves none."""
        shapes = self.raw.get("api_shapes")
        if not isinstance(shapes, list) or any(not isinstance(item, str) for item in shapes):
            return ()
        return tuple(shapes)

    @property
    def capabilities(self) -> tuple[str, ...]:
        """Capabilities evidenced by the catalog for Mortimer's adapter.

        Chat Completions proves the text interface. The current catalog does
        not prove model-specific tools, images or streaming support, so those
        must not be inherited from the gateway's general capabilities.
        """
        return ("text",) if "chat.completions" in self.api_shapes else ()


def validate_endpoint(base_url: str, credential_env: str = API_KEY_ENV) -> str:
    """Pin credential egress in protected code, outside routine config edits.

    A different gateway requires a future human-owned endpoint registry
    entry. Query strings, user info and alternate paths never carry this key.
    """
    try:
        parsed = urlsplit(base_url)
        approved = (
            parsed.scheme == "https" and parsed.hostname == "api.saygm.com"
            and parsed.port in {None, 443} and parsed.username is None
            and parsed.password is None and parsed.path.rstrip("/") == "/v1"
            and not parsed.query and not parsed.fragment
        )
    except (TypeError, ValueError):
        approved = False
    if not approved or credential_env != API_KEY_ENV:
        raise SayGMError("SAYGM endpoint or credential reference is not approved")
    return DEFAULT_BASE_URL


def _models_url(base_url: str) -> str:
    return validate_endpoint(base_url) + "/models"


def parse_catalog(payload: dict) -> list[SayGMModel]:
    entries = payload.get("data", payload.get("models", []))
    if not isinstance(entries, list):
        raise SayGMError("SAYGM model catalog has no list of models")
    result: list[SayGMModel] = []
    for item in entries:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        result.append(SayGMModel(
            model=str(item["id"]),
            tier=str(item.get("tier") or "open"),
            gateway_provider=item.get("gateway_provider"),
            owned_by=item.get("owned_by"),
            raw=item,
        ))
    return result


def fetch_catalog(*, api_key: str | None = None, base_url: str = DEFAULT_BASE_URL,
                  timeout: float = 10.0) -> list[SayGMModel]:
    base_url = validate_endpoint(base_url)
    key = api_key or os.environ.get(API_KEY_ENV)
    if not key:
        raise SayGMError(f"{API_KEY_ENV} is not set")
    request = Request(_models_url(base_url), headers={"Authorization": f"Bearer {key}"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured HTTPS endpoint
            payload = json.load(response)
    except Exception as exc:  # noqa: BLE001 - stable provider boundary
        status = getattr(exc, "code", None)
        status_hint = f", HTTP {status}" if type(status) is int and 100 <= status <= 599 else ""
        raise SayGMError(
            f"SAYGM model catalog request failed (error_type={type(exc).__name__[:64]}{status_hint})"
        ) from exc
    if not isinstance(payload, dict):
        raise SayGMError("SAYGM model catalog response is not an object")
    return parse_catalog(payload)


def catalog_model(catalog: list[SayGMModel], model: str) -> SayGMModel:
    """Select one exact, usable model id without inferring an alias."""
    matches = [entry for entry in catalog if entry.model == model]
    if not matches:
        raise SayGMError(f"SAYGM model {model!r} is not present in the catalog")
    if len(matches) != 1:
        raise SayGMError(f"SAYGM model {model!r} has ambiguous catalog entries")
    entry = matches[0]
    if "available" in entry.raw and entry.raw["available"] is not True:
        raise SayGMError(f"SAYGM model {model!r} is unavailable")
    if "chat.completions" not in entry.api_shapes:
        raise SayGMError(f"SAYGM model {model!r} does not support chat.completions")
    return entry


def confidential_model(catalog: list[SayGMModel], model: str) -> SayGMModel:
    # Select an exact confidential id, never the first open/TEE alias in the
    # provider's list. The complete id (including any slashes) reaches the wire.
    wanted = model if model.endswith("-TEE") else model + "-TEE"
    if not any(entry.model == wanted for entry in catalog):
        if any(entry.model == model for entry in catalog):
            raise SayGMError(f"SAYGM model {model!r} is not a confidential route")
        raise SayGMError(f"SAYGM model {wanted!r} is not present in the catalog")
    entry = catalog_model(catalog, wanted)
    if not entry.confidential:
        raise SayGMError(f"SAYGM model {wanted!r} is not a confidential route")
    return entry
