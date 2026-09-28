"""Spoken summaries of status payloads (spec T2.5, invariants I4 and I5).

`summarize(topic, payload)` is PURE: no I/O, no model call, deterministic,
and at most `MAX_CHARS` characters. The facts are computed by the sidecar;
this only arranges them. Every topic's first line names its source, so
"configured" is never passed off as "available" (I5).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

MAX_CHARS = 1500


def _clip(text: str) -> str:
    return text if len(text) <= MAX_CHARS else text[: MAX_CHARS - 1] + "…"


def _short(sha: Any) -> str:
    s = str(sha or "")
    return s[:7] if s and s != "unknown" else "unknown"


def _clock(iso: Any) -> str:
    """HH:MM in this machine's local time, or "" when unparseable."""
    try:
        return datetime.fromisoformat(str(iso)).astimezone().strftime("%H:%M")
    except (TypeError, ValueError):
        return ""


def _stamp(iso: Any) -> str:
    """YYYY-MM-DD HH:MM of a timestamp in its own offset (already local)."""
    try:
        return datetime.fromisoformat(str(iso)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return "an unknown time"


def _models(p: dict[str, Any]) -> str:
    lines = ["Source: registry (configured, not proof of availability)."]
    lines.append(f"Default: {p.get('default') or 'none'}.")
    profiles = {str(x.get("name")): x for x in p.get("profiles") or []}
    for ref in p.get("providers") or []:
        names = [n for n in ref.get("profiles") or [] if n in profiles]
        if not names:
            continue
        parts = []
        for name in names:
            prof = profiles[name]
            if prof.get("key_env") and not prof.get("key_present"):
                health = "key missing"
            else:
                health = str(prof.get("key_health") or "unknown")
            parts.append(f"{name} ({prof.get('tier') or 'no tier'}, {health})")
        lines.append(f"{ref.get('id')}: " + ", ".join(parts) + ".")
    gaps = p.get("coverage_gaps") or []
    lines.append("Coverage gaps: " + (", ".join(gaps) if gaps else "none") + ".")
    return "\n".join(lines)


def _services(p: dict[str, Any]) -> str:
    when = _clock(p.get("generated_at"))
    lines = [f"Source: live checks{' at ' + when if when else ''} (reachability now, launchd state)."]
    for row in p.get("services") or []:
        text = f"{row.get('name')}: {row.get('state')}"
        launchd = row.get("launchd")
        if launchd and launchd != "unknown":
            text += f", launchd {launchd}"
        lines.append(text + ".")
    src = p.get("source") or {}
    code = f"Code: commit {_short(src.get('head'))}"
    if src.get("dirty_files"):
        code += f", {src['dirty_files']} uncommitted file(s)"
    lines.append(code + ".")
    return "\n".join(lines)


def _build(p: dict[str, Any]) -> str:
    lines = [f"Source: the app bundle on disk ({p.get('app_path') or 'MortimerHost.app'})."]
    if not p.get("exists"):
        lines.append("The Mac app has not been built: no bundle found.")
        return "\n".join(lines)
    rev = p.get("MortimerSourceRevision")
    built = f"Built {_stamp(p.get('modified_at'))}"
    if rev and rev != "unknown":
        built += f" from commit {_short(rev)}"
    else:
        built += "; the bundle does not record its source commit"
    if p.get("MortimerSourceDirty") == "true":
        built += ", with uncommitted changes"
    if p.get("MortimerBuildConfiguration"):
        built += f" ({p['MortimerBuildConfiguration']} build)"
    lines.append(built + ".")
    head = _short(p.get("repo_head"))
    if p.get("matches_repo_head"):
        lines.append(f"It matches the current checkout ({head}).")
    else:
        lines.append(f"It does not match the current checkout ({head}).")
    return "\n".join(lines)


_LOCATION_SOURCES = {
    "device": "the Mac's own location",
    "ip": "IP geolocation (approximate)",
    "env": "a fixed location set in configuration",
}


def _location(p: dict[str, Any]) -> str:
    source = _LOCATION_SOURCES.get(str(p.get("source")), str(p.get("source") or "unknown"))
    if p.get("source") == "device" and p.get("age_s") is not None:
        source += f", reported {int(p['age_s']) // 60} minute(s) ago"
    label = str(p.get("label") or "").strip()
    place = label or f"coordinates {float(p.get('lat', 0)):.2f}, {float(p.get('lon', 0)):.2f}"
    return f"Source: {source}.\nLocation: {place}."


def _overview(p: dict[str, Any]) -> str:
    agents = p.get("agents") or []
    lines = ["Source: configuration (config/agents.yaml, config/mcp_servers.yaml, switches)."]
    named = ", ".join(f"{a.get('name')} ({a.get('model_profile') or 'voice model'})" for a in agents)
    lines.append(f"{len(agents)} agents: {named}.")
    lines.append(f"{len(p.get('mcp_servers') or [])} MCP servers.")
    off = [name for name, state in (p.get("flags") or {}).items() if state == "off"]
    lines.append("Switches off: " + (", ".join(off) if off else "none") + ".")
    return "\n".join(lines)


_CATALOG_SAMPLE = 5


def _catalog(p: dict[str, Any]) -> str:
    lines = ["Source: live provider catalogs — what each account offers now, "
             "not the registry (time fetched shown per provider)."]
    comparison = p.get("comparison") or {}
    for r in p.get("results") or []:
        pid = str(r.get("provider"))
        if not r.get("ok"):
            why = str(r.get("error") or "").rstrip(".")
            lines.append(f"{pid}: {r.get('error_category') or 'failed'}"
                         + (f" ({why})." if why else "."))
            continue
        when = _clock(r.get("fetched_at"))
        text = f"{pid} (catalog:{pid}@{when or 'unknown time'}): {len(r.get('models') or [])} models offered."
        cmp_ = comparison.get(pid)
        if cmp_:
            missing = cmp_.get("configured_missing") or []
            if missing:
                text += " Configured but NOT offered: " + ", ".join(missing) + "."
            elif cmp_.get("configured_available"):
                text += " Every configured model is offered."
            count = int(cmp_.get("offered_not_configured_count") or 0)
            if count:
                sample = (cmp_.get("offered_not_configured_sample") or [])[:_CATALOG_SAMPLE]
                text += f" {count} offered but not configured"
                text += (", newest first: " + ", ".join(sample) + ".") if sample else "."
        lines.append(text)
    return "\n".join(lines)


_PROBE_CATEGORIES = {
    "authentication": "not signed in, or the login was refused (authentication)",
    "model_unavailable": "that model is not available on this subscription (model_unavailable)",
    "timeout": "it timed out (timeout)",
    "runtime_environment": "the command could not run in this environment (runtime_environment)",
    "runtime_error": "the command failed (runtime_error)",
}


def _subscription(p: dict[str, Any]) -> str:
    probe = p.get("probe") or {}
    which = str(probe.get("which") or "unknown")
    name = which.capitalize()
    when = _clock(probe.get("probed_at")) or "an unknown time"
    head = f"Source: a live probe of the {name} subscription at {when} (probe:{which})"
    if probe.get("cached"):
        head += "; reused, since one probe per model is allowed every 10 minutes"
    lines = [head + ".", f"Model tried: {probe.get('model')} (exactly as named)."]
    category = probe.get("category")
    if category == "not_installed":
        lines.append(f"Result: the {probe.get('command') or which} command is not installed "
                     "where Mortimer's services run, so nothing was tried.")
        lines.append("No subscription quota was used.")
        return "\n".join(lines)
    if probe.get("ok"):
        lines.append("Result: it answered — the model is available on this subscription.")
    elif category:
        lines.append("Result: failed — " + _PROBE_CATEGORIES.get(str(category), str(category)) + ".")
    elif probe.get("response_present"):
        lines.append("Result: it answered, but not with the expected check text.")
    else:
        lines.append("Result: no answer came back.")
    lines.append(f"This check used a small amount of your {name} subscription.")
    return "\n".join(lines)


_TOPICS = {
    "models": _models,
    "services": _services,
    "build": _build,
    "location": _location,
    "overview": _overview,
    "catalog": _catalog,
    "subscription": _subscription,
}


def summarize(topic: str, payload: dict) -> str:
    if not isinstance(payload, dict):
        return "system_status failed: the admin sidecar returned no status."
    if not payload.get("ok"):
        error = str(payload.get("error") or "unknown error").rstrip(".")
        return _clip(f"system_status failed: {error}.")
    fn = _TOPICS.get(topic)
    if fn is None:
        return f"system_status failed: unknown topic {topic!r}."
    return _clip(fn(payload))
