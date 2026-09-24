"""The daily status job (spec T4.5, L4/L5): `python -m jarvis.status.daily`.

Run once a day by launchd (`com.mortimer.status-daily`, 06:30, see
scripts/launchd_gen.py's CALENDAR_JOBS). It reads everything the status
tools can read on request, for EVERY configured provider (discovered from
configuration, never a list kept here — L3):

1. `discover_providers()`
2. every model provider's catalog, forced (`fetch_all`), then — spec P5
   A3, the split plan's §4a sync — one `model_catalog.<endpoint>.json` per
   registry endpoint rendered from those lists into the IGNORED
   `data/status/generated/` (never the tracked `config/generated/`, never
   `model_endpoints.yaml`/`model_profiles.yaml`)
3. the Claude and Codex subscription probes on their default models, forced
4. `keyhealth.probe_all()`
5. `model_access_status()` (for coverage gaps)

and writes `data/status/daily-YYYY-MM-DD.json` atomically, keeping the
newest 30. When something changed since the previous file — new models on
a provider we use, a configured model no longer offered, a subscription
probe flipping, a key verdict changing, or any coverage gap — it leaves ONE
notice in the outbox (`jarvis.notices`), spoken after the next greeting.
Nothing changed, no notice.

The exit code is always 0: a failure is recorded inside the file (the
`errors` list), because a launchd retry storm helps nobody.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import IO, Any, Callable, Iterable

from jarvis.status.logs import redact

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
STATUS_DIR = REPO_ROOT / "data" / "status"
# The tracked catalogue baseline. The daily job never writes under it: a
# tracked file changing every day would dirty the runtime checkout. Moving
# rendered catalogues there is the §4a follow-on PR job (out of scope).
TRACKED_CONFIG_DIR = REPO_ROOT / "config"
KEEP_FILES = 30
MAX_NOTICE_CHARS = 600
PREFIX, SUFFIX = "daily-", ".json"
GENERATED_DIRNAME = "generated"  # data/status/generated/model_catalog.<endpoint>.json
SUBSCRIPTIONS = ("claude", "codex")

# Spoken names only; which providers exist always comes from configuration.
_DISPLAY = {"openrouter": "OpenRouter", "anthropic": "Anthropic", "moonshot": "Moonshot",
            "saygm": "SAYGM", "openai": "OpenAI", "voice": "The voice endpoint"}


def _name(pid: str) -> str:
    return _DISPLAY.get(pid, pid)


def _err(step: str, exc: BaseException) -> dict[str, str]:
    return {"step": step, "error": redact(f"{type(exc).__name__}: {exc}")[:200]}


# ---- collection -----------------------------------------------------------

def _default_deps() -> dict[str, Callable[..., Any]]:
    from jarvis import keyhealth
    from jarvis.status import catalog, services, subscriptions
    from jarvis.status.models import model_access_status
    from jarvis.status.providers import discover_providers

    def load_registry() -> dict:
        from jarvis.agents.upgrade_agent import load_model_registry

        return load_model_registry()

    def load_layers() -> dict:
        from jarvis.agents.upgrade_agent import load_registry_layers

        return load_registry_layers()

    return {
        "registry": load_registry,
        "layers": load_layers,
        "discover": lambda registry: discover_providers(registry=registry),
        "fetch_all": lambda refs: catalog.fetch_all(catalog.catalog_refs(refs), force=True),
        "compare": catalog.compare_to_registry,
        "probe": lambda which: subscriptions.probe_subscription(which, force=True),
        "keyprobe": lambda registry: keyhealth.probe_all(registry),
        "access_status": lambda registry: model_access_status(registry=registry),
        "head": services.repo_head,
    }


def collect(deps: dict[str, Callable[..., Any]] | None = None, *,
            now: datetime | None = None,
            generated_dir: Path | None = None) -> dict[str, Any]:
    """One snapshot. Every step is guarded: a failure is recorded in
    `errors` and the rest still run. With `generated_dir`, the catalogs are
    also rendered there per endpoint (`generated_catalogs` in the snapshot)."""
    d = {**_default_deps(), **(deps or {})}
    now = now or datetime.now(timezone.utc)
    snap: dict[str, Any] = {
        "generated_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "source_head": None, "coverage_gaps": [], "catalogs": [], "comparison": {},
        "subscriptions": {}, "key_health": {}, "errors": [],
    }
    try:
        snap["source_head"] = d["head"]()
    except Exception as exc:  # noqa: BLE001
        snap["errors"].append(_err("source_head", exc))
    registry: dict = {}
    try:
        registry = d["registry"]()
    except Exception as exc:  # noqa: BLE001
        snap["errors"].append(_err("registry", exc))
    refs: list = []
    try:
        refs = d["discover"](registry)
        # Review finding 7: lets diff() tell when the voice endpoint is
        # another provider's API under a second name.
        snap["base_urls"] = {str(r.id): str(r.base_url) for r in refs
                             if getattr(r, "base_url", None)}
    except Exception as exc:  # noqa: BLE001
        snap["errors"].append(_err("discover_providers", exc))
    results: list = []
    try:
        results = list(d["fetch_all"](refs))
        snap["catalogs"] = [_as_payload(r) for r in results]
    except Exception as exc:  # noqa: BLE001
        snap["errors"].append(_err("catalogs", exc))
    if generated_dir is not None:
        try:
            snap["generated_catalogs"] = render_endpoint_catalogs(
                d["layers"](), refs, results, out_dir=generated_dir)
        except Exception as exc:  # noqa: BLE001
            snap["errors"].append(_err("generated_catalogs", exc))
    try:
        snap["comparison"] = d["compare"](results, registry)
    except Exception as exc:  # noqa: BLE001
        snap["errors"].append(_err("comparison", exc))
    for which in SUBSCRIPTIONS:
        try:
            snap["subscriptions"][which] = d["probe"](which)
        except Exception as exc:  # noqa: BLE001
            snap["errors"].append(_err(f"subscription:{which}", exc))
    try:
        snap["key_health"] = dict(d["keyprobe"](registry))
    except Exception as exc:  # noqa: BLE001
        snap["errors"].append(_err("key_health", exc))
    try:
        snap["coverage_gaps"] = list(d["access_status"](registry).get("coverage_gaps") or [])
    except Exception as exc:  # noqa: BLE001
        snap["errors"].append(_err("model_access_status", exc))
    return snap


# ---- files -----------------------------------------------------------------

def _files(status_dir: Path) -> list[Path]:
    if not status_dir.is_dir():
        return []
    return sorted(p for p in status_dir.iterdir()
                  if p.name.startswith(PREFIX) and p.name.endswith(SUFFIX))


def _replace_atomic(path: Path, write: Callable[[IO[str]], None]) -> None:
    """Write through `write` to a temp file in the same directory, then
    os.replace: a reader sees the old file or the whole new one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            write(fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON to a temp file in the same directory, then os.replace."""
    def _json(fh: IO[str]) -> None:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")

    _replace_atomic(path, _json)


def prune(status_dir: Path, keep: int = KEEP_FILES) -> list[Path]:
    """Delete all but the newest `keep` daily files; returns what went."""
    files = _files(status_dir)
    gone = files[:-keep] if keep > 0 else files
    for p in gone:
        try:
            p.unlink()
        except OSError:
            pass
    return gone


def load_previous(status_dir: Path, today_name: str) -> dict[str, Any] | None:
    """The newest daily file that is not today's."""
    for p in reversed(_files(status_dir)):
        if p.name == today_name:
            continue
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


# ---- per-endpoint catalogues (spec P5 A3; split plan §4a) -------------------

GENERATED_NOTE = (
    "GENERATED by the daily status job (python -m jarvis.status.daily) - do not "
    "hand-edit. What one registry endpoint's provider offered, joined to the "
    "profile pool by identity (docs/plans/"
    "MORTIMER_MODEL_REGISTRY_SPLIT_PLAN.md section 4a). Runtime data under the "
    "ignored data/status/generated/; only the section 4a follow-on PR job moves "
    "it into the tracked config/generated/.")


def _as_payload(result: Any) -> dict[str, Any]:
    from jarvis.status.catalog import as_payload

    return as_payload(result)


def _field(result: Any, name: str, default: Any = None) -> Any:
    if isinstance(result, dict):
        return result.get(name, default)
    return getattr(result, name, default)


def _per_mtok(value: Any) -> float | None:
    """A provider's USD-per-token price (OpenRouter sends strings) as USD
    per million tokens; None when absent, unparseable or negative (a
    variable-price router)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        per_token = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not per_token.is_finite() or per_token < 0:
        return None
    return float(per_token * 1_000_000)


def _vendor(identities: Iterable[str], fallback: str) -> str:
    """The identity vendor prefix this endpoint's profiles already use
    (e.g. `moonshotai` on the moonshot endpoint), else the provider."""
    counts: dict[str, int] = {}
    for ident in identities:
        if "/" in ident:
            v = ident.split("/", 1)[0]
            counts[v] = counts.get(v, 0) + 1
    return min(counts, key=lambda v: (-counts[v], v)) if counts else fallback


def catalog_entries(result: Any, profiles: list[dict[str, Any]], provider: str
                    ) -> list[dict[str, Any]]:
    """One endpoint's catalogue entries in the §4a schema (the loader's
    CATALOG_ENTRY_KEYS, in order). `identity` is the configured profile's
    when a profile on this endpoint uses the model string (so the join
    holds exactly), the id itself when it is vendor-qualified, else
    `<vendor>/<id>`. Price and context fields are filled when the provider
    published them, otherwise null; nothing is invented."""
    from jarvis.agents.upgrade_agent import CATALOG_ENTRY_KEYS

    by_model = {str(p.get("model")): str(p.get("identity")) for p in profiles
                if p.get("model") and p.get("identity")}
    vendor = _vendor(by_model.values(), provider)
    facts = _field(result, "facts") or {}
    fetched_at, source = _field(result, "fetched_at"), _field(result, "source")
    entries: dict[str, dict[str, Any]] = {}
    for model in _field(result, "models") or ():
        mid = str(model.get("id") or "").strip()
        if not mid or mid in entries:
            continue
        found = facts.get(mid) or {}
        pricing = found.get("pricing") or {}
        entry = dict.fromkeys(CATALOG_ENTRY_KEYS)
        entry.update(
            identity=by_model.get(mid) or (mid if "/" in mid else f"{vendor}/{mid}"),
            model=mid,
            context_window=found.get("context_length"),
            input_price_per_mtok=_per_mtok(pricing.get("prompt")),
            output_price_per_mtok=_per_mtok(pricing.get("completion")),
            fetched_at=fetched_at,
            source=source,
        )
        entries[mid] = entry
    return sorted(entries.values(), key=lambda e: (str(e["identity"]), str(e["model"])))


def _norm_url(url: Any) -> str:
    return str(url or "").strip().rstrip("/")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def render_endpoint_catalogs(layers: dict[str, Any], refs: Iterable[Any],
                             results: Iterable[Any], *, out_dir: Path
                             ) -> dict[str, dict[str, Any]]:
    """Write `model_catalog.<endpoint>.json` into `out_dir` for every
    registry endpoint whose provider's list was fetched from that
    endpoint's own base URL. An endpoint without a usable list (a
    subscription, a failed fetch) is skipped and keeps yesterday's file, so
    one provider down ages only its own entries (§4a.2). Returns endpoint ->
    {"file", "models"} or {"skipped": reason}. Never writes anywhere under
    the tracked config/ directory, and only files the loader's catalogue
    naming produces."""
    from jarvis.agents.upgrade_agent import catalog_path

    if _is_within(out_dir, TRACKED_CONFIG_DIR):
        raise ValueError("the daily job never writes under config/ (spec P5 A3)")
    refs = list(refs)
    by_provider = {str(_field(r, "provider")): r for r in results}
    profiles = [p for p in layers.get("profiles") or [] if isinstance(p, dict)]
    out: dict[str, dict[str, Any]] = {}
    for eid, endpoint in sorted((layers.get("endpoints") or {}).items()):
        mine = [p for p in profiles if str(p.get("endpoint")) == str(eid)]
        names = {str(p.get("name")) for p in mine}
        ref = next((r for r in refs if names & set(r.profiles)), None)
        if ref is None:
            out[eid] = {"skipped": "no discovered provider serves this endpoint"}
            continue
        base = _norm_url(endpoint.get("base_url"))
        if base and _norm_url(ref.base_url) != base:
            out[eid] = {"skipped": "the catalog was fetched from a different base URL"}
            continue
        result = by_provider.get(ref.id)
        if result is None or not _field(result, "ok"):
            why = _field(result, "error_category") if result is not None else None
            out[eid] = {"skipped": f"no model list ({why or 'not fetched'})"}
            continue
        entries = catalog_entries(result, mine, str(endpoint.get("provider") or ref.id))
        doc = {"_generated": GENERATED_NOTE, "schema": 1, "endpoint": eid,
               "provider": endpoint.get("provider"), "models": entries}
        text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
        path = out_dir / catalog_path(eid).name  # the loader's naming, our directory
        _replace_atomic(path, lambda fh, text=text: fh.write(text))
        out[eid] = {"file": path.name, "models": len(entries)}
    return out


# ---- diff and notice (pure) -------------------------------------------------

def _catalog_ids(snap: dict[str, Any]) -> dict[str, list[str]]:
    """provider -> offered ids, for providers whose fetch succeeded."""
    out: dict[str, list[str]] = {}
    for r in snap.get("catalogs") or []:
        if isinstance(r, dict) and r.get("ok"):
            out[str(r.get("provider"))] = [str(m.get("id")) for m in r.get("models") or []]
    return out


def _voice_is_a_duplicate(snap: dict[str, Any]) -> bool:
    """Review finding 7: True when the voice endpoint's list came from the
    same API as another successful result (same base URL; for snapshots
    without base URLs, the identical model list), so it is not reported
    a second time."""
    ids = _catalog_ids(snap)
    if "voice" not in ids:
        return False
    others = [pid for pid in ids if pid != "voice"]
    urls = {pid: str(u).strip().rstrip("/").lower()
            for pid, u in (snap.get("base_urls") or {}).items() if u}
    if urls.get("voice"):
        return any(urls.get(pid) == urls["voice"] for pid in others)
    return bool(ids["voice"]) and any(sorted(ids[pid]) == sorted(ids["voice"])
                                      for pid in others)


def diff(prev: dict[str, Any] | None, cur: dict[str, Any]) -> dict[str, Any]:
    """What changed since `prev` (None on the first run: only gaps count)."""
    out: dict[str, Any] = {"new_offered": {}, "newly_missing": {}, "probe_changes": [],
                           "key_changes": [], "coverage_gaps": list(cur.get("coverage_gaps") or [])}
    if not prev:
        return out
    cur_cmp = cur.get("comparison") or {}
    prev_cmp = prev.get("comparison") or {}
    cur_ids, prev_ids = _catalog_ids(cur), _catalog_ids(prev)
    skip = {"voice"} if _voice_is_a_duplicate(cur) else set()
    for pid, ids in sorted(cur_ids.items()):
        if pid in skip:
            continue
        c = cur_cmp.get(pid) or {}
        configured = (c.get("configured_available") or []) + (c.get("configured_missing") or [])
        if not configured or pid not in prev_ids:
            continue
        before = set(prev_ids[pid])
        added = [i for i in ids if i not in before]
        if added:
            out["new_offered"][pid] = added
    for pid, c in sorted(cur_cmp.items()):
        if pid not in prev_cmp or pid in skip:
            continue
        was = set(prev_cmp[pid].get("configured_missing") or [])
        now = [n for n in c.get("configured_missing") or [] if n not in was]
        if now:
            out["newly_missing"][pid] = now
    for which in SUBSCRIPTIONS:
        a = (prev.get("subscriptions") or {}).get(which)
        b = (cur.get("subscriptions") or {}).get(which)
        if isinstance(a, dict) and isinstance(b, dict) and bool(a.get("ok")) != bool(b.get("ok")):
            out["probe_changes"].append({"which": which, "was": bool(a.get("ok")),
                                         "now": bool(b.get("ok")), "category": b.get("category"),
                                         "model": b.get("model")})
    pk, ck = prev.get("key_health") or {}, cur.get("key_health") or {}
    for key in sorted(set(pk) & set(ck)):
        if pk[key] != ck[key]:
            out["key_changes"].append({"key": key, "was": pk[key], "now": ck[key]})
    return out


def has_changes(d: dict[str, Any]) -> bool:
    return any(bool(d.get(k)) for k in
               ("new_offered", "newly_missing", "probe_changes", "key_changes", "coverage_gaps"))


def daily_notice_text(d: dict[str, Any]) -> str:
    """One short spoken paragraph, <= 600 chars; "" when nothing changed."""
    if not has_changes(d):
        return ""
    parts: list[str] = []
    for pid, ids in (d.get("new_offered") or {}).items():
        shown = ", ".join(ids[:3]) + (", …" if len(ids) > 3 else "")
        parts.append(f"{_name(pid)} added {len(ids)} model{'s' if len(ids) != 1 else ''} ({shown}).")
    for pid, names in (d.get("newly_missing") or {}).items():
        parts.append(f"{_name(pid)} no longer offers {', '.join(names)}.")
    for ch in d.get("probe_changes") or []:
        which = str(ch.get("which")).capitalize()
        if ch.get("now"):
            parts.append(f"{which} subscription probe works again.")
        else:
            parts.append(f"{which} subscription probe failed: {ch.get('category') or 'no valid answer'}.")
    for ch in d.get("key_changes") or []:
        parts.append(f"{ch['key']} is now {ch['now']} (was {ch['was']}).")
    if d.get("coverage_gaps"):
        parts.append("No catalog adapter for: " + ", ".join(d["coverage_gaps"]) + ".")
    text = "Daily check: " + " ".join(parts)
    if len(text) > MAX_NOTICE_CHARS:
        text = text[: MAX_NOTICE_CHARS - 1] + "…"
    return text


# ---- entry point --------------------------------------------------------------

def run(*, status_dir: Path = STATUS_DIR, deps: dict[str, Callable[..., Any]] | None = None,
        now: datetime | None = None,
        notice: Callable[[str, str, str], int] | None = None) -> dict[str, Any]:
    """Collect, write, prune, diff, notify. Never raises."""
    now = now or datetime.now(timezone.utc)
    snap = collect(deps, now=now, generated_dir=status_dir / GENERATED_DIRNAME)
    name = f"{PREFIX}{now.astimezone().date().isoformat()}{SUFFIX}"
    prev = load_previous(status_dir, name)
    change = diff(prev, snap)
    snap["changes"] = change
    text = daily_notice_text(change)
    snap["notice"] = text or None
    try:
        write_atomic(status_dir / name, snap)
        prune(status_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("status_daily_write_failed error=%s", type(exc).__name__)
    if text:
        try:
            if notice is None:
                from jarvis.notices import add_notice as notice
            notice("daily_status", "daily", text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("status_daily_notice_failed error=%s", type(exc).__name__)
    logger.info("status_daily_done file=%s changed=%s errors=%d",
                name, bool(text), len(snap["errors"]))
    return snap


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        from jarvis.vault import inject_env

        inject_env()
    except Exception as exc:  # noqa: BLE001 — .env still supplies what it can
        logger.warning("status_daily_vault_unavailable error=%s", type(exc).__name__)
    try:
        from jarvis.db import run_migrations

        run_migrations()  # the notices table must exist before add_notice
    except Exception as exc:  # noqa: BLE001
        logger.warning("status_daily_migrations_failed error=%s", type(exc).__name__)
    try:
        run()
    except Exception as exc:  # noqa: BLE001 — exit 0 regardless (no retry storm)
        logger.warning("status_daily_failed error=%s", type(exc).__name__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
