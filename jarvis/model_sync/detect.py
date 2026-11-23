"""Decide what the daily new-model check found (WS-41). Pure: no I/O.

Inputs are the three collections described in
docs/plans/MORTIMER_MODEL_SYNC_PLAN_2026-11-23.md §2 (public sources,
subscription lists, pins). Output is a list of findings, each a plain dict
with a stable ``key`` the runner uses to remember what it already handled:

- ``new_model``: a newer release in the same lineage as a pinned model, or
  the Codex default moving to a model Mortimer doesn't pin. Carries the
  files that pin the old ID, the contexts (profiles/workloads) and whether
  the voice model is one of them.
- ``deprecation``: a pinned model that the vendor has deprecated or
  retired, with days left and an escalation level.
- ``cli``: an installed CLI that is older than the newest release or is not
  one of the versions Mortimer verified.

Nothing here decides that a model is *better*; certification does that.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable

from jarvis.model_sync import ids

# Vendor prefixes that mean "through a third-party API router", not through a
# subscription. A pin written that way is not something a subscription
# candidate can replace. `anthropic/` and `moonshotai/` are the vendors' own
# identity prefixes (model_endpoints.yaml supervisor identity) and count.
_ROUTER_PREFIXES = ("openai/", "x-ai/", "google/", "deepseek/", "meta-llama/",
                    "mistralai/", "qwen/")
VOICE_FILE = ".env:OPENAI_MODEL"
# Contexts (pins.scan_config's nearest key) that mean "the voice model":
# config/model_access.yaml workloads.voice_supervisor.profile.
VOICE_CONTEXTS = frozenset({"voice", "voice_supervisor"})

LEVELS = ("notice", "task", "urgent", "retired")


def level_for(days_left: int | None) -> str:
    """Notice beyond 30 days, task at 30 or less, urgent at 7 or less, past the date retired. With no
    date yet it is a notice."""
    if days_left is None:
        return "notice"
    if days_left < 0:
        return "retired"
    if days_left <= 7:
        return "urgent"
    if days_left <= 30:
        return "task"
    return "notice"


def level_rank(level: str | None) -> int:
    return LEVELS.index(level) if level in LEVELS else -1


def _version_tuple(text: Any) -> tuple[int, ...] | None:
    """`2.1.330 (Claude Code)` / `codex-cli 0.171.0` / `0.171.0` -> (2,1,330).
    Pre-release suffixes sort before the release (0.163.0-alpha < 0.163.0)."""
    import re

    m = re.search(r"(\d+)\.(\d+)\.(\d+)(-[0-9A-Za-z.]+)?", str(text or ""))
    if not m:
        return None
    base = tuple(int(m.group(i)) for i in (1, 2, 3))
    return base + ((0,) if m.group(4) else (1,))


def _pinned(pins: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """model -> {files, contexts, voice, vendor} for every subscription-shaped pin."""
    out: dict[str, dict[str, Any]] = {}
    for entry in pins.get("models") or []:
        if not isinstance(entry, dict):
            continue
        raw = str(entry.get("raw") or entry.get("model") or "").strip().lower()
        if raw.startswith(_ROUTER_PREFIXES):
            continue
        parsed = ids.parse(str(entry.get("model") or ""))
        if parsed is None:
            continue
        slot = out.setdefault(parsed.raw, {"files": [], "contexts": [], "voice": False,
                                           "vendor": parsed.vendor})
        f = str(entry.get("file") or "")
        if f and f not in slot["files"]:
            slot["files"].append(f)
        c = str(entry.get("context") or "")
        if c and c not in slot["contexts"]:
            slot["contexts"].append(c)
        if c in VOICE_CONTEXTS:
            slot["voice"] = True
    voice = pins.get("voice") or {}
    vparsed = ids.parse(str(voice.get("model") or "")) if isinstance(voice, dict) else None
    if vparsed is not None:
        slot = out.setdefault(vparsed.raw, {"files": [], "contexts": [], "voice": False,
                                            "vendor": vparsed.vendor})
        slot["voice"] = True
        if "voice" not in slot["contexts"]:
            slot["contexts"].append("voice")
    for slot in out.values():
        slot["files"].sort()
    return out


def _pool(public: dict[str, Any], subs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every model some source says exists -> {sources, on_subscription}."""
    pool: dict[str, dict[str, Any]] = {}

    def add(model: Any, source: str, subscription: bool = False) -> None:
        parsed = ids.parse(str(model or ""))
        if parsed is None:
            return
        slot = pool.setdefault(parsed.raw, {"sources": [], "on_subscription": False})
        if source not in slot["sources"]:
            slot["sources"].append(source)
        slot["on_subscription"] = slot["on_subscription"] or subscription

    for row in public.get("launches") or []:
        if isinstance(row, dict):
            add(row.get("model"), str(row.get("source") or "public"))
    for row in public.get("deprecations") or []:
        # The deprecations table lists every active model; that is evidence
        # it exists. Deprecated and retired rows are not candidates.
        if isinstance(row, dict) and str(row.get("state") or "") == "active":
            add(row.get("model"), str(row.get("source") or "public"))
    claude = (subs.get("claude") or {}) if isinstance(subs, dict) else {}
    for alias, probe in sorted((claude.get("aliases") or {}).items()):
        if isinstance(probe, dict) and probe.get("ok") and probe.get("model"):
            add(probe["model"], f"claude_alias:{alias}", subscription=True)
    codex = (subs.get("codex") or {}) if isinstance(subs, dict) else {}
    if codex.get("ok"):
        for m in codex.get("models") or []:
            if isinstance(m, dict) and not m.get("hidden"):
                add(m.get("id"), "codex_model_list", subscription=True)
    return pool


def _new_models(pinned: dict[str, dict[str, Any]], pool: dict[str, dict[str, Any]],
                subs: dict[str, Any]) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    pinned_ids = set(pinned)
    for old, slot in sorted(pinned.items()):
        newer = [m for m in pool if ids.is_newer(m, old)]
        if not newer:
            continue
        best = next(iter(ids.newest(newer).values()))
        # Already pinned somewhere else (e.g. one profile moved, another
        # not)? Still a candidate for this pin: the files differ.
        out[old] = _candidate(old, best, slot, pool[best], "newer release")
    codex = (subs.get("codex") or {}) if isinstance(subs, dict) else {}
    default = ids.parse(str(codex.get("default") or "")) if codex.get("ok") else None
    if default is not None and default.raw not in pinned_ids:
        # Only pins Codex itself offers are Codex-subscription pins; an
        # OpenAI ID elsewhere in config (an old API default) is not.
        offered = {str(m.get("id")) for m in codex.get("models") or [] if isinstance(m, dict)}
        openai_pins = [m for m, s in pinned.items() if s["vendor"] == "openai" and m in offered]
        for old in openai_pins:
            if old in out or ids.is_newer(old, default.raw):
                continue
            src = pool.get(default.raw) or {"sources": ["codex_model_list"],
                                             "on_subscription": True}
            out[old] = _candidate(old, default.raw, pinned[old], src, "new Codex default")
    return list(out.values())


def _candidate(old: str, new: str, slot: dict[str, Any], src: dict[str, Any],
               reason: str) -> dict[str, Any]:
    return {"kind": "new_model", "key": f"new_model:{old}->{new}", "model": new,
            "replaces": old, "vendor": slot["vendor"], "reason": reason,
            "files": list(slot["files"]), "roles": list(slot["contexts"]),
            "voice": bool(slot["voice"]), "sources": list(src["sources"]),
            "on_subscription": bool(src["on_subscription"])}


def _deprecations(pinned: dict[str, dict[str, Any]], public: dict[str, Any],
                  pool: dict[str, dict[str, Any]], today: date) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in public.get("deprecations") or []:
        if not isinstance(row, dict):
            continue
        state = str(row.get("state") or "")
        if state not in ("deprecated", "retired"):
            continue
        dep_model = str(row.get("model") or "")
        for old, slot in sorted(pinned.items()):
            if not ids.same_model(old, dep_model):
                continue
            retirement = row.get("retirement")
            days = None
            if retirement:
                try:
                    days = (date.fromisoformat(str(retirement)) - today).days
                except ValueError:
                    days = None
            level = "retired" if state == "retired" else level_for(days)
            replacement = row.get("replacement")
            if not ids.parse(str(replacement or "")):
                newer = [m for m in pool if ids.is_newer(m, old)]
                replacement = next(iter(ids.newest(newer).values()), None) if newer else None
            prev = out.get(old)
            if prev and level_rank(prev["level"]) >= level_rank(level):
                continue
            out[old] = {"kind": "deprecation", "key": f"deprecation:{old}", "model": old,
                        "vendor_model": dep_model, "state": state,
                        "retirement": retirement, "days_left": days, "level": level,
                        "replacement": replacement, "files": list(slot["files"]),
                        "roles": list(slot["contexts"]), "voice": bool(slot["voice"]),
                        "source": row.get("source")}
    return list(out.values())


def _cli(public: dict[str, Any], subs: dict[str, Any], pins: dict[str, Any],
         installed: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    latest = public.get("cli_latest") or {}
    verified = pins.get("cli") or {}
    for cli in ("claude", "codex"):
        have = installed.get(cli)
        if not have:
            continue
        have_v = _version_tuple(have)
        latest_v = _version_tuple(latest.get(cli))
        ok_set = [str(v) for v in verified.get(cli) or []]
        is_verified = any(_version_tuple(v) == have_v for v in ok_set) if have_v else False
        behind = bool(have_v and latest_v and have_v[:3] < latest_v[:3])
        if is_verified and not behind:
            continue
        out.append({"kind": "cli", "key": f"cli:{cli}:{have}:{latest.get(cli)}", "cli": cli,
                    "installed": have, "latest": latest.get(cli), "verified": ok_set,
                    "installed_verified": is_verified, "behind": behind})
    return out


def detect(public: dict[str, Any], subs: dict[str, Any], pins: dict[str, Any], *,
           today: date, installed: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """All findings, deprecations first (they have deadlines), then new
    models, then CLI drift. ``installed`` maps cli -> installed version
    string (defaults to the Claude version in ``subs``)."""
    public = public if isinstance(public, dict) else {}
    subs = subs if isinstance(subs, dict) else {}
    pins = pins if isinstance(pins, dict) else {}
    installed = dict(installed or {})
    installed.setdefault("claude", ((subs.get("claude") or {}).get("version")))
    pinned = _pinned(pins)
    pool = _pool(public, subs)
    deps = sorted(_deprecations(pinned, public, pool, today),
                  key=lambda f: (-level_rank(f["level"]), f["days_left"] if f["days_left"] is not None else 10**6))
    news = sorted(_new_models(pinned, pool, subs), key=lambda f: f["key"])
    return deps + news + _cli(public, subs, pins, installed)


def candidates(findings: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """What certification should look at: every new_model finding, plus a
    deprecation's replacement when no new_model finding already covers it."""
    found = [f for f in findings if f.get("kind") == "new_model"]
    covered = {f["replaces"] for f in found}
    for f in findings:
        if f.get("kind") != "deprecation" or f["model"] in covered:
            continue
        rep = ids.parse(str(f.get("replacement") or ""))
        if rep is None:
            continue
        old = ids.parse(f["model"])
        found.append({"kind": "new_model", "key": f"new_model:{f['model']}->{rep.raw}",
                      "model": rep.raw, "replaces": f["model"],
                      "vendor": old.vendor if old else rep.vendor,
                      "reason": f"{f['model']} {'retired' if f['level'] == 'retired' else 'retires'}"
                                + (f" on {f['retirement']}" if f.get("retirement") else ""),
                      "files": list(f["files"]), "roles": list(f["roles"]),
                      "voice": bool(f["voice"]), "sources": [str(f.get("source") or "")],
                      "on_subscription": False})
    return found
