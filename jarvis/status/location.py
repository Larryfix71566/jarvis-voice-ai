"""`current_location()` — where the user is, and how we know (spec T2.3).

Reuses jarvis.ambient_weather's one resolver: an env override, else the
device location the Mac app posts to the sidecar (`POST /api/location`,
held in the sidecar's memory — which is why this runs there), else IP
geolocation. The `source` field says which answered.
"""

from __future__ import annotations

from typing import Any, Callable

from jarvis import ambient_weather


def current_location(*, fetch: Callable[[str], Any] | None = None) -> dict[str, Any]:
    loc = ambient_weather._resolve_location(fetch or ambient_weather._fetch_json)
    if loc is None:
        return {"ok": False, "error": "no location available"}
    return {"ok": True, **loc}
