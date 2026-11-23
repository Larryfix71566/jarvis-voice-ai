"""What Mortimer pins today, for the daily new-model check (WS-41).

Reads tracked ``config/**/*.yaml|yml`` (never ``config/generated/``) as text,
the voice model pin and the verified CLI version sets. Never raises.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jarvis.model_sync import ids

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"

_NAME = re.compile(r"^(\s*)(?:-\s+)?name:\s*['\"]?([^'\"#\s]+)['\"]?\s*$")
_KEY = re.compile(r"^(\s*)(?:-\s+)?['\"]?([A-Za-z0-9_.\-]+)['\"]?:\s*(?:$|#)")
_TRAILING_COMMENT = re.compile(r"\s#.*$")


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def scan_config(config_dir: Path = CONFIG_DIR) -> list[dict[str, Any]]:
    """Every model ID in yaml under ``config_dir`` (minus ``generated/``).

    ``context`` is best effort: the nearest preceding ``name: X`` at a
    lower-or-equal indent, else the nearest preceding parent mapping key
    (``voice_supervisor:``) at a lower indent. Empty string when none.
    """
    config_dir = Path(config_dir)
    results: list[dict[str, Any]] = []
    try:
        files = sorted(p for p in config_dir.rglob("*") if p.suffix in (".yaml", ".yml") and p.is_file())
    except OSError:
        return results
    for path in files:
        try:
            rel_parts = path.relative_to(config_dir).parts
        except ValueError:
            continue
        if rel_parts and rel_parts[0] == "generated":
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        names: list[tuple[int, str]] = []   # (indent, name)
        keys: list[tuple[int, str]] = []    # (indent, key) of parent mappings
        for number, original in enumerate(lines, 1):
            if original.strip().startswith("#") or not original.strip():
                continue
            line = _TRAILING_COMMENT.sub("", original)
            indent = len(line) - len(line.lstrip(" "))
            m = _NAME.match(line)
            if m:
                ind = len(m.group(1)) + (2 if line.lstrip().startswith("- ") else 0)
                names = [n for n in names if n[0] < ind]
                names.append((ind, m.group(2)))
            else:
                gen = re.match(r"^(\s*)(?:-\s+)?[A-Za-z0-9_.\-'\"]+:", line)
                if gen:  # a mapping key closes names nested deeper than itself
                    names = [n for n in names if n[0] <= len(gen.group(1))]
                k = _KEY.match(line)
                if k:
                    ind = len(k.group(1))
                    keys = [x for x in keys if x[0] < ind]
                    keys.append((ind, k.group(2)))
            found = ids.find_ids(line)
            if not found:
                continue
            context = ""
            cand = [n for n in names if n[0] <= indent + 2]
            if cand:
                context = cand[-1][1]
            else:
                parents = [x for x in keys if x[0] < indent]
                if parents:
                    context = parents[-1][1]
            raws = {tok.lower(): tok for tok in re.findall(r"[A-Za-z0-9_./:-]+", line)}
            for mid in found:
                raw = next((t for low, t in raws.items() if low.rsplit("/", 1)[-1] == mid), mid)
                results.append({"model": mid, "file": _rel(path), "line": number,
                                "context": context, "raw": raw})
    return results


VOICE_SOURCE = "config/model_access.yaml:workloads.voice_supervisor"


def _load_yaml(path: Path) -> Any:
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def voice_pin(config_dir: Path = CONFIG_DIR) -> dict[str, str] | None:
    """The voice model: workloads.voice_supervisor.profile of
    model_access.yaml, resolved through the model registry loader (profile
    name -> its ``model``) or used directly when it already is a model ID.
    The voice Supervisor runs only on the Claude subscription (WS-40), so
    there is no OPENAI_MODEL fallback."""
    config_dir = Path(config_dir)
    access = _load_yaml(config_dir / "model_access.yaml")
    try:
        profile = str(access["workloads"]["voice_supervisor"]["profile"]).strip()
    except (TypeError, KeyError):
        profile = ""
    if profile:
        model = ""
        try:  # through the ONE registry loader (split plan §10), never the files
            from jarvis.agents.upgrade_agent import load_model_registry
            registry = load_model_registry(config_dir=config_dir)
            entry = (registry.get("profiles") or {}).get(profile)
            if isinstance(entry, dict):
                model = str(entry.get("model") or "").strip()
        except Exception:  # noqa: BLE001 — a broken registry is reported elsewhere
            model = ""
        parsed = ids.parse(model or profile)
        if parsed:
            return {"model": parsed.raw, "source": VOICE_SOURCE}
    return None


def cli_pins() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"claude": [], "codex": []}
    try:
        from jarvis.subscription_tools import CLAUDE_NATIVE_VERSIONS
        out["claude"] = sorted(CLAUDE_NATIVE_VERSIONS)
    except Exception:  # noqa: BLE001
        pass
    try:
        from jarvis.subscription import CODEX_VERIFIED_VERSIONS
        out["codex"] = sorted(CODEX_VERIFIED_VERSIONS)
    except Exception:  # noqa: BLE001
        pass
    return out


def collect_pins(config_dir: Path = CONFIG_DIR) -> dict[str, Any]:
    return {"models": scan_config(config_dir), "voice": voice_pin(config_dir), "cli": cli_pins()}
