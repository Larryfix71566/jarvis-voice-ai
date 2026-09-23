"""SAYGM catalog and endpoint helpers.

No network call happens at import time. The catalog is authoritative for
whether a route is confidential; a model name or ``-TEE`` suffix alone is not.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "https://api.saygm.com/v1"
API_KEY_ENV = "SAYGM_API_KEY"


class SayGMError(RuntimeError):
    pass


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


def _models_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/models"


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
    key = api_key or os.environ.get(API_KEY_ENV)
    if not key:
        raise SayGMError(f"{API_KEY_ENV} is not set")
    request = Request(_models_url(base_url), headers={"Authorization": f"Bearer {key}"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured HTTPS endpoint
            payload = json.load(response)
    except Exception as exc:  # noqa: BLE001 - stable provider boundary
        raise SayGMError(f"SAYGM model catalog request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise SayGMError("SAYGM model catalog response is not an object")
    return parse_catalog(payload)


def confidential_model(catalog: list[SayGMModel], model: str) -> SayGMModel:
    for entry in catalog:
        if entry.model == model:
            if not entry.confidential:
                raise SayGMError(f"SAYGM model {model!r} is not a confidential route")
            return entry
    raise SayGMError(f"SAYGM model {model!r} is not present in the catalog")

