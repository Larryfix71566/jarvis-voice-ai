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


def model_key_probe(base_url: str, api_key: str, model: str) -> tuple[str, str]:
    """Return (outcome, detail) where outcome is "ok" | "rejected" |
    "unreachable". MORTIMER_KEY_VALIDITY_PLAN.md K1.

    Same contract as github_probe above, and for the same reason: every
    other LLM key check in this repo is `os.environ.get(name)`, a presence
    test, and presence is not validity. github_probe exists because
    check_env said PASS for two days against a dead GITHUB_TOKEN; nothing
    carried that lesson to a single model key until this function.

    WHY chat/completions AND NOT GET /models. The first cut of
    scripts/check_keys.py probed `/models` because it is free and
    read-only. Measured on Larry's machine 2026-08-19, it reported
    ANTHROPIC_API_KEY and OPENAI_API_KEY as REJECTED (401) while Mortimer
    was answering questions by voice on that exact key: Anthropic's
    OpenAI-compatibility layer authenticates /chat/completions with a
    Bearer token but does not serve /models the same way. A probe must
    exercise the SAME call the consumers make, or its verdict answers a
    different question than the one asked.

    Auth is evaluated before request validity on every provider here, so a
    status that is NOT 401/403 means the key was accepted — even a 400 for
    a malformed request. That is reported as ok with the reason attached,
    never as a failure.

    Never logs, prints, or returns the key, not even a prefix: the value
    appears only in the Authorization header of the request it makes.
    """
    body = json.dumps({
        "model": model,
        "max_tokens": 16,
        "messages": [{"role": "user", "content": "ping"}],
    }).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json",
                 "User-Agent": "mortimer-check-env"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return "ok", f"chat/completions accepted the key (HTTP {resp.status})"
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return "rejected", f"HTTP {exc.code} {exc.reason} — key was refused"
        if exc.code == 402:
            # Observed on Larry's OpenRouter key 2026-08-19. Auth succeeded,
            # so the key is genuinely valid — but every model call through it
            # will fail until the account is funded. "Valid" and "usable" are
            # not the same claim, and this is the one status where they
            # diverge, so it gets its own verdict rather than being rounded
            # to the nearer neighbour.
            return "unfunded", (
                f"HTTP 402 Payment Required — the key is VALID but the "
                f"account has no credit, so every call through it will fail")
        return "ok", (f"auth passed; the request itself failed "
                      f"(HTTP {exc.code} {exc.reason}) — key is valid")
    except Exception as exc:  # noqa: BLE001
        return "unreachable", f"{type(exc).__name__}: {str(exc)[:100]}"


def secret_source(name: str, pre_vault_env: dict[str, str],
                  vault_names: set[str]) -> str:
    """Where the value production will actually use came from. K2.

    The vault's precedence rule is that a NON-EMPTY environment variable
    beats the vault, so rotating a key correctly in the vault while a stale
    export sits in the shell produces permanent, silent failure — and until
    this function nothing anywhere reported which source won. Names and
    sources only; never a value.
    """
    if name in pre_vault_env:
        return ("environment — ALSO IN VAULT, the vault copy is ignored"
                if name in vault_names else "environment (.env or shell)")
    return "vault" if os.environ.get(name, "").strip() else "not set"


def _load_model_registry() -> dict:
    """The joined model registry under REPO_ROOT, through the ONE loader.

    docs/plans/MORTIMER_MODEL_REGISTRY_SPLIT_PLAN.md step 3: this script
    used to parse config/upgrade_models.yaml itself in three places. After
    the split, the keys and endpoints live in config/model_endpoints.yaml
    and only jarvis.agents.upgrade_agent.load_model_registry joins them.

    Raises FileNotFoundError when there is no registry at all (the three
    callers keep their own "not found" wording), ImportError when the
    loader cannot be imported (a fresh checkout before dependencies are
    installed), and the loader's own error for a malformed or unsafe one.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from jarvis.agents.upgrade_agent import load_model_registry, registry_source

    config_dir = REPO_ROOT / "config"
    source = registry_source(config_dir=config_dir)
    if not source.exists():
        raise FileNotFoundError(str(source))
    return load_model_registry(config_dir=config_dir)


def check_model_keys(env: dict[str, str], pre_vault_env: set[str],
                     vault_names: set[str]) -> None:
    """One live probe per distinct (api_key_env, base_url) — per KEY and
    ENDPOINT, not per profile, so one dead Moonshot key reads as one
    problem rather than two.

    The endpoint is part of the question, not a detail: OPENAI_API_KEY may
    hold an Anthropic credential when OPENAI_BASE_URL points at Anthropic
    (which .env.example documents), and probing it against api.openai.com
    returns 401 meaning only "not an OpenAI key." Grouping by key alone
    made exactly that mistake and produced a false "renew this key."
    """
    try:
        registry = _load_model_registry()
    except FileNotFoundError:
        return
    except Exception as exc:  # noqa: BLE001
        report(None, "Model key validity", f"could not read registry: {exc}")
        return

    groups: dict[tuple[str, str], dict] = {}
    for prof in registry["profiles"].values():
        if not isinstance(prof, dict):
            continue
        key_env = str(prof.get("api_key_env", "OPENAI_API_KEY"))
        base = str(prof.get("base_url", ""))
        g = groups.setdefault((key_env, base),
                              {"model": str(prof.get("model", "")), "names": []})
        g["names"].append(str(prof.get("name", "?")))

    # The voice model is not in the registry but is the single most
    # important credential in the system — omitting it would leave the one
    # key whose failure silences Mortimer entirely unchecked.
    # `env` (load_env()), NOT os.environ. OPENAI_BASE_URL lives in .env as
    # plain configuration, and .env is NOT exported into os.environ by this
    # script — only the vault's secrets are. Reading os.environ here fell
    # back to the api.openai.com default and probed Larry's ANTHROPIC key
    # against OpenAI's server, producing a required-check FAIL on a system
    # whose voice loop was working perfectly. Third time this exact mistake
    # has been made today: the endpoint a key is used against is part of the
    # question, and it has to come from the same place production reads it.
    voice_base = env.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    voice_model = env.get("OPENAI_MODEL", "gpt-4.1-mini")
    groups.setdefault(("OPENAI_API_KEY", voice_base),
                      {"model": voice_model, "names": []})["names"].append("voice model")

    for (key_env, base), g in sorted(groups.items()):
        used_by = ", ".join(g["names"])
        source = secret_source(key_env, pre_vault_env, vault_names)
        label = f"Key {key_env} -> {base}"
        key = (os.environ.get(key_env) or env.get(key_env, "")).strip()
        if not key:
            report(False, label, f"MISSING (needed by {used_by})")
            continue
        outcome, detail = model_key_probe(base, key, g["model"])
        if outcome == "ok":
            report(True, label, f"{detail} [source: {source}]")
        elif outcome == "unfunded":
            # A valid credential with no balance is a THIRD state, and
            # collapsing it into either neighbour misleads: reported as ok it
            # says a model will answer when every call will fail, reported as
            # rejected it sends you to rotate a perfectly good key. The
            # action is neither "renew" nor "nothing" — it is "add credit".
            report(False, label,
                   f"{detail} — breaks {used_by} [source: {source}]")
        elif outcome == "rejected":
            report(False, label,
                   f"{detail} — breaks {used_by} [source: {source}]")
        else:
            # Never "renew this key": a blocked network and a dead
            # credential call for opposite responses.
            report(None, label, f"{detail} — NOT proven bad [source: {source}]")


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
    model profiles in the model registry actually have their API
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

    try:
        registry = _load_model_registry()
    except FileNotFoundError as exc:
        report(None, "Model registry", f"file not found ({exc})")
        return
    except ImportError as exc:
        report(None, "Model registry", f"registry loader unavailable ({exc}) — skipped")
        return
    except Exception as exc:
        report(None, "Model registry", f"could not parse the model registry: {exc}")
        return

    profiles = list(registry["profiles"].values())
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


# Split plan §4a.2: the sync job runs daily, so an entry older than this has
# missed more than a couple of runs and must not be silently trusted.
CATALOG_STALE_AFTER_DAYS = 3


def check_model_catalog() -> None:
    """docs/plans/MORTIMER_MODEL_REGISTRY_SPLIT_PLAN.md step 8 (§4a.2/§4a.3):
    report each endpoint's generated upstream catalogue — its oldest entry,
    or that it is still the seeded baseline — and warn when a profile's
    identity is missing from its endpoint's catalogue, disagrees with it on
    the model string, or is marked for retirement. WARN-only: a stale or
    seeded catalogue is visible, never a preflight failure. Silent for a
    legacy single-file registry, which has no endpoints to catalogue.
    """
    try:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from jarvis.agents.upgrade_agent import (
            catalog_retirement, load_registry_layers, load_upstream_catalogs)

        config_dir = REPO_ROOT / "config"
        layers = load_registry_layers(config_dir=config_dir)
        catalogs = load_upstream_catalogs(config_dir=config_dir)
    except ImportError as exc:
        report(None, "Model catalogue", f"registry loader unavailable ({exc}) — skipped")
        return
    except Exception as exc:  # noqa: BLE001
        report(None, "Model catalogue", f"could not read: {exc}")
        return
    if layers["shape"] != "split":
        return

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    for endpoint in layers["endpoints"]:
        label = f"Model catalogue {endpoint}"
        catalog = catalogs.get(endpoint)
        if catalog is None:
            report(None, label, "no config/generated catalogue — upstream facts unknown")
            continue
        entries = [e for e in catalog.get("models") or [] if isinstance(e, dict)]
        unfetched = sum(1 for e in entries if not e.get("fetched_at"))
        if not entries:
            report(None, label, "empty")
        elif unfetched:
            report(None, label,
                   f"{len(entries)} models, {unfetched} never fetched (seeded baseline) "
                   "— upstream facts not yet verified by a sync")
        else:
            oldest = min(datetime.fromisoformat(str(e["fetched_at"]).replace("Z", "+00:00"))
                         for e in entries)
            if oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=timezone.utc)
            age = (now - oldest).days
            detail = f"{len(entries)} models, oldest entry fetched {oldest:%Y-%m-%d}"
            if age > CATALOG_STALE_AFTER_DAYS:
                report(None, label, f"{detail} ({age} days ago) — STALE, not refreshed")
            else:
                report(True, label, detail)

    today = now.date().isoformat()
    for prof in layers["profiles"]:
        catalog = catalogs.get(str(prof["endpoint"]))
        if catalog is None:
            continue
        name, identity = prof["name"], prof["identity"]
        entry = next((e for e in catalog.get("models") or []
                      if isinstance(e, dict) and e.get("identity") == identity), None)
        label = f"Model catalogue: profile {name}"
        if entry is None:
            report(None, label,
                   f"{identity} is not in the {prof['endpoint']} catalogue — added since "
                   "the last sync, or gone upstream")
            continue
        if entry.get("model") != prof.get("model"):
            report(None, label,
                   f"model {prof.get('model')!r} differs from the catalogue's "
                   f"{entry.get('model')!r} for {identity}")
        retires = catalog_retirement(entry)
        if retires:
            state = "RETIRED on" if retires <= today else "retires on"
            report(None, label, f"{identity} {state} {retires} — propose a replacement "
                   "on the same endpoint in config/model_profiles.yaml")


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
        import yaml  # noqa: F401 — availability guard; keeps this report's output unchanged (D7)
    except ImportError:
        report(None, "Screen vision", "PyYAML not installed — skipped")
        return
    try:
        registry = _load_model_registry()
    except FileNotFoundError as exc:
        report(None, "Screen vision", f"model registry not found ({exc})")
        return
    except ImportError as exc:
        report(None, "Screen vision", f"registry loader unavailable ({exc}) — skipped")
        return
    except Exception as exc:
        report(None, "Screen vision", f"could not parse the model registry: {exc}")
        return

    vision = [p for p in registry["profiles"].values()
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
    # K2: snapshot which vars the ENVIRONMENT supplies BEFORE the vault gets
    # a chance. A non-empty env var beats the vault, so anything captured
    # here is what production actually uses — and a name that appears in
    # both is a stale export silently shadowing a rotated vault entry.
    pre_vault_env = {k for k, v in os.environ.items() if v.strip()}
    vault_names: set[str] = set()

    try:
        sys.path.insert(0, str(REPO_ROOT))
        from jarvis.vault import VaultError, inject_env, load_secrets

        try:
            try:
                vault_names = set(load_secrets().keys())
            except Exception:  # noqa: BLE001
                pass  # names only, for the shadowing report; not required
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
    # K1/K2 — presence is checked above; this is the only thing here that
    # asks whether the credentials actually WORK.
    check_model_keys(env, pre_vault_env, vault_names)
    check_model_catalog()
    check_screen_vision()

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)} required check(s) failed)")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
