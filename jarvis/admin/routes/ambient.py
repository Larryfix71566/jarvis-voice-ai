"""Admin sidecar routes: ambient strip, device location and clipboard (/api/ambient, /api/location, /api/clipboard*).

Moved verbatim from jarvis/admin/server.py (B6). Helpers, state and imported
modules are reached as `srv.<name>` at call time, never imported here, so a
test that monkeypatches jarvis.admin.server is seen by these handlers.
Only jarvis.admin.server imports this module.
"""

from __future__ import annotations

from jarvis.admin import server as srv
from jarvis.admin.server import (  # request bodies named in signatures
    LocationBody,
)

# Routes register on the server's one FastAPI app (see the B6 note there).
app = srv.app


@app.get("/api/ambient")
def ambient() -> dict:
    """Engagement plan E4 — the console's idle ambient strip. Read-only:
    the next pending reminder (mcp_reminders.logic, same cross-boundary
    import pattern as mcp_git's logic above) and the running session
    summary (same jarvis.memory helper /api/memory uses). The client
    polls this every 60s while connected; chips for null fields hide."""
    srv.run_migrations()
    from mcp_servers.mcp_reminders.logic import list_reminders

    reminder = None
    result = list_reminders("pending")
    for r in result.get("reminders", []):
        # due_at ASC — first row is the next one up.
        reminder = {"text": r["message"], "due_at": r["due_at"]}
        break
    summary = srv.memory_module.get_summary_text() or None
    # Larry 2026-08-18: live weather for the current location — fetched
    # HERE (sidecar), never by the client; jarvis/ambient_weather.py
    # caches 15 min and degrades to None on any failure.
    from jarvis.ambient_weather import get_weather

    return {
        "ok": True,
        "reminder": reminder,
        "summary": summary,
        "weather": get_weather(),
        "system": srv._system_vitals(),
    }


@app.post("/api/location")
def set_location(body: LocationBody) -> dict:
    """Device location, posted by the Mac shell's CoreLocation manager
    (Larry 2026-08-18 — "I want to know where I am so that current
    weather is correct for my current location"). Coordinates are held in
    memory only (jarvis/ambient_weather.py), never written to disk or the
    run log, and go stale after an hour so a shell that stops reporting
    falls back to IP geolocation rather than pinning a place Larry left."""
    if not (-90.0 <= body.lat <= 90.0 and -180.0 <= body.lon <= 180.0):
        return {"ok": False, "error": "coordinates out of range"}
    from jarvis.ambient_weather import set_device_location

    set_device_location(body.lat, body.lon, body.label)
    return {"ok": True}


@app.post("/api/clipboard/clear")
def clipboard_clear() -> dict:
    """MORTIMER_HANDOFF_LOOP_PLAN.md H4 — wipe the clipboard and arm a
    read. The sidecar runs on Larry's Mac, so pbcopy/pbpaste are reachable
    here without any Swift change; the WKWebView bridge is fire-and-forget
    and browser clipboard read needs a user gesture a voice command cannot
    supply."""
    from jarvis import clipboard

    return clipboard.clear()


@app.get("/api/clipboard")
def clipboard_read() -> dict:
    """H4 — read the clipboard, but ONLY if a clear armed it, and disarm
    afterwards. The refusal is the safety property: an unarmed read would
    return whatever happened to be there, which may be a credential copied
    for an unrelated reason."""
    from jarvis import clipboard

    return clipboard.read()
