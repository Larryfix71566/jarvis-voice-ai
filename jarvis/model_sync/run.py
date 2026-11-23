"""The daily new-model check's entry point (WS-41).

Called once a day from `jarvis.status.daily.main()` (the 06:30
`com.mortimer.status-daily` launchd job), and by hand through
`scripts/sync_models.py`. Detect, then certify and propose only what is new
since the last run, then write one report and at most one spoken notice.

Never raises, never changes a model, never edits the local checkout, never
uses an API key. Switches, all default on:

- `MORTIMER_MODEL_SYNC=0`: skip the whole check.
- `MORTIMER_MODEL_SYNC_CERTIFY=0`: detect and report only.
- `MORTIMER_MODEL_SYNC_PROPOSE=0`: certify but open no PR / write no patch.

Files under `data/status/` (ignored by git):

- `model-sync.json`: the latest report (served at `GET /api/status/model-sync`).
- `model-sync-state.json`: what was already certified, proposed or announced,
  so a candidate is tested once per CLI version and a notice isn't repeated.
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
import stat
import subprocess
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from jarvis.model_sync import detect as detect_mod

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
STATUS_DIR = REPO_ROOT / "data" / "status"
REPORT_NAME = "model-sync.json"
STATE_NAME = "model-sync-state.json"
LOCK_NAME = "model-sync.lock"
MAX_CERTIFY_PER_RUN = 3        # bounds subscription quota spent in one morning
RETRY_FAILED_AFTER = timedelta(days=7)
MAX_NOTICE_CHARS = 600
MAX_SPOKEN_CANDIDATES = 3
DONE_PROPOSALS = frozenset({"pr_opened", "pr_exists", "proposal_written", "manual"})


def _enabled(name: str) -> bool:
    return os.environ.get(name, "1").strip() != "0"


@contextmanager
def _lock(status_dir: Path):
    status_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(status_dir / LOCK_NAME, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("invalid model-sync lock")
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.is_symlink():
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, RecursionError):
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    from jarvis.status.daily import write_atomic

    write_atomic(path, payload)


def _err(step: str, exc: BaseException) -> dict[str, str]:
    from jarvis.status.logs import redact

    return {"step": step, "error": redact(f"{type(exc).__name__}: {exc}")[:200]}


def codex_cli_version(*, timeout: float = 10.0) -> str | None:
    """`codex --version` of the executable the subscription route would run."""
    try:
        from jarvis.subscription import (_subscription_env, _temp_cwd,
                                         resolve_provider_executable)

        exe = resolve_provider_executable("codex")
        if exe is None:
            return None
        with _temp_cwd() as tmp:
            done = subprocess.run([exe, "--version"], capture_output=True, text=True,
                                  timeout=timeout, cwd=tmp, env=_subscription_env(tmp))
        line = (done.stdout or "").strip().splitlines()
        return line[0].strip() if done.returncode == 0 and line else None
    except Exception:  # noqa: BLE001 - a version read never fails the check
        return None


def _default_deps(probe_aliases: bool) -> dict[str, Callable[..., Any]]:
    def public() -> dict:
        from jarvis.model_sync.sources import collect_public

        return collect_public()

    def subs() -> dict:
        from jarvis.model_sync.subscription_lists import collect_subscriptions

        return collect_subscriptions(probe_aliases=probe_aliases)

    def pins() -> dict:
        from jarvis.model_sync.pins import collect_pins

        return collect_pins()

    def certify(candidate: dict, status_dir: Path) -> dict:
        from jarvis.model_sync.certify import certify as run_certify

        return run_certify(candidate, status_dir=status_dir)

    def propose(old: str, new: str, files: list[str], evidence: dict, status_dir: Path) -> dict:
        from jarvis.model_sync.propose import propose as run_propose

        return run_propose(old, new, files, evidence, status_dir=status_dir)

    return {"public": public, "subs": subs, "pins": pins, "codex_version": codex_cli_version,
            "certify": certify, "propose": propose}


def _parse_ts(value: Any) -> datetime | None:
    try:
        ts = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _needs_certify(entry: dict[str, Any], cli_versions: dict[str, Any], now: datetime) -> bool:
    """Once per candidate per CLI version; a failure is retried after a week
    or as soon as either CLI changes (a new CLI is what makes new Claude
    models visible)."""
    if not entry.get("certification"):
        return True
    if (entry.get("proposal") or {}).get("status") in DONE_PROPOSALS:
        return False
    if entry.get("cli_versions") != cli_versions:
        return True
    if (entry.get("certification") or {}).get("passed"):
        # Passed but the proposal failed (e.g. GitHub error): retry propose only.
        return False
    last = _parse_ts((entry.get("certification") or {}).get("certified_at"))
    return last is None or now - last >= RETRY_FAILED_AFTER


def _manual_instruction(candidate: dict[str, Any]) -> str:
    return (f"{candidate['replaces']} is set outside the repository; change it to "
            f"{candidate['model']} by hand (for voice: the voice_supervisor profile or "
            f"OPENAI_MODEL in .env), then redeploy.")


def _handle_candidates(cands: list[dict[str, Any]], state: dict[str, Any],
                       deps: dict[str, Callable[..., Any]], status_dir: Path,
                       cli_versions: dict[str, Any], now: datetime,
                       do_certify: bool, do_propose: bool,
                       errors: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Certify/propose what needs it; return per-candidate outcomes, each
    marked `changed` when something happened today."""
    store = state.setdefault("candidates", {})
    outcomes = []
    budget = MAX_CERTIFY_PER_RUN
    for cand in cands:
        key = cand["key"]
        entry = store.setdefault(key, {"first_seen": now.isoformat(timespec="seconds")})
        changed = "notified_at" not in entry
        if do_certify and budget > 0 and _needs_certify(entry, cli_versions, now):
            budget -= 1
            try:
                entry["certification"] = deps["certify"](cand, status_dir)
            except Exception as exc:  # noqa: BLE001
                errors.append(_err(f"certify:{cand['model']}", exc))
                entry["certification"] = {"passed": False, "steps": [
                    {"name": "certify", "ok": False, "detail": type(exc).__name__}],
                    "certified_at": now.isoformat(timespec="seconds")}
            entry["cli_versions"] = dict(cli_versions)
            changed = True
        cert = entry.get("certification") or {}
        done = (entry.get("proposal") or {}).get("status") in DONE_PROPOSALS
        if do_propose and cert.get("passed") and not done:
            files = [f for f in cand.get("files") or [] if not f.startswith(".env")]
            if not files:
                entry["proposal"] = {"status": "manual", "instruction": _manual_instruction(cand)}
            else:
                evidence = {"reason": cand.get("reason"), "certification": cert,
                            "sources": cand.get("sources"), "roles": cand.get("roles")}
                try:
                    entry["proposal"] = deps["propose"](cand["replaces"], cand["model"], files,
                                                        evidence, status_dir)
                except Exception as exc:  # noqa: BLE001
                    errors.append(_err(f"propose:{cand['model']}", exc))
                    entry["proposal"] = {"status": "error", "error": type(exc).__name__}
            changed = True
        outcomes.append({**cand, "certification": entry.get("certification"),
                         "proposal": entry.get("proposal"), "first_seen": entry["first_seen"],
                         "changed": changed})
    return outcomes


def _deprecation_changes(findings: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    """Deprecations to speak about today: first sight, an escalation, or every
    day inside T-7 (urgent)."""
    store = state.setdefault("deprecations", {})
    out = []
    for f in findings:
        if f.get("kind") != "deprecation":
            continue
        prev = store.get(f["key"]) or {}
        escalated = detect_mod.level_rank(f["level"]) > detect_mod.level_rank(prev.get("level"))
        if escalated or f["level"] == "urgent":
            out.append(f)
        store[f["key"]] = {"level": f["level"], "retirement": f.get("retirement")}
    return out


def _cli_changes(findings: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    seen = state.setdefault("cli", {})
    out = []
    for f in findings:
        if f.get("kind") != "cli":
            continue
        if seen.get(f["cli"]) != f["key"]:
            out.append(f)
            seen[f["cli"]] = f["key"]
    return out


def _proposal_phrase(outcome: dict[str, Any]) -> str:
    cert = outcome.get("certification") or {}
    prop = outcome.get("proposal") or {}
    status = prop.get("status")
    if status in ("pr_opened", "pr_exists"):
        return "it passed the checks and a pull request is waiting for you"
    if status == "proposal_written":
        return "it passed the checks; the change is written up, but no GitHub token was available to open a pull request"
    if status == "manual":
        return "it passed the checks; switch it by hand"
    if status == "error":
        return "it passed the checks, but opening the pull request failed"
    if cert and not cert.get("passed"):
        failed = next((s for s in cert.get("steps") or [] if not s.get("ok")), {})
        name = str(failed.get("name") or "certification").replace("_", " ")
        detail = str(failed.get("detail") or "")
        why = f" ({detail})" if detail and len(detail) <= 40 and detail != "ok" else ""
        return f"it failed the {name} check{why}"
    if not cert:
        return "not tested yet"
    return "tested"


def notice_text(new_outcomes: list[dict[str, Any]], deps: list[dict[str, Any]],
                clis: list[dict[str, Any]]) -> str:
    """One short spoken paragraph; "" when there is nothing to say."""
    parts = []
    for d in deps:
        if d["level"] == "retired":
            parts.append(f"{d['model']} has been retired and Mortimer still uses it.")
        else:
            when = (f"in {d['days_left']} days" if d.get("days_left") is not None
                    else "at a date not yet announced")
            rep = f"; the replacement is {d['replacement']}" if d.get("replacement") else ""
            parts.append(f"{d['model']} retires {when}{rep}.")
    if len(new_outcomes) > MAX_SPOKEN_CANDIDATES:
        shown = ", ".join(o["model"] for o in new_outcomes[:MAX_SPOKEN_CANDIDATES])
        prs = sum(1 for o in new_outcomes
                  if (o.get("proposal") or {}).get("status") in ("pr_opened", "pr_exists"))
        parts.append(f"{len(new_outcomes)} newer models could replace ones Mortimer uses, "
                     f"including {shown}; {prs} pull request{'s' if prs != 1 else ''} "
                     "waiting for you. The model check report has the rest.")
    else:
        for o in new_outcomes:
            parts.append(f"{o['model']} could replace {o['replaces']}: {_proposal_phrase(o)}.")
    for c in clis:
        if not c["installed_verified"]:
            parts.append(f"The {c['cli'].capitalize()} CLI on this Mac ({c['installed']}) "
                         "isn't a version Mortimer has verified.")
        elif c["behind"]:
            parts.append(f"The {c['cli'].capitalize()} CLI {c['latest']} is out.")
    if not parts:
        return ""
    text = "Model check: " + " ".join(parts)
    if len(text) > MAX_NOTICE_CHARS:
        text = text[: MAX_NOTICE_CHARS - 1] + "…"
    return text


def run_daily(status_dir: Path = STATUS_DIR, *, deps: dict[str, Callable[..., Any]] | None = None,
              now: datetime | None = None, notice: Callable[[str, str, str], int] | None = None,
              probe_aliases: bool = True, certify: bool | None = None,
              propose: bool | None = None) -> dict[str, Any]:
    """Detect, certify and propose what's new, write the report, speak once.
    Never raises."""
    now = now or datetime.now(timezone.utc)
    if not _enabled("MORTIMER_MODEL_SYNC"):
        return {"ok": False, "skipped": "MORTIMER_MODEL_SYNC=0"}
    do_certify = _enabled("MORTIMER_MODEL_SYNC_CERTIFY") if certify is None else certify
    do_propose = _enabled("MORTIMER_MODEL_SYNC_PROPOSE") if propose is None else propose
    d = {**_default_deps(probe_aliases), **(deps or {})}
    errors: list[dict[str, str]] = []
    collected: dict[str, Any] = {}
    for name in ("public", "subs", "pins"):
        try:
            collected[name] = d[name]() or {}
        except Exception as exc:  # noqa: BLE001
            errors.append(_err(name, exc))
            collected[name] = {}
    try:
        codex_version = d["codex_version"]()
    except Exception as exc:  # noqa: BLE001
        errors.append(_err("codex_version", exc))
        codex_version = None
    claude_version = (collected["subs"].get("claude") or {}).get("version")
    installed = {"claude": claude_version, "codex": codex_version}
    report: dict[str, Any] = {"generated_at": now.isoformat(timespec="seconds"),
                              "mode": "detect_certify_propose", "automatic_switch": False,
                              "installed_cli": installed, "errors": errors}
    try:
        with _lock(status_dir):
            state = _read_json(status_dir / STATE_NAME)
            findings = detect_mod.detect(collected["public"], collected["subs"], collected["pins"],
                                         today=now.astimezone().date(), installed=installed)
            cands = detect_mod.candidates(findings)
            outcomes = _handle_candidates(cands, state, d, status_dir, installed, now,
                                          do_certify, do_propose, errors)
            deps_today = _deprecation_changes(findings, state)
            clis_today = _cli_changes(findings, state)
            fresh = [o for o in outcomes if o["changed"]]
            text = notice_text(fresh, deps_today, clis_today)
            report.update(findings=findings, candidates=outcomes, notice=text or None,
                          sources=(collected["public"].get("sources") or {}),
                          subscriptions=_subscriptions_summary(collected["subs"]),
                          pins={"models": len(collected["pins"].get("models") or []),
                                "voice": collected["pins"].get("voice"),
                                "cli": collected["pins"].get("cli")})
            delivered = True
            if text:
                try:
                    if notice is None:
                        from jarvis.notices import add_notice as notice
                    delivered = notice("daily_status", "model-sync", text) >= 0
                except Exception as exc:  # noqa: BLE001
                    errors.append(_err("notice", exc))
                    delivered = False
            if delivered:
                stamp = now.isoformat(timespec="seconds")
                for o in fresh:
                    state["candidates"][o["key"]]["notified_at"] = stamp
            else:
                # Undelivered: forget today's deprecation/CLI marks so tomorrow retries.
                for f in deps_today:
                    state.get("deprecations", {}).pop(f["key"], None)
                for c in clis_today:
                    state.get("cli", {}).pop(c["cli"], None)
            state["updated_at"] = now.isoformat(timespec="seconds")
            _write_json(status_dir / STATE_NAME, state)
            report["ok"] = True
            _write_json(status_dir / REPORT_NAME, report)
    except Exception as exc:  # noqa: BLE001 - the daily job must never fail on this
        errors.append(_err("run", exc))
        report["ok"] = False
        try:
            _write_json(status_dir / REPORT_NAME, report)
        except Exception:  # noqa: BLE001
            pass
    logger.info("model_sync_done findings=%d notice=%s errors=%d",
                len(report.get("findings") or []), bool(report.get("notice")), len(errors))
    return report


def _subscriptions_summary(subs: dict[str, Any]) -> dict[str, Any]:
    """What the report keeps of the subscription lists: resolved models and
    categories only (no raw CLI output)."""
    claude = subs.get("claude") or {}
    codex = subs.get("codex") or {}
    return {
        "claude": {"version": claude.get("version"),
                   "aliases": {a: {"ok": p.get("ok"), "model": p.get("model"),
                                   "category": p.get("category")}
                               for a, p in (claude.get("aliases") or {}).items()
                               if isinstance(p, dict)}},
        "codex": {"ok": codex.get("ok"), "default": codex.get("default"),
                  "models": [m.get("id") for m in codex.get("models") or [] if isinstance(m, dict)],
                  "category": codex.get("category")},
        "kimi": {k: (subs.get("kimi") or {}).get(k) for k in ("ok", "category")},
    }


def read_report(status_dir: Path = STATUS_DIR) -> dict[str, Any]:
    """The admin route's view: the latest report, read-only."""
    report = _read_json(status_dir / REPORT_NAME)
    if not report:
        return {"ok": False, "error": "No model check has run yet."}
    return {"ok": True, "report": report}
