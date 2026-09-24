"""The daily status job (spec T4.5, L4/L5): `python -m jarvis.status.daily`.

Run once a day by launchd (`com.mortimer.status-daily`, 06:30, see
scripts/launchd_gen.py's CALENDAR_JOBS). It reads everything the status
tools can read on request, for EVERY configured provider (discovered from
configuration, never a list kept here — L3):

1. `discover_providers()`
2. every model provider's catalog, forced (`fetch_all`)
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
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from jarvis.status.logs import redact

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
STATUS_DIR = REPO_ROOT / "data" / "status"
KEEP_FILES = 30
MAX_NOTICE_CHARS = 600
PREFIX, SUFFIX = "daily-", ".json"
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

    return {
        "registry": load_registry,
        "discover": lambda registry: discover_providers(registry=registry),
        "fetch_all": lambda refs: catalog.fetch_all(catalog.catalog_refs(refs), force=True),
        "compare": catalog.compare_to_registry,
        "probe": lambda which: subscriptions.probe_subscription(which, force=True),
        "keyprobe": lambda registry: keyhealth.probe_all(registry),
        "access_status": lambda registry: model_access_status(registry=registry),
        "head": services.repo_head,
    }


def collect(deps: dict[str, Callable[..., Any]] | None = None, *,
            now: datetime | None = None) -> dict[str, Any]:
    """One snapshot. Every step is guarded: a failure is recorded in
    `errors` and the rest still run."""
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
    except Exception as exc:  # noqa: BLE001
        snap["errors"].append(_err("discover_providers", exc))
    results: list = []
    try:
        results = list(d["fetch_all"](refs))
        snap["catalogs"] = [asdict(r) for r in results]
    except Exception as exc:  # noqa: BLE001
        snap["errors"].append(_err("catalogs", exc))
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


def write_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON to a temp file in the same directory, then os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


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


# ---- diff and notice (pure) -------------------------------------------------

def _catalog_ids(snap: dict[str, Any]) -> dict[str, list[str]]:
    """provider -> offered ids, for providers whose fetch succeeded."""
    out: dict[str, list[str]] = {}
    for r in snap.get("catalogs") or []:
        if isinstance(r, dict) and r.get("ok"):
            out[str(r.get("provider"))] = [str(m.get("id")) for m in r.get("models") or []]
    return out


def diff(prev: dict[str, Any] | None, cur: dict[str, Any]) -> dict[str, Any]:
    """What changed since `prev` (None on the first run: only gaps count)."""
    out: dict[str, Any] = {"new_offered": {}, "newly_missing": {}, "probe_changes": [],
                           "key_changes": [], "coverage_gaps": list(cur.get("coverage_gaps") or [])}
    if not prev:
        return out
    cur_cmp = cur.get("comparison") or {}
    prev_cmp = prev.get("comparison") or {}
    cur_ids, prev_ids = _catalog_ids(cur), _catalog_ids(prev)
    for pid, ids in sorted(cur_ids.items()):
        c = cur_cmp.get(pid) or {}
        configured = (c.get("configured_available") or []) + (c.get("configured_missing") or [])
        if not configured or pid not in prev_ids:
            continue
        before = set(prev_ids[pid])
        added = [i for i in ids if i not in before]
        if added:
            out["new_offered"][pid] = added
    for pid, c in sorted(cur_cmp.items()):
        if pid not in prev_cmp:
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
    snap = collect(deps, now=now)
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
