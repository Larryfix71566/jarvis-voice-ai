"""Are the configured model credentials actually usable, right now?
MORTIMER_KEY_VALIDITY_PLAN.md K4.

WHY THIS EXISTS
---------------
`SubAgent` resolves a `model_profile:` by checking that its api_key_env is
SET. A key that is present but dead, or present but unfunded, sails through:
the client constructs, `self._model` is the assigned model, and
`model_is_fallback` is False. The 2026-08-19 Agents-tab model chip therefore
renders it in normal styling while every call 401s or 402s — the chip is
capable of lying, and this module is what stops it.

Two real states from that day make the case:
  - ANTHROPIC_API_KEY was reported dead by a probe that used the wrong
    endpoint, while voice worked fine. A false "dead" is as harmful as a
    missed one, which is why `unreachable` below is NEVER rendered as dead.
  - OPENROUTER_API_KEY authenticated but returned 402 Payment Required. The
    key was genuinely valid; nine profiles behind it were genuinely
    unusable. "Valid" and "usable" are different claims.

DESIGN CONSTRAINTS, all load-bearing
------------------------------------
1. BEST-EFFORT AND NON-BLOCKING. Runs on a daemon thread at bot startup and
   must never delay or prevent boot. A machine with no network still boots
   and still talks; it simply learns nothing here.
2. `unreachable` IS NOT `rejected`. A blocked network and a dead credential
   call for opposite responses, and collapsing them is the invent-a-cause
   error AGENT_DISCIPLINE exists to prevent. Only `rejected`/`unfunded` ever
   mark a profile unusable.
3. UNKNOWN IS THE DEFAULT. Before the probe finishes — or if it never runs —
   every key is `unknown`, which is not unusable. Nothing degrades because a
   measurement is missing.
4. ONE PROBE IMPLEMENTATION. Reuses scripts/check_env.py's
   `model_key_probe`, the same one `python -m jarvis.vault verify` calls, so
   the preflight, the CLI and the running bot can never disagree about
   whether a key works — the rule jarvis/toolresult.py applies to tool
   results, applied to credentials.
5. NO KEY VALUE EVER LEAVES. Names, endpoints and verdicts only.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

KILL_SWITCH_ENV = "JARVIS_KEY_HEALTH_ENABLED"

# ⚙ TUNING KNOB — per-probe timeout at startup. Deliberately shorter than
# check_env.py's 10s: this runs while the user is waiting to talk, and a
# slow answer here is worth less than a fast boot.
PROBE_TIMEOUT_S = 6

# ⚙ TUNING KNOB (status spec T3.3) — how often the refresh loop re-probes
# keys that are NOT ok. Only bad keys are re-probed, so a healthy machine
# makes no calls at all.
REFRESH_INTERVAL_S = 600.0
REFRESH_VERDICTS = ("rejected", "unfunded", "unreachable")
RECOVERED_DETAIL = "recovered: a call succeeded"

# key_env -> "ok" | "rejected" | "unfunded" | "unreachable" | "unknown"
_verdicts: dict[str, str] = {}
_details: dict[str, str] = {}
_lock = threading.Lock()

# The refresh loop is a PROCESS singleton: the bot calls start_refresh_loop
# once per session and the sidecar once at import, and each process must get
# exactly one thread.
_refresh_thread: threading.Thread | None = None
_refresh_stop = threading.Event()
_refresh_guard = threading.Lock()


def enabled() -> bool:
    """Single enforcement point for the kill switch. Disabled means every
    key reports `unknown`, which is exactly the pre-K4 behaviour."""
    value = os.environ.get(KILL_SWITCH_ENV)
    if value is None:
        return True
    return value.strip().lower() not in ("false", "0", "no")


def verdict(key_env: str) -> str:
    with _lock:
        return _verdicts.get(key_env, "unknown")


def detail(key_env: str) -> str:
    with _lock:
        return _details.get(key_env, "")


def is_unusable(key_env: str) -> bool:
    """True ONLY for a credential the provider actively refused or could not
    bill. `unreachable` and `unknown` are both False on purpose — see
    constraint 2 above; a network blip must never paint a working agent red.
    """
    return verdict(key_env) in ("rejected", "unfunded")


def reset_for_tests() -> None:
    global _refresh_thread, _refresh_stop
    with _lock:
        _verdicts.clear()
        _details.clear()
    with _refresh_guard:
        _refresh_stop.set()
        _refresh_thread = None
        _refresh_stop = threading.Event()


def note_success(key_env: str) -> None:
    """A real call on this credential just succeeded (status spec T3.3): a
    verdict that is not `ok` becomes `ok`, so a key that was refused, then
    fixed, stops painting its agents red without waiting for a re-probe.
    KeyHealthNotice then speaks KEYHEALTH_RECOVERED_TEMPLATE."""
    if not key_env or not enabled():
        return
    with _lock:
        previous = _verdicts.get(key_env, "unknown")
        if previous == "ok":
            return
        _verdicts[key_env] = "ok"
        _details[key_env] = RECOVERED_DETAIL
    logger.info("key_health_recovered key=%s previous=%s detail=%s",
                key_env, previous, RECOVERED_DETAIL)


def _load_probe():
    """Import scripts/check_env.py's probe by path. It is a script, not a
    package module, so this is the only way to reuse it — and reusing it is
    the point (constraint 4): a second implementation is how the preflight
    and the bot end up disagreeing about the same key."""
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "_check_env_probe", root / "scripts" / "check_env.py")
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "model_key_probe", None)


def _targets(registry: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """key_env -> (base_url, model). One entry per KEY, using the first
    profile that names it: the probe answers "does this credential work",
    and one call per key is enough to answer that for every profile behind
    it."""
    out: dict[str, tuple[str, str]] = {}
    profiles = registry.get("profiles") or {}
    values = profiles.values() if isinstance(profiles, dict) else profiles
    for prof in values:
        if not isinstance(prof, dict):
            continue
        key_env = str(prof.get("api_key_env", "OPENAI_API_KEY"))
        if key_env not in out:
            out[key_env] = (str(prof.get("base_url", "")),
                            str(prof.get("model", "")))
    return out


def probe_all(registry: dict[str, Any] | None = None,
              probe=None, timeout_s: int = PROBE_TIMEOUT_S) -> dict[str, str]:
    """Probe every distinct key env in the registry. Synchronous; callers
    that must not block use `start_background_probe`. Returns the verdict
    map. Never raises."""
    if not enabled():
        return {}
    try:
        if registry is None:
            from jarvis.agents.upgrade_agent import load_model_registry
            registry = load_model_registry()
        probe = probe or _load_probe()
        if probe is None:
            logger.warning("key_health_probe_unavailable")
            return {}
        for key_env, (base_url, model) in _targets(registry).items():
            key = os.environ.get(key_env, "").strip()
            if not key or not base_url:
                continue
            try:
                outcome, why = probe(base_url, key, model)
            except Exception as exc:  # noqa: BLE001
                outcome, why = "unreachable", f"{type(exc).__name__}: {exc}"
            with _lock:
                _verdicts[key_env] = outcome
                _details[key_env] = why
            # A dead credential is a WARNING, an unreached one is INFO: the
            # log level is itself the rejected/unreachable distinction.
            (logger.warning if outcome in ("rejected", "unfunded")
             else logger.info)(
                "key_health key=%s endpoint=%s outcome=%s detail=%s",
                key_env, base_url, outcome, why)
    except Exception as exc:  # noqa: BLE001
        logger.warning("key_health_probe_failed error=%s", exc)
    with _lock:
        return dict(_verdicts)


def refresh_bad_keys(registry: dict[str, Any] | None = None, probe=None,
                     timeout_s: int = PROBE_TIMEOUT_S) -> dict[str, str]:
    """One refresh pass: re-probe ONLY keys whose verdict is rejected,
    unfunded or unreachable, with the same `_targets()` and `_load_probe()`
    as probe_all. Returns {key_env: new verdict} for the keys it probed.
    Never raises."""
    if not enabled():
        return {}
    probed: dict[str, str] = {}
    try:
        with _lock:
            bad = {k for k, v in _verdicts.items() if v in REFRESH_VERDICTS}
        if not bad:
            return {}
        if registry is None:
            from jarvis.agents.upgrade_agent import load_model_registry
            registry = load_model_registry()
        probe = probe or _load_probe()
        if probe is None:
            logger.warning("key_health_probe_unavailable")
            return {}
        for key_env, (base_url, model) in _targets(registry).items():
            if key_env not in bad:
                continue
            key = os.environ.get(key_env, "").strip()
            if not key or not base_url:
                continue
            try:
                outcome, why = probe(base_url, key, model)
            except Exception as exc:  # noqa: BLE001
                outcome, why = "unreachable", f"{type(exc).__name__}: {exc}"
            with _lock:
                previous = _verdicts.get(key_env, "unknown")
                _verdicts[key_env] = outcome
                _details[key_env] = why
            probed[key_env] = outcome
            (logger.warning if outcome in ("rejected", "unfunded")
             else logger.info)(
                "key_health_refresh key=%s endpoint=%s previous=%s outcome=%s "
                "detail=%s",
                key_env, base_url, previous, outcome, why)
    except Exception as exc:  # noqa: BLE001
        logger.warning("key_health_refresh_failed error=%s", exc)
    return probed


def start_refresh_loop(interval_s: float = REFRESH_INTERVAL_S) -> threading.Thread | None:
    """Start the per-process refresh loop (status spec T3.3): a daemon
    thread that every `interval_s` re-probes the keys that are not ok.
    Idempotent — a second call returns the running thread. None when the
    kill switch is off."""
    global _refresh_thread
    if not enabled():
        return None
    with _refresh_guard:
        if _refresh_thread is not None and _refresh_thread.is_alive():
            return _refresh_thread
        stop = _refresh_stop

        def _loop() -> None:
            while not stop.wait(interval_s):
                refresh_bad_keys()

        thread = threading.Thread(target=_loop, name="key-health-refresh",
                                  daemon=True)
        thread.start()
        _refresh_thread = thread
        logger.info("key_health_refresh_loop_started interval_s=%.0f", interval_s)
        return thread


def start_background_probe() -> threading.Thread | None:
    """Fire probe_all on a daemon thread. Called once at bot startup beside
    the run-log prune and orphan reconciliation. Daemon so a hung provider
    can never keep the process alive at shutdown."""
    if not enabled():
        return None
    thread = threading.Thread(
        target=probe_all, name="key-health", daemon=True)
    thread.start()
    return thread
