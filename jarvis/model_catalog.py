"""The model catalog the Supervisor reads, rendered from the registry.

MORTIMER_EVAL_CONFIG_PARITY_PLAN.md follow-up, 2026-09-05. The spoken-name
mapping used to be prose in two places — rule 8 in jarvis/prompts.py and
the model_profile description in jarvis/agents/delegate.py — and both had
drifted from config/upgrade_models.yaml:

    rule 8              said `fable`        no such profile
    both locations      said `or-sonnet-5`  no such profile

An unresolvable profile makes the run REFUSE rather than quietly picking
another model, so "use Sonnet" failed outright and "use Fable" failed or
not depending on which instruction the model followed. The routing eval
never saw it: it scores delegate_start, and the refusal happens inside the
sub-agent afterwards.

The fix is structural rather than a correction. One renderer, one source,
and prose that points at the rendered block instead of restating it — so
the two cannot disagree again.

What is RENDERED (never duplicated): provider, tier, vision, label. Those
answer "Claude's frontier model" and "which one can see images" from the
registry itself, and stay right when a profile is added. What is
DECLARED in config/model_aliases.yaml: which member of a family a bare
spoken name means, because that is a choice rather than a lookup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "config" / "upgrade_models.yaml"
ALIASES_PATH = REPO_ROOT / "config" / "model_aliases.yaml"


def load_profiles(path: Path | None = None) -> list[dict[str, Any]]:
    """Profiles from the registry, in file order."""
    data = yaml.safe_load((path or REGISTRY_PATH).read_text(encoding="utf-8"))
    return list((data or {}).get("profiles") or [])


def load_aliases(path: Path | None = None) -> dict[str, str]:
    """Spoken name -> profile name."""
    data = yaml.safe_load((path or ALIASES_PATH).read_text(encoding="utf-8"))
    return dict((data or {}).get("aliases") or {})


def unknown_alias_targets(
    aliases: dict[str, str], profiles: list[dict[str, Any]]
) -> dict[str, str]:
    """Aliases whose target is not a real profile. Empty means consistent.

    This is the check that was missing: `fable` and `or-sonnet-5` sat in
    the prompt for as long as they did because nothing compared the names
    the model is told to use against the names that exist.
    """
    known = {str(p.get("name")) for p in profiles}
    return {a: t for a, t in aliases.items() if t not in known}


def render_model_catalog(
    profiles: list[dict[str, Any]] | None = None,
    aliases: dict[str, str] | None = None,
) -> str:
    """One line per profile, in registry order.

    Registry order rather than sorted: it keeps the rendered block
    traceable to the file a human edits, and a diff of one shows up as a
    diff of the other.

    A profile with no spoken name still appears. Omitting it would make the
    catalog a worse answer to "what can you use" than the registry itself,
    and it is exactly how a model ends up inventing options — case 30
    offered "Claude 3.5 Sonnet", which is in no registry here.
    """
    profiles = load_profiles() if profiles is None else profiles
    aliases = load_aliases() if aliases is None else aliases

    spoken: dict[str, list[str]] = {}
    for name, target in aliases.items():
        spoken.setdefault(target, []).append(name)

    lines: list[str] = []
    for profile in profiles:
        name = str(profile.get("name") or "")
        if not name:
            continue
        says = spoken.get(name) or []
        say = (' (say "' + '" or "'.join(says) + '")') if says else " (no spoken name)"
        traits = [str(profile.get("provider") or "unknown provider"),
                  "tier " + str(profile.get("tier") or "unknown")]
        if profile.get("vision"):
            traits.append("vision")
        lines.append(f"- {name}{say}: {', '.join(traits)}")
    return "\n".join(lines)
