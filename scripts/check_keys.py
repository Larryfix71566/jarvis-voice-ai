"""Are Mortimer's configured API keys actually VALID? (not merely present)

Standalone, read-only diagnostic. Writes nothing, changes nothing, and
NEVER prints or logs a key value - the value appears only in the
Authorization header of the request it makes.

Answers three questions the rest of the system currently cannot:

  1. Does each key WORK, not just exist? Every other check in this repo
     is `os.environ.get(name)`, a presence test. The one exception is
     check_env.py's github_probe, which exists precisely because
     check_env said PASS for two days against a dead GITHUB_TOKEN.

  2. Where did each key come from? A non-empty environment variable
     BEATS the vault, so a stale shell export silently shadows a
     correctly-rotated vault entry. That is reported explicitly.

  3. What breaks if it is bad? Each key is reported with the profiles
     that depend on it.

REJECTED and UNREACHABLE are kept distinct on purpose: a dead credential
and a blocked network both stop the request but call for opposite
responses, and collapsing them is the invent-a-cause error AGENT_DISCIPLINE
exists to prevent. UNREACHABLE never means "renew this key."

Run from the repo root with the venv active:

    python scripts/check_keys.py

Superseded when MORTIMER_KEY_VALIDITY_PLAN.md K1 folds this probe into
scripts/check_env.py. Until then this is the only live key check here.
"""
import os
import sys
from pathlib import Path

# Running `python scripts/check_keys.py` puts scripts/ on sys.path, NOT the
# repo root, so `import jarvis` fails even from a correctly-activated venv
# in the right directory. Anchor to the file's own location rather than the
# cwd (same REPO_ROOT convention as check_env.py) so the script works from
# anywhere, including a double-click or an absolute path.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_env import require_model_api_access

# Refuse before vault access or credential diagnostics in retirement mode.
require_model_api_access()

# 1. Snapshot which vars the ENVIRONMENT already supplies, before the vault
#    gets a chance. A non-empty env var BEATS the vault, so anything here
#    is what production will actually use.
from_env = {k for k, v in os.environ.items() if v.strip()}

vault_names = set()
try:
    from jarvis.vault import inject_env, load_secrets
    try:
        vault_names = set(load_secrets().keys())
    except Exception:                                     # noqa: BLE001
        pass
    inject_env()
    vault_note = f"vault read ok ({len(vault_names)} secrets)"
except Exception as exc:                                  # noqa: BLE001
    vault_note = f"vault NOT read ({type(exc).__name__}) - .env only"

try:
    from jarvis.agents.upgrade_agent import load_model_registry
    from openai import OpenAI
except Exception as exc:                                  # noqa: BLE001
    print(f"cannot import Mortimer modules: {exc}")
    print("run this from the repo root with the venv active")
    sys.exit(1)

# 2. Group profiles by (api_key_env, base_url): probe once per KEY and
#    endpoint, so one dead key reads as one problem not two. Subscription
#    profiles carry no api_key_env/base_url and are skipped (not reachable
#    by API). Larry 2026-11-23: the Anthropic, OpenAI and Moonshot keys are
#    retired and never probed.
registry = load_model_registry()
RETIRED_KEYS = {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "MOONSHOT_API_KEY"}
groups = {}
for prof in registry["profiles"].values():
    if not isinstance(prof, dict):
        continue
    env_name = str(prof.get("api_key_env") or "")
    base_url = str(prof.get("base_url") or "")
    if not env_name or not base_url or env_name in RETIRED_KEYS:
        continue
    g = groups.setdefault((env_name, base_url),
                          {"model": str(prof.get("model", "")), "profiles": []})
    g["profiles"].append(str(prof.get("name", "?")))

for name in sorted(RETIRED_KEYS):
    if os.environ.get(name, "").strip():
        print(f"WARNING: {name} is still set. It is retired; remove it from "
              "the .env / vault and revoke it in the provider console.")


def probe(base_url, key, model):
    """-> (outcome, detail). Never returns OK for something not reached, and
    never returns REJECTED for something production never calls.

    WHY THIS USES chat/completions AND NOT GET /models: a 401 from an
    endpoint production never calls is not evidence about the key. The
    probe must exercise the SAME call the consumers make.

    Auth is evaluated before request validity on the provider here, so any
    status that is NOT 401/403 means the key was accepted - even a 400 for a
    malformed request. That is reported as OK with the reason attached,
    rather than as a failure.
    """
    require_model_api_access()
    from jarvis.provider_access import require_not_retired
    require_not_retired(base_url=base_url, model=model)
    client = OpenAI(api_key=key, base_url=base_url, timeout=30.0, max_retries=0)
    try:
        client.chat.completions.create(
            model=model, max_tokens=16,
            messages=[{"role": "user", "content": "ping"}])
        return "OK", "chat/completions accepted the key"
    except Exception as exc:                              # noqa: BLE001
        name = type(exc).__name__
        status = getattr(exc, "status_code", None)
        if name in ("APIConnectionError", "APITimeoutError"):
            return "UNREACHABLE", f"{name} - network/DNS, key NOT proven bad"
        if name in ("AuthenticationError", "PermissionDeniedError") or status in (401, 403):
            return "REJECTED", f"{name} (HTTP {status}) - key was refused"
        if status is not None:
            return "OK", (f"auth passed; the request itself failed "
                          f"(HTTP {status} {name}) - key is valid")
        return "UNKNOWN", f"{name}: {str(exc)[:90]}"


print()
print(f"Mortimer API key validity - {vault_note}")
print("=" * 78)

bad = []
for env_name, base_url in sorted(groups):
    g = groups[(env_name, base_url)]
    key = os.environ.get(env_name, "").strip()
    if env_name in from_env:
        source = ("environment - ALSO IN VAULT, the vault copy is being ignored"
                  if env_name in vault_names else "environment (.env or shell)")
    elif key:
        source = "vault"
    else:
        source = "-"
    used_by = ", ".join(g["profiles"])
    print()
    print(f"{env_name}  ->  {base_url}")
    print(f"  used by : {used_by}")
    print(f"  source  : {source}")
    if not key:
        print("  verdict : MISSING - not set anywhere")
        bad.append((env_name, base_url, "MISSING", used_by))
        continue
    outcome, detail = probe(base_url, key, g["model"])
    print(f"  verdict : {outcome} - {detail}")
    if outcome != "OK":
        bad.append((env_name, base_url, outcome, used_by))

print()
print("=" * 78)
if not bad:
    print("All configured keys answered OK. Nothing to renew.")
else:
    # A key that is OK at one endpoint and REJECTED at another is NOT a
    # contradiction: it means the value is a valid credential for a
    # different provider than the one that rejected it. Reported per
    # endpoint so that distinction survives to the summary.
    print("NEEDS ATTENTION:")
    for env_name, base_url, outcome, used_by in bad:
        verb = {"REJECTED": "RENEW this key, or it belongs to another provider",
                "MISSING": "SET this key",
                "UNREACHABLE": "re-run when online - not proven bad",
                "UNKNOWN": "investigate"}[outcome]
        print(f"  {env_name:22} {outcome:12} {verb}")
        print(f"  {'':22} endpoint: {base_url}")
        print(f"  {'':22} breaks:   {used_by}")
    print()
    print("  A REJECTED verdict proves the key was refused BY THAT ENDPOINT.")
    print("  Check the endpoint above matches the provider the key came from")
    print("  before rotating anything.")
print()
