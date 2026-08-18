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


def read_dotenv_only() -> dict[str, str]:
    """Parse .env WITHOUT merging os.environ — needed by the D9 shadowing
    check below, which must compare the two sources separately rather than
    the single merged view load_env() returns."""
    env_file = REPO_ROOT / ".env"
    values: dict[str, str] = {}
    if not env_file.exists():
        return values
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_env() -> dict[str, str]:
    """os.environ overlaid with repo .env (simple KEY=VALUE parser)."""
    env = dict(os.environ)
    for key, value in read_dotenv_only().items():
        env.setdefault(key, value)
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


def github_probe(token: str) -> tuple[str, str, str]:
    """Return (outcome, detail, scopes) where outcome is "ok" | "rejected" |
    "unreachable". Folded in from scripts/check_github.py
    (MORTIMER_AGENT_TRUST_PLAN.md D9).

    "rejected" and "unreachable" are kept DISTINCT on purpose. A dead
    credential and a blocked network both stop the request, but they call
    for opposite responses — rotate the token vs. check the connection —
    and collapsing them into one FAIL is the same invent-a-cause error that
    made a GitHub 401 get reported to a user as "admin sidecar may be
    offline" (plan §1.4/D7). Never returns "ok" for something that was not
    actually reached — that is the exact failure this check exists to
    catch (§1.5: check_env.py said PASS for two days while GITHUB_TOKEN
    was dead, because nothing here looked at GitHub at all).
    """
    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "mortimer-check-env"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read())
            scopes = resp.headers.get("x-oauth-scopes") or ""
            return "ok", f"HTTP {resp.status}, login={data.get('login')}", scopes
    except urllib.error.HTTPError as exc:
        return "rejected", f"HTTP {exc.code} {exc.reason}", ""
    except Exception as exc:  # noqa: BLE001
        return "unreachable", f"{type(exc).__name__}: {str(exc)[:120]}", ""


# Two distinct credentials (plan D9) — GITHUB_TOKEN needs 'repo' scope
# because app_create makes private repositories; JARVIS_GITHUB_TOKEN is a
# fine-grained token for jarvis/selfedit/service.py and reports no
# x-oauth-scopes header at all, so it is never scope-checked.
_GITHUB_TOKENS = [
    ("GITHUB_TOKEN", "mcp_apps (app_* tools)", "repo"),
    ("JARVIS_GITHUB_TOKEN", "jarvis/selfedit (PR flow)", None),
]


def check_github(env: dict[str, str], env_file_values: dict[str, str]) -> None:
    """WARN-degradable (plan D9) — voice, memory, scheduling and research
    all work with no GitHub access at all, so a dead token here must never
    produce a required FAIL, only visibility. Every branch below reports
    via WARN or PASS, never FAIL, and is therefore never added to
    `failures`."""
    for name, consumer, needed_scope in _GITHUB_TOKENS:
        label = f"GitHub: {name} ({consumer})"
        file_val = env_file_values.get(name, "")
        shell_val = os.environ.get(name, "")

        # Shadowing check: pydantic-settings resolves the OS environment
        # ahead of the .env file (jarvis/config.py's Settings), so an
        # exported shell variable silently defeats every edit to .env.
        if shell_val and file_val and shell_val != file_val:
            report(None, label,
                   "an exported shell variable DIFFERS from .env and will "
                   f"win — edits to .env have no effect until `unset {name}`")
            continue

        effective = shell_val or file_val
        if not effective:
            report(None, label, "not configured")
            continue

        outcome, detail, scopes = github_probe(effective)
        if outcome == "ok":
            scope_note = ""
            if needed_scope and scopes and needed_scope not in scopes.split(", "):
                scope_note = (f"; WARNING: '{needed_scope}' scope missing — "
                               "app_create/app_write_file will 403")
            report(True, label, detail + scope_note)
        elif outcome == "rejected":
            report(None, label,
                   f"{detail} — invalid, expired, or revoked. Fix: "
                   f"./scripts/set_github_token.sh {name}")
        else:  # unreachable
            report(None, label,
                   f"could not verify ({detail}) — network/proxy problem, "
                   "not a credential verdict")


def check_model_registry() -> None:
    """H2 (MORTIMER_CONFIRMATION_AND_CAPABILITY_PLAN.md): report which
    model profiles in config/upgrade_models.yaml actually have their API
    key present, then cross-reference config/agents.yaml so a sub-agent
    pinned to a profile whose key is missing is visible BEFORE a
    delegation fails. WARN-only by design — a missing planner key must
    never block preflight, since voice itself still boots on one key.
    The refuse-mode wording is the point: developer with
    on_profile_fallback=refuse and no key refuses every delegation.
    """
    try:
        import yaml
    except ImportError:
        report(None, "Model registry", "PyYAML not installed — skipped")
        return

    registry_path = REPO_ROOT / "config" / "upgrade_models.yaml"
    if not registry_path.exists():
        report(None, "Model registry", f"file not found ({registry_path})")
        return
    try:
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        report(None, "Model registry", f"could not parse upgrade_models.yaml: {exc}")
        return

    profiles = registry.get("profiles") or []
    default_name = registry.get("default")
    by_name = {}
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        name = str(profile.get("name", ""))
        if not name:
            continue
        by_name[name] = profile
        key_env = str(profile.get("api_key_env", "OPENAI_API_KEY"))
        label = f"{name} (registry default)" if name == default_name else name
        present = bool(os.environ.get(key_env, "").strip())
        report(
            True if present else None,
            f"Model profile {label}",
            f"{key_env} {'present' if present else 'missing'}",
        )

    agents_path = REPO_ROOT / "config" / "agents.yaml"
    if not agents_path.exists():
        return
    try:
        agents_cfg = yaml.safe_load(agents_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return

    entries = agents_cfg.get("sub_agents")
    if isinstance(entries, dict):
        entries = [{"name": k, **(v or {})} for k, v in entries.items()]
    for agent in entries or []:
        if not isinstance(agent, dict):
            continue
        name = str(agent.get("name", ""))
        profile_name = agent.get("model_profile")
        if not name or not profile_name:
            continue
        mode = str(agent.get("on_profile_fallback", "warn")).strip().lower()
        profile = by_name.get(str(profile_name)) or {}
        key_env = str(profile.get("api_key_env", "OPENAI_API_KEY"))
        present = bool(os.environ.get(key_env, "").strip())
        label = f"{name}'s model_profile ({profile_name}, on_profile_fallback={mode})"
        if present:
            report(True, label, f"{key_env} present")
        elif mode == "refuse":
            report(None, label,
                   f"{key_env} missing — {name} will REFUSE every delegation until this is fixed")
        else:
            report(None, label,
                   f"{key_env} missing — {name} will silently fall back to the voice model")


def check_screen_vision() -> None:
    """V5 (MORTIMER_SHELL_FIX_AND_SCREEN_VISION_PLAN.md): report whether
    screen vision is on and which vision profile would answer a
    view_screen call. WARN-only, and it always ends with the macOS
    Screen Recording reminder — that permission cannot be detected from
    a script and its failure mode is silent (wallpaper-only capture).
    """
    enabled = os.environ.get("JARVIS_SCREEN_ENABLED", "").strip().lower() not in (
        "false", "0", "no",
    )
    if not enabled:
        report(None, "Screen vision", "disabled (JARVIS_SCREEN_ENABLED=false)")
        return
    try:
        import yaml
    except ImportError:
        report(None, "Screen vision", "PyYAML not installed — skipped")
        return
    registry_path = REPO_ROOT / "config" / "upgrade_models.yaml"
    if not registry_path.exists():
        report(None, "Screen vision", "config/upgrade_models.yaml not found")
        return
    try:
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        report(None, "Screen vision", f"could not parse upgrade_models.yaml: {exc}")
        return

    vision = [p for p in (registry.get("profiles") or [])
              if isinstance(p, dict) and p.get("vision")]
    named = os.environ.get("JARVIS_VISION_PROFILE", "").strip()
    chosen = None
    if named:
        match = next((p for p in vision if str(p.get("name")) == named), None)
        if match is None:
            report(None, "Screen vision",
                   f"JARVIS_VISION_PROFILE={named} is not a vision:true profile")
        elif not os.environ.get(str(match.get("api_key_env", "")), "").strip():
            report(None, "Screen vision", f"{named}'s {match.get('api_key_env')} is missing")
        else:
            chosen = match
    else:
        chosen = next((p for p in vision
                       if os.environ.get(str(p.get("api_key_env", "")), "").strip()), None)
        if chosen is None:
            report(None, "Screen vision", "no vision:true profile has its API key set")
    if chosen is not None:
        report(True, "Screen vision", f"will use profile {chosen.get('name')}")
    report(None, "Screen recording permission",
           "cannot be checked from a script — grant it in System Settings > Privacy "
           "& Security > Screen Recording, or captures come back as wallpaper only")


def main() -> int:
    # Credential vault (MORTIMER_CREDENTIAL_VAULT_PLAN.md S4, call site
    # 3 of 3): pull vault secrets into os.environ before any check reads
    # them. Guarded import because this script is documented stdlib-only
    # so it works in a fresh checkout before dependencies are installed —
    # in that state there is no vault to read anyway.
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from jarvis.vault import VaultError, inject_env

        try:
            inject_env()
        except VaultError as exc:
            # S6's hard-error rule, rendered in this script's own
            # PASS/FAIL format: a present-but-unreadable vault must
            # stop the check (never validate half-configured), but a
            # validator reports — it doesn't traceback.
            report(False, "Credential vault readable", str(exc))
            return 1
    except ImportError:
        pass

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
        headers = {"Authorization": f"Bearer {env['OPENAI_API_KEY']}"}
        if "anthropic" in base:
            # Anthropic's /v1/models expects native auth; Bearer only works
            # on /chat/completions (the path the bot actually calls).
            headers = {"x-api-key": env["OPENAI_API_KEY"],
                       "anthropic-version": "2023-06-01"}
        code, _ = http_status(f"{base}/models", headers)
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

    # 9. GitHub credentials (plan D9). WARN-degradable — see check_github's
    # docstring for why this must never be a required FAIL.
    check_github(env, read_dotenv_only())

    # 10. Stale git index lock (plan D15). Mirrors mcp_git/logic.py's
    # GIT_LOCK_STALE_AFTER_S (300s) by value, not by import — check_env.py
    # is stdlib-only so it can run before dependencies are installed, and
    # this constant is trivial enough that duplicating it beats coupling
    # this script to the full package.
    _GIT_LOCK_STALE_AFTER_S = 300
    lock_path = REPO_ROOT / ".git" / "index.lock"
    if lock_path.exists():
        import time as _time
        age_s = _time.time() - lock_path.stat().st_mtime
        if age_s > _GIT_LOCK_STALE_AFTER_S:
            report(None, "git index lock",
                   f".git/index.lock is {int(age_s)}s old — if no git "
                   "process is running, remove it manually: "
                   "rm .git/index.lock")
        else:
            report(None, "git index lock",
                   f".git/index.lock present ({int(age_s)}s old — may be "
                   "an in-progress commit)")
    else:
        report(True, "git index lock", "not present")

    # 9.5/9.6 — planner-model and screen-vision preflight (WARN-only).
    check_model_registry()
    check_screen_vision()

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)} required check(s) failed)")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
