#!/usr/bin/env python3
"""Environment & connectivity validator (plan Phase 0, step 0.5 / Exit Gate 0).

Stdlib only, so it works before any dependencies are installed.
Prints one PASS / FAIL / WARN line per check; exit code 0 only if every
required check passes. TAVILY is WARN-degradable per plan §6.2.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 10

REQUIRED_VARS = ["OPENAI_API_KEY", "DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY"]

failures: list[str] = []


def report(ok: bool | None, label: str, detail: str = "") -> None:
    """ok=True -> PASS, ok=False -> FAIL, ok=None -> WARN."""
    tag = "PASS" if ok else ("WARN" if ok is None else "FAIL")
    suffix = f" — {detail}" if detail else ""
    print(f"[{tag}] {label}{suffix}")
    if ok is False:
        failures.append(label)


def load_env() -> dict[str, str]:
    """os.environ overlaid with repo .env (simple KEY=VALUE parser)."""
    env = dict(os.environ)
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env.setdefault(key.strip(), value.strip())
    return env


def http_status(url: str, headers: dict[str, str] | None = None,
                method: str = "GET", payload: dict | None = None,
                read_limit: int = 4096) -> tuple[int | None, str]:
    """Return (status_code, body_snippet). (None, error) on network failure."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read(read_limit).decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return None, str(e)


def main() -> int:
    env = load_env()

    # 1. Python version
    v = sys.version_info
    report(v >= (3, 11), "Python >= 3.11", f"found {v.major}.{v.minor}.{v.micro}")

    # 2. Required env vars present
    missing = [name for name in REQUIRED_VARS if not env.get(name)]
    report(not missing, "Required env vars present",
           f"missing: {', '.join(missing)}" if missing else "all set")

    # 3. LLM reachable
    if env.get("OPENAI_API_KEY"):
        base = env.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        code, _ = http_status(f"{base}/models",
                              {"Authorization": f"Bearer {env['OPENAI_API_KEY']}"})
        report(code is not None and 200 <= code < 300,
               "LLM reachable (GET {}/models)".format(base),
               f"HTTP {code}" if code else "connection error")
    else:
        report(False, "LLM reachable", "skipped (no OPENAI_API_KEY)")

    # 4. Deepgram reachable
    if env.get("DEEPGRAM_API_KEY"):
        code, _ = http_status("https://api.deepgram.com/v1/projects",
                              {"Authorization": f"Token {env['DEEPGRAM_API_KEY']}"})
        report(code is not None and 200 <= code < 300, "Deepgram reachable",
               f"HTTP {code}" if code else "connection error")
    else:
        report(False, "Deepgram reachable", "skipped (no DEEPGRAM_API_KEY)")

    # 5. ElevenLabs reachable (+ voice count)
    if env.get("ELEVENLABS_API_KEY"):
        code, body = http_status("https://api.elevenlabs.io/v1/voices",
                                 {"xi-api-key": env["ELEVENLABS_API_KEY"]},
                                 read_limit=4_000_000)
        detail = f"HTTP {code}" if code else "connection error"
        if code == 200:
            try:
                detail = f"{len(json.loads(body).get('voices', []))} voices on account"
            except Exception:
                pass
        report(code == 200, "ElevenLabs reachable", detail)
    else:
        report(False, "ElevenLabs reachable", "skipped (no ELEVENLABS_API_KEY)")

    # 6. Tavily reachable (WARN-degradable per §6.2). D-011: probe the
    # hosted MCP endpoint (the transport web_search uses first); the classic
    # REST API is WAF-blocked for some egress IPs even with a healthy key.
    if not env.get("TAVILY_API_KEY"):
        report(None, "Tavily reachable", "no key — mcp-web will run degraded")
    else:
        code, _ = http_status(
            f"https://mcp.tavily.com/mcp/?tavilyApiKey={env['TAVILY_API_KEY']}",
            {"Content-Type": "application/json",
             "Accept": "application/json, text/event-stream"},
            method="POST",
            payload={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": "tavily_search",
                                "arguments": {"query": "ping", "max_results": 1}}})
        report(code is not None and 200 <= code < 300, "Tavily reachable",
               f"HTTP {code}" if code else "connection error")

    # 7. Open-Meteo reachable
    code, _ = http_status(
        "https://api.open-meteo.com/v1/forecast?latitude=40.71&longitude=-74.00"
        "&current=temperature_2m")
    report(code == 200, "Open-Meteo reachable",
           f"HTTP {code}" if code else "connection error")

    # 8. Timezone valid
    tz = env.get("JARVIS_TIMEZONE", "")
    try:
        ZoneInfo(tz)
        report(True, "JARVIS_TIMEZONE valid", tz)
    except Exception:
        report(False, "JARVIS_TIMEZONE valid", f"invalid: {tz!r}")

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)} required check(s) failed)")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
