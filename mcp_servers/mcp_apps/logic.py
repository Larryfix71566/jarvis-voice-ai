"""mcp-apps: application development & storage as pure logic.

Transport-free (invariant 9): no MCP imports here; server.py is the thin
wrapper. All network access lives in github.py and is INJECTED — every
public function takes a client object, so this module is unit-testable
fully offline.

Conventions (AGENTS.md on the mortimer-dev branch):
- Each new application gets its OWN private GitHub repository.
- Repo creation is two-phase: app_create with confirm=False returns a
  preview (proposed name + file list) and creates nothing; the human
  confirms, then app_create is called again with confirm=True.
- The app registry (apps/index.json) lives in the Mortimer repo on the
  mortimer-dev branch. Any registry write targeting main is refused.
- Agents never delete repositories; there is no delete tool at all.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

APP_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
REGISTRY_PATH = "apps/index.json"
DEFAULT_TEMPLATE = "web_app"


def _registry_repo() -> str:
    return os.environ.get("JARVIS_REGISTRY_REPO", "jarvis-voice-ai")


def _registry_branch() -> str:
    return os.environ.get("JARVIS_REGISTRY_BRANCH", "mortimer-dev")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------- validation


def validate_app_name(name: str) -> str:
    """Normalize and validate an app/repo name. Raises ValueError."""
    normalized = (name or "").strip().lower().replace("_", "-").replace(" ", "-")
    if not APP_NAME_RE.match(normalized):
        raise ValueError(
            f"invalid app name {name!r}: use 3-64 chars, lowercase letters, "
            "digits and hyphens, starting and ending with a letter or digit "
            f"(normalized form {normalized!r} also failed)"
        )
    return normalized


def validate_repo_path(path: str) -> str:
    """Validate a path inside an app repo. Raises ValueError."""
    p = (path or "").strip()
    if p.startswith("/"):
        raise ValueError(f"path {path!r} is absolute — repo-relative paths only")
    if not p:
        raise ValueError("path is empty")
    parts = p.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"path {path!r} contains empty, '.' or '..' segments")
    if parts[0] == ".git" or ".git" in parts:
        raise ValueError(f"path {path!r} touches .git — refused")
    if any(ch in p for ch in ("\\", "\x00")):
        raise ValueError(f"path {path!r} contains invalid characters")
    return p


# -------------------------------------------------------------- templates


def available_templates() -> list[str]:
    if not TEMPLATES_DIR.is_dir():
        return []
    return sorted(
        d.name for d in TEMPLATES_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


def _render(text: str, name: str, description: str, created_at: str) -> str:
    return (
        text.replace("__APP_NAME__", name)
            .replace("__DESCRIPTION__", description or f"{name} — built by Mortimer")
            .replace("__CREATED_AT__", created_at)
    )


def scaffold_files(name: str, template: str, description: str) -> dict[str, str]:
    """Render a template into {repo_path: content}. Raises ValueError."""
    name = validate_app_name(name)
    template_dir = TEMPLATES_DIR / template
    if not template_dir.is_dir():
        raise ValueError(
            f"unknown template {template!r}; available: "
            f"{', '.join(available_templates()) or 'none'}"
        )
    created_at = _now_iso()
    files: dict[str, str] = {}
    for src in sorted(template_dir.rglob("*")):
        if src.is_file():
            rel = src.relative_to(template_dir).as_posix()
            files[rel] = _render(
                src.read_text(encoding="utf-8"), name, description, created_at
            )
    if not files:
        raise ValueError(f"template {template!r} is empty")
    return files


# --------------------------------------------------------------- registry


def registry_add(registry: dict, entry: dict) -> dict:
    """Return a NEW registry dict with entry inserted or replaced by name."""
    apps = [a for a in registry.get("apps", []) if a.get("name") != entry["name"]]
    apps.append(entry)
    apps.sort(key=lambda a: a.get("created_at", ""))
    return {"apps": apps}


def _load_registry(client) -> tuple[dict, str | None]:
    """Fetch the registry from the Mortimer repo. Returns (registry, sha)."""
    doc = client.get_file(_registry_repo(), REGISTRY_PATH, _registry_branch())
    if doc is None:
        return {"apps": []}, None
    try:
        return json.loads(doc["content"]), doc["sha"]
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"registry at {REGISTRY_PATH} is not valid JSON: {exc}")


def _store_registry(client, registry: dict, sha: str | None, message: str) -> dict:
    branch = _registry_branch()
    if branch == "main":
        # Hard rule (AGENTS.md): agents never write main. Defense in depth —
        # app_register checks this before doing any work; this is the backstop.
        raise RuntimeError("registry writes to branch 'main' are refused")
    return client.put_file(
        _registry_repo(), REGISTRY_PATH,
        json.dumps(registry, indent=2) + "\n",
        message, branch, sha=sha,
    )


# ----------------------------------------------------------- orchestration


def _err(message: str) -> dict:
    return {"ok": False, "error": message}


def app_create(
    client,
    name: str,
    template: str = DEFAULT_TEMPLATE,
    description: str = "",
    confirm: bool = False,
) -> dict:
    """Two-phase app creation. confirm=False previews; confirm=True executes.

    Executes: create private repo -> scaffold template files -> register in
    apps/index.json on the registry branch. Never deletes, never overwrites
    an existing repo.
    """
    try:
        name = validate_app_name(name)
        files = scaffold_files(name, template, description)
    except ValueError as exc:
        return _err(str(exc))

    try:
        exists = client.repo_exists(name)
    except Exception as exc:  # noqa: BLE001 — surface as data, not a crash
        return _err(f"could not check whether repo exists: {exc}")
    if exists:
        return _err(
            f"repo '{name}' already exists — choose a different name. "
            "Agents never overwrite or delete repositories."
        )

    if not confirm:
        listing = "\n".join(f"  - {p}" for p in files)
        return {
            "ok": True,
            "pending": True,
            "summary": (
                f"Ready to create private repo '{name}' from template "
                f"'{template}' with {len(files)} file(s):\n{listing}\n"
                "Confirm and I will create it."
            ),
            "proposed_name": name,
            "template": template,
            "files": sorted(files),
        }

    commits: list[str] = []
    try:
        repo = client.create_repo(name, description, private=True)
        repo_url = repo.get("html_url", "")
        for path, content in files.items():
            res = client.put_file(
                name, path, content, f"chore: scaffold {path}", "main"
            )
            sha = (res.get("commit") or {}).get("sha", "")
            if sha:
                commits.append(sha)
        reg = app_register(client, name, repo_url, description)
        if not reg.get("ok"):
            return _err(
                f"repo created at {repo_url} but registry update failed: "
                f"{reg.get('error')}"
            )
    except Exception as exc:  # noqa: BLE001
        return _err(f"creation failed partway: {exc}")

    return {
        "ok": True,
        "pending": False,
        "name": name,
        "repo_url": repo_url,
        "files": sorted(files),
        "commits": commits,
        "summary": (
            f"Created private repo {repo_url} with {len(files)} file(s) "
            f"({len(commits)} commit(s)) and registered it. To start over, "
            "delete the repo on GitHub (human-only action)."
        ),
    }


def app_write_file(client, app: str, path: str, content: str, rationale: str = "") -> dict:
    """Create or update one file in an app's own repo (default branch)."""
    try:
        app = validate_app_name(app)
        path = validate_repo_path(path)
    except ValueError as exc:
        return _err(str(exc))
    try:
        existing = client.get_file(app, path, "main")
    except Exception as exc:  # noqa: BLE001
        return _err(f"could not read {path} in {app}: {exc}")
    verb = "update" if existing else "add"
    message = f"feat: {verb} {path}" + (f" — {rationale}" if rationale else "")
    try:
        res = client.put_file(
            app, path, content, message, "main",
            sha=existing["sha"] if existing else None,
        )
    except Exception as exc:  # noqa: BLE001
        return _err(f"write failed: {exc}")
    sha = (res.get("commit") or {}).get("sha", "")
    return {
        "ok": True,
        "app": app,
        "path": path,
        "action": verb,
        "commit": sha,
        "summary": f"{verb.capitalize()}d {path} in {app} (commit {sha[:7]}).",
    }


def app_register(client, app: str, repo_url: str, description: str = "") -> dict:
    """Insert or update an app entry in apps/index.json (idempotent)."""
    try:
        app = validate_app_name(app)
    except ValueError as exc:
        return _err(str(exc))
    if _registry_branch() == "main":
        return _err("registry writes to branch 'main' are refused")
    try:
        registry, sha = _load_registry(client)
        entry = {
            "name": app,
            "repo": repo_url,
            "created_at": _now_iso(),
            "description": description,
        }
        updated = registry_add(registry, entry)
        res = _store_registry(
            client, updated, sha, f"chore: register app {app}"
        )
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))
    return {
        "ok": True,
        "app": app,
        "registry_size": len(updated["apps"]),
        "commit": (res.get("commit") or {}).get("sha", ""),
    }


def app_list(client) -> dict:
    """Read-only: the app registry."""
    try:
        registry, _sha = _load_registry(client)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))
    return {"ok": True, "apps": registry.get("apps", [])}


def app_read(client, app: str, path: str) -> dict:
    """Read-only: one file from an app's repo."""
    try:
        app = validate_app_name(app)
        path = validate_repo_path(path)
    except ValueError as exc:
        return _err(str(exc))
    try:
        doc = client.get_file(app, path, "main")
    except Exception as exc:  # noqa: BLE001
        return _err(f"could not read {path} in {app}: {exc}")
    if doc is None:
        return _err(f"{path} not found in {app}")
    return {"ok": True, "app": app, "path": path, "content": doc["content"]}
