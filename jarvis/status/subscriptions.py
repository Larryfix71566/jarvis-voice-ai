"""CLI subscription probes (spec T4.2, L5).

"Is model X available on my Claude (or Codex) subscription?" has no list
API to answer it: the only honest answer is to try that exact model once
through the official CLI and report what happened. That is what
`probe_subscription` does. It is the one subscription probe (R8):
`scripts/verify_model_access.py` imports it, and the admin sidecar's
`POST /api/status/subscription/probe` calls it.

Each probe spends a little subscription quota (I2), so a result is reused
for `PROBE_RATE_LIMIT_S` per `(which, model)` unless `force`. The model is
passed through EXACTLY as given — no alias mapping — and the result names
it, so the answer says which model was tried (I5).

The five failure categories and their classification are moved verbatim
from the script's former `_probe_subscription`; `not_installed` is new and
is returned without running anything when the CLI is not on PATH.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Literal

PROBE_TOKEN = "MORTIMER_SUBSCRIPTION_PROBE_OK"
PROBE_PROMPT = f"Reply with exactly {PROBE_TOKEN} and do not use tools."
PROBE_RATE_LIMIT_S = 600
DEFAULT_TIMEOUT_S = 25.0  # under the MCP registry's CALL_TIMEOUT of 30 s

# The Claude default is fixed; the Codex default is the model of the
# registry profile below, read at call time (see default_probe_model).
DEFAULT_PROBE_MODEL = {"claude": "claude-sonnet-5"}
CODEX_PROFILE = "codex-subscription"

COMMANDS = {
    "claude": ("JARVIS_CLAUDE_SUBSCRIPTION_COMMAND", "claude"),
    "codex": ("JARVIS_CODEX_SUBSCRIPTION_COMMAND", "codex"),
}

Which = Literal["claude", "codex"]

_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def clear_cache_for_tests() -> None:
    with _cache_lock:
        _cache.clear()


def default_probe_model(which: str, registry: dict | None = None) -> str:
    """DEFAULT_PROBE_MODEL[which]; for codex, the registry profile
    `codex-subscription`'s model (one registry loader, I6)."""
    if which != "codex":
        return DEFAULT_PROBE_MODEL[which]
    if registry is None:
        from jarvis.agents.upgrade_agent import load_model_registry

        registry = load_model_registry()
    profiles = registry.get("profiles") or {}
    if isinstance(profiles, dict):
        profile = profiles.get(CODEX_PROFILE) or {}
    else:
        profile = next((p for p in profiles if isinstance(p, dict)
                        and p.get("name") == CODEX_PROFILE), {})
    model = str(profile.get("model") or "").strip()
    if not model:
        raise ValueError(f"registry profile {CODEX_PROFILE!r} names no model")
    return model


def subscription_command(which: str) -> str:
    env_name, default = COMMANDS[which]
    return os.environ.get(env_name) or default


def _classify(message: str) -> str:
    """Moved verbatim from scripts/verify_model_access.py's
    `_probe_subscription` (the five pre-existing categories)."""
    message = message.lower()
    if ("401" in message or "revoked" in message or "authenticate" in message
            or "not logged in" in message or "login" in message):
        category = "authentication"
    elif "not found" in message or "unsupported" in message or "model" in message:
        category = "model_unavailable"
    elif "timed out" in message or "timeout" in message:
        category = "timeout"
    elif ("operation not permitted" in message or "permission denied" in message
          or "readonly database" in message or "read-only" in message):
        category = "runtime_environment"
    else:
        category = "runtime_error"
    return category


def _default_runner(which: str) -> Callable[[str, list[dict[str, Any]], float], str]:
    from jarvis.subscription import _run_claude, _run_codex

    return _run_claude if which == "claude" else _run_codex


def probe_subscription(which: Which, model: str | None = None, *,
                       force: bool = False, timeout: float = DEFAULT_TIMEOUT_S,
                       runner=None, check_installed: bool = True) -> dict[str, Any]:
    """Send one fixed synthetic prompt through the `which` subscription CLI
    on `model` (default: DEFAULT_PROBE_MODEL). Returns
    {which, model, ok, response_present, category, installed, command,
    probed_at, cached}. `check_installed=False` skips the not_installed
    short-circuit (the readiness script's pre-existing behaviour: a missing
    CLI surfaces through the runner's own failure)."""
    from jarvis.subscription import SubscriptionRuntimeError

    if which not in COMMANDS:
        raise ValueError("which must be 'claude' or 'codex'")
    tried = model if model else default_probe_model(which)
    key = (which, tried)
    if not force:
        with _cache_lock:
            hit = _cache.get(key)
        if hit is not None and time.monotonic() - hit[0] < PROBE_RATE_LIMIT_S:
            return {**hit[1], "cached": True}

    command = subscription_command(which)
    installed = shutil.which(command) is not None
    result: dict[str, Any] = {
        "which": which, "model": tried, "ok": False, "response_present": False,
        "category": None, "installed": installed, "command": command,
        "probed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cached": False,
    }
    if check_installed and not installed:
        result["category"] = "not_installed"
        return result  # nothing ran, nothing spent: not rate-limited
    run = runner or _default_runner(which)
    try:
        text = run(tried, [{"role": "user", "content": PROBE_PROMPT}], timeout)
        result["ok"] = text.strip() == PROBE_TOKEN
        result["response_present"] = bool(text.strip())
    except SubscriptionRuntimeError as exc:
        result["category"] = _classify(str(exc))
    with _cache_lock:
        _cache[key] = (time.monotonic(), dict(result))
    return result


def subscription_status(which: str, model: str | None = None, *,
                        force: bool = False) -> dict[str, Any]:
    """The /api/status/subscription/probe payload. A failed probe is a
    result (`ok` True, `probe.ok` False), not a route error."""
    if which not in COMMANDS:
        return {"ok": False, "error": "which must be 'claude' or 'codex'"}
    probe = probe_subscription(which, model or None, force=force)  # type: ignore[arg-type]
    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": f"probe:{which}@{probe['probed_at']}",
        "probe": probe,
    }
