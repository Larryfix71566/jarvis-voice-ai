"""Subscription-side model lists for the daily new-model check (WS-41).

No API keys: every child process gets only ``_subscription_env(...)``.

Verified locally (2026-11-23, container, no login) against
``@openai/codex`` 0.171.0 (``codex-cli 0.171.0``):

- ``codex app-server`` speaks newline-delimited JSON on stdio. Messages
  carry NO ``"jsonrpc"`` field (``{"id":1,"method":"initialize",...}``);
  a ``jsonrpc: "2.0"`` field is also accepted.
- ``initialize`` with ``{"clientInfo": {"name", "version"}}`` answered
  without any login: ``{"id":1,"result":{"userAgent":...,"codexHome":...}}``.
  Then the notification ``{"method":"initialized"}`` (no id).
- Server notifications (``configWarning``, ``remoteControl/status/changed``)
  arrive interleaved, so responses are matched by ``id``.
- ``model/list`` with ``{"includeHidden": true}`` answered WITHOUT a login
  with ``result.data`` = list of models (``id``, ``model``, ``displayName``,
  ``hidden``, ``isDefault``, ``supportedReasoningEfforts`` ...) and
  ``result.nextCursor`` (null/absent at the end; ``"1"`` with ``limit: 1``,
  passed back as ``params.cursor``). That unauthenticated list is the CLI's
  bundled catalogue; on the Mac's ChatGPT login it may differ (untested).
"""
from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import time
from typing import Any, Callable

from jarvis.model_sync import ids

ALIASES = ("opus", "sonnet", "haiku", "fable")
ALIAS_PROMPT = "Reply with exactly OK and do not use tools."
_MAX_PAGES = 5


def claude_cli_version(*, timeout=10, run=subprocess.run) -> str | None:
    """First line of ``claude --version`` (e.g. "2.1.330 (Claude Code)")."""
    try:
        from jarvis.subscription import (_subscription_env, _temp_cwd,
                                         resolve_provider_executable)
        exe = resolve_provider_executable("claude")
        if not exe:
            return None
        with _temp_cwd() as tmp:
            result = run([exe, "--version"], env=_subscription_env(tmp), cwd=tmp,
                         capture_output=True, text=True, timeout=timeout)
        if getattr(result, "returncode", 1) != 0:
            return None
        lines = (result.stdout or "").strip().splitlines()
        return lines[0].strip() if lines and lines[0].strip() else None
    except Exception:  # noqa: BLE001 - never raises
        return None


def claude_alias_probe(alias: str, *, timeout: float = 60.0, run_sync=None) -> dict[str, Any]:
    """Run one alias through the restricted subscription argv and report the
    model that actually ran (``modelUsage`` keys). The alias is used ONLY
    here; nothing downstream may pin an alias."""
    if alias not in ALIASES:
        raise ValueError(f"unknown alias {alias!r}")
    out: dict[str, Any] = {"alias": alias, "ok": False, "model": None, "models": [], "category": None}
    try:
        from jarvis import subscription
        from jarvis.status.subscriptions import _category_for
        runner = run_sync or subscription._run_sync
        try:
            stdout = runner(subscription._claude_argv(alias), ALIAS_PROMPT, timeout, provider="Claude")
        except subscription.SubscriptionRuntimeError as exc:
            out["category"] = _category_for(exc)
            return out
        try:
            payload = json.loads(stdout)
        except (TypeError, ValueError):
            payload = None
        if not isinstance(payload, dict):
            out["category"] = "unresolved"
            return out
        usage = payload.get("modelUsage")
        keys = sorted(k for k in usage if isinstance(k, str)) if isinstance(usage, dict) else []
        declared = payload.get("model")
        if isinstance(declared, str) and declared and declared not in keys:
            keys.append(declared)
            keys.sort()
        out["models"] = keys
        match = next((k for k in keys if (p := ids.parse(k)) is not None
                      and p.vendor == "anthropic" and p.family == alias), None)
        if match is None:
            out["category"] = "unresolved"
            return out
        out["ok"], out["model"] = True, match
        return out
    except Exception as exc:  # noqa: BLE001 - never raises
        out["category"] = "unresolved"
        out["error"] = type(exc).__name__
        return out


def _kill_group(proc: Any) -> None:
    try:
        pid = proc.pid
        if not isinstance(pid, int) or pid <= 1:  # never signal our own group
            proc.terminate()
            return
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError, TypeError):
            proc.terminate()
        try:
            proc.wait(timeout=2)
        except Exception:  # noqa: BLE001
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError, TypeError):
                proc.kill()
    except Exception:  # noqa: BLE001
        pass


def _start_reader(proc: Any) -> "queue.Queue[str | None]":
    """Pump stdout lines into a queue on a daemon thread. select() on a
    buffered text pipe can miss lines already read into the buffer (several
    JSON-RPC messages often arrive in one chunk), so lines are read here and
    the deadline is enforced on the queue instead."""
    import threading

    lines: "queue.Queue[str | None]" = queue.Queue()

    def pump() -> None:
        try:
            for line in iter(proc.stdout.readline, ""):
                lines.put(line)
        except Exception:  # noqa: BLE001 - the process was killed
            pass
        finally:
            lines.put(None)

    threading.Thread(target=pump, name="codex-model-list-reader", daemon=True).start()
    return lines


def _read_response(lines: Any, want_id: int, deadline: float) -> dict[str, Any]:
    """Read lines until the response with ``want_id``; notifications are skipped."""

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("codex app-server timed out")
        try:
            line = lines.get(timeout=remaining)
        except queue.Empty:
            raise TimeoutError("codex app-server timed out") from None
        if line is None:
            raise EOFError("codex app-server closed stdout")
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if isinstance(msg, dict) and msg.get("id") == want_id and "method" not in msg:
            return msg


def codex_model_list(*, timeout: float = 20.0, popen=subprocess.Popen) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "models": [], "default": None, "category": None, "error": None}
    proc = None
    try:
        from jarvis.subscription import (_subscription_env, _temp_cwd,
                                         resolve_provider_executable)
        exe = resolve_provider_executable("codex")
        if not exe:
            out.update(category="not_installed", error="codex CLI not found")
            return out
        deadline = time.monotonic() + timeout
        with _temp_cwd() as tmp:
            proc = popen([exe, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, cwd=tmp,
                         env=_subscription_env(tmp), start_new_session=True)

            def send(msg: dict[str, Any]) -> None:
                proc.stdin.write(json.dumps(msg) + "\n")
                proc.stdin.flush()

            send({"id": 1, "method": "initialize",
                  "params": {"clientInfo": {"name": "mortimer-model-sync", "version": "1"}}})
            lines = _start_reader(proc)
            first = _read_response(lines, 1, deadline)
            if "error" in first:
                out.update(category="runtime_error", error=_short(first["error"]))
                return out
            send({"method": "initialized"})
            models: list[dict[str, Any]] = []
            cursor = None
            for page in range(_MAX_PAGES):
                params: dict[str, Any] = {"includeHidden": True}
                if cursor:
                    params["cursor"] = cursor
                rid = 2 + page
                send({"id": rid, "method": "model/list", "params": params})
                resp = _read_response(lines, rid, deadline)
                if "error" in resp:
                    out.update(category="runtime_error", error=_short(resp["error"]))
                    return out
                result = resp.get("result")
                items: Any = []
                if isinstance(result, dict):
                    items = result.get("data") or result.get("models") or []
                elif isinstance(result, list):
                    items = result
                for item in items if isinstance(items, list) else []:
                    if not isinstance(item, dict):
                        continue
                    mid = item.get("id") or item.get("model")
                    if not isinstance(mid, str) or not mid:
                        continue
                    models.append({"id": mid,
                                   "display_name": item.get("displayName") or item.get("display_name") or mid,
                                   "is_default": bool(item.get("isDefault") or item.get("is_default")),
                                   "hidden": bool(item.get("hidden"))})
                cursor = result.get("nextCursor") if isinstance(result, dict) else None
                if not cursor:
                    break
            out["models"] = models
            out["default"] = next((m["id"] for m in models if m["is_default"]), None)
            out["ok"] = True
            return out
    except TimeoutError:
        out.update(category="timeout", error="codex app-server timed out")
    except Exception as exc:  # noqa: BLE001 - never raises
        out.update(category="runtime_error", error=f"{type(exc).__name__}: {str(exc)[:120]}")
    finally:
        if proc is not None:
            _kill_group(proc)
    return out


def _short(value: Any) -> str:
    return str(value)[:160]


def kimi_model_list() -> dict[str, Any]:
    return {"ok": False, "category": "unsupported",
            "error": "Kimi Code has no non-interactive model list (untested)"}


def collect_subscriptions(*, probe_aliases: bool = True, deps: dict[str, Callable] | None = None) -> dict[str, Any]:
    d = {"version": claude_cli_version, "probe": claude_alias_probe,
         "codex": codex_model_list, "kimi": kimi_model_list}
    d.update(deps or {})

    def guard(fn: Callable[[], Any], fallback: Any) -> Any:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            if isinstance(fallback, dict):
                return {**fallback, "error": f"{type(exc).__name__}"}
            return fallback

    aliases: dict[str, Any] = {}
    for alias in ALIASES:
        if not probe_aliases:
            aliases[alias] = {"ok": False, "category": "skipped"}
        else:
            aliases[alias] = guard(lambda a=alias: d["probe"](a),
                                   {"alias": alias, "ok": False, "category": "runtime_error"})
    return {
        "claude": {"version": guard(d["version"], None), "aliases": aliases},
        "codex": guard(d["codex"], {"ok": False, "models": [], "default": None, "category": "runtime_error"}),
        "kimi": guard(d["kimi"], {"ok": False, "category": "unsupported"}),
    }
