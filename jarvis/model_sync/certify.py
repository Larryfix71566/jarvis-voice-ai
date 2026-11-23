"""Certify a candidate model before Mortimer proposes it (WS-41).

Steps run in order and stop at the first required failure. Nothing here
uses an API key: every call goes through the subscription CLIs. Nothing
raises out of ``certify``; an exception becomes a failed step whose detail
is the exception's type name.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]

VOICE_PROMPTS = (
    "What time is it in London?",
    "Turn the lights down a bit.",
    "Remind me to call Sam at five.",
    "What's the weather tomorrow?",
    "Say that again, shorter.",
)
VOICE_SYSTEM = "You are a voice assistant. Answer in one short sentence."
VOICE_TIMEOUT_S = 30.0
P50_TARGET_MS = 1200   # scripts/latency_probe.py gate, non-delegated
P90_TARGET_MS = 3500   # scripts/latency_probe.py gate, overall
CODEX_RECEIPT_TIMEOUT_S = 180


def _percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100.0 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def _default_runner(vendor: str) -> Callable[[str, list, float], str]:
    from jarvis import subscription
    return subscription._run_codex if vendor == "openai" else subscription._run_claude


def voice_bench(model: str, runner: Callable[[str, list, float], str] | None = None,
                runs: int = 5, *, vendor: str = "anthropic") -> dict[str, Any]:
    """Time ``runs`` short voice-style prompts through the subscription CLI.

    This is whole-reply wall time (process start to full reply), a stricter
    measure than time-to-first-token. It gates on the same p50 <= 1200 ms and
    p90 <= 3500 ms as scripts/latency_probe.py, but the live latency_probe on
    real logs after a switch is still the final gate.
    """
    if runner is None:
        runner = _default_runner(vendor)
    times: list[float] = []
    errors = 0
    for i in range(runs):
        prompt = VOICE_PROMPTS[i % len(VOICE_PROMPTS)]
        messages = [{"role": "system", "content": VOICE_SYSTEM},
                    {"role": "user", "content": prompt}]
        start = time.perf_counter()
        try:
            out = runner(model, messages, VOICE_TIMEOUT_S)
            if not str(out or "").strip():
                raise ValueError("empty reply")
        except Exception:  # noqa: BLE001
            errors += 1
            continue
        times.append((time.perf_counter() - start) * 1000.0)
    p50 = _percentile(times, 50)
    p90 = _percentile(times, 90)
    ok = (errors == 0 and len(times) == runs and p50 is not None and p90 is not None
          and p50 <= P50_TARGET_MS and p90 <= P90_TARGET_MS)
    return {"runs": len(times), "p50_ms": None if p50 is None else round(p50, 1),
            "p90_ms": None if p90 is None else round(p90, 1),
            "errors": errors, "ok": ok}


def _default_run_script(argv: list[str], timeout: float):
    return subprocess.run(argv, cwd=str(REPO_ROOT), capture_output=True, text=True,
                          timeout=timeout)


def _last_line(proc: Any) -> str:
    text = (getattr(proc, "stderr", "") or "").strip() or (getattr(proc, "stdout", "") or "").strip()
    lines = text.splitlines()
    return (lines[-1] if lines else "")[:200]


def _manual(candidate: dict) -> list[str]:
    model = candidate["model"]
    out: list[str] = []
    roles = [r for r in candidate.get("roles") or [] if r != "voice"]
    if candidate.get("vendor") == "anthropic" and roles:
        out.append(f"python scripts/verify_claude_developer_capability.py --model {model} "
                   f"--live --output data/status/model-sync/receipts/{model}-developer.json")
    if candidate.get("voice"):
        out.append("python scripts/latency_probe.py  # after switching OPENAI_MODEL, on live logs")
    return out


def certify(candidate: dict, *, status_dir: Path, probe=None, run_script=None,
            voice_runner=None, now=None) -> dict[str, Any]:
    model = str(candidate.get("model", ""))
    vendor = candidate.get("vendor")
    steps: list[dict[str, Any]] = []
    result: dict[str, Any] = {"model": model, "replaces": candidate.get("replaces"),
                              "steps": steps, "passed": False, "manual": []}
    stamp = now() if callable(now) else (now or datetime.now(timezone.utc))
    result["certified_at"] = stamp.isoformat(timespec="seconds") if hasattr(stamp, "isoformat") else str(stamp)

    def run(name: str, fn: Callable[[], tuple[bool, str]]) -> bool:
        try:
            ok, detail = fn()
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, type(exc).__name__
        steps.append({"name": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    try:
        result["manual"] = _manual({**candidate, "model": model})
        which = {"anthropic": "claude", "openai": "codex"}.get(vendor)
        if which is None:
            steps.append({"name": "subscription_probe", "ok": False,
                          "detail": "no subscription route for this vendor"})
            return result

        def _probe() -> tuple[bool, str]:
            if probe is not None:
                res = probe(which, model)
            else:
                from jarvis.status.subscriptions import probe_subscription
                res = probe_subscription(which, model, force=True)
            ok = bool(res.get("ok"))
            return ok, "ok" if ok else str(res.get("category") or "failed")

        if not run("subscription_probe", _probe):
            return result

        if vendor == "openai":
            receipt = Path(status_dir) / "model-sync" / "receipts" / f"{model}.json"

            def _receipt() -> tuple[bool, str]:
                receipt.parent.mkdir(parents=True, exist_ok=True)
                argv = [sys.executable, "scripts/verify_subscription_capability.py",
                        "--model", model, "--output", str(receipt)]
                proc = (run_script or _default_run_script)(argv, timeout=CODEX_RECEIPT_TIMEOUT_S)
                ok = proc.returncode == 0
                return ok, "ok" if ok and not _last_line(proc) else _last_line(proc)

            if not run("codex_receipt", _receipt):
                return result

        if candidate.get("voice"):
            def _voice() -> tuple[bool, str]:
                b = voice_bench(model, runner=voice_runner, runs=5, vendor=vendor)
                return b["ok"], json.dumps(b, sort_keys=True)

            if not run("voice_bench", _voice):
                return result

        result["passed"] = all(s["ok"] for s in steps)
    except Exception as exc:  # noqa: BLE001
        steps.append({"name": "certify", "ok": False, "detail": type(exc).__name__})
        result["passed"] = False
    return result
