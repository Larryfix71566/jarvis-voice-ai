#!/usr/bin/env python3
"""One-shot: split config/upgrade_models.yaml into the endpoint map and the
profile pool (docs/plans/MORTIMER_MODEL_REGISTRY_SPLIT_PLAN.md D1, D6).

    python scripts/split_model_registry.py [--source FILE] [--config-dir DIR]
                                           [--check]

Renders, next to each other in ``--config-dir`` (default ``config/``):

- ``model_endpoints.yaml`` — DENIED. Endpoint id -> provider, base_url,
  api_key_env (or ``kind: subscription`` for a credential-less endpoint,
  A1), plus the ``supervisor:`` pin on the registry default (D4).
- ``model_profiles.yaml`` — ROUTINE. The source file's text with each
  profile's ``provider``/``base_url``/``api_key_env`` lines replaced by one
  ``endpoint:`` line, so every comment and the profile order survive.
- ``generated/model_catalog.<endpoint>.json`` — the upstream catalogue
  baseline (§4a, step 8): one entry per profile on that endpoint, keyed by
  ``identity``, every §4a field present and null except the model string,
  ``fetched_at: null`` and ``source: "seeded"``.

Mechanical and provably lossless: before writing anything the script joins
what it rendered through the real loader and refuses unless the result
equals the source registry profile-for-profile, key-for-key (D6).
``--check`` renders and verifies without writing.

Kept (not deleted after the migration, as §5 first said) because
tests/unit/test_model_registry_split.py re-runs it over the frozen
pre-split registry as the permanent proof of D6, and the §9 rollback keeps
legacy acceptance for at least one release. Delete both together.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from jarvis.agents import upgrade_agent as ua  # noqa: E402

# A credential-less profile becomes an endpoint of its own. The legacy file
# does not record which access route reaches it; config/model_access.yaml
# does, and this is the one such profile (spec P5 A1).
SUBSCRIPTION_ROUTES = {"codex-subscription": "codex_subscription"}

ENDPOINTS_HEADER = """\
# Model ENDPOINTS — where requests go and which credential they carry.
#
# Tier 0 (deny) in config/self_edit_allowlist.json: human-only, merged by
# Larry. This is the credential boundary of the model registry
# (docs/plans/MORTIMER_MODEL_REGISTRY_SPLIT_PLAN.md D1/D3). Nothing in the
# codebase validates a host, so an edit that keeps a key variable and swaps
# a base_url would send that key to someone else's server on the next run.
# That is why hosts and key NAMES live only here, and why
# config/model_profiles.yaml — which the self-edit loop may change — cannot
# even express them: a profile that declares base_url, api_key_env or any
# other host-bearing key is a load error, and so is a profile naming an
# endpoint id that is not below.
#
# Key VALUES never live in config: api_key_env names an environment/vault
# variable (python -m jarvis.vault).
#
# `kind: subscription` is an endpoint with no API credential, reachable only
# through the named access route (config/model_access.yaml); its profiles
# carry no base_url or api_key_env at all.
#
# `supervisor:` pins the planner's own brain — the registry default the
# self-edit loop, the planning pathway, site research and the Edit panel
# fall back to. The loader refuses a model_profiles.yaml whose `default`
# is not this identity on this endpoint, and
# tests/unit/test_model_registry_split.py checks its model string against
# the seeded catalogue, so a routine edit cannot re-point the planner.
# Changing it is a human PR against this file (and the profile's default).
#
# Adding a PROVIDER or endpoint is always a human change here. Adding a
# MODEL on an existing endpoint is a routine change in
# config/model_profiles.yaml.
"""

PROFILES_HEADER = """\
# Model PROFILES — the pool Mortimer's agents, planner and council draw on.
#
# ROUTINE (Tier A, via `config/**` in config/self_edit_allowlist.json): the
# self-edit loop may add, retire or retune a profile here, and a human still
# merges the PR. What this file CANNOT say is where a request goes or which
# key it carries: each profile names an `endpoint:` id from
# config/model_endpoints.yaml (human-only), and the one loader,
# jarvis.agents.upgrade_agent.load_model_registry, joins provider/base_url/
# api_key_env in from there. A profile declaring base_url, api_key_env,
# provider, routes or any URL is a LOAD ERROR (split plan D3), as is an
# unknown endpoint id. Upstream facts (context window, prices, deprecation)
# are written daily into config/generated/model_catalog.<endpoint>.json by
# the sync job and joined by `identity`; never hand-edit those.
#
# Selection order when a planner session starts:
#   1. explicit per-session choice (Edit panel, or a spoken "use Claude Opus")
#   2. JARVIS_UPGRADE_PROFILE environment variable
#   3. the `default` below — pinned by `supervisor:` in
#      config/model_endpoints.yaml; changing it is a human PR there.
#
# temperature: set to null to OMIT the parameter entirely. Moonshot's
# kimi-k2.x family rejects any temperature other than 1 (DEVIATIONS.md
# D-003), so all Moonshot profiles omit it.
#
# vision: true — MORTIMER_SHELL_FIX_AND_SCREEN_VISION_PLAN.md V2. Marks a
# profile whose model can read IMAGES, making it eligible to answer
# view_screen questions (resolution order: JARVIS_VISION_PROFILE, then
# the first key-present vision profile in this file's order). Set it
# only for models actually confirmed multimodal — do not set it
# speculatively; an unset profile is simply never chosen for vision.
#
# tier: economy | mid | frontier — MORTIMER_LLM_COUNCIL_PLAN.md D4. Which
# escalation tier's proposer/judge pool a profile belongs to. Read by
# jarvis.agents.upgrade_agent.available_models() and jarvis.council.config,
# so the council and the console picker (D9) share one source of truth for
# "what tier is this model."
#
# identity: REQUIRED, and it is not decorative (Larry 2026-08-19). It is the
# canonical vendor/model string — the thing that identifies the MODEL, as
# distinct from `name` (this profile) or `model` (the string this endpoint
# wants). It is also the join key into the generated catalogue. Two
# profiles may legitimately differ in name, endpoint and model string while
# being the same underlying model: `openai/gpt-5.1` reached through
# OpenRouter and a direct OpenAI `gpt-5.1` are one model wearing two
# profile names.
#
# That is a correctness problem, not tidiness. The council's founding rule
# is that a model never scores its own proposal, and resolve_members'
# `exclude` enforces it on PROFILE NAMES — so a duplicate underlying model
# would let a model judge itself while the guarantee still read as enforced.
# tests/unit/test_model_registry.py fails if two profiles share an identity.
#
# The rule when adding an OpenRouter profile: if you can already reach that
# model directly, do not add it. Pick a different one — the whole value of a
# second route is a model you did not already have.
"""


def assign_endpoints(profiles: list[dict[str, Any]]) -> tuple[dict[str, dict], dict[str, str]]:
    """-> (endpoints in first-seen order, profile name -> endpoint id)."""
    by_triple: dict[tuple[str, str, str], str] = {}
    endpoints: dict[str, dict[str, Any]] = {}
    assignment: dict[str, str] = {}
    triples_per_provider: dict[str, set] = {}
    for prof in profiles:
        if prof.get("base_url") or prof.get("api_key_env"):
            triples_per_provider.setdefault(str(prof["provider"]), set()).add(
                (str(prof.get("base_url", "")), str(prof.get("api_key_env", ""))))
    for prof in profiles:
        name = str(prof["name"])
        provider = str(prof.get("provider") or "")
        if not provider:
            raise SystemExit(f"profile {name!r} has no provider; cannot assign an endpoint")
        base_url, key_env = prof.get("base_url"), prof.get("api_key_env")
        if not base_url and not key_env:
            if name not in SUBSCRIPTION_ROUTES:
                raise SystemExit(f"profile {name!r} has no endpoint and no known route")
            eid = name
            endpoints[eid] = {"provider": provider, "kind": "subscription",
                              "route": SUBSCRIPTION_ROUTES[name]}
            assignment[name] = eid
            continue
        if not base_url or not key_env:
            raise SystemExit(f"profile {name!r} has only one of base_url/api_key_env")
        triple = (provider, str(base_url), str(key_env))
        if triple not in by_triple:
            eid = provider
            if len(triples_per_provider[provider]) > 1:
                eid = f"{provider}-{len([t for t in by_triple if t[0] == provider]) + 1}"
            by_triple[triple] = eid
            endpoints[eid] = {"provider": provider, "base_url": str(base_url),
                              "api_key_env": str(key_env)}
        assignment[name] = by_triple[triple]
    return endpoints, assignment


def render_endpoints(endpoints: dict[str, dict], supervisor: dict[str, str] | None) -> str:
    lines = [ENDPOINTS_HEADER, "endpoints:"]
    for eid, entry in endpoints.items():
        lines.append(f"  {eid}:")
        for key in ("provider", "kind", "route", "base_url", "api_key_env"):
            if key in entry:
                lines.append(f"    {key}: {entry[key]}")
    if supervisor:
        lines += ["", "supervisor:",
                  f"  identity: {supervisor['identity']}",
                  f"  endpoint: {supervisor['endpoint']}"]
    return "\n".join(lines) + "\n"


_NAME = re.compile(r"^  - name:\s*(\S+)\s*$")
_FIELD = re.compile(r"^    (provider|base_url|api_key_env):")


def render_profiles(source_text: str, assignment: dict[str, str]) -> str:
    """The source text with endpoint lines swapped in, header replaced."""
    lines = source_text.splitlines()
    default_at = next(i for i, line in enumerate(lines) if line.startswith("default:"))
    start = default_at
    while start > 0 and lines[start - 1].startswith("#"):
        start -= 1
    out: list[str] = [PROFILES_HEADER.rstrip("\n"), ""]
    current: str | None = None
    for line in lines[start:]:
        m = _NAME.match(line)
        if m:
            current = m.group(1)
        f = _FIELD.match(line)
        if f and current is not None:
            if f.group(1) == "provider":
                out.append(f"    endpoint: {assignment[current]}")
            continue
        out.append(line)
    return "\n".join(out) + "\n"


CATALOG_NOTE = (
    "GENERATED - do not hand-edit; a pull request that changes this file by hand "
    "is a mistake. Upstream facts for one endpoint, joined to "
    "config/model_profiles.yaml by identity "
    "(docs/plans/MORTIMER_MODEL_REGISTRY_SPLIT_PLAN.md section 4a). Seeded from "
    "the pre-split registry by scripts/split_model_registry.py (fetched_at null, "
    "source seeded) so the sync job's first run reads as a diff."
)


def render_catalogs(source: Path) -> dict[str, str]:
    """Step 8: endpoint id -> seeded model_catalog.<endpoint>.json text."""
    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    profiles = [p for p in data.get("profiles") or [] if isinstance(p, dict)]
    endpoints, assignment = assign_endpoints(profiles)
    out: dict[str, str] = {}
    for eid, entry in endpoints.items():
        models = []
        for prof in sorted((p for p in profiles if assignment[str(p["name"])] == eid),
                           key=lambda p: str(p["identity"])):
            seeded = dict.fromkeys(ua.CATALOG_ENTRY_KEYS)
            seeded.update(identity=str(prof["identity"]), model=str(prof["model"]),
                          source="seeded")
            models.append(seeded)
        doc = {"_generated": CATALOG_NOTE, "schema": 1, "endpoint": eid,
               "provider": entry["provider"], "models": models}
        out[eid] = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    return out


def render(source: Path) -> tuple[str, str]:
    """-> (model_endpoints.yaml text, model_profiles.yaml text)."""
    text = source.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    profiles = [p for p in data.get("profiles") or [] if isinstance(p, dict)]
    endpoints, assignment = assign_endpoints(profiles)
    supervisor = None
    default = data.get("default")
    if default:
        planner = next(p for p in profiles if p["name"] == default)
        supervisor = {"identity": str(planner["identity"]),
                      "endpoint": assignment[str(default)]}
    return render_endpoints(endpoints, supervisor), render_profiles(text, assignment)


def verify(source: Path, endpoints_text: str, profiles_text: str) -> None:
    """D6: the join of what was rendered equals the source, or nothing is
    written."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ua.ENDPOINTS_FILENAME).write_text(endpoints_text, encoding="utf-8")
        pool = Path(tmp) / ua.PROFILES_FILENAME
        pool.write_text(profiles_text, encoding="utf-8")
        joined = ua.load_model_registry(pool)
    before = ua.load_model_registry(source)
    if joined != before or list(joined["profiles"]) != list(before["profiles"]):
        raise SystemExit("split is NOT lossless — refusing to write")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path,
                        default=REPO_ROOT / "config" / ua.LEGACY_REGISTRY_FILENAME)
    parser.add_argument("--config-dir", type=Path, default=REPO_ROOT / "config")
    parser.add_argument("--check", action="store_true", help="render and verify only")
    args = parser.parse_args(argv)
    endpoints_text, profiles_text = render(args.source)
    verify(args.source, endpoints_text, profiles_text)
    if args.check:
        print("split verified: lossless")
        return 0
    args.config_dir.mkdir(parents=True, exist_ok=True)
    (args.config_dir / ua.ENDPOINTS_FILENAME).write_text(endpoints_text, encoding="utf-8")
    (args.config_dir / ua.PROFILES_FILENAME).write_text(profiles_text, encoding="utf-8")
    print(f"wrote {ua.ENDPOINTS_FILENAME} and {ua.PROFILES_FILENAME} in {args.config_dir}")
    for eid, text in render_catalogs(args.source).items():
        path = ua.catalog_path(eid, config_dir=args.config_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"seeded {path.relative_to(args.config_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
